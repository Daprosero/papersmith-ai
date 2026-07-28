# Exploration: Paper Proposal V2 Token Efficiency

## Scope and evidence

Read-only inspection of the production Paper Proposal V2 path for exact-block semantic `MODIFY`. No source, tests, proposals, or runtime configuration were changed. CodeGraph was unavailable through the supplied executor tools; targeted searches and reads were used after loading the injected skills. Existing context in `openspec/changes/paper-proposal-v2-functional-repair/explore.md` was read before this audit.

## Executive finding

The productive path does **not** invoke tutor or reviewer for an exact-block MODIFY, and the role markdown files are not loaded by the production runtime. It performs one planner/model call. The strongest cost defect is the returned tool payload, not an extra role call: the success result exposes full publication bytes and several other full-document/derived structures, and `proposal-workspace.ts` deliberately places complete managed bytes in read-result `details`.

The model input is also larger than necessary because the single planner request serializes the full `SemanticPlannerInput` plus a long planner system prompt. Exact-block MODIFY duplicates user-supplied blocks in the instruction, `intent.fidelity`, target composite data, and local context. This is input/context cost; it is separate from the oversized tool output.

## Request-to-response path

1. `.pi/extensions/proposal-workspace.ts` registers exactly one `paper_proposal_v2_execute` tool. Its handler runs `productionRuntime.withContext(...)`, calls `orchestrator.execute({...params})`, then returns both `content: JSON.stringify(result)` and `details: result`.
2. `paper-proposal-v2/orchestrator.ts:PaperProposalV2Orchestrator.execute` resolves intent, validates the managed filename/marker, loads the SHA-bound `DocumentState`, resolves an exact composite target through `target-resolver.ts`, materializes it, and calls `buildContext`.
3. `context-builder.ts:buildContext` includes the target, neighboring entries, symbol-definition entries, up to 8 fragments and up to 32,000 local bytes, plus nearby symbols and direct references.
4. `edit-planner.ts:buildEditPlan` treats MODIFY as semantic and calls the planner once through `modelCall('planner', ...)`.
5. `production-planner-adapter.ts:createProductionSemanticPlanner` sends one `ProductionModelRuntime.structured` request. For fidelity MODIFY it supplies the structured-output schema requiring exactly one replace action and byte-identical replacement text.
6. `production-runtime.ts:structured` sends one user text message containing `JSON.stringify(payload)`, with `PLANNER_PROMPT` as system prompt and one required output tool. No tutor/reviewer call occurs on this branch.
7. `orchestrator.ts:publish` compiles/validates the candidate and calls `ProposalWorkspaceAdapter.publishSuccessor`.
8. `paper-proposal-v2/proposal-workspace-adapter.ts:publishSuccessor` performs guard begin/preflight/authorize, derives the successor, rereads the target and source for hash/byte checks, and returns `publishedBytes: Buffer` from the reread.
9. `orchestrator.ts:publish` compares `published.publishedBytes` with the compiled candidate, rebuilds derived state, saves a receipt, and returns a broad object containing `published`, `derived`, `plan`, `compiled`, `validation`, and `context`. The production tool JSON-stringifies that entire object.

## Cost split and ranked causes

### 1. Very likely: oversized output payload (highest confidence)

`PublishedSuccessor` explicitly contains `publishedBytes`. The adapter obtains it from `proposal-workspace.ts` read `details.managedBytes`; the same read details also travel in `published.workspaceEvidence.read` and `published.workspaceEvidence.source`. Therefore a successful result can serialize the complete document multiple times (Buffer JSON form, typically `{type:"Buffer",data:[...]}`).

The result also contains `compiled.candidate` (the complete candidate document string), `derived` (a rebuilt `DocumentState` including `documentBytes` and indexes), and `context` (bounded fragments). `JSON.stringify(result)` exposes all of these to the caller. This is directly evidenced by the handler and return shape, not an inference from role prompts. It can dominate observed output tokens even when the model completion itself is tiny.

### 2. Likely: planner input duplicates exact-block content

`intent-resolver.ts:fidelityConstraints` extracts both blocks from the complete instruction. `buildContext` receives `intent.fidelity`, and `production-planner-adapter.ts` serializes `instruction`, `target`, `constraints`, `fidelity`, `documentSha256`, and `context` together. The original blocks therefore appear in the instruction and fidelity fields; the target composite carries `exactProvidedText`, and context fragments may carry the source block. This increases provider input tokens while preserving only one model call.

### 3. Likely but bounded: broad local context for a fidelity operation

`buildContext` can include neighboring entries and symbol-definition entries, up to 8 fragments/32,000 bytes. For an exact replacement whose semantics are already byte-constrained, much of that context is unnecessary for the planner, although target IDs and document identity remain necessary. This is a candidate optimization, not yet proof that the observed proposal reached the 32 KB limit.

### 4. Possible: fixed planner prompt/schema overhead

`production-planner-adapter.ts:PLANNER_PROMPT` is a long multi-operation prompt despite this request being fidelity MODIFY. The required structured-output schema is appropriately bounded, but its description and schema still add fixed input overhead. A MODIFY-specific prompt/schema path is a bounded candidate.

### Not supported by evidence: tutor/reviewer/role-file loading

The production extension constructs tutor and reviewer adapters, but exact MODIFY branches directly into `buildEditPlan`; only conceptual revision, deliberate, and review branches call roles. `.pi/subagents/paper-proposal-{tutor,reviewer}.md` are explicitly manual/reference contracts. No filesystem load of those files appears in the V2 runtime. Role loading is therefore not a cause for this operation. General host/system prompt overhead outside this repository is not measurable from the inspected path.

## Semantic/publication constraints for any fix

Do not remove the adapter reread, hash comparison, source verification, guard completion, derived-state rebuild, receipt, or SelfAudit/consistency guarantees. `publishedBytes` is currently used by `orchestrator.ts` to prove the adapter result equals the compiled candidate and to rebuild derived state. The smallest safe optimization is to retain bytes internally for verification/rebuild but return a redacted/minimal public result, or split internal publication evidence from the user-facing response. Do not change the proposal bytes or exact-block matching semantics.

## Recommended smallest next SDD phase

Proceed to **proposal**, focused only on a bounded response-shaping change: preserve internal `publishedBytes` and all publication checks, but return a compact success envelope (metadata, receipt, manifest/audit status) instead of full `published`, `derived`, `compiled.candidate`, workspace read details, and context. In the proposal, separately record a follow-up/measurement slice for exact-MODIFY planner input reduction (remove duplicated fields or use a fidelity-specific payload) and context narrowing. Do not combine model-input redesign with publication semantics in the first implementation slice.

## Risks

- Redacting fields may break existing callers/tests that inspect `result.published`, `result.compiled`, or `result.context`; inventory and compatibility decisions are required.
- Returning only hashes without retaining internal bytes could weaken the existing candidate/publication equality proof; internal bytes must remain until verification and derived rebuild finish.
- Context/prompt reduction can affect planner target/action correctness if applied beyond fidelity MODIFY; scope it strictly and add byte-exact regression coverage.
- No runtime benchmark was executed in this read-only phase; payload dominance is source-backed but should be measured in the proposal/spec phase.
