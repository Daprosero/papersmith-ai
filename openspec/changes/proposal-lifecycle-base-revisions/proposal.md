# Proposal: Semantic Lifecycle Contract for Base Documents and Revisions

## Intent

Establish one explicit lifecycle model for a proposal workspace so that the base document, its first materialization, successors, withdrawals, restoration, active resolution, and restart reconstruction have stable and testable semantics.

The canonical first-materialization contract is:

```text
BASE_DOCUMENT(identity, contentHash)
  -> approved first materialization
  -> ACTIVE_REVISION(identity, source = base identity)
```

The contract separates domain identity from filenames, preserves the base as immutable lineage evidence, and makes persistent withdrawal identity authoritative for restoration. It prevents a base document or an unresolved filename from being misclassified as a withdrawn revision.

## Product outcome

After this change:

- Deliberation can read the registered base document and its content hash.
- The first revision is a materialized document derived from the complete base content plus only explicitly approved changes.
- Every revision has a stable identity independent of its output filename.
- A workspace has at most one registered base document and at most one active revision.
- Successor creation and restoration update the active pointer without rewriting or replacing historical content.
- Withdrawn revisions remain visible in the lifecycle inventory.
- Active resolution is identity- and state-based, never “highest filename wins.”
- A fresh process reconstructs the same logical lifecycle state from durable records.

## Scope

### In scope

1. Semantic entities and invariants for `BaseDocument`, `Revision`, `Withdrawal`, `WorkspaceLifecycleState`, `LineageReference`, `MaterializationRequest`, and `MaterializationResult`.
2. The seven lifecycle and materialization operations defined below.
3. State transitions, error classification, idempotency, persistence, restart reconstruction, and inventory consistency.
4. Explicit separation between stable lifecycle identity and presentation/output filenames.
5. Compatibility classification of the current behavior and the intended target behavior.

### Out of scope / non-goals

- Classes, adapters, module boundaries, filesystem layout, database schema, or API transport shape.
- Migration scripts or automatic conversion of existing state.
- A particular hashing, patching, rendering, or merge algorithm.
- Renaming or deleting user content as a product feature.
- Changing scientific deliberation rules beyond making the registered base and lifecycle evidence readable.
- Allowing multiple bases, multiple active revisions, or implicit revision selection.
- Treating a filename as proof of a revision, withdrawal, lineage relationship, or restoration authority.

## Canonical semantic model

A workspace owns one lifecycle. The lifecycle contains one immutable base document, zero or more revisions, zero or more persistent withdrawal records, and one active-revision pointer at most.

A revision is a durable content artifact with a stable identity. The first revision points directly to the base document as its source. Each successor points to an existing revision as its source. The active pointer identifies the one revision currently selected for the workspace; it is not computed by ordering filenames.

A withdrawn revision remains a revision in the inventory and retains its withdrawal record and recovery content. Restoration reactivates the identified revision while preserving the withdrawal record as historical evidence.

## Entity contracts

### BaseDocument

| Concern | Contract |
|---|---|
| Identity | Required stable `baseDocumentId`, unique within the workspace lifecycle. Identity is independent of filename, path, display name, or output location. |
| Required fields | `workspaceId`; `baseDocumentId`; `contentHash`; the complete readable base content or an authoritative durable content reference; registration state; registration provenance/time. |
| Optional fields | Original source filename, display name, media/content type, human-readable description, source provenance, and approval metadata. None is identity. |
| Allowed states | `REGISTERED` only after successful registration. A rejected or uncommitted candidate is not a `BaseDocument`. |
| Invariants | Content always hashes to `contentHash`; identity and content hash do not change after registration; the base participates in every revision lineage; the base is readable for deliberation; the base cannot be withdrawn, restored, replaced, overwritten, or deleted through lifecycle operations. |
| Relationships | Owns the first lineage source for exactly the first revision in a chain. Every revision ultimately resolves to this base identity. |
| Persistence | Registration and content are durable before the operation reports success. The immutable record remains available for restart reconstruction and deliberation. Re-registration with the same idempotency identity may return the original result; a conflicting registration is rejected. |

The base is a domain object, not an alias for `r01` and not a filename convention. A managed filename may locate its content, but changing or losing that locator does not change the base identity; loss of the authoritative content or hash makes the inventory inconsistent rather than creating a new base.

### Revision

| Concern | Contract |
|---|---|
| Identity | Required stable `revisionId`, unique within the workspace lifecycle. It is independent of filename and may not be regenerated from filename, claims, or metadata. |
| Required fields | `workspaceId`; `revisionId`; immutable materialized content or authoritative durable content reference; `contentHash`; `baseDocumentId`; a `LineageReference`; materialization provenance; lifecycle state. |
| Optional fields | `parentRevisionId` as a queryable projection of the lineage reference, output filename/locator, approved-change summary, approval provenance, created/withdrawn/restored timestamps, and display metadata. |
| Allowed states | `ACTIVE`, `SUPERSEDED`, or `WITHDRAWN`. `ACTIVE` is the unique current selection. `SUPERSEDED` means a later revision became active. `WITHDRAWN` means a persistent withdrawal record exists. A revision cannot move directly from `WITHDRAWN` to `SUPERSEDED`; restoration first makes it active. |
| Invariants | Content hash matches materialized content; identity is stable; base identity and source reference are immutable; the first revision has source `BASE_DOCUMENT(baseDocumentId, contentHash)`; a successor has source `REVISION(sourceRevisionId, sourceContentHash)`; the first revision contains all unmodified base content and only approved changes; it is not reconstructible from claims or metadata alone; at most one revision is `ACTIVE` per workspace. |
| Relationships | The first revision is rooted at the base. Each successor references an existing revision. A revision may have at most one immediate successor in the canonical chain. Withdrawal belongs to a revision and never to the base. |
| Persistence | A successful materialization durably persists the revision identity, bytes/content reference, hash, source reference, and lifecycle state atomically with the corresponding materialization result. Historical revisions remain discoverable after successor creation, withdrawal, restore, and restart. Content is never overwritten in place. |

Successor creation changes the source revision from `ACTIVE` to `SUPERSEDED` and makes the new revision `ACTIVE`. Withdrawal of the active revision changes it to `WITHDRAWN`, clears the active-revision pointer, and leaves the workspace `WITHDRAWN_ONLY`; it never promotes or silently restores a predecessor.

### Withdrawal

| Concern | Contract |
|---|---|
| Identity | Required stable persistent `withdrawalId`. It is distinct from `revisionId`, request identity, filename, and output path. |
| Required fields | `workspaceId`; `withdrawalId`; withdrawn `revisionId`; revision content hash; exact revision identity evidence; reason/provenance; committed lifecycle state; durable recovery content/reference; creation time. |
| Optional fields | Request identity, actor, audit data, prior active revision, restore time, and human-readable explanation. A withdrawal has no resulting active revision. |
| Allowed states | `COMMITTED`, `RESTORED`, or `ABORTED`. Only `COMMITTED` records authorize restoration. `ABORTED` records are historical and do not authorize restoration. |
| Invariants | A committed withdrawal references a real non-base revision; its stored content and hash equal the withdrawn revision; it cannot reference a base; it is durable before withdrawal reports success; its identity can be resolved after restart. Committing a withdrawal clears the workspace active-revision pointer and leaves the workspace `WITHDRAWN_ONLY`; no predecessor is promoted or implicitly restored. A restored record remains immutable historical evidence and is not replaced by a new withdrawal record. |
| Relationships | Exactly one committed withdrawal record describes each withdrawal event. A revision may have multiple historical withdrawal events only if the product explicitly permits repeated withdraw/restore cycles; each event has a distinct identity. A committed withdrawal has no active revision result; restoration is the separate operation that may establish an active revision. |
| Persistence | The record, recovery content, audit outcome, and cleared active pointer are retained after withdrawal and restore. Public visibility and inventory membership are derived from the record plus revision state, not from whether a filename is currently present. |

A restore request must first resolve a real persistent `Withdrawal` identity. A base document and an unresolved generic filename are not withdrawal identities.

### WorkspaceLifecycleState

| Concern | Contract |
|---|---|
| Identity | Required stable `workspaceId`. |
| Required fields | `workspaceId`; at most one `baseDocumentId`; revision inventory; withdrawal inventory; zero or one `activeRevisionId`; lifecycle state; an integrity/version marker sufficient to detect inconsistent reconstruction. |
| Optional fields | Current active filename/locator, inventory digest, last successful operation identity, scientific-state summary, and timestamps. These are projections, not authority for identity. |
| Allowed states | `EMPTY`, `BASE_REGISTERED`, `ACTIVE`, `WITHDRAWN_ONLY`, or `INCONSISTENT`. `EMPTY` has no base or revision. `BASE_REGISTERED` has a base and no revision. `ACTIVE` has a base and exactly one active revision. `WITHDRAWN_ONLY` has a base, no active revision, and at least one visible withdrawn revision. `INCONSISTENT` is a fail-closed state and permits no mutating lifecycle operation until rebuilt or repaired by an explicit process. |
| Invariants | At most one base; at most one active revision; every revision belongs to the workspace and resolves to the base; every withdrawal resolves to a revision and persistent identity; active resolution agrees with revision states; inventory is reproducible from durable records; no filename ordering is authoritative. |
| Relationships | Contains the base, revision, and withdrawal records for one workspace. Scientific deliberation may read this state and its base/revision evidence but cannot create a second lifecycle authority. |
| Persistence | The logical state and its integrity marker are durably updated with each committed transition. A derived inventory may be rebuilt; rebuilding must not invent or discard domain records. |

### LineageReference

| Concern | Contract |
|---|---|
| Identity | The reference itself is immutable and identified by its source kind plus source identity and source content hash. |
| Required fields | `sourceKind` (`BASE_DOCUMENT` or `REVISION`); `sourceId`; `sourceContentHash`; `baseDocumentId`; source revision identity when `sourceKind = REVISION`. |
| Optional fields | Source filename/locator, source revision number, and human-readable lineage label. |
| Allowed states | `RESOLVED` or `UNRESOLVED`. An unresolved reference may exist only in a rejected/inconsistent diagnostic, never in a successfully materialized revision. |
| Invariants | Base source must resolve to the registered base and its exact hash. Revision source must resolve to an existing revision in the same workspace with the exact hash recorded by the reference. A filename alone is never a valid lineage reference. A successor must reference a `Revision`, not a base document. |
| Relationships | A first revision has one resolved base reference. A successor has one resolved revision reference. The reference establishes the complete ancestry back to the base. |
| Persistence | The reference is stored as part of the revision’s immutable lineage evidence and is sufficient to validate the chain after restart. |

### MaterializationRequest

| Concern | Contract |
|---|---|
| Identity | Required stable `requestId` used for idempotency and restart recovery. It is not a revision identity. |
| Required fields | `requestId`; `workspaceId`; operation kind (`CREATE_FROM_BASE` or `CREATE_SUCCESSOR`); source `LineageReference`; approved change set or explicit empty set; approval/provenance evidence; requested output locator if required by the product boundary. |
| Optional fields | Expected source content hash duplicated for caller safety, requested revision label/filename, actor, reason, correlation data, and client retry token. |
| Allowed states | `RECEIVED`, `VALIDATED`, `COMMITTED`, `REJECTED`, or `RECOVERY_REQUIRED`. |
| Invariants | The request is immutable once accepted; approved changes are explicit and bounded; source identity and hash are unambiguous; a request cannot change operation kind during retry; output filename is a locator and must not define identity. |
| Relationships | One request produces at most one committed materialization result and at most one revision. It references the base for first materialization or a revision for successor creation. |
| Persistence | The request and its terminal result are durable enough to distinguish a committed retry from an interrupted attempt. A restart resumes or reconciles the same request; it does not infer a new request from claims or filename. |

### MaterializationResult

| Concern | Contract |
|---|---|
| Identity | Required stable `resultId`, associated with exactly one `requestId`. |
| Required fields | `resultId`; `requestId`; workspace; operation kind; outcome; resulting revision identity when committed; resulting content hash; resolved source identity/hash; resulting lifecycle state; durable completion status. |
| Optional fields | Output filename/locator, prior active revision, promoted/superseded revision, warnings, audit data, and completion time. |
| Allowed states | `COMMITTED`, `ALREADY_COMMITTED`, `REJECTED`, `INCONSISTENT`, or `RECOVERY_REQUIRED`. |
| Invariants | A committed result points to a durable revision whose bytes match the result hash and whose lineage matches the request. `ALREADY_COMMITTED` is returned only when the same request identity resolves to the same committed result. A result never claims success for a revision that cannot be reconstructed from persisted content. |
| Relationships | One result belongs to one materialization request and one lifecycle transition. It may identify the active revision after the transition. |
| Persistence | The result is written durably with the materialization transition. Restart reads it before considering replay; successful work is not repeated blindly. |

## Operations

### REGISTER_BASE_DOCUMENT

**Preconditions**

- The workspace is not `INCONSISTENT`.
- No base document is registered for the workspace.
- The request carries a stable base identity and complete content (or an authoritative content reference).

**Input**

`workspaceId`, `baseDocumentId`, complete base content/reference, `contentHash`, optional source locator/provenance, and an idempotency request identity.

**Validation**

- Verify the content produces the supplied hash.
- Verify the base identity is not already bound to different content.
- Verify the workspace contains no different registered base.
- Reject filename-only registration and missing content/hash evidence.

**Transition**

`EMPTY -> BASE_REGISTERED`.

**Output**

The registered immutable `BaseDocument` and the updated `WorkspaceLifecycleState`.

**Semantic errors**

`BASE_DOCUMENT_ALREADY_REGISTERED` for an existing base or conflicting registration; `SOURCE_CONTENT_HASH_MISMATCH` for content/hash disagreement; `LIFECYCLE_INVENTORY_INCONSISTENT` when the pre-state cannot be trusted.

**Persistent effects**

Persist the base content/reference, identity, hash, provenance, registration result, and lifecycle inventory update. No revision or withdrawal is created.

**Idempotency and restart**

A retry with the same request identity returns the original successful registration if all inputs are identical. A retry with different content or identity is rejected. After restart, the durable base record is authoritative and remains unchanged.

### CREATE_FROM_BASE

**Preconditions**

- A registered base exists.
- No revision is active and no first revision has already been committed for this lifecycle.
- The workspace is not inconsistent.

**Input**

A `MaterializationRequest` whose source is exactly `BASE_DOCUMENT(baseDocumentId, contentHash)`, plus approved changes and an optional output locator.

**Validation**

- Resolve the base identity, not a filename.
- Verify the source hash against the persisted base.
- Verify approval evidence and that every change is within the approved change set.
- Materialize complete base content, preserving every unmodified portion, and verify the resulting content hash.
- Reject a request that supplies only claims, metadata, or a filename without base content.
- Reject an output locator already occupied by a different durable artifact.

**Transition**

`BASE_REGISTERED -> ACTIVE`, creating the first `Revision` with source `BASE_DOCUMENT(baseDocumentId, contentHash)`.

**Output**

A committed `MaterializationResult` containing the new stable `revisionId`, resulting hash, source identity/hash, and active lifecycle state.

**Semantic errors**

`BASE_DOCUMENT_NOT_REGISTERED`, `ACTIVE_REVISION_ALREADY_EXISTS`, `INVALID_LINEAGE_REFERENCE`, `SOURCE_CONTENT_HASH_MISMATCH`, `OUTPUT_FILENAME_CONFLICT`, or `LIFECYCLE_INVENTORY_INCONSISTENT`.

**Persistent effects**

Persist the request, complete materialized revision content, revision identity, lineage reference, result, and active pointer as one logical committed transition. The base is not modified.

**Idempotency and restart**

A committed request returns the original result and revision identity. A request with a different request identity cannot create a second first revision. Restart either finds the committed result, resumes a clearly uncommitted request, or reports `RECOVERY_REQUIRED`; it never reconstructs the revision from claims alone.

### CREATE_SUCCESSOR

**Preconditions**

- A registered base exists.
- Exactly one active revision exists.
- The request references that source `Revision` identity and its exact content hash.
- The workspace is consistent.

**Input**

A `MaterializationRequest` with `sourceKind = REVISION`, source revision identity/hash, approved changes, and optional output locator.

**Validation**

- Resolve the source revision by stable identity.
- Verify its persisted content hash and that it is the current active revision.
- Verify the source lineage resolves to the workspace base.
- Apply only approved changes to the complete source content and persist the resulting content/hash.
- Reject a base reference, generic filename, stale source, unresolved reference, or conflicting output locator.

**Transition**

`ACTIVE(source) -> SUPERSEDED(source) + ACTIVE(successor)`.

**Output**

A committed `MaterializationResult` identifying the successor, its source revision/hash, resulting hash, and the unique active revision.

**Semantic errors**

`ACTIVE_REVISION_NOT_FOUND`, `INVALID_LINEAGE_REFERENCE`, `SOURCE_CONTENT_HASH_MISMATCH`, `OUTPUT_FILENAME_CONFLICT`, `ACTIVE_REVISION_ALREADY_EXISTS` when the request would create a second active result, or `LIFECYCLE_INVENTORY_INCONSISTENT`.

**Persistent effects**

Persist the immutable successor content and lineage, the source state transition, the new active pointer, request, result, and inventory update. Existing content is never overwritten.

**Idempotency and restart**

A committed request returns its original result. A retry with the same request identity cannot create another successor. If a restart observes a durable successor but an incomplete pointer update, it reconciles to the only state supported by the committed transition or reports `LIFECYCLE_INVENTORY_INCONSISTENT`; it does not choose by filename.

### WITHDRAW_REVISION

**Preconditions**

- The target resolves to a real `Revision` identity in the workspace.
- The target is the current `ACTIVE` revision and is not the base document.
- The revision has complete persisted content and matching hash.
- The workspace is consistent.

**Input**

`workspaceId`, revision identity (optionally accompanied by expected hash), reason/provenance, and withdrawal request identity.

**Validation**

- Resolve the revision before interpreting any filename.
- Verify it is withdrawable and not the immutable first/base materialization.
- Verify the source content hash and recovery content are intact.
- Verify no forbidden dependent active transition would be created.

**Transition**

`ACTIVE(target) -> WITHDRAWN(target)`, clear the active-revision pointer, persist a `COMMITTED` `Withdrawal`, and leave the workspace `WITHDRAWN_ONLY`. No predecessor is promoted or implicitly restored.

**Output**

The committed `Withdrawal`, updated inventory, and updated `WorkspaceLifecycleState`.

**Semantic errors**

`REVISION_NOT_WITHDRAWABLE` for the base/first revision or a non-withdrawable target; `ACTIVE_REVISION_NOT_FOUND`; `SOURCE_CONTENT_HASH_MISMATCH`; `LIFECYCLE_INVENTORY_INCONSISTENT`; `OUTPUT_FILENAME_CONFLICT` only if recovery/publication naming would collide.

**Persistent effects**

Persist the withdrawal identity, exact recovery content/reference, revision state, cleared active pointer, audit/provenance, and inventory. Withdrawn history remains visible and the workspace remains `WITHDRAWN_ONLY`.

**Idempotency and restart**

A retry with the same withdrawal request identity returns the committed withdrawal. A retry naming an already withdrawn revision returns `REVISION_NOT_WITHDRAWABLE` or the existing withdrawal only when the caller supplies the original withdrawal identity. Restart discovers the persistent withdrawal record, reproduces the cleared active pointer, and returns the same `WITHDRAWN_ONLY` state.

### RESTORE_WITHDRAWN_REVISION

**Preconditions**

- The request supplies a real persistent `withdrawalId`, or a reference that resolves uniquely to a persistent committed withdrawal.
- The withdrawal record is `COMMITTED` and its recovery content/hash is valid.
- The referenced revision is currently `WITHDRAWN`.
- The workspace is consistent.

**Input**

`workspaceId`, persistent withdrawal identity, optional expected revision identity/hash, and restore request identity.

**Validation**

1. Resolve identity against durable withdrawal records.
2. If the supplied target is a registered `BaseDocument`, return `BASE_DOCUMENT_NOT_RESTORABLE`.
3. If it resolves to a revision that has no committed withdrawal, return `REVISION_NOT_WITHDRAWN`.
4. If a generic filename or other unresolved reference cannot identify a persistent withdrawal, return `WITHDRAWAL_IDENTITY_NOT_FOUND`; never return the legacy generic `WITHDRAWAL_NOT_FOUND`.
5. Verify recovery content and hash, revision identity, lineage, and any output locator conflict.

**Transition**

`WITHDRAWN(target) -> ACTIVE(target)`. If another revision is active, that revision becomes `SUPERSEDED` as part of the same transition; the base is never changed. The withdrawal record remains `RESTORED` historical evidence.

**Output**

The restored revision identity/hash, updated `Withdrawal`, updated inventory, and `WorkspaceLifecycleState` with exactly one active revision.

**Semantic errors**

`BASE_DOCUMENT_NOT_RESTORABLE`, `WITHDRAWAL_IDENTITY_NOT_FOUND`, `REVISION_NOT_WITHDRAWN`, `OUTPUT_FILENAME_CONFLICT`, `SOURCE_CONTENT_HASH_MISMATCH`, `INVALID_LINEAGE_REFERENCE`, or `LIFECYCLE_INVENTORY_INCONSISTENT`.

**Persistent effects**

Persist the restored revision state, active pointer, restore event/result, and the withdrawal’s terminal historical state. Restore uses the preserved content; it does not regenerate or overwrite the revision.

**Idempotency and restart**

A committed restore retry returns the original result. A retry against the same withdrawal after restoration returns the existing restored outcome rather than creating a new revision. A fresh process resolves the same `withdrawalId` and recovery content; it never infers restoration from a filename.

### RESOLVE_ACTIVE_REVISION

**Preconditions**

- The workspace inventory is available and internally consistent.
- The caller requests one workspace, optionally with an expected revision identity/hash.

**Input**

`workspaceId` and optional expected `revisionId`, content hash, or lineage reference.

**Validation**

- Count revisions by persisted lifecycle state.
- Require exactly zero or one active revision; more than one is inconsistent.
- Validate the active revision’s base and source hash.
- Do not use filename order, lexical order, timestamps, or claims to select the result.

**Transition**

No lifecycle mutation. The operation may first invoke the semantic equivalent of inventory reconstruction when the cached inventory is absent; it must fail closed if reconstruction is inconsistent.

**Output**

The unique active `Revision`, or an explicit absence result.

**Semantic errors**

`ACTIVE_REVISION_NOT_FOUND` when no active revision exists; `SOURCE_CONTENT_HASH_MISMATCH`, `INVALID_LINEAGE_REFERENCE`, or `LIFECYCLE_INVENTORY_INCONSISTENT` when evidence conflicts. `ACTIVE_REVISION_ALREADY_EXISTS` applies to a mutation that would create a second active revision, not to a successful resolution.

**Persistent effects**

Normally none. A validated inventory digest/cache may be persisted as a derived projection, but it cannot replace authoritative records.

**Idempotency and restart**

Read-only and naturally idempotent. The same durable records produce the same logical active revision after restart.

### REBUILD_LIFECYCLE_INVENTORY

**Preconditions**

- Durable lifecycle records and content evidence are accessible.
- The workspace identity is known.
- No mutating lifecycle operation is concurrently committed against the same inventory boundary.

**Input**

`workspaceId`, durable base/revision/withdrawal/materialization records, and any public or locator metadata needed only to verify content presence. No filename ordering input is authoritative.

**Validation**

- Require zero or one base.
- Resolve every revision identity and lineage reference.
- Verify every recorded content hash.
- Verify every committed withdrawal has a real withdrawal identity and exact recovery evidence.
- Recompute active state from persisted revision states and transition records.
- Detect duplicate identities, missing content, contradictory states, orphan withdrawals, multiple active revisions, or impossible lineage.

**Transition**

No content lifecycle transition. Produce the canonical `WorkspaceLifecycleState`; set it to `INCONSISTENT` and fail closed if validation cannot establish one logical state.

**Output**

A complete inventory containing the base, all revisions, all withdrawn records, the unique active pointer if present, lifecycle state, and deterministic integrity digest.

**Semantic errors**

`LIFECYCLE_INVENTORY_INCONSISTENT` for any contradiction; `SOURCE_CONTENT_HASH_MISMATCH` for content evidence; `INVALID_LINEAGE_REFERENCE` for broken ancestry; `WITHDRAWAL_IDENTITY_NOT_FOUND` for an invalid withdrawal reference.

**Persistent effects**

Persist only a validated inventory projection/digest and reconstruction evidence. Do not delete, rename, replace, or invent domain records. An inconsistent result must remain visible as fail-closed state until explicitly repaired.

**Idempotency and restart**

Rebuilding twice over unchanged durable records yields byte-for-byte equivalent logical state and equivalent digest. Rebuilding after restart uses stable identities and explicit transition evidence; it never selects the maximum filename or treats a missing filename as proof that a revision never existed.

## Target state machine

```text
EMPTY
  | REGISTER_BASE_DOCUMENT
  v
BASE_REGISTERED
  | CREATE_FROM_BASE
  v
ACTIVE(revision)
  | CREATE_SUCCESSOR
  v
ACTIVE(successor), with source revision SUPERSEDED
  | WITHDRAW_REVISION
  v
WITHDRAWN_ONLY
                                  (target is WITHDRAWN; active pointer is cleared; no predecessor promotion)

WITHDRAWN(revision)
  | RESTORE_WITHDRAWN_REVISION
  v
ACTIVE(revision), with any prior active revision SUPERSEDED

Any valid state
  | REBUILD_LIFECYCLE_INVENTORY
  v
same logical state, or INCONSISTENT

Any state with conflicting durable evidence -> INCONSISTENT
```

`RESOLVE_ACTIVE_REVISION` is read-only and does not transition the state. A base document is not a revision state and has no withdrawal or restoration edge.

## Full transition table

| Origin | Operation/event | Required condition | Revision/base effect | Workspace result |
|---|---|---|---|---|
| `EMPTY` | `REGISTER_BASE_DOCUMENT` | No base exists; content/hash validate | Create immutable registered base | `BASE_REGISTERED` |
| `BASE_REGISTERED` | `CREATE_FROM_BASE` | Exact registered base reference; no first revision; approved changes | Create first revision from complete base; source is base identity; revision becomes active | `ACTIVE` |
| `BASE_REGISTERED` | `CREATE_SUCCESSOR` | No active revision/source revision cannot resolve | No mutation | `ACTIVE_REVISION_NOT_FOUND` or `INVALID_LINEAGE_REFERENCE` |
| `ACTIVE(source)` | `CREATE_SUCCESSOR` | Source is the unique active revision; hash and approval validate | Source becomes `SUPERSEDED`; successor is created and becomes `ACTIVE` | `ACTIVE` |
| `ACTIVE(first/base revision)` | `WITHDRAW_REVISION` | Target is immutable first revision | No mutation | `REVISION_NOT_WITHDRAWABLE` |
| `ACTIVE(revision)` | `WITHDRAW_REVISION` | Target resolves to active revision; recovery evidence validates | Target becomes `WITHDRAWN`; committed withdrawal persists; active pointer is cleared; no predecessor is promoted or restored | `WITHDRAWN_ONLY` |
| `SUPERSEDED(revision)` | `WITHDRAW_REVISION` | Target is not current active | No mutation | `REVISION_NOT_WITHDRAWABLE` |
| `WITHDRAWN(revision)` | `RESTORE_WITHDRAWN_REVISION` | Committed persistent withdrawal identity resolves; recovery hash validates | Target becomes `ACTIVE`; existing active becomes `SUPERSEDED`; withdrawal becomes `RESTORED` | `ACTIVE` |
| `ACTIVE(revision)` | `RESTORE_WITHDRAWN_REVISION` | Target is already active, not withdrawn | No mutation | `REVISION_NOT_WITHDRAWN` |
| `BASE_DOCUMENT` | `RESTORE_WITHDRAWN_REVISION` | Base identity resolves | No mutation; base has no withdrawal lifecycle | `BASE_DOCUMENT_NOT_RESTORABLE` |
| unknown/generic filename | `RESTORE_WITHDRAWN_REVISION` | No persistent withdrawal identity resolves | No mutation | `WITHDRAWAL_IDENTITY_NOT_FOUND` |
| any consistent state | `RESOLVE_ACTIVE_REVISION` | Zero or one active revision | No mutation | Unique active revision or `ACTIVE_REVISION_NOT_FOUND` |
| any state | `REBUILD_LIFECYCLE_INVENTORY` | Durable evidence validates | Rebuild projection only | Same state or `INCONSISTENT` |
| any state | conflicting evidence | Duplicate/missing/contradictory durable identities or hashes | No lifecycle mutation | `INCONSISTENT` / `LIFECYCLE_INVENTORY_INCONSISTENT` |

## Global invariants

1. **Single base:** each workspace has zero or one `BaseDocument`; registration is one-time and immutable.
2. **Base immutability:** the base identity, content, and content hash never change. No lifecycle operation withdraws, restores, replaces, or overwrites it.
3. **Stable identity:** base, revision, and withdrawal identities are durable domain identities independent of filenames, paths, revision numbers, or display labels.
4. **Complete first materialization:** the first revision preserves all unmodified base content and applies only approved changes. Claims and metadata alone cannot create a valid first revision.
5. **Explicit root:** the first revision’s source is exactly `BASE_DOCUMENT(baseDocumentId, contentHash)`.
6. **Explicit successor source:** every successor references an existing `Revision` identity and exact source content hash.
7. **Hash agreement:** every persisted content artifact agrees with its recorded content hash; disagreement is inconsistent state, not a new identity.
8. **Single active revision and withdrawal outcome:** a workspace has zero or one `ACTIVE` revision, never more than one; `WITHDRAW_REVISION` clears the active pointer and leaves the workspace `WITHDRAWN_ONLY`, with no predecessor promotion or implicit restoration.
9. **Visible history:** withdrawn revisions and their persistent withdrawal identities remain in inventory after withdrawal, restore, and restart.
10. **No filename authority:** filenames are locators or presentation values. Active resolution and lineage resolution never select by maximum or lexical filename.
11. **Withdrawal identity authority:** restoration requires a durable committed `Withdrawal`. A base document, active revision, superseded revision, or unresolved filename is not sufficient.
12. **No generic misclassification:** the deprecated generic `WITHDRAWAL_NOT_FOUND` result must not be emitted for a base document or unresolved generic filename; use `BASE_DOCUMENT_NOT_RESTORABLE`, `REVISION_NOT_WITHDRAWN`, or `WITHDRAWAL_IDENTITY_NOT_FOUND` according to the resolved evidence.
13. **No in-place replacement:** materialization, successor creation, withdrawal, and restore preserve historical content and identities.
14. **Atomic logical transitions:** a successful operation persists its request/result and all affected lifecycle records so restart cannot produce a second logical outcome.
15. **Fail closed:** contradictory evidence produces `LIFECYCLE_INVENTORY_INCONSISTENT`; no active revision is selected from inconsistent data.
16. **Deterministic reconstruction:** unchanged durable evidence produces the same logical state, active identity, relationships, and inventory membership after every restart.
17. **Base lineage closure:** following any revision’s lineage reaches the one registered base without cycles, missing references, or cross-workspace references.
18. **Approval boundary:** only changes present in the materialization request’s approved change set may affect the resulting revision content.

## Required semantic error catalog

| Error | Meaning | Must not be substituted with |
|---|---|---|
| `BASE_DOCUMENT_NOT_REGISTERED` | The requested first materialization has no registered base in the workspace. | A synthetic revision or filename-derived base. |
| `BASE_DOCUMENT_ALREADY_REGISTERED` | Registration conflicts with an existing base or attempts a second base. | Silent replacement or overwrite. |
| `ACTIVE_REVISION_ALREADY_EXISTS` | A mutation would create or preserve more than one active revision, or first materialization is attempted after an active revision exists. | Choosing the highest filename. |
| `ACTIVE_REVISION_NOT_FOUND` | A required active revision is absent, or no active revision can be resolved. | Selecting a superseded/withdrawn revision implicitly. |
| `INVALID_LINEAGE_REFERENCE` | Source kind, source identity, workspace, ancestry, or source hash does not resolve exactly. | Accepting a filename or claims as lineage proof. |
| `REVISION_NOT_WITHDRAWABLE` | The target is the immutable first/base revision, is not active, or violates withdrawal policy. | Creating a withdrawal record anyway. |
| `REVISION_NOT_WITHDRAWN` | The target revision exists but has no committed withdrawal eligible for restoration. | `WITHDRAWAL_NOT_FOUND`. |
| `WITHDRAWAL_IDENTITY_NOT_FOUND` | No persistent withdrawal identity can be resolved from the supplied identity/reference. | Treating an unresolved filename as a withdrawal. |
| `BASE_DOCUMENT_NOT_RESTORABLE` | The supplied identity resolves to the base document, which has no withdrawal lifecycle. | `WITHDRAWAL_NOT_FOUND`. |
| `OUTPUT_FILENAME_CONFLICT` | A requested output locator conflicts with a different durable artifact or identity. | Overwriting or silently renaming. |
| `SOURCE_CONTENT_HASH_MISMATCH` | Supplied or recovered source content differs from its persisted hash. | Recomputing identity from the mismatched content. |
| `LIFECYCLE_INVENTORY_INCONSISTENT` | Durable records cannot produce one valid logical lifecycle state. | Best-effort active selection or mutation. |

`WITHDRAWAL_NOT_FOUND` is not a target semantic error in this contract. Existing callers may receive a compatibility mapping only outside the semantic contract, but base and unresolved-reference cases must map to the explicit errors above.

## Restart reconstruction rules

1. Load durable base, revision, materialization, and withdrawal records before consulting public filenames or cached projections.
2. Reconstruct identities from persisted stable IDs, never from filenames or ordering.
3. Verify base content and hash, then verify every revision’s content/hash and lineage reference.
4. Include all revisions, including withdrawn and superseded revisions, in the inventory.
5. Resolve withdrawal records by persistent `withdrawalId`; retain `COMMITTED`, `RESTORED`, and `ABORTED` history according to their recorded status.
6. Recompute the active pointer from committed transition evidence and revision state. If zero or one active revision cannot be established, produce `INCONSISTENT`.
7. Reproduce `BASE_REGISTERED`, `ACTIVE`, `WITHDRAWN_ONLY`, or `EMPTY` only when their entity counts and relationships satisfy the invariants.
8. Treat a missing optional filename/locator as a locator problem, not as missing identity. Treat a conflicting filename as `OUTPUT_FILENAME_CONFLICT` or inventory inconsistency according to whether the conflict is in a pending request or committed evidence.
9. Replaying a request first checks its durable request/result identity. A committed request is returned, not rerun; an incomplete request is resumed or explicitly marked recovery-required.
10. Persist a deterministic inventory projection/digest only after validation. Rebuilding must not mutate immutable domain records or invent a withdrawal.
11. A fresh runtime over unchanged durable evidence must return the same active `revisionId`, base `baseDocumentId`, withdrawal identities, states, and lineage relationships.

## Explicit differences from the current contract

The exploration identified these current behaviors that this proposal intentionally changes:

| Current behavior | Target semantic contract |
|---|---|
| The fixed `matematica_propuesta_CREDA.md` base is handled by legacy derivation and has no lifecycle identity. | Register one immutable `BaseDocument` with stable identity and content hash; keep it readable and in every revision lineage. |
| `CREATE_R01` renders a new minimal document from claims/metadata and does not inherit the fixed base. | `CREATE_FROM_BASE` materializes complete base content plus only approved changes; claims/metadata alone are insufficient. |
| Managed revision identity, predecessor, and successor naming are filename-derived. | Revision identity and lineage are stable persisted identities; filename is only a locator/presentation field. |
| `latestManagedFilename()` and filesystem inventory choose the highest numeric filename. | `RESOLVE_ACTIVE_REVISION` reads the persisted unique active state and fails closed on ambiguity. |
| Canonical filesystem inventory reports only the latest public revision and drops withdrawn history. | Inventory includes active, superseded, and withdrawn revisions and persistent withdrawal identities. |
| Withdrawal can expose a prior public revision as the apparent latest revision after the current revision is withdrawn. | Withdrawal always clears the active pointer and leaves the workspace `WITHDRAWN_ONLY`; a predecessor becomes active only through a separate explicit lifecycle operation, never implicitly. |
| Restore accepts a syntactically valid `r01` filename and eventually returns generic `WITHDRAWAL_NOT_FOUND`. | Base resolves to `BASE_DOCUMENT_NOT_RESTORABLE`; an existing non-withdrawn revision resolves to `REVISION_NOT_WITHDRAWN`; an unresolved reference resolves to `WITHDRAWAL_IDENTITY_NOT_FOUND`. |
| Withdrawal identity is durable, but it is not consistently represented in project-entry reconstruction. | Persistent withdrawal identity is authoritative for restore and survives inventory rebuild/restart. |
| Multiple public files may be collapsed to one “latest” active entry. | More than one persisted active revision is an explicit lifecycle inconsistency; no silent collapse. |
| Restore and successor behavior relies on public artifact movement and filename conventions. | These operations are defined by stable entity identity, exact hashes, and atomic logical state transitions; physical representation remains a later design concern. |

## Affected areas

- **Lifecycle domain:** base registration, revision lineage, active-pointer transitions, withdrawal, and restore classification.
- **Materialization:** first materialization source semantics, approved-change boundary, content/hash evidence, and idempotent results.
- **Workspace entry and deliberation:** readable base evidence and complete active/withdrawn inventory after re-entry or restart.
- **Persistence/recovery:** durable identity records, inventory reconstruction, request/result replay, and fail-closed inconsistency detection.
- **Compatibility surface:** existing callers that use filename-based lifecycle references or the generic `WITHDRAWAL_NOT_FOUND` classification will need an explicit compatibility decision.

## Risks and mitigations

| Risk | Mitigation in this proposal |
|---|---|
| Existing persisted state lacks explicit base or stable revision identity. | Mark reconstruction as `LIFECYCLE_INVENTORY_INCONSISTENT` rather than guessing; handle migration as a separate decision. |
| A filename rename or conflict is mistaken for a new revision or overwrite. | Keep locator separate from identity and reject conflicts explicitly. |
| Restoring a historical revision creates two active revisions. | Restore performs one atomic active-pointer transition and supersedes any existing active revision. |
| A base is accidentally treated as withdrawable. | Base is a distinct entity; classification occurs before withdrawal lookup. |
| Withdrawal history disappears after restart. | Rebuild inventory from persistent withdrawal identities and recovery records, not public files alone. |
| Partial materialization leaves claims without durable content. | Do not report committed result unless complete content, hash, lineage, request, and result are durable; otherwise require recovery. |
| Consumers assume withdrawal selects a fallback revision. | Expose the cleared active pointer and `WITHDRAWN_ONLY` state explicitly; require a separate user-authorized lifecycle operation to establish an active revision. |

## Rollback and recovery

Rollback means restoring the prior logical lifecycle state, not deleting records or overwriting content.

- A failed registration leaves no registered base.
- A failed first materialization leaves no active revision; any incomplete request is recoverable or marked `RECOVERY_REQUIRED`.
- A failed successor leaves the source active and does not expose a partial successor.
- A failed withdrawal leaves the target active and does not expose a committed withdrawal identity.
- A failed restore leaves the target withdrawn and preserves the committed withdrawal record and recovery content.
- A completed withdrawal is reversed only through `RESTORE_WITHDRAWN_REVISION`, never by deleting its record.
- A completed successor is not erased to recover an earlier state; a subsequent explicit withdrawal/restore transition is required.
- Any contradictory durable state enters `INCONSISTENT` and blocks mutation until an explicit repair/rebuild decision is made.

## Success criteria

The proposal is successful when the implementation and verification can demonstrate that:

- A base is registered once, remains immutable, retains its hash, is readable for deliberation, and is present in every revision’s lineage.
- First materialization produces an `ACTIVE` revision whose content contains all unmodified base content and only approved changes, with source exactly equal to the base identity/hash.
- Successor creation references a real revision identity and exact hash and leaves no more than one active revision.
- Withdrawal creates a persistent identity, preserves recovery content, and keeps the withdrawn revision visible after restart.
- Restore succeeds only from a resolved persistent withdrawal identity; base and unresolved filename cases return the explicit semantic errors and never `WITHDRAWAL_NOT_FOUND`.
- Active resolution returns the persisted active identity and is unaffected by filename ordering or renaming of a locator.
- Inventory rebuild detects multiple active revisions, broken lineage, missing content, and hash conflicts instead of silently selecting a result.
- Rebuilding in a fresh process over unchanged durable records reproduces identical logical state, identities, relationships, and active selection.
- Retries of committed requests/results are idempotent and do not create duplicate revisions, withdrawals, or active pointers.

## Technical-design decisions still open

These are intentionally deferred implementation/product decisions; they must not weaken the semantic contract above:

1. The durable representation and storage location for base content, immutable revision content, withdrawal recovery content, request records, results, and inventory projections.
2. Whether content hashes are fixed to SHA-256 for compatibility or abstracted behind a versioned content-hash contract.
3. The canonical content-normalization boundary used before hashing, provided the stored hash always verifies the stored content.
4. Whether repeated withdrawal/restore cycles for one revision are allowed and how their multiple historical `Withdrawal` records are ordered.
5. The approval provenance required for approved changes and how scientific decisions map to that evidence.
6. The compatibility and migration policy for existing filename-derived r01/r02 records, the fixed CREDA source, and persisted withdrawal directories.
7. Whether output filename conflicts are resolved by rejection only or may be resolved by an explicitly user-approved new locator; identity must remain unchanged either way.
8. The public inventory shape and transport vocabulary for `SUPERSEDED`, `WITHDRAWN_ONLY`, `INCONSISTENT`, and recovery-required states.
9. The retention and integrity policy for restored withdrawal records and historical recovery content.
10. The concurrency boundary used to serialize transitions for one workspace.
11. Whether scientific evidence may reference `SUPERSEDED` or `WITHDRAWN` revisions for historical deliberation, and which operations must require the active revision.


## Proposal question round

The semantic contract is sufficiently specified for downstream specification work, but these product questions should be confirmed before implementation decisions are finalized. They are intended to uncover business rules, implications, impact, edge cases, and product tradeoffs—not delivery mechanics:


1. Should a successor always be created from the currently active revision, or may an explicitly authorized user create a new successor from a superseded historical revision?
2. Should every existing project be required to register the fixed CREDA document as its immutable base, or is base registration only mandatory for new lifecycles while legacy projects remain compatibility-readable?
3. May deliberation continue to cite superseded or withdrawn revisions as historical evidence, and what should happen when a materialization request is based on such evidence?

## Recommendation

Adopt this semantic contract as the proposal baseline. Resolve the remaining open product choices—legacy base registration and historical-evidence usage in particular—before defining storage adapters or migration behavior. No source, test, existing proposal document, or `.paper-proposal-v2` persistent state is changed by this artifact.
