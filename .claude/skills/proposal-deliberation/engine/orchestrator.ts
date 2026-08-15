import { readFile, readdir, stat } from 'node:fs/promises'; import { join } from 'node:path'; import { loadDocumentState } from './document-state.js'; import { extractManagedRevisionFilename,extractRevisionReference,extractWithdrawalOperationId,resolveIntent } from './intent-resolver.js'; import { materializeCompositeTarget,resolveSuccessorTarget,resolveTargets,resolveSourceAndDestination } from './target-resolver.js'; import { ambiguityGate } from './ambiguity-gate.js'; import { buildContext,buildMoveCopyContext,buildSuccessorCompositeContext } from './context-builder.js'; import { buildEditPlan,buildMoveCopyPlan } from './edit-planner.js'; import { buildConceptualPlan } from './conceptual-planner.js'; import { compilePatches,compileSuccessorCompositeReplacement } from './patch-compiler.js'; import { validateCandidate } from './candidate-validator.js'; import { rebuildDerivedState } from './derived-state-builder.js'; import { createRevisionReceipt } from './revision-receipt.js'; import { commitDerivedState,markDerivedState,saveRevisionReceipt } from './derived-state-store.js'; import { withMutationLock,mutationLockKey,recordSuccessfulPublication,recordStaleMutationBlock } from './mutation-lock.js'; import { sha256,type CreateSuccessorOperation,type EditAction,type Position,type PublicV2Operation,type RevisionLifecycleOperation,SemanticEditPlanner,type SuccessorEditIntent,TargetCandidate,UserRequest } from './types.js'; import { ProposalWorkspaceAdapter } from './proposal-workspace-adapter.js'; import { resolveEffectiveOperationProfile,reviewerRequired } from './operation-spec.js'; import { type TutorAdapter,validateTutorAssessment } from './tutor-adapter.js'; import { type ReviewerAdapter,validateReviewerAssessment } from './reviewer-adapter.js'; import { writeTask,recordMutation,modelCall,recordRebuildAttempt,recordRebuildFailure } from './runtime-metrics.js'; import { RevisionLifecycleTransaction } from './revision-lifecycle-transaction.js'; import { createSuccessorAcceptanceRegistry,type SuccessorAcceptanceRegistry } from './successor-acceptance-registry.js'; import { resolveLatestManagedRevision } from './revision-lifecycle-store.js'; import { createAmbientSuppliedPlanner,resolveAmbientCompositeDecisions,type AmbientCompositeGroup } from './ambient-supplied-planner.js'; import { compileSuccessorCompositeChangeset } from './patch-compiler.js'; import { evaluateSuccessorGrowthThresholdFromTargets,type GrowthThresholdVerdict } from './growth-threshold.js';
const MANAGED_ARTIFACT_MARKER=Buffer.from('<!-- proposal-workspace:artifact:v1 -->\n');
const MANAGED_REVISION_FILENAME=/^research-concept-(?:[a-z0-9]+(?:-[a-z0-9]+)*-)?r\d{2,}\.md$/;
export type V2Request=UserRequest&{operation?:PublicV2Operation;editIntent?:SuccessorEditIntent;sourceFilename?:string;sourceQuery?:string;destinationQuery?:string;position?:Position;adaptive?:boolean;literalContent?:string;expectedSourceSha256?:string;withdrawalOperationId?:string;withdrawalReason?:string;priorConclusion?:string;sessionIdentity?:string;successorAcceptanceToken?:string;acceptSuccessor?:boolean;/** CREATE_SUCCESSOR accept only: the `mathDelta.lost[].id` values the preview reported, echoed back to authorise removing them. Any lost mathematical atom left out of this list blocks the publish with MATH_REMOVALS_NOT_ACKNOWLEDGED. */acknowledgedMathRemovals?:readonly string[];/** CREATE_SUCCESSOR only: one independent locus query per approved section (design amendment: multi-section successor); when present, overrides `selectedEntryId`/instruction-derived single-locus resolution entirely. */selectedEntryIds?:readonly string[];/** CREATE_SUCCESSOR + MODIFY only (design `sdd/proposal-deliberation-ambient-model`): one already-resolved `EditAction` per approved locus, supplied by the caller (the ambient model) instead of a separate model call. When present, the orchestrator routes through `ambient-supplied-planner.ts` (echo + the migrated planner OUTPUT validation) instead of `semanticPlanner`/`request.model` -- no model/network call happens on this path. */resolvedDecisions?:readonly EditAction[]}; export type DerivedStore={commitDerivedState:typeof commitDerivedState;markDerivedState:typeof markDerivedState;saveRevisionReceipt:typeof saveRevisionReceipt}; export type V2Roles={tutor?:TutorAdapter;reviewer?:ReviewerAdapter};
const CREATE_SUCCESSOR:CreateSuccessorOperation='CREATE_SUCCESSOR';
function lifecycleFailure(operation:RevisionLifecycleOperation,warning:string,status:'blocked'|'ambiguous'='blocked',question?:string){return {status,operation,withdrawnFilename:null,restoredLatestFilename:null,artifactCount:0,backupLocation:null,auditStatus:'NOT_RUN',selfAuditStatus:'NOT_RUN',warnings:[warning],...(question?{question}:{})}}
function lifecycleClarification(result:any){if(result?.status==='blocked'&&result?.warnings?.includes('WITHDRAWAL_LOOKUP_AMBIGUOUS'))return {...result,status:'ambiguous',question:'Specify the exact withdrawalOperationId because this filename has multiple withdrawn records.'};return result}
function expandHeadingSubtree(state:any,entryId:string){const e=state.structuralIndex.byId[entryId];if(!e||!['section','subsection','heading'].includes(e.type))return;const source=state.documentBytes.toString();const heads=[...source.matchAll(/^(#{1,6})\s+.+$/gm)].map(h=>({level:h[1].length,start:Buffer.byteLength(source.slice(0,h.index))})),i=heads.findIndex(h=>h.start===e.startByte),next=heads.slice(i+1).find(h=>h.level<=heads[i].level),end=next?.start??state.documentBytes.length;if(end!==e.endByte){const x={...e,endByte:end,textSha256:sha256(state.documentBytes.subarray(e.startByte,end))};state.structuralIndex.byId[entryId]=x;state.structuralIndex.entries=state.structuralIndex.entries.map((q:any)=>q.entryId===entryId?x:q)}}
function executionFailure(error:unknown){const value=error as any;if(value?.code==='MODIFY_INPUT_BUDGET_EXCEEDED')return {status:'budget_block',category:'budget_block',reason:value.code,budget:value.evidence,modelCalls:0,plannerCalls:0,mutations:0};return {status:'blocked',reason:error instanceof Error?error.message:String(error),modelCalls:0,plannerCalls:0,mutations:0}}
/** True when two or more resolved successor targets name the same composite entry. */
function duplicateSuccessorTargets(targets:TargetCandidate[]){return new Set(targets.map(t=>t.entryId)).size!==targets.length}
/** True when any two resolved successor targets' byte spans overlap (disjoint-splice is only valid across non-overlapping spans). */
function overlappingSuccessorTargets(targets:TargetCandidate[]){const spans=targets.map(t=>({startByte:t.composite!.startByte,endByte:t.composite!.endByte})).sort((a,b)=>a.startByte-b.startByte);for(let i=1;i<spans.length;i++)if(spans[i].startByte<spans[i-1].endByte)return true;return false}
/**
 * Combines the ordered per-target instruction hashes (re-audit cleanup): a
 * multi-section successor's receipt provenance (`RevisionReceipt.instructionHash`)
 * must reflect EVERY resolved target, not only whichever target's `buildEditPlan`
 * call happened to run last in `executeMultiSectionSuccessor`'s loop. Each entry
 * pairs a target's own `entryId` with its own `EditPlan.instructionHash` (both
 * already computed per-target by `buildEditPlan`), so the combined hash changes
 * whenever the resolved target SET, ORDER, or any individual target's plan changes
 * -- not only when the shared request-level instruction text changes.
 */
export function combineSuccessorInstructionHashes(perTarget:readonly {entryId:string;instructionHash:string}[]):string{return sha256(perTarget.map(t=>`${t.entryId}:${t.instructionHash}`).join('|'));}
/**
 * True when at least one supplied `resolvedDecisions` entry is NOT a
 * well-formed `kind:'replace'` decision (design `sdd/proposal-deliberation-ambient-model`,
 * SLICE 1b): routes the batch through `executeAmbientCompositeSuccessor`'s
 * byte-preserving composite path INSTEAD of the SLICE-1 `buildEditPlan` path,
 * which hard-requires exactly one `replace` action. A malformed `kind:'replace'`
 * object (e.g. missing `replacementText`) still reports `kind==='replace'` here
 * and is left to the EXISTING SLICE-1 path's own validation (untouched,
 * `createAmbientSuppliedPlanner` already rejects it identically).
 */
function ambientBatchNeedsComposite(decisions:readonly unknown[]):boolean{return decisions.some(d=>!(d&&typeof d==='object'&&!Array.isArray(d))||(d as any).kind!=='replace');}
/** Builds the minimal `EditPlan` shape `publish()`/`compileSuccessorCompositeChangeset`'s frozenCompiled callers need for one homogeneous ambient composite group (design `sdd/proposal-deliberation-ambient-model`, SLICE 1b). `resolvedTargets`/`actions` counts intentionally do NOT need to match 1:1 (a `move` decision claims two targets but contributes one action) -- unlike `compileSuccessorCompositeReplacement`'s replace-only invariant, this plan is only ever consumed via a precompiled `frozenCompiled` passed into `publish()`, never recompiled from `plan.actions` downstream. */
function buildAmbientCompositeGroupPlan(documentSha256:string,group:AmbientCompositeGroup,intent:'MODIFY'|'MOVE',instructionSeed:string):any{return {planVersion:'2',documentSha256,intent,instructionHash:sha256(JSON.stringify({instructionSeed,actions:group.actions})),resolvedTargets:[...group.targetIds],semanticChange:false,destructiveIntent:false,cleanupLevel:'NONE',constraints:[],actions:[...group.actions],expectedEffects:[],unresolvedQuestions:[],successorCompositeTarget:true};}
/** Remaps one relocation decision's own declared entryId field(s) from the ORIGINAL (pre-in-place-publish) resolved entryId to the FRESHLY re-resolved entryId at the SAME locus after the in-place half publishes (design `sdd/proposal-deliberation-ambient-model`, SLICE 1b) -- byte-offset-derived composite entryIds are never stable across a publish, only the fuzzy locus query is. */
function remapAmbientDecisionEntryIds(decision:EditAction,map:ReadonlyMap<string,string>):EditAction{
 if(decision.kind==='replace'||decision.kind==='delete')return {...decision,targetEntryId:map.get(decision.targetEntryId)??decision.targetEntryId};
 if(decision.kind==='insert')return {...decision,anchorEntryId:map.get(decision.anchorEntryId)??decision.anchorEntryId};
 if(decision.kind==='move'||decision.kind==='copy')return {...decision,sourceEntryIds:[map.get(decision.sourceEntryIds[0]!)??decision.sourceEntryIds[0]!],destinationAnchorId:map.get(decision.destinationAnchorId)??decision.destinationAnchorId};
 return decision;
}

export class ProposalDeliberationOrchestrator {
 constructor(private readonly root:string,private readonly adapter:ProposalWorkspaceAdapter,private readonly store:DerivedStore={commitDerivedState,markDerivedState,saveRevisionReceipt},private readonly semanticPlanner?:SemanticEditPlanner,private readonly roles:V2Roles={},private readonly stateLoader:typeof loadDocumentState=loadDocumentState,private readonly lifecycle:Pick<RevisionLifecycleTransaction,'withdraw'|'restore'>=new RevisionLifecycleTransaction(root),private readonly successorAcceptance:SuccessorAcceptanceRegistry=createSuccessorAcceptanceRegistry()){if(!adapter)throw new Error('PROPOSAL_WORKSPACE_ADAPTER_REQUIRED')}
 /** Unified resolver (design decision I3/I4): delegates to `resolveLatestManagedRevision`, sharing its exact tie-break with every other call site. Preserves this method's historical contract -- `undefined` on both "no managed proposal" and "tied/ambiguous latest" -- for existing callers; `execute()` uses `resolveExecutionBase` below when it needs to distinguish those two cases explicitly. */
 async latest(markerOwned=false){const resolution=await resolveLatestManagedRevision(this.root,{markerOwned});return resolution.status==='active'?resolution.latest.filename:undefined}
 /** Distinguishes NO_MANAGED_PROPOSAL from MULTIPLE_ACTIVE_REVISIONS (I4) for `execute()`'s own blocked-reason reporting, instead of collapsing both into a bare `undefined`. */
 private async resolveExecutionBase(markerOwned:boolean):Promise<{filename?:string;multipleCandidates?:string[]}> {
  const resolution=await resolveLatestManagedRevision(this.root,{markerOwned});
  if(resolution.status==='multiple')return {multipleCandidates:resolution.candidates.map(c=>c.filename)};
  if(resolution.status==='active')return {filename:resolution.latest.filename};
  return {};
 }
 async execute(request:V2Request):Promise<any>{
  const classifiedIntent=resolveIntent(request.instruction);
  const successorRequest=request.operation===CREATE_SUCCESSOR;
  const successorEditIntent:SuccessorEditIntent=request.editIntent==='CONCEPTUAL_REVISION'?'CONCEPTUAL_REVISION':'MODIFY';
  const resolvedIntent=successorRequest?{...classifiedIntent,intent:successorEditIntent,semanticChange:true,pendingQuestions:[],unresolvedQuestions:[],destructiveIntent:false}:request.operation?{...classifiedIntent,intent:request.operation,pendingQuestions:[],unresolvedQuestions:[],destructiveIntent:true}:classifiedIntent;
  const priorConclusion=typeof request.priorConclusion==='string'&&request.priorConclusion.trim()?request.priorConclusion.trim():undefined;
  const intent=priorConclusion?{...resolvedIntent,evidence:[`${request.instruction}\n\nPrior chat conclusion (advisory; apply only to the explicit edit): ${priorConclusion}`]}:resolvedIntent;
  if(intent.intent==='WITHDRAW_REVISION'||intent.intent==='RESTORE_WITHDRAWN_REVISION'){
   if(request.sourceFilename!==undefined&&!MANAGED_REVISION_FILENAME.test(request.sourceFilename))return lifecycleFailure(intent.intent,'INVALID_MANAGED_SOURCE_FILENAME');
   const operationId=request.withdrawalOperationId??extractWithdrawalOperationId(request.instruction);
   let lifecycleFilename=request.sourceFilename??extractManagedRevisionFilename(request.instruction);
   if(!lifecycleFilename&&intent.intent==='WITHDRAW_REVISION'){
    const revision=extractRevisionReference(request.instruction);
    if(revision){
     const names=(await readdir(join(this.root,'proposals'))).filter(name=>MANAGED_REVISION_FILENAME.test(name)&&name.endsWith(`-${revision}.md`));
     if(names.length===1)lifecycleFilename=names[0];
     else if(names.length>1)return lifecycleFailure(intent.intent,'AMBIGUOUS_REVISION_REFERENCE','ambiguous','Specify the exact managed revision filename.');
     else return lifecycleFailure(intent.intent,'MANAGED_REVISION_NOT_FOUND');
    }
   }
   if(intent.intent==='WITHDRAW_REVISION'){
    if(!lifecycleFilename)return lifecycleFailure(intent.intent,'WITHDRAWAL_FILENAME_REQUIRED');
    return this.lifecycle.withdraw({filename:lifecycleFilename,reason:request.withdrawalReason});
   }
   if(!operationId&&!lifecycleFilename)return lifecycleFailure(intent.intent,'RESTORE_IDENTITY_REQUIRED');
   return lifecycleClarification(await this.lifecycle.restore({operationId,filename:lifecycleFilename}));
  }
  let filename:string|undefined;if(request.sourceFilename!==undefined){if(!/^research-concept-(?:[a-z0-9]+(?:-[a-z0-9]+)*-)?r\d{2,}\.md$/.test(request.sourceFilename))return {status:'blocked',reason:'INVALID_MANAGED_SOURCE_FILENAME',modelCalls:0,plannerCalls:0,mutations:0};try{const sourcePath=join(this.root,'proposals',request.sourceFilename);if(!(await stat(sourcePath)).isFile())return {status:'blocked',reason:'MANAGED_SOURCE_NOT_FOUND',modelCalls:0,plannerCalls:0,mutations:0};if(!(await readFile(sourcePath)).subarray(0,MANAGED_ARTIFACT_MARKER.length).equals(MANAGED_ARTIFACT_MARKER))return {status:'blocked',reason:'UNMANAGED_SOURCE',modelCalls:0,plannerCalls:0,mutations:0};filename=request.sourceFilename}catch{return {status:'blocked',reason:'MANAGED_SOURCE_NOT_FOUND',modelCalls:0,plannerCalls:0,mutations:0}}}else {const base=await this.resolveExecutionBase(successorRequest);if(base.multipleCandidates)return {status:'blocked',reason:'MULTIPLE_ACTIVE_REVISIONS',candidates:base.multipleCandidates,modelCalls:0,plannerCalls:0,mutations:0};filename=base.filename;}if(!filename)return {status:'blocked',reason:'NO_MANAGED_PROPOSAL',modelCalls:0,plannerCalls:0,mutations:0};let state;try{recordRebuildAttempt();state=await this.stateLoader(this.root,filename)}catch(e){recordRebuildFailure();return {status:'blocked',reason:'DERIVED_STATE_REBUILD_FAILED',modelCalls:0,plannerCalls:0,mutations:0}}if(request.expectedSourceSha256&&request.expectedSourceSha256!==state.documentSha256){recordStaleMutationBlock();return {status:'blocked',reason:'STALE_SOURCE_SHA',modelCalls:0,plannerCalls:0,mutations:0};}if(intent.intent==='AMBIGUOUS')return {status:'ambiguous',question:intent.pendingQuestions[0],modelCalls:0,plannerCalls:0,mutations:0};
  if(successorRequest&&Array.isArray(request.selectedEntryIds))return this.executeMultiSectionSuccessor(state,filename,intent,request);
  const successorResolution=successorRequest?resolveSuccessorTarget(state,request.selectedEntryId??intent.targetDescription):undefined;
  if(successorRequest&&!successorResolution?.candidates.length)return {status:'blocked',reason:successorResolution?.reason??'SUCCESSOR_TARGET_NOT_FOUND',modelCalls:0,plannerCalls:0,mutations:0};
  const ambientDecisions=successorRequest&&successorEditIntent==='MODIFY'&&Array.isArray(request.resolvedDecisions)?request.resolvedDecisions:undefined;
  const planner=ambientDecisions?createAmbientSuppliedPlanner(ambientDecisions):this.semanticPlanner??(request.model?.plan?request.model as SemanticEditPlanner:undefined);
  let target:TargetCandidate|undefined; const targetGate=()=>successorRequest?ambiguityGate(successorResolution!.candidates):ambiguityGate(resolveTargets(state,request.selectedEntryId??intent.targetDescription,{allowInterEntryWhitespaceFallback:intent.intent==='MODIFY'&&Boolean(intent.fidelity.targetBlock)}));
  if(intent.intent==='DELIBERATE'||intent.intent==='REVIEW'){const gate=targetGate();if(gate.blocked)return {status:'ambiguous',question:gate.question,modelCalls:0,plannerCalls:0,mutations:0};target=gate.candidate!;const context=buildContext(state,[target.entryId],request.instruction);let calls=0;try{if(intent.intent==='REVIEW'){if(!this.roles.reviewer)return {status:'blocked',reason:'REVIEWER_REQUIRED',modelCalls:0,mutations:0};const assessment=validateReviewerAssessment(await modelCall('reviewer',()=>{calls++;return this.roles.reviewer!.review({instruction:request.instruction,context})}));return {status:'deliberated',assessment,alternatives:[],risks:[assessment.riskLevel],unresolvedQuestions:assessment.unresolvedQuestions,modelCalls:calls,plannerCalls:0,mutations:0,context};}if(!this.roles.tutor)return {status:'blocked',reason:'TUTOR_REQUIRED',modelCalls:0,mutations:0};const assessment=validateTutorAssessment(await modelCall('tutor',()=>{calls++;return this.roles.tutor!.assess({instruction:request.instruction,context})}),context.fragments.map(f=>f.entryId));return {status:'deliberated',assessment,alternatives:assessment.proposedAlternative?[assessment.proposedAlternative]:[],risks:[assessment.riskLevel],unresolvedQuestions:assessment.unresolvedQuestions,modelCalls:calls,plannerCalls:0,mutations:0,context};}catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),modelCalls:calls,plannerCalls:0,mutations:0};}}
  if(intent.intent==='MOVE'||intent.intent==='COPY'){const sourceQuery=request.sourceQuery??intent.sourceDescription,destinationQuery=request.destinationQuery??intent.destinationDescription;if(!sourceQuery||!destinationQuery)return {status:'ambiguous',question:!sourceQuery?'Indicá la fuente.':'Indicá el destino.',modelCalls:0,plannerCalls:0,mutations:0};const pair=resolveSourceAndDestination(state,sourceQuery,destinationQuery),sg=ambiguityGate(pair.sourceCandidates),dg=ambiguityGate(pair.destinationCandidates);if(sg.blocked||dg.blocked)return {status:'ambiguous',question:sg.blocked?sg.question:dg.question,modelCalls:0,plannerCalls:0,mutations:0};const source=sg.candidate!,destination=dg.candidate!;if(source.entryId===destination.entryId)return {status:'blocked',reason:'SOURCE_EQUALS_DESTINATION',modelCalls:0,plannerCalls:0,mutations:0};expandHeadingSubtree(state,source.entryId);const se=state.structuralIndex.byId[source.entryId],de=state.structuralIndex.byId[destination.entryId];if(['section','subsection','heading'].includes(se.type)&&de.startByte>se.startByte&&de.startByte<se.endByte)return {status:'blocked',reason:'HIERARCHY_CYCLE_DESTINATION_DESCENDANT',modelCalls:0,plannerCalls:0,mutations:0};const position=request.position??intent.requestedPosition??(['section','subsection','heading'].includes(de.type)?'inside_end':'after'),context=buildMoveCopyContext(state,source.entryId,destination.entryId,request.instruction);try{return this.publish(state,filename,intent.intent,await buildMoveCopyPlan({...intent,moveMode:request.adaptive?'ADAPTIVE':intent.moveMode},state.documentSha256,source,destination,position,context.sourceContext,context.destinationContext,planner),context)}catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),modelCalls:0,plannerCalls:0,mutations:0};}}
  const gate=targetGate();if(gate.blocked)return {status:'ambiguous',question:gate.question,candidates:gate.candidates,modelCalls:0,plannerCalls:0,mutations:0};target=gate.candidate!;materializeCompositeTarget(state,target);let context;try{context=successorRequest?{...buildSuccessorCompositeContext(state,target.entryId,request.instruction),successorRangeEntryIds:target.composite?.entryIds}:buildContext(state,[target.entryId],request.instruction,intent.fidelity)}catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),modelCalls:0,plannerCalls:0,mutations:0}}
  if(successorRequest&&ambientDecisions&&ambientBatchNeedsComposite(ambientDecisions))return this.executeAmbientCompositeSuccessor(state,filename,[target],[request.selectedEntryId??intent.targetDescription],context,request,ambientDecisions);
  if(successorRequest&&request.acceptSuccessor===true)return this.acceptFrozenSuccessor(state,filename,[target],context,request);if(successorRequest&&request.successorAcceptanceToken!==undefined)return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_CURRENT_TURN_REQUIRED',modelCalls:0,plannerCalls:0,mutations:0};
  if(intent.intent==='CONCEPTUAL_REVISION'){if(!planner)return {status:'blocked',reason:'CONCEPTUAL_PLANNER_REQUIRED',modelCalls:0,mutations:0};let calls=0,plannerCalls=0;const mathematical=/matem|ecuaci|regularización|semi-supervisado|teórico/i.test(request.instruction);try{let tutor:any;if(mathematical){if(!this.roles.tutor)return {status:'blocked',reason:'TUTOR_REQUIRED',modelCalls:0,mutations:0};tutor=validateTutorAssessment(await modelCall('tutor',()=>{calls++;return this.roles.tutor!.assess({instruction:request.instruction,context})}),context.fragments.map(f=>f.entryId));if(['NEEDS_CLARIFICATION','REJECT_WITH_REASON'].includes(tutor.decision))return {status:'needs-clarification',assessment:tutor,question:tutor.unresolvedQuestions[0]??tutor.summary,modelCalls:calls,plannerCalls,mutations:0};}const review=reviewerRequired(intent.intent,request.instruction,tutor?.riskLevel);if(review&&mathematical)return {status:'blocked',reason:'REVIEW_EXCEEDS_MODEL_BUDGET',modelCalls:calls,plannerCalls,mutations:0};const planned=await modelCall('planner',()=>{calls++;plannerCalls++;return buildConceptualPlan(intent,state.documentSha256,target,context,planner)});if(review){if(!this.roles.reviewer)return {status:'blocked',reason:'REVIEWER_REQUIRED',modelCalls:calls,plannerCalls,mutations:0};const assessment=validateReviewerAssessment(await modelCall('reviewer',()=>{calls++;return this.roles.reviewer!.review({instruction:request.instruction,context,plan:planned.plan})}));if(assessment.decision==='BLOCK'||assessment.decision==='NEEDS_CLARIFICATION')return {status:'blocked',reason:'REVIEWER_BLOCK',assessment,modelCalls:calls,plannerCalls,mutations:0};}return this.publish(state,filename,intent.intent,{plan:planned.plan,modelCalls:calls,plannerCalls},context,successorRequest?CREATE_SUCCESSOR:intent.intent,request);}catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),modelCalls:calls,plannerCalls,mutations:0};}}
  try{const planned=await buildEditPlan(intent,state.documentSha256,target,context,planner,state);if(successorRequest){const attempted=(planned.plan.actions[0] as any)?.targetEntryId;if(planned.plan.actions.length!==1||planned.plan.actions[0]?.kind!=='replace'||attempted!==target.entryId)return {status:'blocked',reason:context.successorRangeEntryIds?.includes(attempted)?'SUCCESSOR_CHILD_TARGET_FORBIDDEN':'SUCCESSOR_OUTSIDE_TARGET_FORBIDDEN',modelCalls:planned.modelCalls,plannerCalls:planned.plannerCalls??0,mutations:0};planned.plan={...planned.plan,successorCompositeTarget:true,resolvedTargets:[target.entryId]};}if(intent.intent==='INSERT'&&request.literalContent&&!planned.plan.actions.length)planned.plan.actions=[{kind:'insert',anchorEntryId:target.entryId,position:request.position==='before'?'before':'after',content:request.literalContent}];const growthAdvisory=ambientDecisions&&successorRequest?evaluateSuccessorGrowthThresholdFromTargets([target],state.documentBytes.length):undefined;return this.publish(state,filename,intent.intent,planned,context,successorRequest?CREATE_SUCCESSOR:intent.intent,request,undefined,growthAdvisory)}catch(e){return executionFailure(e)}}
 private successorFilename(sourceFilename:string){const match=/-r(\d+)\.md$/.exec(sourceFilename);if(!match)throw new Error('INVALID_MANAGED_SOURCE_FILENAME');return sourceFilename.slice(0,match.index)+`-r${String(Number(match[1])+1).padStart(match[1].length,'0')}.md`;}
 /**
  * Resolves the interactive CREATE_SUCCESSOR pipeline for MULTIPLE independent,
  * disjoint locus queries (`request.selectedEntryIds`) in one turn (design
  * amendment: multi-section successor). Each query is resolved and planned
  * exactly as the single-target path resolves and plans its one query; the
  * resulting per-target replace actions are then combined into ONE EditPlan
  * so `compileSuccessorCompositeReplacement` splices every approved section
  * into the SAME successor via the disjoint-splice composite engine. The
  * `acceptSuccessor`/`successorAcceptanceToken` current-turn consent gate is
  * preserved unchanged (via the now target-array-generic `acceptFrozenSuccessor`).
  */
 private async executeMultiSectionSuccessor(state:any,filename:string,intent:any,request:V2Request):Promise<any>{
  const queries=request.selectedEntryIds!;
  if(!queries.length)return {status:'blocked',reason:'SUCCESSOR_TARGET_NOT_FOUND',modelCalls:0,plannerCalls:0,mutations:0};
  if(request.successorAcceptanceToken!==undefined&&request.acceptSuccessor!==true)return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_CURRENT_TURN_REQUIRED',modelCalls:0,plannerCalls:0,mutations:0};
  const targets:TargetCandidate[]=[];
  for(const query of queries){
   const resolution=resolveSuccessorTarget(state,query);
   if(!resolution.candidates.length)return {status:'blocked',reason:resolution.reason??'SUCCESSOR_TARGET_NOT_FOUND',modelCalls:0,plannerCalls:0,mutations:0};
   const gate=ambiguityGate(resolution.candidates);
   if(gate.blocked)return {status:'ambiguous',question:gate.question,candidates:gate.candidates,modelCalls:0,plannerCalls:0,mutations:0};
   targets.push(gate.candidate!);
  }
  if(duplicateSuccessorTargets(targets))return {status:'blocked',reason:'SUCCESSOR_DUPLICATE_TARGET',modelCalls:0,plannerCalls:0,mutations:0};
  if(overlappingSuccessorTargets(targets))return {status:'blocked',reason:'SUCCESSOR_TARGET_OVERLAP',modelCalls:0,plannerCalls:0,mutations:0};
  for(const target of targets)materializeCompositeTarget(state,target);
  let perTargetContexts:any[];
  try{perTargetContexts=targets.map(target=>({...buildSuccessorCompositeContext(state,target.entryId,request.instruction),successorRangeEntryIds:target.composite?.entryIds}))}catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),modelCalls:0,plannerCalls:0,mutations:0}}
  const mergedContext={...perTargetContexts[0],fragments:perTargetContexts.flatMap(c=>c.fragments),authorizedEntryIds:perTargetContexts.flatMap(c=>c.authorizedEntryIds??[]),successorRangeEntryIds:perTargetContexts.flatMap(c=>c.successorRangeEntryIds??[])};
  const ambientDecisions=Array.isArray(request.resolvedDecisions)?request.resolvedDecisions:undefined;
  if(ambientDecisions&&ambientBatchNeedsComposite(ambientDecisions))return this.executeAmbientCompositeSuccessor(state,filename,targets,queries,mergedContext,request,ambientDecisions);
  if(request.acceptSuccessor===true)return this.acceptFrozenSuccessor(state,filename,targets,mergedContext,request);
  if(intent.intent==='CONCEPTUAL_REVISION')return {status:'blocked',reason:'SUCCESSOR_MULTI_TARGET_CONCEPTUAL_REVISION_UNSUPPORTED',modelCalls:0,plannerCalls:0,mutations:0};
  const planner=ambientDecisions?createAmbientSuppliedPlanner(ambientDecisions):this.semanticPlanner??(request.model?.plan?request.model as SemanticEditPlanner:undefined);
  let modelCalls=0,plannerCalls=0;const actions:any[]=[];const unresolvedQuestions:string[]=[];let basePlan:any;const perTargetInstructionHashes:{entryId:string;instructionHash:string}[]=[];
  for(const [index,target] of targets.entries()){
   const context=perTargetContexts[index];
   let planned;try{planned=await buildEditPlan(intent,state.documentSha256,target,context,planner,state)}catch(e){return executionFailure(e)}
   modelCalls+=planned.modelCalls;plannerCalls+=planned.plannerCalls??0;
   unresolvedQuestions.push(...(planned.plan.unresolvedQuestions??[]));
   const attempted=(planned.plan.actions[0] as any)?.targetEntryId;
   if(planned.plan.actions.length!==1||planned.plan.actions[0]?.kind!=='replace'||attempted!==target.entryId)return {status:'blocked',reason:context.successorRangeEntryIds?.includes(attempted)?'SUCCESSOR_CHILD_TARGET_FORBIDDEN':'SUCCESSOR_OUTSIDE_TARGET_FORBIDDEN',modelCalls,plannerCalls,mutations:0};
   actions.push(planned.plan.actions[0]);basePlan=planned.plan;perTargetInstructionHashes.push({entryId:target.entryId,instructionHash:planned.plan.instructionHash});
  }
  // Full multi-target provenance (re-audit cleanup): do NOT inherit `instructionHash`
  // from `...basePlan` (which is only the LAST target's plan) -- combine every
  // resolved target's own instruction hash instead, so the receipt covers the whole set.
  const combinedPlan={...basePlan,resolvedTargets:targets.map(t=>t.entryId),actions,unresolvedQuestions,successorCompositeTarget:true as const,instructionHash:combineSuccessorInstructionHashes(perTargetInstructionHashes)};
  const growthAdvisory=ambientDecisions?evaluateSuccessorGrowthThresholdFromTargets(targets,state.documentBytes.length):undefined;
  return this.publish(state,filename,intent.intent,{plan:combinedPlan,modelCalls,plannerCalls},mergedContext,CREATE_SUCCESSOR,request,undefined,growthAdvisory);
 }
 private async acceptFrozenSuccessor(state:any,filename:string,targets:TargetCandidate[],context:any,request:V2Request):Promise<any>{const token=request.successorAcceptanceToken;if(!token)return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_REQUIRED',modelCalls:0,plannerCalls:0,mutations:0};const preview=this.successorAcceptance.consume(request.sessionIdentity??'direct-orchestrator',token);if(!preview)return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_INVALID',modelCalls:0,plannerCalls:0,mutations:0};const targetIds=targets.map(t=>t.entryId);const sameTargets=preview.compositeTargetIds.length===targetIds.length&&preview.compositeTargetIds.every((id,i)=>id===targetIds[i]);if(preview.sourceFilename!==filename||preview.sourceRevision!==state.revision||preview.sourceSha256!==state.documentSha256||!sameTargets||preview.sectionRange!==(request.sectionRange??''))return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_STALE_SOURCE',modelCalls:0,plannerCalls:0,mutations:0};if(preview.targetFilename!==this.successorFilename(filename)||preview.plan.resolvedTargets.length!==targetIds.length||!preview.plan.resolvedTargets.every((id,i)=>id===targetIds[i])||preview.compiled.patches.length!==targetIds.length||preview.compiled.candidateSha256!==sha256(preview.compiled.candidate))return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_BINDING_INVALID',modelCalls:0,plannerCalls:0,mutations:0};try{if((await stat(join(this.root,'proposals',preview.targetFilename))).isFile())return {status:'blocked',reason:'SUCCESSOR_TARGET_COLLISION',modelCalls:0,plannerCalls:0,mutations:0}}catch{}return this.publish(state,filename,preview.plan.intent,{plan:preview.plan,modelCalls:preview.modelCalls,plannerCalls:preview.plannerCalls},context,CREATE_SUCCESSOR,request,preview.compiled)}
 /**
  * Resolves CREATE_SUCCESSOR + `resolvedDecisions` for ANY EditAction kind
  * (design `sdd/proposal-deliberation-ambient-model`, SLICE 1b): bypasses
  * `buildEditPlan`'s replace-only MODIFY invariant entirely, reducing the
  * WHOLE decision batch through `resolveAmbientCompositeDecisions` into two
  * homogeneous groups (SEPARATE-VERSION grouping, mirroring
  * `scientific-workflow-runtime.ts`'s `classifyMaterializationGroups`):
  * `inPlace` (replace/insert/delete -- one version) and `relocation`
  * (move/copy -- a SEPARATE version). A homogeneous batch (all in-place, or
  * all relocation) produces exactly one preview/accept round, exactly like
  * the SLICE-1 replace-only path. A MIXED batch freezes the in-place half
  * immediately and defers the relocation half's re-resolution to
  * `acceptAmbientCompositeSuccessor` (byte offsets are never stable across a
  * publish; only the original locus queries are). The current-turn
  * successor-acceptance consent gate stays required for every kind.
  */
 private async executeAmbientCompositeSuccessor(state:any,filename:string,targets:TargetCandidate[],queries:readonly string[],context:any,request:V2Request,ambientDecisions:readonly EditAction[]):Promise<any>{
  if(request.acceptSuccessor===true)return this.acceptAmbientCompositeSuccessor(state,filename,context,request);
  if(request.successorAcceptanceToken!==undefined)return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_CURRENT_TURN_REQUIRED',modelCalls:0,plannerCalls:0,mutations:0};
  let resolution;
  try{resolution=resolveAmbientCompositeDecisions(ambientDecisions,targets,state)}catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),modelCalls:0,plannerCalls:0,mutations:0}}
  const {inPlace,relocation}=resolution;
  try{
   if(relocation.parts.length===0){
    const compiled=await compileSuccessorCompositeChangeset(state,inPlace.parts);
    const plan=buildAmbientCompositeGroupPlan(state.documentSha256,inPlace,'MODIFY',request.instruction);
    const growthAdvisory=evaluateSuccessorGrowthThresholdFromTargets(targets,state.documentBytes.length);
    return this.publish(state,filename,'MODIFY',{plan,modelCalls:0,plannerCalls:0},context,CREATE_SUCCESSOR,request,compiled,growthAdvisory);
   }
   if(inPlace.parts.length===0){
    const compiled=await compileSuccessorCompositeChangeset(state,relocation.parts);
    const plan=buildAmbientCompositeGroupPlan(state.documentSha256,relocation,'MOVE',request.instruction);
    const growthAdvisory=evaluateSuccessorGrowthThresholdFromTargets(targets,state.documentBytes.length);
    return this.publish(state,filename,'MOVE',{plan,modelCalls:0,plannerCalls:0},context,CREATE_SUCCESSOR,request,compiled,growthAdvisory);
   }
   // Mixed batch: freeze the in-place half now; the relocation half is
   // deferred (queries + validated decisions only) for re-resolution once
   // the in-place half's own successor has published (see
   // `acceptAmbientCompositeSuccessor`).
   const inPlaceCompiled=await compileSuccessorCompositeChangeset(state,inPlace.parts);
   const inPlacePlan=buildAmbientCompositeGroupPlan(state.documentSha256,inPlace,'MODIFY',request.instruction);
   const growthAdvisory=evaluateSuccessorGrowthThresholdFromTargets(targets,state.documentBytes.length);
   const relocationQueries=relocation.targetIndices.map(index=>queries[index]!);
   const relocationOldEntryIds=relocation.targetIndices.map(index=>targets[index]!.entryId);
   return this.publish(state,filename,'MODIFY',{plan:inPlacePlan,modelCalls:0,plannerCalls:0},context,CREATE_SUCCESSOR,request,inPlaceCompiled,growthAdvisory,{queries:relocationQueries,oldEntryIds:relocationOldEntryIds,decisions:relocation.actions});
  }catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),modelCalls:0,plannerCalls:0,mutations:0}}
 }
 /**
  * Consumes an `executeAmbientCompositeSuccessor` preview token and publishes.
  * For a homogeneous batch this is a single `publish()` call, exactly like
  * `acceptFrozenSuccessor` (but without that method's replace-only
  * `patches.length===targetIds.length` assumption, which a `copy` decision
  * -- two claimed targets, one insert-only patch -- would violate). For a
  * MIXED batch, publishes the frozen in-place half FIRST, then re-resolves
  * the relocation half's ORIGINAL locus queries fresh against the
  * just-published state (composite entryIds are byte-offset-derived and
  * never survive a publish; the fuzzy query does), remaps the already-
  * validated relocation decisions onto the freshly resolved entryIds, and
  * publishes the relocation half as a SECOND, independent successor version
  * -- both within this ONE accept call, one consent token.
  */
 private async acceptAmbientCompositeSuccessor(state:any,filename:string,context:any,request:V2Request):Promise<any>{
  const token=request.successorAcceptanceToken;
  if(!token)return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_REQUIRED',modelCalls:0,plannerCalls:0,mutations:0};
  const preview=this.successorAcceptance.consume(request.sessionIdentity??'direct-orchestrator',token);
  if(!preview)return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_INVALID',modelCalls:0,plannerCalls:0,mutations:0};
  if(preview.sourceFilename!==filename||preview.sourceRevision!==state.revision||preview.sourceSha256!==state.documentSha256||preview.sectionRange!==(request.sectionRange??''))return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_STALE_SOURCE',modelCalls:0,plannerCalls:0,mutations:0};
  if(preview.targetFilename!==this.successorFilename(filename)||preview.compiled.candidateSha256!==sha256(preview.compiled.candidate))return {status:'blocked',reason:'SUCCESSOR_ACCEPTANCE_BINDING_INVALID',modelCalls:0,plannerCalls:0,mutations:0};
  try{if((await stat(join(this.root,'proposals',preview.targetFilename))).isFile())return {status:'blocked',reason:'SUCCESSOR_TARGET_COLLISION',modelCalls:0,plannerCalls:0,mutations:0}}catch{}
  const first=await this.publish(state,filename,preview.plan.intent,{plan:preview.plan,modelCalls:preview.modelCalls,plannerCalls:preview.plannerCalls},context,CREATE_SUCCESSOR,request,preview.compiled);
  if(!preview.pendingRelocation)return first;
  if(first.status!=='published')return {status:'blocked',reason:'SUCCESSOR_MIXED_BATCH_IN_PLACE_PUBLISH_FAILED',firstResult:first,modelCalls:0,plannerCalls:0,mutations:0};
  let freshState:any;
  try{freshState=await this.stateLoader(this.root,first.published.targetFilename)}catch{return {status:'blocked',reason:'DERIVED_STATE_REBUILD_FAILED',firstResult:first,modelCalls:0,plannerCalls:0,mutations:1}}
  const freshTargets:TargetCandidate[]=[];
  for(const query of preview.pendingRelocation.queries){
   const resolution=resolveSuccessorTarget(freshState,query);
   if(!resolution.candidates.length)return {status:'blocked',reason:resolution.reason??'SUCCESSOR_TARGET_NOT_FOUND',firstResult:first,modelCalls:0,plannerCalls:0,mutations:1};
   const gate=ambiguityGate(resolution.candidates);
   if(gate.blocked)return {status:'ambiguous',question:gate.question,firstResult:first,modelCalls:0,plannerCalls:0,mutations:1};
   freshTargets.push(gate.candidate!);
  }
  if(duplicateSuccessorTargets(freshTargets)||overlappingSuccessorTargets(freshTargets))return {status:'blocked',reason:'SUCCESSOR_TARGET_OVERLAP',firstResult:first,modelCalls:0,plannerCalls:0,mutations:1};
  for(const target of freshTargets)materializeCompositeTarget(freshState,target);
  const remap=new Map(preview.pendingRelocation.oldEntryIds.map((id,index)=>[id,freshTargets[index]!.entryId] as const));
  const remappedDecisions=preview.pendingRelocation.decisions.map(decision=>remapAmbientDecisionEntryIds(decision,remap));
  let relocationResolution;
  try{relocationResolution=resolveAmbientCompositeDecisions(remappedDecisions,freshTargets,freshState)}catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),firstResult:first,modelCalls:0,plannerCalls:0,mutations:1}}
  let compiled2;
  try{compiled2=await compileSuccessorCompositeChangeset(freshState,relocationResolution.relocation.parts)}catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),firstResult:first,modelCalls:0,plannerCalls:0,mutations:1}}
  const plan2=buildAmbientCompositeGroupPlan(freshState.documentSha256,relocationResolution.relocation,'MOVE',request.instruction);
  const second=await this.publish(freshState,first.published.targetFilename,'MOVE',{plan:plan2,modelCalls:0,plannerCalls:0},context,CREATE_SUCCESSOR,request,compiled2);
  return {status:second.status==='published'?'published':second.status,operation:CREATE_SUCCESSOR,versions:[first,second],published:second.published,receipt:second.receipt,derived:second.derived,plan:second.plan,compiled:second.compiled,validation:second.validation,context,modelCalls:0,plannerCalls:0,mutations:(first.mutations??0)+(second.mutations??0)};
 }
 private async publish(state:any,filename:string,intent:string,planned:any,context:any,operation:typeof CREATE_SUCCESSOR|any=intent,request?:V2Request,frozenCompiled?:any,growthAdvisory?:GrowthThresholdVerdict,pendingRelocation?:{queries:readonly string[];oldEntryIds:readonly string[];decisions:readonly EditAction[]}):Promise<any>{const plannerCalls=planned.plannerCalls??(planned.plan.semanticChange?1:0);if(planned.plannerDiagnostic)return {status:'blocked',reason:'PRODUCTION_PLANNER_RESPONSE_REJECTED',plannerDiagnostic:planned.plannerDiagnostic,modelCalls:planned.modelCalls,plannerCalls,mutations:0};const effectiveOperationProfile=resolveEffectiveOperationProfile({intent:intent as any,cleanupLevel:planned.plan.cleanupLevel,semanticChange:planned.plan.semanticChange,conceptualRisk:planned.plan.intent==='CONCEPTUAL_REVISION'?'MEDIUM':'LOW',successorCompositeTarget:operation===CREATE_SUCCESSOR&&planned.plan.successorCompositeTarget===true,successorTargetCount:planned.plan.resolvedTargets?.length});const roleAuthorizations=planned.roleAuthorizations??(planned.plan.cleanupLevel==='SEMANTIC'?1:0);if(planned.modelCalls>effectiveOperationProfile.maxModelCalls||plannerCalls>effectiveOperationProfile.maxPlannerCalls||roleAuthorizations>effectiveOperationProfile.maxRoleAuthorizations)return {status:'blocked',reason:'PLANNER_BUDGET_EXCEEDED',modelCalls:planned.modelCalls,plannerCalls,mutations:0};if(planned.plan.unresolvedQuestions.length)return {status:'needs-clarification',question:planned.plan.unresolvedQuestions[0],plan:planned.plan,context,modelCalls:planned.modelCalls,plannerCalls,mutations:0};if(!planned.plan.actions.length)return {status:'blocked',reason:'NO_MUTATION_PLAN',modelCalls:planned.modelCalls,plannerCalls:planned.modelCalls,mutations:0};return withMutationLock(mutationLockKey(this.root,state.lineage,filename,state.documentSha256),async()=>{let compiled;try{compiled=frozenCompiled??(planned.plan.successorCompositeTarget===true?await compileSuccessorCompositeReplacement(state,planned.plan):compilePatches(state,planned.plan))}catch(e){return {status:'blocked',reason:e instanceof Error?e.message:String(e),modelCalls:planned.modelCalls,plannerCalls:planned.modelCalls,mutations:0}};const validation=await validateCandidate(state,planned.plan,compiled);if(!validation.ok)return {status:'blocked',reason:'CANDIDATE_VALIDATION_FAILED',validation,modelCalls:planned.modelCalls,plannerCalls:planned.modelCalls,mutations:0};if(operation===CREATE_SUCCESSOR&&request?.acceptSuccessor!==true){const targetFilename=this.successorFilename(filename);const acceptanceToken=this.successorAcceptance.create(request?.sessionIdentity??'direct-orchestrator',{sourceFilename:filename,sourceRevision:state.revision,sourceSha256:state.documentSha256,compositeTargetIds:[...planned.plan.resolvedTargets],sectionRange:request?.sectionRange??'',targetFilename,plan:planned.plan,compiled,modelCalls:planned.modelCalls,plannerCalls,...(pendingRelocation?{pendingRelocation}:{})});return {status:'awaiting_acceptance',operation,sourceFilename:filename,targetFilename,acceptanceToken,patchCount:compiled.patches.length,plan:planned.plan,compiled,validation,mathDelta:validation.mathDelta,context,modelCalls:planned.modelCalls,plannerCalls,mutations:0,...(growthAdvisory?{growthAdvisory}:{}),...(pendingRelocation?{groups:{inPlace:planned.plan.resolvedTargets.length,relocationPending:true}}:{})};}
 // Accept gate for mathematical preservation. The preview above already
 // reported every lost atom with its id; publishing requires echoing them back,
 // so an equation can only leave the document deliberately, never by omission.
 if(operation===CREATE_SUCCESSOR&&validation.mathDelta.lost.length){const acknowledged=new Set(Array.isArray(request?.acknowledgedMathRemovals)?request.acknowledgedMathRemovals:[]);const unacknowledged=validation.mathDelta.lost.filter((atom:{id:string})=>!acknowledged.has(atom.id));if(unacknowledged.length)return {status:'blocked',reason:'MATH_REMOVALS_NOT_ACKNOWLEDGED',mathDelta:validation.mathDelta,unacknowledged,modelCalls:planned.modelCalls,plannerCalls,mutations:0};}let published;try{published=await writeTask(()=>this.adapter.publishSuccessor({intent:intent as any,sourceFilename:filename,sourceSha256:state.documentSha256,patches:compiled.patches,modelCalls:planned.modelCalls,plannerCalls,cleanupLevel:planned.plan.cleanupLevel,effectiveOperationProfile,roleAuthorizations,validationResults:validation.results}))}catch(e:any){return {status:'blocked',reason:String(e?.message??e),modelCalls:planned.modelCalls,plannerCalls:planned.modelCalls,mutations:0}}recordSuccessfulPublication();recordMutation();if(!published.publishedBytes.equals(Buffer.from(compiled.candidate)))return {status:'published-derived-failed',published,modelCalls:planned.modelCalls,mutations:1};const derived=await rebuildDerivedState(published.targetFilename,published.targetRevision,state.lineage,published.publishedBytes);try{await this.store.commitDerivedState(this.root,derived);const receipt=createRevisionReceipt({sourceRevision:state.revision,targetRevision:published.targetRevision,sourceFilename:filename,targetFilename:published.targetFilename,intent:intent as any,operation,instructionHash:planned.plan.instructionHash,documentShaBefore:state.documentSha256,documentShaAfter:published.publishedSha256,resolvedEntryIds:planned.plan.resolvedTargets,patchIds:compiled.patchIds,patchCount:compiled.patchIds.length,cleanupLevel:planned.plan.cleanupLevel,derivedStateStatus:'COMMITTED',modelCalls:planned.modelCalls,roleAuthorizations,inputTokens:0,outputTokens:0,elapsedMs:0,parallelTasks:1,validationResults:validation.results});await this.store.saveRevisionReceipt(this.root,published.targetFilename,receipt);return {status:'published',operation,published,receipt,derived:{...derived,derivedStateManifest:{...derived.derivedStateManifest,status:'COMMITTED'}},plan:planned.plan,compiled,validation,context,plannerInputBudget:planned.budgetEvidence,modelCalls:planned.modelCalls,plannerCalls,mutations:1}}catch(e){await this.store.markDerivedState(this.root,published.targetFilename,'FAILED',e instanceof Error?e.message:String(e));return {status:'published-derived-failed',published,modelCalls:planned.modelCalls,mutations:1}}});}
}
