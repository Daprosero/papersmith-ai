import type { TutorAdapter } from './tutor-adapter.js';
import { ProductionModelRuntime } from './production-runtime.js';

const TUTOR_PROMPT = `You are the Paper Proposal V2 tutor. Return JSON only with decision, summary, mathematicalIssues, notationIssues, assumptionIssues, requiredRevisions, unresolvedQuestions, riskLevel, affectedEntryIds, and optional proposedAlternative. Decisions are ACCEPT, ACCEPT_WITH_REVISIONS, PROPOSE_ALTERNATIVE, NEEDS_CLARIFICATION, or REJECT_WITH_REASON. Assess only supplied bounded context. Do not read files, calculate offsets or SHA values, publish, or alter a plan. affectedEntryIds must be a subset of supplied fragment entry IDs.`;

export function createProductionTutorAdapter(runtime: ProductionModelRuntime): TutorAdapter {
 return {
  async assess(input) {
   return await runtime.structured(TUTOR_PROMPT, input) as any;
  },
 };
}
