import { createHash } from 'node:crypto';

export const PARSER_VERSION = 'paper-proposal/1';
export const LIMITS = Object.freeze({ maxCandidates: 8, maxContextFragments: 8, maxContextBytesLocal: 32000, maxContextBytesSection: 32000, maxPatchCountLocal: 4, maxCleanupRanges: 3, maxModelCallsLocal: 1, maxModelCallsConceptual: 2, maxParallelReadTasks: 4, maxParallelValidationTasks: 6, maxParallelModelCalls: 1, maxParallelWriteTasks: 1 });
export type Intent = 'MODIFY'|'INSERT'|'DELETE'|'MOVE'|'COPY'|'CONCEPTUAL_REVISION'|'REVIEW'|'DELIBERATE'|'WITHDRAW_REVISION'|'RESTORE_WITHDRAWN_REVISION'|'CLOSE_DELIBERATION'|'AMBIGUOUS';
/** Explicit public route: derives the only permitted target from the managed source. */
export type CreateSuccessorOperation = 'CREATE_SUCCESSOR';
export type SuccessorEditIntent = Extract<Intent,'MODIFY'|'CONCEPTUAL_REVISION'>;
export type PublicV2Operation = RevisionLifecycleOperation|CreateSuccessorOperation;
export const PENDING_AUDIT_LEASE_MS = 30_000;
export type RevisionLifecycleOperation = Extract<Intent,'WITHDRAW_REVISION'|'RESTORE_WITHDRAWN_REVISION'>;
export type PendingAuditPhase = 'WITHDRAW_PUBLIC_ARTIFACTS_MOVED'|'RESTORE_PUBLIC_ARTIFACTS_MOVED';
export type PendingAuditArtifact = {
 publicRelativePath:string;
 sha256:string;
 expectedLocation:'quarantine-public-backup'|'public';
};
export type PendingAuditContext = {
 operationType:RevisionLifecycleOperation;
 operationId:string;
 pendingAudit:true;
 phase:PendingAuditPhase;
 temporarilyMovedArtifacts:PendingAuditArtifact[];
 expectedMarker:{
  relativePath:string;
  state:'PENDING_AUDIT';
  inventoryDigest:string;
  expiresAt:string;
 };
};
export type RevisionLifecycleLockOwner = Readonly<{
 operationId:string;
 filename:string;
}>;
export type RevisionLifecycleArtifact = {
 publicRelativePath:string;
 quarantineRelativePath:string;
 sha256:string;
};
export type RevisionWithdrawalMetadata = {
 schemaVersion:'1';
 operationId:string;
 operationTimestamp:string;
 requestedFilename:string;
 revision:string;
 documentSha256:string;
 sourceRevision:string;
 sourceFilename:string;
 reason:string;
 artifacts:RevisionLifecycleArtifact[];
 inventoryDigest:string;
 preWithdrawalLatestFilename:string;
};
export type RevisionLifecycleResult = {
 status:'withdrawn'|'restored'|'blocked';
 operation:RevisionLifecycleOperation;
 withdrawnFilename:string|null;
 restoredLatestFilename:string|null;
 artifactCount:number;
 backupLocation:string|null;
 auditStatus:'PASS'|'WARN'|'FAIL'|'NOT_RUN';
 selfAuditStatus:'PASS'|'WARN'|'FAIL'|'NOT_RUN';
 warnings:string[];
};
export type EntryType = 'document'|'section'|'subsection'|'heading'|'paragraph'|'display_equation'|'inline_math_region'|'list'|'code_block'|'definition'|'theorem'|'algorithm'|'figure_reference'|'table_reference'|'composite';
export type Position = 'before'|'after'|'inside_start'|'inside_end';
export type DerivedStateStatus = 'VALID'|'STALE'|'MISSING'|'BUILDING'|'FAILED'|'COMMITTED';
export type CleanupLevel = 'NONE'|'STRUCTURAL'|'SEMANTIC'; export type MoveMode = 'LITERAL'|'ADAPTIVE';
export const sha256 = (value: string | Buffer) => createHash('sha256').update(value).digest('hex');
export type StructuralEntry = { entryId:string; type:EntryType; startByte:number; endByte:number; textSha256:string; parentId?:string; childIds:string[]; ordinal:number; headingPath:string[]; labels:string[]; tags:string[]; lexicalTerms:string[]; deterministicAliases:string[]; neighboringEntryIds:string[]; sectionReplacement?:SectionReplacementContract };
export type StructuralIndex = { entries: StructuralEntry[]; byId: Record<string, StructuralEntry> };
export type ReferenceIndex = { labels:Record<string,string>; tags:Record<string,string>; references:{kind:string; value:string; entryId:string}[]; missing:string[]; duplicates:string[] };
export type SymbolIndex = { symbols:Record<string,{normalized:string; definition?:string; domain?:string; firstEntryId:string; uses:string[]; section:string[]}>; conflicts:string[] };
export type ConceptIndex = { terms:Record<string,string[]>; aliases:Record<string,string[]> };
export type DerivedStateManifest = { schemaVersion:'1'; parserVersion:string; documentFilename:string; documentSha256:string; structuralIndexSha256:string; referenceIndexSha256:string; symbolIndexSha256:string; conceptIndexSha256:string; createdAt:string; status:DerivedStateStatus; revision:string };
export type DocumentState = { filename:string; revision:string; lineage:string; documentSha256:string; documentBytes:Buffer; parserVersion:string; structuralIndex:StructuralIndex; referenceIndex:ReferenceIndex; symbolIndex:SymbolIndex; conceptIndex:ConceptIndex; derivedStateStatus:DerivedStateStatus; derivedStateManifest:DerivedStateManifest };
export type UserRequest = { instruction:string; selectedEntryId?:string; model?: EditModel; operationId?:string };
export type FidelityConstraints = { targetBlock?:string; replacementBlock?:string; preserveExternalBytes?:true; noReformat?:true; noSemanticReinterpretation?:true };
export type ResolvedIntent = { intent:Intent; targetDescription:string; sourceDescription?:string; destinationDescription?:string; requestedPosition?:Position; requestedEffect?:string; semanticChange:boolean; constraints:string[]; fidelity:FidelityConstraints; scope:'LOCAL'|'SECTION'|'DOCUMENT'; evidence:string[]; destructiveIntent:boolean; cleanupAuthorized:boolean; moveMode:MoveMode; removeSource:boolean; cleanupLevel:CleanupLevel; modelBudget:number; confidence:number; pendingQuestions:string[]; unresolvedQuestions:string[] };
export type SectionReplacementContract = { kind:'numbered-section-range'; startByte:number; endByte:number; newline:'\n'|'\r\n'; startAtLineStart:true; endAfterCompleteLine:true; requestedSectionIds:string[] };
export type CompositeTarget = { entryIds:string[]; startByte:number; endByte:number; documentSha256:string; textSha256:string; exactProvidedText:string; sectionReplacement?:SectionReplacementContract };
export type TargetCandidate = { entryId:string; type:EntryType; headingPath:string[]; matchedTerms:string[]; matchedLabels:string[]; matchedTags:string[]; matchedSymbols:string[]; score:number; confidence:number; shortPreview:string; evidence:string[]; composite?:CompositeTarget };
export type ContextFragment = { entryId:string; type:EntryType; text:string; textSha256:string; headingPath:string[] };
export type LocalContext = { documentSha256:string; targetEntryId:string; instruction:string; fragments:ContextFragment[]; nearbySymbols:Record<string,string>; directReferences:string[]; fidelity?:FidelityConstraints; maxBytes?:number; authorizedEntryIds?:string[]; successorCompositeTarget?:true; successorRangeEntryIds?:string[] };
export type MoveCopyContext = { documentSha256:string; instruction:string; sourceContext:LocalContext; destinationContext:LocalContext; fragments:ContextFragment[] };
export type EditAction = { kind:'replace'; targetEntryId:string; replacementText:string; semanticChange?:boolean; rationale?:string } | { kind:'insert'; anchorEntryId:string; position:Position; content:string } | { kind:'delete'; targetEntryId:string; instructionEvidence:string; reason:string } | { kind:'move'|'copy'; sourceEntryIds:string[]; destinationAnchorId:string; position:Position; moveMode:MoveMode; removeSource:boolean; transformedContent?:string; cleanupLevel:CleanupLevel } | { kind:'cleanup'; boundedRangeIds:string[]; action:'delete'|'rewrite'; reason:string; instructionEvidence:string } | { kind:'rewrite_transition'; boundedRangeId:string; replacementText:string; reason:string };

/**
 * The public byte cap for a persisted scientific `proposedEdit.replacementText`
 * (or `.content`) leaf ONLY. Every other public payload string (including every
 * OTHER field nested inside `proposedEdit` itself) stays bounded at the
 * pre-existing 2,000-byte guard -- see `scientific-state-store.ts`'s
 * `assertPublicValue`, which is the sole enforcement point.
 */
export const PROPOSED_EDIT_REPLACEMENT_MAX_BYTES = 20_000;

/**
 * Validates an untrusted, persisted `TUTOR_ASSESSED.payload.proposedEdit` value
 * into a genuine `EditAction`. Currently recognizes only the single-locus
 * `replace` shape -- the only shape `ScientificWorkflowService.candidate()`
 * ever emits. Anything else (a malformed object, or a well-formed but
 * unimplemented `insert`/`delete`/`move`/`copy`/`cleanup`/`rewrite_transition`
 * shape) returns `undefined` so callers fall back to the pre-existing
 * summary-annotation route rather than trusting an edit shape this pipeline
 * never validated end-to-end.
 */
export function parseProposedEdit(value: unknown): EditAction | undefined {
	if (!value || typeof value !== 'object') return undefined;
	const candidate = value as Record<string, unknown>;
	if (candidate.kind !== 'replace') return undefined;
	if (typeof candidate.targetEntryId !== 'string' || candidate.targetEntryId.length === 0 || candidate.targetEntryId.length > 128) return undefined;
	if (typeof candidate.replacementText !== 'string' || candidate.replacementText.length === 0 || candidate.replacementText.length > PROPOSED_EDIT_REPLACEMENT_MAX_BYTES) return undefined;
	if (candidate.semanticChange !== undefined && typeof candidate.semanticChange !== 'boolean') return undefined;
	if (candidate.rationale !== undefined && (typeof candidate.rationale !== 'string' || candidate.rationale.length > 2_000)) return undefined;
	return {
		kind: 'replace',
		targetEntryId: candidate.targetEntryId,
		replacementText: candidate.replacementText,
		...(candidate.semanticChange !== undefined ? { semanticChange: candidate.semanticChange as boolean } : {}),
		...(candidate.rationale !== undefined ? { rationale: candidate.rationale as string } : {}),
	};
}
export type DeletePlan = { planVersion:'2'; documentSha256:string; targetEntryIds:string[]; destructiveIntent:true; instructionEvidence:string[]; reason:string; affectedReferences:string[]; affectedSymbols:string[]; cleanupLevel:CleanupLevel; unresolvedQuestions:string[] };
export type EditPlan = { planVersion:'2'; documentSha256:string; intent:Intent; instructionHash:string; resolvedTargets:string[]; destination?:string; semanticChange:boolean; destructiveIntent:boolean; cleanupLevel:CleanupLevel; constraints:string[]; actions:EditAction[]; expectedEffects:string[]; unresolvedQuestions:string[]; successorCompositeTarget?:true };
export type MovePlan = EditPlan & { intent:'MOVE'; sourceEntryIds:string[]; destinationEntryId:string; position:Position; mode:MoveMode; removeSource:true; transformedContent?:string; semanticChange:boolean };
export type CopyPlan = EditPlan & { intent:'COPY'; sourceEntryIds:string[]; destinationEntryId:string; position:Position; mode:MoveMode; removeSource:false; transformedContent?:string; semanticChange:boolean };
export type StructuralPatchSelector = {entryId:string;startByte:number;endByte:number;textSha256:string;documentSha256:string};
export type CompiledPatch = { id:string; kind:'replace'|'insert'; oldText?:string; newText?:string; anchor?:string; position?:'before'|'after'; content?:string; selector?:StructuralPatchSelector };
export type Compilation = { patches:CompiledPatch[]; candidate:string; candidateSha256:string; patchIds:string[]; unchangedByteCoverage:boolean; modifiedRanges:{startByte:number;endByte:number}[]; sourceBytes?:Buffer; destinationEntryId?:string; position?:Position };
export type SemanticPlannerInput = { intent:ResolvedIntent; instruction:string; target?:TargetCandidate; context?:LocalContext; sourceContext?:LocalContext; destinationContext?:LocalContext; sourceEntryIds?:string[]; destinationEntryId?:string; position?:Position; constraints:string[]; fidelity?:FidelityConstraints; documentSha256:string };
export type PlannerInputBudgetEvidence = { unit:'utf8_bytes'; accountingVersion:'1'; payloadPath:'fidelity_modify'; effectiveBytes:number; budgetBytes:number };
export type SemanticEditPlanner = {
 preflight?(input:SemanticPlannerInput):PlannerInputBudgetEvidence|undefined;
 plan(input:SemanticPlannerInput):Promise<Partial<EditPlan>&{transformedContent?:string; sourceEntryIds?:string[]; destinationEntryId?:string; position?:Position; actions?:EditAction[]}>;
};
export type EditModel = { plan?(input:any):Promise<Partial<EditPlan>>; validate?(input:{plan:EditPlan; candidate:string}):Promise<{ok:boolean; reason?:string}> };
export type RevisionReceipt = { sourceRevision:string; targetRevision:string; sourceFilename:string; targetFilename:string; intent:Intent; operation:Intent|CreateSuccessorOperation; instructionHash:string; documentShaBefore:string; documentShaAfter:string; resolvedEntryIds:string[]; patchIds:string[]; patchCount:number; cleanupLevel:CleanupLevel; derivedStateStatus:DerivedStateStatus; modelCalls:number; roleAuthorizations:number; inputTokens:number; outputTokens:number; elapsedMs:number; parallelTasks:number; validationResults:Record<string,boolean> };
export type OperationRisk='LOW'|'MEDIUM'|'HIGH';
export type EffectiveOperationProfile={intent:Intent;cleanupLevel:CleanupLevel;maxModelCalls:number;maxPlannerCalls:number;maxRoleAuthorizations:number;maxMutations:number;maxPatchCount:number;maxCleanupRanges:number;requiresTutor:boolean;requiresReviewer:boolean;operationRisk:OperationRisk};
export type LifecycleV1RecordState='ACTIVE'|'SUPERSEDED'|'WITHDRAWN';
export type LifecycleV1WorkspaceState='EMPTY'|'BASE_REGISTERED'|'ACTIVE'|'WITHDRAWN_ONLY'|'INCONSISTENT';
export type LifecycleV1ErrorCode='BASE_DOCUMENT_NOT_REGISTERED'|'BASE_DOCUMENT_ALREADY_REGISTERED'|'ACTIVE_REVISION_ALREADY_EXISTS'|'ACTIVE_REVISION_NOT_FOUND'|'INVALID_LINEAGE_REFERENCE'|'REVISION_NOT_WITHDRAWABLE'|'REVISION_NOT_WITHDRAWN'|'WITHDRAWAL_IDENTITY_NOT_FOUND'|'BASE_DOCUMENT_NOT_RESTORABLE'|'OUTPUT_FILENAME_CONFLICT'|'SOURCE_CONTENT_HASH_MISMATCH'|'LIFECYCLE_INVENTORY_INCONSISTENT'|'LIFECYCLE_V1_UNREGISTERED'|'REQUEST_ID_CONFLICT'|'RECOVERY_REQUIRED';
export type LineageReference={sourceKind:'BASE_DOCUMENT'|'REVISION';sourceId:string;sourceContentHash:string;baseDocumentId:string};
export type BaseDocument={schemaVersion:'lifecycle-v1';workspaceId:string;baseDocumentId:string;contentHash:string;content:string;provenance?:string;locator?:string;transitionId:string};
export type LifecycleRevision={schemaVersion:'lifecycle-v1';workspaceId:string;revisionId:string;baseDocumentId:string;contentHash:string;content:string;lineage:LineageReference;locator?:string;isFirst:boolean;transitionId:string};
export type WithdrawalRecord={schemaVersion:'lifecycle-v1';workspaceId:string;withdrawalId:string;revisionId:string;contentHash:string;recoveryContent:string;reason?:string;transitionId:string;state:'COMMITTED'|'RESTORED'|'ABORTED'};
export type MaterializationRequest={requestId:string;workspaceId:string;operation:'CREATE_FROM_BASE'|'CREATE_SUCCESSOR';source:LineageReference;approvedChanges:ReadonlyArray<{from:string;to:string}>;revisionId:string;locator?:string};
export type MaterializationResult={resultId:string;requestId:string;workspaceId:string;operation:'CREATE_FROM_BASE'|'CREATE_SUCCESSOR';revisionId:string;contentHash:string;source:LineageReference;outcome:'COMMITTED'|'ALREADY_COMMITTED'|'REJECTED'|'INCONSISTENT'|'RECOVERY_REQUIRED';code?:LifecycleV1ErrorCode;transitionId?:string};
export type WorkspaceLifecycleState={schemaVersion:'lifecycle-v1';workspaceId:string;lifecycleState:LifecycleV1WorkspaceState;base?:BaseDocument;revisions:Array<LifecycleRevision&{state:LifecycleV1RecordState}>;withdrawals:WithdrawalRecord[];activeRevisionId?:string;integrityDigest:string};
export type LifecycleTransitionEvidence={schemaVersion:'lifecycle-v1';transitionId:string;workspaceId:string;sequence:number;operation:string;requestId:string;outcome:'COMMITTED'|'REJECTED'|'RECOVERY_REQUIRED';recordPaths:string[];stateChanges:Array<{revisionId:string;state:LifecycleV1RecordState}>;committedAt:string};
export type { ScientificThread, ScientificDecision, ScientificEvent, ThreadRelation, ThreadSynthesis, ScientificAct, ScientificActResolution, BoundedScientificSeed, ThreadTransitionIntent, ThreadResolution, ProjectEntryState, ScientificWorkflowOperation, ScientificWorkflowPublicStatus, ScientificActKind, ScientificThreadStatus, ScientificDecisionStatus, ScientificEventType, ThreadRelationKind, ThreadSynthesisStatus, MaterializationState, MaterializationPlanKind, FrozenDecisionSelection, MaterializationRecord, MaterializationReservedDecision, MaterializationClaimProvenance, CanonicalProposalMetadata, FrozenPatchPreconditions, FrozenEditPlan, CreateR01PayloadV1, CreateSuccessorPayloadV1, MaterializationPlan, ScientificActorKind, ConceptualReviewOutcome, ScientificResolutionStatus, ScientificAuditStatus, ScientificWorkflowRequest, ScientificWorkflowPublicResult } from './scientific-domain.js';
