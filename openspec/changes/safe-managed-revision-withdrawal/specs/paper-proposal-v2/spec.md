# Paper Proposal V2 Specification

## Purpose

Provide safe, reversible withdrawal and restoration of managed Paper Proposal V2 revisions without conflating revision lifecycle operations with document-content deletion.

## Requirements

### Requirement: Public withdrawal and restoration operations

The system MUST publicly accept `WITHDRAW_REVISION` and `RESTORE_WITHDRAWN_REVISION` operations. A successful withdrawal response MUST expose only `status`, `operation`, `withdrawnFilename`, `restoredLatestFilename`, `artifactCount`, `backupLocation`, `auditStatus`, `selfAuditStatus`, and `warnings`. The `operation` value MUST be `WITHDRAW_REVISION` or `RESTORE_WITHDRAWN_REVISION` as applicable.

#### Scenario: Withdrawal reports the defined public contract

- GIVEN a valid managed revision eligible for withdrawal
- WHEN `WITHDRAW_REVISION` completes successfully
- THEN the response exposes only the defined withdrawal response fields
- AND `operation` is `WITHDRAW_REVISION`
- AND both audit status fields report success.

#### Scenario: Restoration reports its public operation

- GIVEN an eligible quarantined withdrawal
- WHEN `RESTORE_WITHDRAWN_REVISION` completes successfully
- THEN `operation` is `RESTORE_WITHDRAWN_REVISION`
- AND the response includes the defined public response fields.

### Requirement: Revision withdrawal intent classification

The system MUST classify a request to withdraw, retire, or remove a managed revision as `WITHDRAW_REVISION` when the request identifies a managed revision by explicit filename or unambiguous revision reference. It MUST NOT route such a request to `DELETE` and MUST NOT provide `DELETE` as a fallback.

An explicit managed-filename withdrawal MUST resolve deterministically without model, planner, tutor, reviewer, product-level subagent, or other subagent calls.

#### Scenario: Explicit filename resolves without delegated reasoning

- GIVEN a request to withdraw managed filename `research-concept-r02.md`
- WHEN the request is classified
- THEN it resolves to `WITHDRAW_REVISION`
- AND no model, planner, tutor, reviewer, product-level subagent, or other subagent is called
- AND it does not resolve to `DELETE`.

#### Scenario: Semantic revision request resolves to withdrawal

- GIVEN a request equivalent to `retira la revisión r02`
- WHEN the request is classified
- THEN it resolves to `WITHDRAW_REVISION`
- AND it does not resolve to `DELETE`.

### Requirement: Content deletion boundary

The system MUST preserve `DELETE` for requests that target content within a document or an explicitly selected document section rather than the lifecycle of a managed revision. Withdrawal support MUST NOT alter unrelated `DELETE` semantics or proposal content-editing behavior.

#### Scenario: Section deletion remains DELETE

- GIVEN a request equivalent to `elimina esta sección` with a resolved document-content target
- WHEN the request is classified
- THEN it resolves to `DELETE`
- AND it does not resolve to `WITHDRAW_REVISION`.

### Requirement: Withdrawal eligibility validation

Before mutating publication or quarantine state, the system MUST validate that the requested revision exists; is managed; is revision `r02` or later; has managed state and receipt; has matching filename, revision, and SHA across document, managed state, and receipt; has an existing prior source revision; and has no later dependent revision.

The system MUST block withdrawal without publication or mutation if the target is `r01` or the base revision, any required artifact is missing, identities are inconsistent, the source revision is missing, or a later dependent revision exists. The system MUST NOT infer or automatically repair missing or inconsistent artifact identity data.

#### Scenario: Base revision is blocked

- GIVEN a managed base or `r01` revision
- WHEN withdrawal is requested
- THEN the operation blocks
- AND no publication or quarantine mutation occurs.

#### Scenario: Unsafe managed state is blocked

- GIVEN a requested `r02+` revision with a missing artifact, cross-artifact identity mismatch, missing source revision, or later dependent revision
- WHEN withdrawal is requested
- THEN the operation blocks
- AND no publication or quarantine mutation occurs.

### Requirement: Atomic withdrawal quarantine and publication

The system MUST atomically quarantine every artifact exclusive to a valid withdrawn revision under `.paper-proposal-v2/withdrawn/<operation-id>/`. It MUST preserve the document, managed state, receipt, manifest-exclusive metadata, and a `metadata.json` record containing the withdrawal timestamp, SHA, source revision, and reason.

The system MUST coherently update the published/latest view to the appropriate remaining revision without irreversibly deleting the withdrawn revision. No path MAY garbage-collect or irreversibly delete a withdrawn revision.

#### Scenario: Eligible revision is quarantined and latest is coherent

- GIVEN a valid managed `r02+` revision with no dependent later revision
- WHEN withdrawal completes
- THEN every exclusive revision artifact is present under its operation-specific backup location
- AND `metadata.json` records timestamp, SHA, source revision, and reason
- AND the published/latest view is coherent
- AND the withdrawn revision has not been irreversibly deleted.

### Requirement: Withdrawal rollback and audit completion

Withdrawal MUST behave as one atomic transaction. If validation, any quarantine move, publication update, `ConsistencyAudit`, or `SelfAudit` fails, the system MUST restore every artifact and the latest pointer to their pre-operation state. It MUST leave no partial quarantine and no partial public-state update.

The system MUST report withdrawal success only after both `ConsistencyAudit` and `SelfAudit` pass. A failed or incomplete audit MUST remain unresolved and MUST NOT be reported as successful completion.

#### Scenario: Deterministic move failure restores the original state

- GIVEN a deterministic quarantine move failure is injected
- WHEN withdrawal is attempted
- THEN the original public artifacts and latest pointer remain intact
- AND no partial quarantine remains
- AND no partial publication update remains.

#### Scenario: Post-mutation audit failure rolls back

- GIVEN a withdrawal reaches publication mutation
- WHEN `ConsistencyAudit` or `SelfAudit` fails or is incomplete
- THEN the operation does not report success
- AND the pre-operation artifact and latest state is restored.

### Requirement: Exact atomic restoration

The system MUST restore only the exact withdrawn revision bound to its quarantine operation ID and metadata. Restoration MUST atomically reinstate the original document and managed artifacts, including managed state, receipt, manifest-exclusive metadata, filename, revision, SHA, and source-revision association. It MUST preserve quarantine copy and metadata availability according to the managed recovery contract.

Restoration MUST run `ConsistencyAudit` and `SelfAudit` and MUST report success only when both pass. On restoration failure, the system MUST preserve a consistent pre-restoration state without partial restoration.

#### Scenario: Exact withdrawn revision is restored

- GIVEN a completed withdrawal with valid quarantine metadata
- WHEN `RESTORE_WITHDRAWN_REVISION` succeeds
- THEN the original revision and its metadata are reinstated exactly
- AND the managed state, receipt, manifest, and published/latest view are consistent
- AND both audits pass.

#### Scenario: Restoration failure is atomic

- GIVEN a quarantined revision
- WHEN restoration cannot complete
- THEN no partial restored public state is visible
- AND the recoverable quarantine artifacts and metadata remain available.

### Requirement: Temporary-root test isolation and coverage

The test suite MUST execute all withdrawal and restoration cases exclusively in isolated temporary roots. Tests MUST NOT modify the real `proposals/` directory and MUST NOT withdraw `research-concept-r02.md` from repository fixtures.

The test suite MUST cover: explicit filename classification; zero delegated calls for explicit filename withdrawal; content deletion classification; semantic revision withdrawal classification; base/r01 blocking; missing or inconsistent artifact blocking; dependent-later-revision blocking; successful full quarantine with coherent latest view and both audits; deterministic move-failure rollback; and exact atomic restoration.

#### Scenario: Required matrix runs without repository fixture mutation

- GIVEN the withdrawal and restoration test matrix is executed
- WHEN all required cases run
- THEN every case uses an isolated temporary root
- AND the real `proposals/` directory is unchanged
- AND repository fixture `research-concept-r02.md` is not withdrawn.
