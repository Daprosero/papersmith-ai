import { randomUUID } from 'node:crypto';
import { nextSuccessorTarget, type DocumentOperationGuard, type ProposalWorkspaceInput } from '../proposal-workspace.js';
import { sha256, type CleanupLevel, type CompiledPatch, type EffectiveOperationProfile, type Intent } from './types.js';

type WorkspaceResult={details:Record<string,unknown>;content:Array<{type:string;text:string}>};
type Workspace={execute(id:string,input:ProposalWorkspaceInput,signal?:AbortSignal):Promise<WorkspaceResult>};
export type PublishSuccessorInput={intent:Intent;cleanupLevel:CleanupLevel;effectiveOperationProfile:EffectiveOperationProfile;sourceFilename:string;sourceSha256:string;patches:CompiledPatch[];modelCalls:number;plannerCalls:number;roleAuthorizations:number;validationResults:Record<string,boolean>;operationId?:string};
export type PublishedSuccessor={operationId:string;sourceFilename:string;sourceSha256:string;targetFilename:string;targetRevision:string;publishedSha256:string;publishedBytes:Buffer;patchCount:number;workspaceEvidence:Record<string,unknown>;guardEvidence:Record<string,unknown>};
function requireAllowed(receipt:any,step:string){if(receipt?.decision!=='allowed')throw new Error(`PROPOSAL_ADAPTER_${step}_${receipt?.reason?.code??'DENIED'}`);return receipt}
function managedBytes(result:WorkspaceResult):Buffer { const bytes=result.details.managedBytes; if(Buffer.isBuffer(bytes)) return bytes; if(typeof bytes==='string') return Buffer.from(bytes,'utf8'); throw new Error('MANAGED_READ_BYTES_UNAVAILABLE'); }
export class ProposalWorkspaceAdapter {
 constructor(private readonly projectRoot:string,private readonly guard:DocumentOperationGuard,private readonly workspace:Workspace,private readonly operationIdFactory:()=>string=()=>`paper-proposal-v2-${randomUUID()}`){}
 async publishSuccessor(input:PublishSuccessorInput):Promise<PublishedSuccessor>{
  const profile=input.effectiveOperationProfile; if(!profile||profile.intent!==input.intent||profile.cleanupLevel!==input.cleanupLevel) throw new Error('INVALID_EFFECTIVE_OPERATION_PROFILE');
  if(!/^research-concept-(?:[a-z0-9]+(?:-[a-z0-9]+)*-)?r\d{2,}\.md$/.test(input.sourceFilename)||!/^[a-f0-9]{64}$/.test(input.sourceSha256)||!Array.isArray(input.patches)||input.patches.length<1) throw new Error('INVALID_SUCCESSOR_INPUT');
  if(input.modelCalls<0||input.plannerCalls<0||input.roleAuthorizations<0||input.modelCalls>profile.maxModelCalls||input.plannerCalls>profile.maxPlannerCalls||input.roleAuthorizations>profile.maxRoleAuthorizations||input.patches.length>profile.maxPatchCount||profile.maxMutations<1) throw new Error('INVALID_OPERATION_BUDGET');
  const patches=input.patches; const targetFilename=nextSuccessorTarget(input.sourceFilename); const targetRevision=targetFilename.match(/-r(\d+)\.md$/)?.[1]; if(!targetRevision) throw new Error('INVALID_TARGET_REVISION'); const targetRevisionLabel=`r${targetRevision}`;
  const operationId=input.operationId??this.operationIdFactory(); let published=false; let guardEvidence:any={};
  try {
   guardEvidence.begin=requireAllowed(await this.guard.execute({action:'begin_document_operation',operation_id:operationId}),'BEGIN');
   guardEvidence.preflight=requireAllowed(await this.guard.execute({action:'preflight_plan',operation_id:operationId,mode:'INCREMENTAL_EDIT',operation:input.intent,budget:{max_document_delegations:input.roleAuthorizations,attempts:1,model_candidates:input.modelCalls,patches:input.patches.length},sourceFilename:input.sourceFilename,sourceSha256:input.sourceSha256,successorFilename:targetFilename,mutationAction:'derive_successor'}),'PREFLIGHT');
   const authorization=requireAllowed(await this.guard.execute({action:'authorize_mutation',operation_id:operationId}),'AUTHORIZE'); if(!authorization.authorization) throw new Error('MUTATION_AUTHORIZATION_MISSING'); guardEvidence.authorization=authorization;
   const derived=await this.workspace.execute(operationId,{action:'derive_successor',resource:'proposal',source:input.sourceFilename,sourceSha256:input.sourceSha256,slug:targetFilename.slice('research-concept-'.length,-'.md'.length),patches,operation_id:operationId,operationAuthorization:authorization.authorization} as ProposalWorkspaceInput); published=true;
   const details=derived.details; const actual=String(details.target??'').replace(/^proposals\//,''); if(actual!==targetFilename) throw new Error('UNEXPECTED_PUBLISHED_TARGET');
   const publishedSha=String(details.targetSha256??details.sha256??''); const reread=await this.workspace.execute(operationId,{action:'read',resource:'managed_target',name:actual}); const bytes=managedBytes(reread); const readSha=String(reread.details.sha256??'');
   const source=await this.workspace.execute(operationId,{action:'read',resource:'managed_target',name:input.sourceFilename}); if(String(source.details.sha256??'')!==input.sourceSha256) throw new Error('SOURCE_CHANGED_AFTER_PUBLISH');
   if(!/^r\d{2,}$/.test(targetRevisionLabel)||publishedSha!==readSha||sha256(bytes)!==readSha) throw new Error(`PUBLISHED_READ_MISMATCH:${publishedSha}:${readSha}:${sha256(bytes)}`);
   guardEvidence.complete=requireAllowed(await this.guard.execute({action:'complete_operation',operation_id:operationId}),'COMPLETE');
   return {operationId,sourceFilename:input.sourceFilename,sourceSha256:input.sourceSha256,targetFilename:actual,targetRevision:targetRevisionLabel,publishedSha256:readSha,publishedBytes:bytes,patchCount:input.patches.length,workspaceEvidence:{derive:details,read:reread.details,source:source.details},guardEvidence};
  } catch(error) { if(!published){try{guardEvidence.block=await this.guard.execute({action:'block_operation',operation_id:operationId,reason:error instanceof Error?error.message:String(error)})}catch{}} throw Object.assign(error instanceof Error?error:new Error(String(error)),{published,operationId,guardEvidence}); }
 }
}
