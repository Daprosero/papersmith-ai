# Proposal Lifecycle Specification

## Purpose

Define durable, identity-based lifecycle behavior for one registered proposal base document and its revisions. The lifecycle MUST preserve complete source content, expose a single active revision at most, and retain withdrawn history across restart.

## Requirements

### Requirement: Base document registration and durable persistence

The system MUST allow a workspace to register exactly one immutable base document. A successful registration MUST durably persist the base's stable identity, complete readable content or authoritative content reference, content hash, and registration provenance before reporting success. Base identity and content hash MUST be independent of filename or path.

The system MUST reject a second or conflicting base registration without changing the registered base. A registered base MUST NOT be withdrawn, restored, replaced, or overwritten by lifecycle operations.

#### Scenario: Register one valid base

- GIVEN a workspace with no registered base
- WHEN complete base content, its matching hash, and a stable base identity are registered
- THEN the workspace state is `BASE_REGISTERED`
- AND the durable base record is readable by its identity after restart
- AND no revision or withdrawal record is created.

#### Scenario: Reject conflicting re-registration

- GIVEN a workspace with a registered base
- WHEN a request attempts to register another base or binds the same base identity to different content
- THEN the request is rejected
- AND the existing base identity, content, and hash remain unchanged.

### Requirement: Read-only lifecycle deliberation

Deliberation and lifecycle inspection MUST be able to read the registered base and the unique active revision, including their stable identities, content hashes, and lineage evidence. Read-only deliberation MUST NOT register a base, materialize a revision, change the active pointer, create a withdrawal, or alter durable lifecycle records.

When no active revision exists, the read result MUST explicitly report its absence and the applicable lifecycle state; it MUST NOT select a historical revision by filename, timestamp, or ordering.

#### Scenario: Deliberation reads base and active revision without mutation

- GIVEN a workspace with a registered base and one active revision
- WHEN deliberation requests lifecycle evidence
- THEN it receives the base and active revision identities, hashes, and lineage evidence
- AND no lifecycle record or active pointer changes.

#### Scenario: Deliberation observes withdrawn-only state

- GIVEN a workspace has a registered base, no active revision, and visible withdrawn history
- WHEN deliberation requests lifecycle evidence
- THEN it receives `WITHDRAWN_ONLY` and no active revision
- AND it does not promote a predecessor or restore a withdrawn revision.

### Requirement: First materialization preserves complete base content

The system MUST create a first revision only from the exact registered base identity and content hash. The resulting revision MUST preserve all unmodified base content and apply only explicitly approved changes. Claims, metadata, a filename, or a display label alone MUST NOT substitute for complete base content or its authoritative content reference.

A successful first materialization MUST create an immutable revision with stable identity, exact base lineage evidence, a verified resulting content hash, and the unique active-revision pointer.

#### Scenario: Create the first revision from the base

- GIVEN a registered base with verified complete content and no committed first revision
- WHEN an authorized request materializes approved changes from that exact base identity and hash
- THEN the result is a new active revision whose lineage source is that base
- AND every unmodified portion of the base is present in the revision
- AND no unapproved change is present.

#### Scenario: Reject a metadata-only first materialization

- GIVEN a registered base exists
- WHEN a first-materialization request supplies only claims, metadata, or a filename without resolvable complete base content and matching hash
- THEN the request is rejected
- AND no revision or active pointer is created.

### Requirement: Successor revision creation

The system MUST create a successor only from the unique active revision's stable identity and exact persisted content hash. A successful successor MUST preserve all unmodified source content, apply only explicitly approved changes, retain immutable source lineage, transition the source to `SUPERSEDED`, and make the successor the sole `ACTIVE` revision.

The system MUST reject a successor request that uses a base reference, a filename-only reference, a stale hash, a superseded or withdrawn source, or an unresolved lineage reference.

#### Scenario: Create a successor from the active revision

- GIVEN a workspace has exactly one active revision with verified content and hash
- WHEN an authorized successor request references that exact revision identity and hash
- THEN a new revision is created with that revision as its source
- AND the source becomes `SUPERSEDED`
- AND the successor is the sole active revision.

#### Scenario: Reject a stale or filename-only source

- GIVEN a workspace has an active revision
- WHEN a successor request identifies its source only by filename or uses a non-matching content hash
- THEN the request is rejected
- AND the active revision and its content remain unchanged.

### Requirement: Active revision resolution

The system MUST resolve the active revision from persisted lifecycle state and stable revision identity. It MUST return one active revision only when exactly one valid active revision exists. It MUST NOT derive activity from filename order, revision number, lexical order, timestamps, or locator availability.

The system MUST return an explicit absence when no active revision exists. If durable evidence indicates multiple active revisions, broken lineage, missing required content, or mismatched hashes, the system MUST fail closed with `LIFECYCLE_INVENTORY_INCONSISTENT` and MUST NOT select an active revision.

#### Scenario: Resolve the persisted active identity

- GIVEN durable lifecycle state contains exactly one valid active revision
- WHEN the active revision is resolved
- THEN the result identifies that revision and its verified hash
- AND changing the revision's filename or display locator alone does not change the resolved identity.

#### Scenario: Reject ambiguous active evidence

- GIVEN durable lifecycle evidence identifies more than one active revision
- WHEN the active revision is resolved
- THEN the result is `LIFECYCLE_INVENTORY_INCONSISTENT`
- AND no revision is selected as active.

### Requirement: Active withdrawal yields withdrawn-only state

The system MUST withdraw only a real, non-base, currently active revision with intact content and hash evidence. A successful withdrawal MUST durably create a persistent withdrawal identity and exact recovery evidence, transition the revision to `WITHDRAWN`, clear the active-revision pointer, and set the workspace to `WITHDRAWN_ONLY`.

Withdrawing an active revision MUST NOT promote, reactivate, or otherwise select a predecessor. It MUST preserve the withdrawn revision and its withdrawal identity as visible historical inventory.

#### Scenario: Withdraw the active revision without predecessor promotion

- GIVEN a workspace has an eligible active non-base revision and a superseded predecessor
- WHEN the active revision is successfully withdrawn
- THEN the withdrawn revision has persistent recovery evidence
- AND the active pointer is empty
- AND the workspace state is `WITHDRAWN_ONLY`
- AND the predecessor remains `SUPERSEDED` rather than becoming active.

#### Scenario: Block withdrawal of the base or first revision

- GIVEN a request targets the registered base or immutable first revision
- WHEN withdrawal is requested
- THEN the result is `REVISION_NOT_WITHDRAWABLE`
- AND no withdrawal record, recovery record, or active-pointer change is created.

### Requirement: Restoration requires persistent withdrawal identity

The system MUST restore a revision only when the request resolves to one unique, durable, `COMMITTED` withdrawal identity with verified recovery content, revision identity, hash, and lineage. A successful restore MUST reactivate the exact withdrawn revision, retain the withdrawal record as historical evidence with restored status, and establish exactly one active revision.

A base identity MUST yield `BASE_DOCUMENT_NOT_RESTORABLE`. An existing revision without a committed withdrawal MUST yield `REVISION_NOT_WITHDRAWN`. An unresolved filename or other reference that does not resolve to a persistent withdrawal identity MUST yield `WITHDRAWAL_IDENTITY_NOT_FOUND`. The system MUST NOT emit generic `WITHDRAWAL_NOT_FOUND` for these cases.

#### Scenario: Restore through a valid persistent withdrawal identity

- GIVEN a committed withdrawal record with verified recovery content for a withdrawn revision
- WHEN restoration references that withdrawal identity
- THEN the exact withdrawn revision becomes active
- AND the withdrawal record remains durable historical evidence
- AND no new revision is created.

#### Scenario: Reject a base or unresolved filename as restoration authority

- GIVEN a request identifies either the registered base or a filename that does not resolve to a committed withdrawal identity
- WHEN restoration is requested
- THEN no lifecycle state changes
- AND the result is respectively `BASE_DOCUMENT_NOT_RESTORABLE` or `WITHDRAWAL_IDENTITY_NOT_FOUND`
- AND the result is not `WITHDRAWAL_NOT_FOUND`.

### Requirement: Restart inventory reconstruction

The system MUST reconstruct lifecycle inventory from durable base, revision, materialization, and withdrawal evidence before using derived caches or filenames. Reconstruction MUST include active, superseded, and withdrawn revisions; persistent withdrawal identities; and the registered base.

Over unchanged valid durable evidence, reconstruction after restart MUST produce the same logical state, stable identities, lineage relationships, inventory membership, and active resolution. Missing content, duplicate identities, contradictory transitions, orphan withdrawals, invalid hashes, invalid lineage, or multiple active revisions MUST produce `LIFECYCLE_INVENTORY_INCONSISTENT` without inventing, deleting, or silently repairing records.

#### Scenario: Reconstruct withdrawn-only state after restart

- GIVEN a workspace has a durable base, a committed withdrawal, and no active revision
- WHEN a fresh process rebuilds the lifecycle inventory
- THEN the inventory includes the base, withdrawn revision, and withdrawal identity
- AND the reconstructed workspace state is `WITHDRAWN_ONLY`
- AND no predecessor is inferred as active.

#### Scenario: Fail closed for contradictory durable records

- GIVEN durable lifecycle records contain conflicting active states or a missing required content artifact
- WHEN lifecycle inventory is rebuilt
- THEN the result is `LIFECYCLE_INVENTORY_INCONSISTENT`
- AND no active revision is selected or synthesized.

### Requirement: Identity is distinct from filename

The system MUST treat base, revision, and withdrawal identities as durable domain identities independent of filenames, paths, revision labels, and display names. A filename MAY locate or present an artifact but MUST NOT prove revision identity, lineage, withdrawal authority, or active status.

A filename collision with a different durable artifact MUST be rejected without overwriting either artifact. Loss or change of an optional locator MUST be handled as locator evidence, not as replacement, deletion, or regeneration of the underlying identity.

#### Scenario: Locator changes do not change revision identity

- GIVEN a revision has a valid stable identity and verified content
- WHEN its filename or presentation locator differs from a prior locator while durable identity evidence remains valid
- THEN lifecycle resolution retains the same revision identity
- AND it does not create a second revision or change active status solely because of the locator.

#### Scenario: Reject a conflicting filename locator

- GIVEN a requested filename is already bound to a different durable artifact identity
- WHEN materialization or restoration requests that locator
- THEN the result is `OUTPUT_FILENAME_CONFLICT`
- AND neither artifact is overwritten or silently renamed.

### Requirement: Atomic and idempotent lifecycle transitions

The system MUST atomically persist every successful registration, materialization, successor creation, withdrawal, and restoration with all affected lifecycle records, content evidence, request identity, result identity, and active-pointer state. The system MUST report success only when restart can reconstruct the same completed logical outcome.

A repeated request with the same request identity and equivalent input MUST return the original committed outcome without creating duplicate bases, revisions, withdrawals, or active pointers. A conflicting reuse of a request identity MUST be rejected. An interrupted operation MUST resolve to a validated committed outcome, a safely resumable state, or an explicit recovery-required outcome; it MUST NOT expose a partial successful transition.

#### Scenario: Retry a committed successor idempotently

- GIVEN a successor materialization request has committed
- WHEN the same request identity and equivalent input are retried, including after restart
- THEN the original result and revision identity are returned
- AND no additional successor or active pointer is created.

#### Scenario: Interrupted withdrawal does not expose partial state

- GIVEN a withdrawal is interrupted before all required lifecycle evidence is committed
- WHEN the workspace is reopened
- THEN it exposes either the validated pre-withdrawal state, the validated committed withdrawal outcome, or an explicit recovery-required state
- AND it does not expose a partially withdrawn revision as a successful result.

## Acceptance Criteria

- A workspace can durably register one immutable, readable base document with a stable identity and verified content hash.
- Read-only deliberation can inspect the registered base and active revision without lifecycle mutation.
- The first revision demonstrably preserves complete base content except for explicitly approved changes and records exact base lineage.
- A successor requires the exact active revision identity and hash, leaves one active revision, and preserves immutable historical content.
- Active resolution is state- and identity-based, never filename-order-based, and fails closed on inconsistent evidence.
- Withdrawing an active eligible revision clears the active pointer and yields `WITHDRAWN_ONLY` without predecessor promotion.
- Restoration succeeds only through a valid persistent withdrawal identity; base, non-withdrawn, and unresolved references receive their specific semantic errors.
- A fresh process rebuilds the same valid lifecycle inventory, including withdrawn history and withdrawal identities, or explicitly reports inconsistency.
- Locator changes do not redefine durable identity, and locator conflicts do not overwrite artifacts.
- Retried committed operations are idempotent and interrupted operations never report a partial transition as successful.
