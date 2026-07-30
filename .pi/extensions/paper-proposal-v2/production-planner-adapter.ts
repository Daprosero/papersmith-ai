import { Type } from 'typebox';
import type { SemanticEditPlanner, SemanticPlannerInput } from './types.js';
import { ProductionModelRuntime } from './production-runtime.js';

const plannerPrompt = (maxConceptualActions: number) => `You are the Paper Proposal V2 semantic planner. Return one plain JSON object only through the required structured-output tool, without prose, Markdown, code fences, or text outside the tool call. Use only the supplied local context and supplied document SHA. Never read files, publish, return a full document, invent entry IDs, offsets, or hashes. Return the smallest valid V2 plan fragment. For adaptive MOVE/COPY return only transformedContent and preserve supplied source, destination, and position. For semantic cleanup return only bounded cleanup/rewrite_transition actions inside supplied context. For conceptual revision, return exactly two top-level keys: actions and unresolvedQuestions. Do not return expectedEffects, expectedEffects-like plan metadata, or any other top-level key. Return 1-${maxConceptualActions} bounded replace actions on supplied context entry IDs. Include unresolvedQuestions when clarification is needed.`;
const FIDELITY_MODIFY_PROMPT = `Return exactly one required tool call for the supplied exact MODIFY. Copy replacementBlock byte-for-byte into replacementText, use targetEntryId unchanged, and return only actions and unresolvedQuestions. Never broaden the edit, invent identifiers, use external or session context, or return document content.`;
const SUCCESSOR_REPLACEMENT_PROMPT = `You are the Paper Proposal V2 successor replacement writer. Return one plain JSON object only through the required structured-output tool. Supply only replacementText and unresolvedQuestions for the one already-authorized bounded successor section. Do not return actions, target IDs, source or destination information, publication instructions, offsets, hashes, or a complete document.`;

const FIDELITY_RESPONSE_KEYS = new Set(['actions', 'unresolvedQuestions']);
const SUCCESSOR_RESPONSE_KEYS = new Set(['replacementText', 'unresolvedQuestions']);
const REPLACE_ACTION_KEYS = new Set(['kind', 'targetEntryId', 'replacementText']);
const CONCEPTUAL_RESPONSE_KEYS = new Set(['actions', 'unresolvedQuestions']);
const conceptualOutput = (maxActions: number) => Object.freeze({
 name: 'paper_proposal_v2_conceptual_revision',
 description: `Return 1-${maxActions} authorized Paper Proposal V2 conceptual replacements and any unresolved questions.`,
 schema: Type.Object({
  actions: Type.Array(Type.Object({
   kind: Type.Literal('replace'),
   targetEntryId: Type.String({ minLength: 1 }),
   replacementText: Type.String(),
  }, { additionalProperties: false }), { minItems: 1, maxItems: maxActions }),
  unresolvedQuestions: Type.Array(Type.String({ minLength: 1 })),
 }, { additionalProperties: false }),
});
const FIDELITY_MODIFY_OUTPUT = Object.freeze({
 name: 'paper_proposal_v2_fidelity_modify',
 description: 'Return the one authorized Paper Proposal V2 fidelity MODIFY replacement.',
 schema: Type.Object({
  actions: Type.Array(Type.Object({
   kind: Type.Literal('replace'),
   targetEntryId: Type.String({ minLength: 1 }),
   replacementText: Type.String(),
  }, { additionalProperties: false }), { minItems: 1, maxItems: 1 }),
  unresolvedQuestions: Type.Array(Type.String()),
 }, { additionalProperties: false }),
});
const SUCCESSOR_REPLACEMENT_OUTPUT = Object.freeze({
 name: 'paper_proposal_v2_successor_replacement',
 description: 'Return replacement content for the one already-authorized successor section.',
 schema: Type.Object({
  replacementText: Type.String({ minLength: 1 }),
  unresolvedQuestions: Type.Array(Type.String()),
 }, { additionalProperties: false }),
});

export type PlannerDiagnosticCode =
 | 'MODEL_RESPONSE_ERROR'
 | 'RESPONSE_NOT_OBJECT'
 | 'UNEXPECTED_RESPONSE_FIELD'
 | 'MISSING_RESPONSE_FIELD'
 | 'INVALID_UNRESOLVED_QUESTIONS'
 | 'INVALID_ACTION_COUNT'
 | 'ACTION_NOT_OBJECT'
 | 'UNEXPECTED_ACTION_FIELD'
 | 'MISSING_ACTION_FIELD'
 | 'WRONG_ACTION_KIND'
 | 'INVALID_TARGET_ENTRY_ID'
 | 'INVALID_REPLACEMENT_TEXT'
 | 'WRONG_TARGET_ENTRY_ID'
 | 'ALTERED_REPLACEMENT_TEXT';

export type PlannerDiagnosticStage = 'runtime' | 'adapter' | 'plan-validation';
type InvocationState = Readonly<{ modelCalls: 1; plannerCalls: 1 }>;
type PlannerDiagnostic = Readonly<{
 code: PlannerDiagnosticCode;
 stage: PlannerDiagnosticStage;
 expectedFields: readonly string[];
 unexpectedFields: readonly string[];
 receivedActionCount: number;
 receivedKind: string | null;
 plannerInvoked: true;
 plannerCalls: 1;
 modelCalls: 1;
}>;

/** Carries completed planner/model invocation counts across fail-closed normalization. */
export class ProductionPlannerResponseError extends Error {
 readonly code = 'PRODUCTION_PLANNER_RESPONSE_REJECTED';
 readonly diagnostic: PlannerDiagnostic;
 readonly invocation: InvocationState = Object.freeze({ modelCalls: 1, plannerCalls: 1 });

 constructor(
  diagnosticCode: PlannerDiagnosticCode,
  state: { response?: unknown; expectedFields?: readonly string[]; unexpectedFields?: readonly string[] } = {},
  stageOrOptions: PlannerDiagnosticStage | { cause?: unknown } = 'adapter',
  options?: { cause?: unknown },
 ) {
  const stage = typeof stageOrOptions === 'string' ? stageOrOptions : 'adapter';
  const errorOptions = typeof stageOrOptions === 'string' ? options : stageOrOptions;
  super(`${'PRODUCTION_PLANNER_RESPONSE_REJECTED'}:${diagnosticCode}`, errorOptions);
  this.name = 'ProductionPlannerResponseError';
  const action = isRecord(state.response) && Array.isArray(state.response.actions) ? state.response.actions[0] : undefined;
  this.diagnostic = Object.freeze({
   code: diagnosticCode,
   stage,
   expectedFields: [...(state.expectedFields ?? REPLACE_ACTION_KEYS)],
   unexpectedFields: [...(state.unexpectedFields ?? (isRecord(action) ? Object.keys(action).filter((key) => !REPLACE_ACTION_KEYS.has(key)) : []))],
   receivedActionCount: isRecord(state.response) && Array.isArray(state.response.actions) ? state.response.actions.length : 0,
   receivedKind: isRecord(action) && typeof action.kind === 'string' ? action.kind : null,
   plannerInvoked: true,
   plannerCalls: 1,
   modelCalls: 1,
  });
 }
}

function rejectResponse(
 code: PlannerDiagnosticCode,
 state: { response?: unknown; expectedFields?: readonly string[]; unexpectedFields?: readonly string[] } = {},
 cause?: unknown,
 stage: PlannerDiagnosticStage = 'adapter',
): never {
 throw new ProductionPlannerResponseError(code, state, stage, cause === undefined ? undefined : { cause });
}

function isRecord(value: unknown): value is Record<string, unknown> {
 return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function unexpectedKeys(value: Record<string, unknown>, allowed: ReadonlySet<string>): string[] {
 return Object.keys(value).filter((key) => !allowed.has(key));
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: ReadonlySet<string>): boolean {
 return unexpectedKeys(value, allowed).length === 0;
}

function normalizeQuestions(value: unknown, response: unknown): string[] {
 if (value === undefined) return [];
 if (!Array.isArray(value) || value.some((question) => typeof question !== 'string' || question.trim().length === 0)) {
  rejectResponse('INVALID_UNRESOLVED_QUESTIONS', { response, expectedFields: ['actions', 'unresolvedQuestions'] });
 }
 return [...value];
}

function buildFidelityModifyPayload(input: SemanticPlannerInput) {
 if (!input.target || input.fidelity?.targetBlock === undefined || input.fidelity.replacementBlock === undefined) throw new Error('INVALID_FIDELITY_MODIFY_INPUT');
 return {
  operation: 'MODIFY',
  documentSha256: input.documentSha256,
  targetEntryId: input.target.entryId,
  targetType: input.target.type,
  targetHeadingPath: input.target.headingPath,
  targetBlock: input.fidelity.targetBlock,
  replacementBlock: input.fidelity.replacementBlock,
  constraints: { preserveExternalBytes: true, noReformat: true, singleReplaceAction: true },
 } as const;
}

function normalizeConceptualRevision(
 input: SemanticPlannerInput,
 response: unknown,
): Awaited<ReturnType<SemanticEditPlanner['plan']>> {
 const expectedResponseFields = ['actions', 'unresolvedQuestions'];
 const maxActions = input.context?.successorCompositeTarget === true ? 1 : 3;
 if (!isRecord(response)) rejectResponse('RESPONSE_NOT_OBJECT', { response, expectedFields: expectedResponseFields });
 if (!hasOnlyKeys(response, CONCEPTUAL_RESPONSE_KEYS)) rejectResponse('UNEXPECTED_RESPONSE_FIELD', { response, expectedFields: expectedResponseFields, unexpectedFields: unexpectedKeys(response, CONCEPTUAL_RESPONSE_KEYS) });
 if (!Object.hasOwn(response, 'actions') || !Object.hasOwn(response, 'unresolvedQuestions')) rejectResponse('MISSING_RESPONSE_FIELD', { response, expectedFields: expectedResponseFields });
 const unresolvedQuestions = normalizeQuestions(response.unresolvedQuestions, response);
 if (!Array.isArray(response.actions) || response.actions.length < 1 || response.actions.length > maxActions) rejectResponse('INVALID_ACTION_COUNT', { response, expectedFields: [...REPLACE_ACTION_KEYS] });
 const actions = response.actions.map((action) => {
  if (!isRecord(action)) rejectResponse('ACTION_NOT_OBJECT', { response, expectedFields: [...REPLACE_ACTION_KEYS] });
  if (!hasOnlyKeys(action, REPLACE_ACTION_KEYS)) rejectResponse('UNEXPECTED_ACTION_FIELD', { response, expectedFields: [...REPLACE_ACTION_KEYS], unexpectedFields: unexpectedKeys(action, REPLACE_ACTION_KEYS) });
  if (!Object.hasOwn(action, 'kind') || !Object.hasOwn(action, 'targetEntryId') || !Object.hasOwn(action, 'replacementText')) rejectResponse('MISSING_ACTION_FIELD', { response, expectedFields: [...REPLACE_ACTION_KEYS] });
  if (action.kind !== 'replace') rejectResponse('WRONG_ACTION_KIND', { response, expectedFields: [...REPLACE_ACTION_KEYS] });
  if (typeof action.targetEntryId !== 'string' || action.targetEntryId.length === 0) rejectResponse('INVALID_TARGET_ENTRY_ID', { response, expectedFields: [...REPLACE_ACTION_KEYS] });
  if (typeof action.replacementText !== 'string') rejectResponse('INVALID_REPLACEMENT_TEXT', { response, expectedFields: [...REPLACE_ACTION_KEYS] });
  return { kind: 'replace' as const, targetEntryId: action.targetEntryId, replacementText: action.replacementText };
 });
 return { actions, unresolvedQuestions };
}

function normalizeSuccessorReplacement(
 input: SemanticPlannerInput,
 response: unknown,
): Awaited<ReturnType<SemanticEditPlanner['plan']>> {
 const expectedResponseFields = ['replacementText', 'unresolvedQuestions'];
 if (!isRecord(response)) rejectResponse('RESPONSE_NOT_OBJECT', { response, expectedFields: expectedResponseFields });
 if (!hasOnlyKeys(response, SUCCESSOR_RESPONSE_KEYS)) rejectResponse('UNEXPECTED_RESPONSE_FIELD', { response, expectedFields: expectedResponseFields, unexpectedFields: unexpectedKeys(response, SUCCESSOR_RESPONSE_KEYS) });
 if (!Object.hasOwn(response, 'replacementText') || !Object.hasOwn(response, 'unresolvedQuestions')) rejectResponse('MISSING_RESPONSE_FIELD', { response, expectedFields: expectedResponseFields });
 if (typeof response.replacementText !== 'string' || response.replacementText.trim().length === 0) rejectResponse('INVALID_REPLACEMENT_TEXT', { response, expectedFields: expectedResponseFields });
 const unresolvedQuestions = normalizeQuestions(response.unresolvedQuestions, response);
 if (!input.target) throw new Error('SUCCESSOR_TARGET_REQUIRED');
 return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: response.replacementText }], unresolvedQuestions };
}

function normalizeFidelityModify(
 input: SemanticPlannerInput,
 response: unknown,
): Awaited<ReturnType<SemanticEditPlanner['plan']>> {
 if (!isRecord(response)) rejectResponse('RESPONSE_NOT_OBJECT', { response, expectedFields: ['actions', 'unresolvedQuestions'] });
 if (!hasOnlyKeys(response, FIDELITY_RESPONSE_KEYS)) rejectResponse('UNEXPECTED_RESPONSE_FIELD', { response, expectedFields: ['actions', 'unresolvedQuestions'], unexpectedFields: unexpectedKeys(response, FIDELITY_RESPONSE_KEYS) });

 const unresolvedQuestions = normalizeQuestions(response.unresolvedQuestions, response);
 if (!Array.isArray(response.actions) || response.actions.length !== 1) rejectResponse('INVALID_ACTION_COUNT', { response });
 const action = response.actions[0];
 if (!isRecord(action)) rejectResponse('ACTION_NOT_OBJECT', { response });
 if (!hasOnlyKeys(action, REPLACE_ACTION_KEYS)) rejectResponse('UNEXPECTED_ACTION_FIELD', { response, unexpectedFields: unexpectedKeys(action, REPLACE_ACTION_KEYS) });
 if (action.kind !== 'replace') rejectResponse('WRONG_ACTION_KIND', { response });
 if (action.targetEntryId !== input.target?.entryId) rejectResponse('WRONG_TARGET_ENTRY_ID', { response });
 if (action.replacementText !== input.fidelity?.replacementBlock) rejectResponse('ALTERED_REPLACEMENT_TEXT', { response });

 return {
  actions: [{
   kind: 'replace',
   targetEntryId: input.target.entryId,
   replacementText: input.fidelity.replacementBlock,
  }],
  unresolvedQuestions,
 };
}

export function createProductionSemanticPlanner(runtime: ProductionModelRuntime): SemanticEditPlanner {
 const fidelityInput = (input: SemanticPlannerInput) => input.intent.intent === 'MODIFY' && input.fidelity?.replacementBlock !== undefined;
 const successorInput = (input: SemanticPlannerInput) => input.context?.successorCompositeTarget === true;
 return {
  preflight(input) {
   if (successorInput(input) || !fidelityInput(input)) return undefined;
   return runtime.preflightFidelityModify(FIDELITY_MODIFY_PROMPT, buildFidelityModifyPayload(input), FIDELITY_MODIFY_OUTPUT);
  },
  async plan(input) {
   let response: unknown;
   const successor = successorInput(input);
   const fidelityModify = !successor && fidelityInput(input);
   const conceptualRevision = input.intent.intent === 'CONCEPTUAL_REVISION';
   const maxConceptualActions = successor ? 1 : 3;
   const conceptualContract = conceptualRevision ? conceptualOutput(maxConceptualActions) : undefined;
   const fidelityPayload = fidelityModify ? buildFidelityModifyPayload(input) : undefined;
   if (fidelityPayload) runtime.preflightFidelityModify(FIDELITY_MODIFY_PROMPT, fidelityPayload, FIDELITY_MODIFY_OUTPUT);
   try {
    response = successor
     ? await runtime.structured(SUCCESSOR_REPLACEMENT_PROMPT, { operation: 'CREATE_SUCCESSOR_REPLACEMENT', instruction: input.instruction, constraints: input.constraints, documentSha256: input.documentSha256, context: input.context }, SUCCESSOR_REPLACEMENT_OUTPUT)
     : fidelityPayload
      ? await runtime.structured(FIDELITY_MODIFY_PROMPT, fidelityPayload, FIDELITY_MODIFY_OUTPUT)
      : await runtime.structured(plannerPrompt(maxConceptualActions), {
        intent: input.intent,
        instruction: input.instruction,
        target: input.target,
        sourceEntryIds: input.sourceEntryIds,
        destinationEntryId: input.destinationEntryId,
        position: input.position,
        constraints: input.constraints,
        fidelity: input.fidelity,
        documentSha256: input.documentSha256,
        context: input.context,
        sourceContext: input.sourceContext,
        destinationContext: input.destinationContext,
       }, conceptualContract);
   } catch (error) {
    rejectResponse('MODEL_RESPONSE_ERROR', { response }, error, 'runtime');
   }

   if (successor) return normalizeSuccessorReplacement(input, response);
   if (fidelityModify) return normalizeFidelityModify(input, response);
   if (conceptualRevision) return normalizeConceptualRevision(input, response);
   return response as Awaited<ReturnType<SemanticEditPlanner['plan']>>;
  },
 };
}
