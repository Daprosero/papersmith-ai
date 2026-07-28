# Exploration: Paper Proposal V2 Functional Repair

## Scope and constraints

This audit covers the production Paper Proposal V2 path only. It does not modify source proposals, proposal infrastructure, guard/publication infrastructure, or managed artifacts. The acceptance fixture must copy `proposals/research-concept-r01.md` byte-for-byte into a temporary workspace and publish only there.

The repository CodeGraph MCP/CLI was not available through the supplied executor tools, so structural inspection used targeted repository reads/searches after the injected skills were loaded.

## Reconstructed request path

1. `.pi/skills/paper-proposal/SKILL.md` requires a single user-facing `paper_proposal_v2_execute` call for normal execution. Exact-block semantic MODIFY must pass only `sourceFilename` and the complete instruction, retaining both blocks byte-for-byte; it must not pass entry IDs or patch fields.
2. `.pi/extensions/proposal-workspace.ts` registers the production `paper_proposal_v2_execute` tool. The production boundary therefore needs to preserve the skill contract rather than accept caller-composed patches.
3. `PaperProposalV2Orchestrator.execute` resolves intent, validates the managed source filename/marker, loads SHA-bound derived state, rejects ambiguity before planning, resolves the semantic target (including the adjacent-equation composite fallback), and builds bounded local context.
4. For semantic MODIFY, `buildEditPlan` invokes the supplied planner exactly once through `modelCall('planner', ...)`. It expects one `replace` action, the resolved target entry ID, and non-empty replacement text; fidelity-constrained requests additionally require byte-identical `replacementText`.
5. `ProductionModelRuntime.structured` sends the context as one provider request, extracts text, accepts plain JSON or a JSON code fence, and rejects empty/non-JSON output. `createProductionSemanticPlanner` wraps the response for fidelity MODIFY and validates the response object, allowed keys, question array, exactly one action, action shape, action kind, target ID, and exact replacement bytes.
6. `PaperProposalV2Orchestrator.publish` enforces the effective operation profile and no-unresolved-question/no-empty-plan gates, compiles the plan into patches, validates the candidate, and calls `ProposalWorkspaceAdapter.publishSuccessor`.
7. `ProposalWorkspaceAdapter` revalidates profile, budgets, source identity, patch count, and successor naming before guard preflight/authorization and `derive_successor`. It rereads the target and source, verifies hashes and bytes, completes the guarded operation, and returns publication evidence. The orchestrator then rebuilds/commits derived state and saves the receipt.

## Hypothesis audit: `INVALID_SEMANTIC_EDIT_PLAN`

The hypothesis is **partly refuted for the current fidelity-production path**. A real production adapter response cannot reach the generic `INVALID_SEMANTIC_EDIT_PLAN` check when it violates the fidelity contract: `production-planner-adapter.ts` rejects it first with `ProductionPlannerResponseError`, carrying `PRODUCTION_PLANNER_RESPONSE_REJECTED`, a diagnostic code, and `{modelCalls: 1, plannerCalls: 1}`. `buildEditPlan` catches that specific error and converts it to an empty plan with a diagnostic, after which publication is blocked by `NO_MUTATION_PLAN`/the surrounding publish gate. The existing `tests/paper-proposal-v2-production-modify.test.mjs` verifies one provider call, one planner call, zero mutations, no successor, and unchanged source for zero/two/wrong-action/wrong-target/altered/non-JSON responses.

The hypothesis remains **valid as a contract risk** in two places:

- The generic fake/in-process planner contract is intentionally weaker. A fake planner returns a partial `EditPlan` fragment directly; `buildEditPlan` performs the one-action/target/non-empty/fidelity checks itself. This is why fake-planner tests can exercise `INVALID_SEMANTIC_EDIT_PLAN` directly while production fidelity failures use adapter diagnostics.
- `createProductionSemanticPlanner` returns non-fidelity responses without schema normalization. That is relevant to other semantic planner modes, although the requested P0 is fidelity-constrained exact-block MODIFY. Any repair must not accidentally make production output permissive or allow a malformed response to become publishable.

One observability weakness is visible: the adapter diagnostic is retained in the `planned` result but `publish` does not expose `plannerDiagnostic` in the returned blocked result. Runtime counters (`totalModelCalls`/`totalPlannerCalls`) are incremented by `modelCall`, while the public result counters are manually carried. The P0 must assert both provider call trace and returned result counters/diagnostic visibility, not infer calls from a requested profile.

## P0 feasibility

P0 is feasible without touching real proposals. `tests/paper-proposal-v2-production-modify.test.mjs` already demonstrates the safe shape:

- create a temporary root and `proposals/` directory;
- copy the repository `proposals/research-concept-r01.md` with `copyFile`, rather than constructing a synthetic document or request;
- construct the real guard, workspace tool, `ProposalWorkspaceAdapter`, `ProductionModelRuntime`, and `PaperProposalV2Orchestrator`;
- register one provider-equivalent faux model through `aiCompat.registerFauxProvider`;
- run the real provider protocol through `runtime.withContext`, with the orchestrator request containing only `sourceFilename` and the complete exact-block instruction;
- capture the JSON payload sent to the provider and return a provider-equivalent structured response containing exactly one `ReplaceAction` (`kind: replace`) whose target is the supplied composite target ID and whose replacement is the supplied fidelity block;
- assert exactly one provider/model/planner call, exactly one compiled patch, unchanged `r01`, temporary `r02` publication, preserved bytes before/after the target, committed derived state, and receipt evidence;
- assert the repository’s real `proposals/research-concept-r01.md` hash is unchanged and no real successor is created.

The supplied current production test uses a small synthetic two-equation fixture, so the missing acceptance slice is the same real-adapter trace against a byte-identical temporary copy of the real research proposal and the exact adjacent-equation P0 instruction. It must not pass `selectedEntryId`, `literalContent`, a planner object, or manually-built patch data.

## Existing operation coverage to preserve

Existing V2 suites cover the skill request boundary, semantic MODIFY, ambiguity/no-planner behavior, literal INSERT, literal/adaptive MOVE and COPY, DELETE and semantic cleanup, conceptual revision with tutor/reviewer budgets, deliberate/review read-only behavior, production smoke, restart/persistence, derived-state recovery, receipts, consistency/self-audit, concurrency, and representation/adapter boundaries. Tutor and reviewer contracts are separately validated in `paper-proposal-v2-tutor-reviewer.test.mjs`. A repair should add the P0 regression and retain a full existing-operation validation run; it should not invoke tutor, reviewer, maintenance, or extra planner calls for this exact semantic MODIFY.

## Exact affected files

Likely implementation/test surface:

- `.pi/extensions/paper-proposal-v2/production-planner-adapter.ts` — production response wrapper and diagnostic contract.
- `.pi/extensions/paper-proposal-v2/edit-planner.ts` — generic semantic plan validation and propagation of production diagnostics.
- `.pi/extensions/paper-proposal-v2/orchestrator.ts` — blocked-result observability and publication gate behavior.
- `.pi/extensions/paper-proposal-v2/production-runtime.ts` — provider-equivalent JSON parsing boundary, only if the repair changes parsing/schema handling.
- `.pi/extensions/paper-proposal-v2/runtime-metrics.ts` — only if counters need a proven diagnostic/event metric rather than existing call counters.
- `tests/paper-proposal-v2-production-modify.test.mjs` — production contract/P0 regression coverage.
- `tests/paper-proposal-v2-semantic-modify-e2e.test.mjs` and the existing operation suites — regression validation; avoid modifying managed proposal files.

No change is justified yet to `proposal-workspace.ts`, guard logic, publication infrastructure, role adapters, or the managed proposal itself.

## Minimal coherent repair direction

Keep the single-planner/single-ReplaceAction invariant at both boundaries. Make production normalization and generic plan validation converge on one explicit, observable blocked result: preserve `{modelCalls: 1, plannerCalls: 1}`, expose the adapter diagnostic in the result (without publishing), and ensure malformed production responses cannot be silently converted into a publishable empty/partial plan. Add the real-copy P0 acceptance test through the skill-shaped request and ProductionPlannerAdapter/provider-equivalent protocol, then run the existing all-operation, tutor/reviewer, and self-audit suites. Do not add tutor/reviewer/maintenance calls or alter successor/guard mechanics.

## Risks and open questions

- The exact acceptance gap may be observability rather than execution: current tests already prove the P0 mechanics on a synthetic fixture, while the requested real proposal copy primarily proves parser/target resolution against production bytes.
- Generic non-fidelity production planner responses remain an unnormalized surface and need an explicit scope decision; broad normalization could affect conceptual revision and adaptive MOVE/COPY contracts.
- The current orchestrator catch path returns `modelCalls: 0` for caught planner/build failures in several branches; changing this broadly could alter existing operation expectations. Limit any counter repair to the typed production rejection path and add assertions for invalid variants.
- No runtime test was executed in this explore phase; conclusions are from source and test inspection.
