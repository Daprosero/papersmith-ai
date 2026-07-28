# Design: Paper Proposal V2 Functional Repair

## Goal

Repair the minimum coherent production path for Paper Proposal V2 semantic exact-block `MODIFY` without changing the V2 architecture. The repair makes every planner response—valid or rejected—flow through one strict, observable planner-result contract. It preserves the single semantic planner route, byte-exact fidelity, P0's one provider/model/planner invocation, existing operation modes, and workspace/guard security boundaries.

This design is based on `explore.md`. No proposal or spec artifact is created: the requested change explicitly skips those phases.

## Scope

### In scope

- Production semantic exact-block `MODIFY` planner response normalization and rejection classification.
- Runtime structured-response classification required to surface malformed provider output through the same planner-result contract.
- Generic edit-plan validation and propagation of typed planner rejection details.
- Blocked-result observability: stable reason, planner diagnostic, invocation counters, and zero mutation evidence.
- Production P0 acceptance against a temporary byte-for-byte copy of `proposals/research-concept-r01.md`.
- Invalid-response, tutor/deliberate, conceptual, and existing V2 regression coverage.

### Out of scope / no-go zones

- Do not modify `proposals/research-concept-r01.md`, create a real successor, or mutate any source proposal.
- Do not alter `.pi/extensions/proposal-workspace.ts`, `ProposalWorkspaceAdapter`, document-operation guards, publication authorization, successor naming, derived-state persistence, receipts, or mutation locking.
- Do not add a literal-mode bypass, caller-provided entry ID/patch path, extra planner call, tutor/reviewer call, or fixed multi-agent execution chain for P0.
- Do not broaden non-fidelity semantic operation behavior as part of this repair; adaptive `MOVE`/`COPY`, semantic cleanup, and conceptual revision keep their existing contracts.
- Do not change role files, skills, proposal artifacts, or public publication policy.

## Architecture and data flow

The production route remains:

```text
paper_proposal_v2_execute
  -> PaperProposalV2Orchestrator.execute
  -> intent + managed-source + semantic target resolution
  -> buildEditPlan
  -> modelCall('planner') exactly once
  -> ProductionPlannerAdapter / ProductionModelRuntime
  -> strict planner outcome
  -> publish gate
  -> existing patch validation and ProposalWorkspaceAdapter publication
```

For an exact-block semantic `MODIFY`, the tool request remains restricted to `sourceFilename` plus the complete original instruction. Intent resolution derives fidelity blocks and target semantics; the runtime resolves the real target. No caller input may supply `selectedEntryId`, literal content, a planner fragment, or patch mechanics.

### Strict planner outcome contract

Introduce or formalize an internal discriminated result shared by production normalization and generic planner handling. It represents the completed planner invocation rather than substituting an empty edit plan for an error.

```ts
type PlannerInvocation = Readonly<{ modelCalls: 1; plannerCalls: 1 }>;

type PlannerDiagnostic = Readonly<{
  code: PlannerDiagnosticCode;
  stage: 'runtime' | 'adapter' | 'plan-validation';
}>;

type StrictPlannerOutcome =
  | Readonly<{
      status: 'accepted';
      proposal: PlannerProposal;
      invocation: PlannerInvocation;
    }>
  | Readonly<{
      status: 'rejected';
      reason: 'PRODUCTION_PLANNER_RESPONSE_REJECTED';
      diagnostic: PlannerDiagnostic;
      invocation: PlannerInvocation;
    }>;
```

`PlannerProposal` is the existing planner-fragment shape. The contract is internal; the public result does not expose model prompts, payloads, hashes, offsets, or patches.

For P0 fidelity `MODIFY`, an `accepted` outcome requires all of the following:

1. Top-level object contains only `actions` and optional `unresolvedQuestions`.
2. `unresolvedQuestions` is absent or an array of non-blank strings.
3. `actions` contains exactly one object and only `kind`, `targetEntryId`, and `replacementText`.
4. The action is `replace` and its target equals the runtime-resolved target entry ID.
5. `replacementText` equals `input.fidelity.replacementBlock` byte-for-byte.

Any failed condition yields `rejected`, never a partial plan. A valid unresolved-question response still has exactly one valid replacement action and yields normal `needs-clarification` behavior; it does not publish.

### Runtime and adapter responsibilities

- `ProductionModelRuntime.structured` remains the only provider boundary and makes one `complete` call. It extracts text and parses plain JSON or a JSON fenced payload as today.
- It must expose structured-output failure in a typed/classifiable form (empty response, invalid JSON, aborted/provider error) so the adapter maps it to the strict rejection outcome. It must not retry, repair, or ask another model.
- `createProductionSemanticPlanner` remains the sole production semantic planner adapter. It converts runtime parse/provider failures to `MODEL_RESPONSE_ERROR`; it converts schema/fidelity violations to their specific diagnostic codes. It must not return `response as ...` for the P0 fidelity path.
- Dynamic role activation remains unchanged: P0 activates only the planner. Tutor/reviewer remain conditional responsibilities for their existing deliberate/review and conceptual paths, not a fixed chain.

### Generic edit-plan validation and blocked results

`buildEditPlan` consumes the strict outcome. For `accepted`, it builds the existing `EditPlan` and runs generic semantic checks. For `rejected`, it returns a non-publishable planning result carrying the diagnostic and completed invocation counts; it must not manufacture a valid-looking empty plan that loses the reason.

The orchestrator/publish boundary recognizes the rejected result before generic `NO_MUTATION_PLAN`. It returns:

```ts
{
  status: 'blocked',
  reason: 'PRODUCTION_PLANNER_RESPONSE_REJECTED',
  plannerDiagnostic: { code, stage },
  modelCalls: 1,
  plannerCalls: 1,
  mutations: 0,
}
```

The diagnostic code is observable and stable for tests and clients; raw provider text, exceptions, and internals are not exposed. Generic in-process planners retain their existing `INVALID_SEMANTIC_EDIT_PLAN`, `INVALID_SEMANTIC_EDIT_TARGET`, and fidelity checks. The repair must not collapse those generic errors into production diagnostics or loosen their validation.

`publish` continues to enforce operation budgets, unresolved questions, compiled patch validation, and all existing adapter/guard controls. Rejected planner output never reaches compilation or publication.

## File changes

| File | Change |
|---|---|
| `.pi/extensions/paper-proposal-v2/production-runtime.ts` | Make structured-output failures classifiable at the runtime boundary while preserving one provider call and plain/fenced JSON support. |
| `.pi/extensions/paper-proposal-v2/production-planner-adapter.ts` | Define/produce the strict accepted-or-rejected production planner outcome; retain exact P0 response allowlists and fidelity equality. |
| `.pi/extensions/paper-proposal-v2/edit-planner.ts` | Consume the outcome, preserve invocation counts and diagnostics, and distinguish typed production rejection from generic edit-plan validation failures. |
| `.pi/extensions/paper-proposal-v2/orchestrator.ts` | Return the typed blocked result before the empty-plan gate, with diagnostic and one-call counters; leave publication flow unchanged. |
| `tests/paper-proposal-v2-production-modify.test.mjs` | Add the real-entry temporary-copy P0 path and assert accepted, invalid, and no-mutation outcomes through the real production runtime/adapter route. |
| Existing tutor/deliberate, conceptual, semantic-modify, and full V2 operation suites | Regression-only validation unless an assertion needs adjustment to the now-observable blocked diagnostic. |

`runtime-metrics.ts` is not a planned edit: current `modelCall('planner')` metrics are sufficient unless implementation proves the existing counters cannot represent the completed rejected invocation. If so, add only a minimal metric representation; do not add a second call or role metric.

## Test design

### P0 real-entry acceptance

Extend the production test harness to:

1. Create a temporary root and copy repository `proposals/research-concept-r01.md` byte-for-byte into its `proposals/` directory.
2. Build the real guard, workspace tool, `ProposalWorkspaceAdapter`, `ProductionModelRuntime`, production semantic planner, and orchestrator in that temporary root.
3. Register a faux provider that records the sole provider payload and returns exactly one `replace` action for the runtime-provided composite target and exact fidelity replacement block.
4. Execute the skill-shaped request with only the source filename and the full exact-block instruction.
5. Assert one provider/model/planner call; one patch; a temporary `r02` successor; byte-exact replacement with all external source bytes unchanged; committed derived state and receipt evidence.
6. Assert the repository source hash and bytes are unchanged, and that no repository `r02` exists.

### Invalid production responses

For zero/two actions, wrong action kind, wrong target, altered replacement, non-object/unexpected fields, invalid questions, empty output, invalid JSON, and provider/runtime failure:

- exactly one provider request where a provider response exists;
- `status: 'blocked'` and `reason: 'PRODUCTION_PLANNER_RESPONSE_REJECTED'`;
- the expected stable `plannerDiagnostic.code` and stage;
- `modelCalls: 1`, `plannerCalls: 1`, `mutations: 0`;
- unchanged temporary source and no temporary successor.

### Regression matrix

- Valid planner output with unresolved questions remains `needs-clarification`, contains the valid plan, performs zero mutation, and preserves one planner/model call.
- Existing generic/fake planner tests retain their generic invalid-plan reasons and do not receive production-only diagnostics.
- Tutor and deliberate/review tests prove no planner is activated for those routes and existing role budget behavior is unchanged.
- Conceptual revision tests prove dynamic tutor/reviewer/planner activation and its current budget limits remain unchanged.
- Run the full existing V2 semantic MODIFY, MOVE/COPY, DELETE/cleanup, conceptual, tutor/reviewer, receipts/recovery, consistency/self-audit, concurrency, and representation/adapter suites to detect contract drift.

## Rollout and compatibility

This is an internal repair with no migration and no publication-policy change. The only intentional observable change is that malformed production planner responses become a stable typed blocked result instead of being visible merely as a later empty-plan block. Existing successful P0 output and all source/successor guard behavior remain unchanged. Ship with the targeted production test and full V2 regression suite; if any non-fidelity operation depends on the prior untyped production cast, stop and scope that work separately rather than broadening this repair.

## Risks and mitigations

- **Counter drift in catch paths:** preserve the typed invocation receipt from the completed planner attempt; test public counters rather than only runtime trace.
- **Accidental permissiveness:** enforce allowlists, exactly-one action, resolved target equality, and byte equality before any edit-plan construction.
- **Scope creep into all semantic modes:** limit strict normalization behavior to P0 fidelity MODIFY; leave non-fidelity contract changes for a separate change.
- **Test contaminates managed assets:** only mutate a fresh temporary copy and explicitly hash/check the repository source before and after.
- **Security regression:** do not modify workspace adapter, guard, publication, successor, or derived-state code; rejected paths terminate before those components.
