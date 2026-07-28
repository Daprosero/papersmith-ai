# Proposal: Paper Proposal V2 Token Efficiency

## Intent

Reduce token and payload overhead in the production `paper_proposal_v2_execute` path for exact-block semantic `MODIFY`, without weakening document verification, publication guards, receipts, consistency audits, or SelfAudit evidence.

The change should make the public result compact and predictable, remove avoidable duplication from the planner request, and prevent oversized MODIFY requests before invoking the model. Internal evidence remains available to the runtime for correctness and recovery; it is not exposed wholesale in the public success or error response.

## Product outcome

Callers receive a small, stable success or error envelope that communicates the operation outcome, receipt, manifest, audit/recovery status, and actionable metadata. They do not receive repeated full-document bytes, compiled candidates, derived document state, workspace read details, or planner context unless a narrowly defined diagnostic contract requires it.

Exact-block MODIFY continues to be one bounded planner/model operation when planning is allowed. Its planner input contains each target and replacement block once, uses only the required local document context, and has no dependency on session history. Requests that exceed the configured MODIFY input budget are rejected before model invocation.

## Scope

### 1. Compact public envelopes

- Define compact, explicit public success and error envelopes for `paper_proposal_v2_execute`.
- Preserve outcome metadata needed by callers: operation/status, receipt reference or summary, manifest/publication result, consistency-audit status, SelfAudit status, and recovery or next-action guidance when applicable.
- Keep publication bytes, candidate bytes, derived state, workspace reads, planner context, hashes, and verification material internal where they are required for verification, rebuild, auditing, or recovery.
- Ensure errors remain actionable and distinguish validation, budget-block, model, publication, recovery, and audit failures without leaking broad internal structures.
- Treat envelope shape as a compatibility surface; inventory and update affected callers/tests in the specification and implementation phases rather than silently removing fields.

### 2. Exact-MODIFY planner payload deduplication

- For exact-block semantic `MODIFY`, construct a fidelity-specific planner payload in which the target and replacement occur exactly once each.
- Retain the information necessary to resolve the selected target, enforce byte identity, and produce the single replace action.
- Scope payload changes to this exact-MODIFY path; do not alter semantics for other operations until separately justified.
- Preserve byte-for-byte matching and the existing requirement that the planner cannot broaden the requested replacement.

### 3. Configurable MODIFY budget and invocation policy

- Add a configurable input budget for `MODIFY`, with a documented unit and deterministic accounting rule.
- Perform budget accounting before model invocation and return a typed budget-block error when the request would exceed the limit.
- Keep the exact-MODIFY path to a single model/planner call when it is not blocked.
- Build planner input from local resolved document context only; do not use session history as an implicit source of context or as a fallback when the local budget is exceeded.
- Bound or narrow local context for exact-block fidelity operations while retaining target identity and any context required for correctness.
- Make the effective budget and accounting outcome observable in internal evidence and, where appropriate, compact metadata, without returning the full planner payload.

### 4. P0 measurement and non-regression evidence

- Add a P0 temporary-replacement measurement slice before or alongside rollout to establish baseline and post-change measurements for:
  - public response size/token footprint;
  - exact-MODIFY planner input size and field occurrence counts;
  - model invocation count;
  - budget-block behavior before invocation;
  - success/error envelope shape and latency where measurable.
- Use temporary replacement instrumentation or fixtures only as measurement scaffolding; keep it clearly bounded and removable, and do not change proposal document content as part of this change.
- Capture non-regression evidence that internal candidate/publication equality, source reread/hash checks, guard authorization/completion, receipt creation, derived-state rebuild, consistency audit, SelfAudit, recovery behavior, exact-block semantics, and existing operation behavior remain intact.
- Include negative evidence for session-history independence and over-budget requests: no model call occurs when blocked, and no hidden history is consulted.

## Affected areas

- Public result construction and tool serialization in the Paper Proposal V2 extension.
- Orchestrator success/error mapping and publication result shaping.
- Publication adapter/internal evidence flow, retaining bytes through verification and derived-state rebuild.
- Exact-MODIFY intent/context/planner payload construction.
- Runtime configuration and budget accounting for MODIFY.
- Tests, fixtures, and measurement instrumentation covering response contracts, payload deduplication, call count, budget blocking, and publication/audit invariants.
- Existing callers that inspect broad result fields may require an explicit compatibility adjustment; proposal/spec work must identify them before implementation.

## Non-goals

- Do not weaken, remove, or bypass internal document verification, hash/byte comparisons, publication guards, receipts, consistency audits, SelfAudit, recovery state, or publishing evidence.
- Do not modify proposal document content or exact-block matching semantics.
- Do not hide evidence from the runtime; retain it internally for verification, auditing, rebuild, and recovery.
- Do not add tutor/reviewer calls or change role-file behavior for exact-MODIFY.
- Do not redesign planner behavior for unrelated operations.
- Do not make session history a required or optional hidden context source.
- Do not claim token savings without the P0 measurements and non-regression evidence.

## Business and technical rules

1. Correctness and auditability take precedence over public payload minimization.
2. Internal evidence may be retained longer than it is exposed, but must remain available until all dependent checks and state rebuilds complete.
3. Exact-MODIFY must remain deterministic in its input construction and must account for every budgeted input before invocation.
4. A budget block is a pre-invocation terminal result for that request, not a model-assisted clarification.
5. A compact envelope must never convert an ambiguous, interrupted, inconsistent, or failed SelfAudit into apparent success.
6. Configuration must have a safe, documented default and reject invalid budget configuration deterministically.

## Risks and mitigations

- **Caller compatibility:** existing consumers may depend on broad fields. Mitigate with an inventory, explicit envelope contract, migration notes, and contract tests.
- **Evidence regression:** early redaction could break publication equality or derived-state rebuild. Mitigate by separating internal and public result types and retaining evidence through all checks.
- **Planner correctness:** overly aggressive context reduction or deduplication could alter target/action decisions. Mitigate with byte-exact fixtures, target-resolution coverage, and before/after behavior evidence limited to exact-MODIFY.
- **Budget ambiguity:** inconsistent token/byte accounting could produce surprising blocks. Mitigate with one documented accounting function, boundary tests, effective-budget telemetry, and deterministic configuration validation.
- **Measurement distortion:** temporary instrumentation may affect payloads or behavior. Keep instrumentation out of proposal documents and production semantics, isolate it behind tests/diagnostics, and compare with instrumentation-off behavior.
- **Operational diagnosis:** compact errors may omit useful debugging detail. Preserve internal structured evidence and return stable error categories plus recovery/next-action guidance.

## Rollback

Rollback must be configuration- and release-reversible without changing managed proposal documents. Restore the prior public-result adapter and planner-payload path only after confirming that internal verification artifacts and receipts remain readable. If budget configuration causes unexpected blocks, temporarily raise or disable the new threshold only through the documented configuration mechanism; do not bypass pre-invocation accounting or invoke the model with an over-budget request. Temporary measurement scaffolding must be independently removable.

## Success criteria

- Successful and failed executions return the documented compact envelopes; full managed bytes, compiled candidates, derived state, workspace read details, and planner context are not serialized in normal public results.
- Internal publication evidence remains present through candidate/publication comparison, derived-state rebuild, receipt creation, consistency audit, SelfAudit, and recovery handling.
- Exact-MODIFY planner payload tests prove the target and replacement each occur once, with no session-history dependency.
- Exact-MODIFY performs at most one model call, and an over-budget MODIFY performs zero model calls with a typed pre-invocation budget-block result.
- Budget configuration and boundary behavior are deterministic and documented.
- P0 measurements show the intended response/input footprint reduction and provide model-call and budget-block evidence.
- Non-regression evidence passes for exact-block semantics, publication integrity, audits, receipts, recovery, and unaffected operation paths.
- No proposal document content is changed by this work.

## Delivery boundary

This proposal covers the public contract, exact-MODIFY input/budget policy, and P0 evidence needed to validate the change. Detailed envelope schemas, compatibility decisions, budget units/defaults, measurement design, and file-level implementation tasks belong in the subsequent specification, design, and task phases. No code implementation is part of this phase.
