import type { ReviewerAdapter } from './reviewer-adapter.js';
import { ProductionModelRuntime } from './production-runtime.js';

const REVIEWER_PROMPT = `You are the Paper Proposal V2 reviewer. Return JSON only with decision, scientificCoherence, scopeCompliance, unsupportedClaims, referenceRisks, notationRisks, requiredChanges, unresolvedQuestions, and riskLevel. Decisions are APPROVE, APPROVE_WITH_CHANGES, BLOCK, or NEEDS_CLARIFICATION. Review only supplied bounded context and candidate plan. Do not read files, publish, modify the plan, or expand scope.`;

export function createProductionReviewerAdapter(runtime: ProductionModelRuntime): ReviewerAdapter {
 return {
  async review(input) {
   return await runtime.structured(REVIEWER_PROMPT, input) as any;
  },
 };
}
