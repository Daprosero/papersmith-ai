# Design: Paper Proposal V2 Token Efficiency

## Architecture decision

Split the current broad execution result into two layers:

1. **Internal execution evidence** remains available only within the orchestrator until publication verification, derived-state rebuild, receipt persistence, consistency audit, SelfAudit, and recovery handling complete.
2. **Public execution envelope** is projected only at the extension/tool boundary and contains stable outcome metadata rather than document bytes, compiled candidates, workspace reads, planner context, hashes, or derived document state.

The exact-block semantic `MODIFY` path receives a fidelity-specific planner request builder. It constructs one bounded local request and invokes the existing planner/model at most once. All other operation payloads retain their current construction and semantics.

## Public-envelope compatibility policy

Introduce explicit versioned public result types for `paper_proposal_v2_execute`:

- `success`: operation, status, compact receipt reference/summary, manifest/publication summary, consistency-audit status, SelfAudit status, and recovery/next-action guidance when applicable.
- `error`: operation, status, stable error category, actionable message, recovery/next-action guidance, and compact safe metadata.

Stable error categories are: `validation`, `budget_block`, `model`, `publication`, `recovery`, and `audit`.

The envelope must not serialize full managed or candidate bytes, buffers, hashes, workspace evidence/read details, planner payload/context, plan internals, validation internals, or rebuilt derived state. Internal evidence is not discarded or redacted until dependent correctness operations finish.

Because the current broad result is observable, this is a compatibility change. Implementation must inventory direct result consumers and tests, migrate in-repository consumers to the envelope, and add contract tests that assert both required retained fields and prohibited broad fields. The tool must continue to return the same host-level `content`/`details` transport shape, but both values represent the compact public envelope rather than the internal execution object. No compatibility alias should expose legacy evidence fields; callers needing diagnostics use the bounded receipt/recovery information.

## Exact-MODIFY request construction

Add a dedicated fidelity-MODIFY payload builder after target resolution and before planner invocation. Its input is the resolved target identity, replacement block, document identity, and strictly required local context.

The builder will:

- retain the resolved entry/target identity and document SHA needed to bind the request to the loaded document;
- include the original target block exactly once and replacement block exactly once;
- avoid serializing the original instruction, fidelity constraints, target composite text, and context fragments in combinations that repeat either block;
- use only bounded local context needed to identify the target and preserve the one-replace-action constraint; omit broad neighbor/symbol/fragment context unless it is explicitly required by the fidelity contract;
- use a MODIFY-specific system prompt and structured-output schema requiring exactly one replacement action with byte-identical replacement content;
- not read, accept, or fall back to session history.

The planner response is validated by the existing exact-block and publication safeguards. The specialized payload narrows only exact-block semantic MODIFY; conceptual MODIFY and every other operation continue through the existing generic planner path.

## Pre-invocation budget policy

Define a runtime configuration value `modifyInputBudget` with a documented safe default and a single unit: UTF-8 bytes of the complete provider-bound planner input. The accounting function deterministically sums:

- the fidelity-MODIFY system prompt encoded as UTF-8;
- the serialized structured request payload encoded as UTF-8;
- the serialized required output schema/tool definition encoded as UTF-8.

The same function is used for configuration validation, runtime decision-making, diagnostic evidence, and boundary tests. Configuration must be a positive finite integer; absent configuration uses the safe default, and invalid values fail deterministic configuration validation rather than silently falling back.

After payload construction and before `ProductionModelRuntime.structured`, compare the effective input size to `modifyInputBudget`. If it exceeds the budget, return a typed `budget_block` terminal result with configured/effective budget metadata and actionable guidance. Do not call the model, consult session history, issue a clarification, begin publication, or create a misleading success receipt. At or below the limit, invoke the planner exactly once.

Internal execution evidence records the configured budget, measured input size, accounting unit/version, selected payload path, and model-call count. The public envelope may expose only safe compact budget metadata needed to explain a block; it never exposes the payload itself.

## Execution and recovery flow

1. Resolve and validate the request, managed document, and exact target using existing behavior.
2. Construct the fidelity-MODIFY payload and calculate its budget before model invocation.
3. On budget block, project the typed compact error and terminate without model or publication activity.
4. On allowed input, make one planner/model call and validate the bounded replacement action.
5. Run the existing candidate compilation, adapter reread/hash/byte equality checks, guard authorization/completion, derived-state rebuild, receipt persistence, consistency audit, SelfAudit, and recovery handling using internal evidence.
6. Only after all terminal checks complete, project internal outcome to the compact public success/error envelope.

Model, publication, recovery, audit, interrupted, ambiguous, inconsistent, and incomplete-SelfAudit outcomes remain non-successful. Projection must preserve recovery/next-action guidance and must never make a failed or unresolved internal state appear successful. Receipt and manifest summaries remain sufficient to correlate a caller-visible outcome with internal audit/recovery records.

## Measurement and rollout

Add a P0 test/fixture measurement harness, isolated from production proposal content and removable independently. It records baseline and post-change response serialized size, exact-MODIFY provider-bound input size, target/replacement occurrence counts, model-call count, budget-block-before-invocation behavior, and latency when the test runtime can measure it.

Run measurements with instrumentation enabled and validate behavior with it disabled. Report reductions only from captured baseline/post-change evidence. Roll out with the safe default budget and compact envelope contract. Rollback is release/configuration reversible: restore the prior adapter/payload path only after confirming receipt readability and internal verification behavior; unexpected blocks are addressed through the documented budget configuration, never by bypassing pre-invocation accounting.

## Test strategy and acceptance mapping

| Acceptance requirement | Verification |
| --- | --- |
| Compact success/error contract | Contract tests assert required public fields and absence of bytes, candidate, derived state, workspace reads, context, hashes, plan, and validation internals. |
| Caller compatibility | Inventory tests identify current result consumers; migrated callers compile/pass against the explicit envelope. |
| Internal publication integrity | Regression tests prove candidate/publication equality, source reread/hash checks, guard completion, derived rebuild, receipt, audit, SelfAudit, and recovery still receive internal evidence. |
| Target/replacement occur once | Serialized fidelity payload fixtures count one occurrence of each block, including adversarial repeated-text inputs. |
| No session-history dependency | Tests provide no history and conflicting synthetic history; payload and outcome remain determined solely by resolved local inputs. |
| One model call when allowed | Spy/fake runtime asserts exactly one structured planner invocation for an in-budget exact MODIFY. |
| Zero calls when blocked | Boundary tests assert `budget_block`, zero planner/model calls, no publication work, and compact actionable metadata. |
| Deterministic budget | Unit tests cover absent/default, invalid, below/equal/above threshold, UTF-8 multibyte text, and schema/prompt inclusion. |
| Unaffected operations | Regression coverage confirms generic planner payload and behavior for non-fidelity operations remain unchanged. |
| P0 evidence | Measurement fixtures report output/input footprint, occurrence counts, invocation count, block behavior, and available latency before/after. |

## Planned files

- `.pi/extensions/proposal-workspace.ts` — project the compact public envelope in tool `content` and `details`.
- `paper-proposal-v2/orchestrator.ts` — retain internal evidence through terminal checks and return/project a distinct public result only after completion.
- `paper-proposal-v2/production-planner-adapter.ts` — add the fidelity-MODIFY prompt/schema and payload route.
- `paper-proposal-v2/edit-planner.ts` — route exact-block semantic MODIFY through the specialized bounded planner input.
- `paper-proposal-v2/context-builder.ts` — expose a minimal, explicitly bounded fidelity-context construction without changing generic context behavior.
- `paper-proposal-v2/intent-resolver.ts` and/or `target-resolver.ts` — provide only the resolved identity and exact values needed by the dedicated payload builder, avoiding duplicate composite serialization.
- `paper-proposal-v2/production-runtime.ts` — apply pre-invocation accounting at the provider request boundary and expose internal measurement hooks.
- Paper Proposal V2 runtime configuration module — define, validate, and document `modifyInputBudget` and its UTF-8 accounting rule.
- Existing Paper Proposal V2 unit/integration/contract test files plus dedicated measurement fixtures — cover envelopes, budget boundaries, payload occurrences, call counts, and publication/audit non-regression.

Exact test and configuration filenames must be selected from the existing implementation layout during the tasks phase; no proposal document content is modified.
