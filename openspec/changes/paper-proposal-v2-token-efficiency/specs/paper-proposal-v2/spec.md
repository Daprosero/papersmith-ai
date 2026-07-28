# Paper Proposal V2 Token Efficiency Specification

## Purpose

Reduce public response and exact-block semantic `MODIFY` planner-input footprint while preserving Paper Proposal V2 correctness, verification, publication, audit, and recovery guarantees.

## Scope

This change covers compact public execution envelopes, fidelity-`MODIFY` payload deduplication and bounded local context, configurable pre-invocation MODIFY budgets, and P0 measurement/non-regression evidence.

## Token-Efficiency Constraints

- Normal public success and error responses MUST NOT serialize complete managed-document bytes, compiled candidate bytes, derived document state, workspace-read details, planner payloads/context, hashes, or verification evidence.
- Internal evidence MUST remain available until candidate/publication equality checks, source reread and hash checks, publication guards, receipt creation, derived-state rebuild, consistency audit, SelfAudit, and recovery processing have completed.
- For exact-block semantic `MODIFY`, the planner input MUST contain the requested target block exactly once and the requested replacement block exactly once.
- Exact-block semantic `MODIFY` MUST use only resolved local document context; session history MUST NOT be consulted or used as fallback context.
- A MODIFY request exceeding its effective input budget MUST be rejected before model invocation, with zero planner/model calls.
- A permitted exact-block semantic `MODIFY` MUST perform no more than one planner/model call.

## Requirements

### Requirement: Compact Public Execution Envelope

The system MUST return explicit, stable, compact public success and error envelopes from `paper_proposal_v2_execute`.

A success envelope MUST communicate operation and status, receipt reference or summary, manifest/publication outcome, consistency-audit status, SelfAudit status, and recovery or next-action guidance when applicable.

An error envelope MUST classify validation, budget-block, model, publication, recovery, and audit failures and MUST provide actionable recovery or next-action guidance without exposing broad internal structures.

The system MUST NOT report success when execution is ambiguous, interrupted, inconsistent, recovering, or has a failed or incomplete SelfAudit.

#### Scenario: Successful execution returns compact outcome metadata

- GIVEN an execution completes publication and all required checks successfully
- WHEN `paper_proposal_v2_execute` returns its public result
- THEN the result contains the documented compact success fields
- AND the result does not contain managed-document bytes, compiled candidate content, derived state, workspace-read details, planner context, or verification evidence.

#### Scenario: Failure remains actionable without internal payload leakage

- GIVEN an execution fails during validation, budget evaluation, model processing, publication, recovery, or audit
- WHEN `paper_proposal_v2_execute` returns its public result
- THEN the result identifies the applicable error category and next action or recovery guidance
- AND the result does not expose complete internal evidence structures or document bytes.

### Requirement: Internal Verification Evidence Preservation

The system MUST retain internal publication and verification evidence through every dependent correctness, audit, rebuild, and recovery step before redacting it from the public result.

The system MUST preserve candidate/publication byte equality checks, source reread and hash checks, publication guard authorization and completion, receipt creation, derived-state rebuild, consistency audit, SelfAudit, and recovery behavior.

#### Scenario: Compact response does not weaken publication verification

- GIVEN a successful execution with a compiled candidate and published successor
- WHEN publication verification and state rebuilding run
- THEN the system compares and validates the required internal evidence before producing the compact public result
- AND receipt, derived-state, audit, and SelfAudit outcomes remain available for the envelope.

#### Scenario: Verification failure is not masked by response shaping

- GIVEN a publication, audit, consistency, or SelfAudit check fails or is incomplete
- WHEN the execution reaches result construction
- THEN the system returns a non-success compact result with the applicable status and guidance
- AND it does not publish an apparent success result.

### Requirement: Fidelity MODIFY Planner Payload Deduplication

For exact-block semantic `MODIFY`, the system MUST construct a fidelity-specific planner payload that includes the target block once and replacement block once while retaining the data required to resolve the selected target, enforce byte identity, and request exactly one replacement action.

The planner MUST NOT broaden the requested replacement or alter exact-block matching semantics. This requirement applies only to exact-block semantic `MODIFY`; unrelated operation semantics MUST remain unchanged.

#### Scenario: Exact blocks occur once in planner input

- GIVEN an exact-block semantic `MODIFY` request with a target block and replacement block
- WHEN the system constructs its planner payload
- THEN the target block occurs exactly once
- AND the replacement block occurs exactly once
- AND the payload retains deterministic target identity and byte-identity constraints.

#### Scenario: Exact replacement remains bounded

- GIVEN an exact-block semantic `MODIFY` request
- WHEN the planner returns its action
- THEN the action replaces only the resolved requested target with the byte-identical requested replacement
- AND the system does not broaden the requested edit.

### Requirement: Local Context and Session-History Independence

The system MUST construct exact-block semantic `MODIFY` planner input from resolved local document context only. It MUST bound or narrow that context as needed for the effective budget while preserving target identity and correctness-critical context.

The system MUST NOT read, consult, or use session history as implicit context or as a fallback for an over-budget local request.

#### Scenario: Planner request is independent of session history

- GIVEN identical document state and identical exact-block semantic `MODIFY` input in sessions with different histories
- WHEN the system constructs planner input
- THEN the resulting input is determined by the request and resolved local document context
- AND no session-history content is consulted.

### Requirement: Configurable MODIFY Input Budget

The system MUST provide a documented MODIFY input budget with a documented unit, deterministic accounting rule, safe default, and deterministic invalid-configuration handling.

The system MUST account for every budgeted planner-input component before invoking the model. The effective budget and accounting outcome MUST be recorded in internal evidence and MAY be included as compact metadata without exposing the full planner payload.

#### Scenario: Request within budget invokes planner once

- GIVEN a valid configured MODIFY budget
- AND an exact-block semantic `MODIFY` request whose accounted input is within that budget
- WHEN the request is executed
- THEN the system performs at most one planner/model call
- AND records the effective budget and accounting outcome internally.

#### Scenario: Over-budget request blocks before invocation

- GIVEN a valid configured MODIFY budget
- AND a MODIFY request whose accounted input exceeds that budget
- WHEN the request is executed
- THEN the system returns a typed budget-block error
- AND performs zero planner/model calls
- AND does not consult session history as fallback context.

#### Scenario: Invalid budget configuration fails deterministically

- GIVEN an invalid MODIFY budget configuration
- WHEN the system evaluates or initializes the configuration
- THEN it rejects the configuration deterministically
- AND does not silently substitute an undocumented budget.

### Requirement: P0 Measurement and Non-Regression Evidence

The system MUST provide bounded, removable P0 measurement scaffolding or fixtures that establish baseline and post-change evidence for public response footprint, exact-MODIFY planner-input footprint and field occurrences, model invocation count, pre-invocation budget blocking, public envelope shape, and latency where measurable.

The measurement slice MUST NOT modify managed proposal document content or production semantics. The system MUST capture non-regression evidence for exact-block semantics, candidate/publication equality, source reread and hash checks, publication guards, receipt creation, derived-state rebuild, consistency audit, SelfAudit, recovery behavior, and unaffected operations.

#### Scenario: Measurements demonstrate compactness and invocation behavior

- GIVEN baseline and post-change P0 measurement fixtures
- WHEN the measurement suite runs with its instrumentation enabled
- THEN it reports response and planner-input footprint measurements, exact-block occurrence counts, model-call counts, and budget-block behavior
- AND it demonstrates that an over-budget request makes zero model calls.

#### Scenario: Instrumentation is removable and behavior-preserving

- GIVEN measurement instrumentation or fixtures are disabled or removed
- WHEN normal execution and regression tests run
- THEN proposal document content and production semantics are unchanged
- AND required verification, audit, recovery, and unaffected-operation behavior remains intact.

## Acceptance Criteria

- Public success and error contract tests verify compact documented envelopes and absence of prohibited broad payload fields.
- Compatibility inventory identifies callers and tests that consume broad result fields; migration decisions are documented before those fields are removed from public results.
- Exact-block semantic `MODIFY` tests prove one occurrence each of target and replacement in planner input, byte-exact replacement behavior, local-context-only construction, and session-history independence.
- Budget tests cover default, valid boundaries, invalid configuration, deterministic accounting, within-budget single-call behavior, and over-budget typed blocking with zero calls.
- Publication regression tests demonstrate that internal evidence remains sufficient for equality checks, source verification, guard completion, receipts, derived-state rebuild, consistency audit, SelfAudit, and recovery.
- P0 evidence records baseline and post-change response/input footprints and confirms no claimed savings without those measurements.
- Tests demonstrate unchanged behavior for operations outside exact-block semantic `MODIFY`.

## Planned Files

Implementation planning MUST identify the concrete files after compatibility inventory. Expected affected areas include:

- the Paper Proposal V2 tool response serialization and public result adapter;
- orchestrator success and error result mapping;
- publication adapter and internal evidence flow;
- exact-MODIFY intent, context, and planner payload construction;
- MODIFY runtime configuration and deterministic budget accounting;
- response-contract, planner-payload, budget, publication-invariant, and P0 measurement tests/fixtures.

## Non-Goals

- Changing managed proposal document content or exact-block matching semantics.
- Removing or bypassing internal document verification, hash or byte comparisons, publication guards, receipts, derived-state rebuild, consistency audits, SelfAudit, recovery state, or publication evidence.
- Adding tutor or reviewer calls, or changing role-file behavior for exact-block semantic `MODIFY`.
- Redesigning planner behavior for operations other than exact-block semantic `MODIFY`.
- Using session history as required or optional planner context.
- Claiming token savings without P0 measurements and non-regression evidence.

## Risks

- Existing consumers may rely on broad result fields; compatibility inventory and explicit migration decisions are required.
- Premature evidence redaction could break verification or rebuild; public and internal result representations MUST remain separated.
- Context narrowing could change planner behavior; coverage MUST remain scoped to exact-block semantic `MODIFY` and preserve byte-exact fixtures.
- Budget units or accounting ambiguity could produce unexpected blocks; configuration and boundary behavior MUST be documented and deterministic.

## Assumption

The proposal does not declare a `Capabilities` section. This specification infers the `paper-proposal-v2` domain from the affected areas; this should be confirmed during design and task planning.
