# Exploration: Proposal Lifecycle Base Revisions

## Scope and evidence

This is a read-only lifecycle reconnaissance for Paper Proposal V2. No functional source, proposal document, test, or existing `.paper-proposal-v2` state was modified. Only this OpenSpec exploration artifact was written.

Engram was unavailable and the executor did not have a CodeGraph execution tool; targeted repository searches and reads were used after loading the injected skills. Existing OpenSpec context was read, including `scientific-reasoning-workflow` and `safe-managed-revision-withdrawal` artifacts.

Primary evidence:

- `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts`
- `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts`
- `.pi/extensions/paper-proposal-v2/intent-resolver.ts`
- `.pi/extensions/paper-proposal-v2/orchestrator.ts`
- `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`
- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/materialization-planner.ts`
- `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts`
- `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts`
- `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts`
- `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts`
- `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`
- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts`
- `.pi/extensions/paper-proposal-v2/derived-state-store.ts`
- `.pi/extensions/proposal-workspace.ts`
- `tests/paper-proposal-v2-revision-lifecycle.test.mjs`
- `tests/paper-proposal-v2-scientific-entry.test.mjs`
- `tests/paper-proposal-v2-scientific-materialization.test.mjs`
- `tests/paper-proposal-v2-restart-persistence.test.mjs`
- current repository `.paper-proposal-v2` artifacts and `proposals/research-concept-r01.md`

## Executive finding

The lifecycle implementation is strong for a valid withdrawn `r02+` record, but the project-level revision inventory and the restore classifier do not share a complete model of base, active, and withdrawn history.

The immediate root cause of the observed `WITHDRAWAL_NOT_FOUND` class of failure is:

1. `RESTORE_WITHDRAWN_REVISION` is selected by explicit operation before any document-state loading.
2. The restore branch accepts a syntactically valid managed filename, including `research-concept-r01.md`.
3. `findWithdrawal()` searches only completed withdrawal records and requires metadata identity equality.
4. `r01` is intentionally never a valid withdrawal record, so restoring it produces the generic `WITHDRAWAL_NOT_FOUND` result instead of a base/not-withdrawn classification.

Separately, `readCanonicalManagedRevisionInventory()` scans only public managed files and always returns the highest public revision as the sole `activeRevisions` entry while returning `withdrawnRevisions: []`. Therefore persisted withdrawn history is available to direct lifecycle restore, but is invisible to scientific project-entry resolution after restart or re-entry.

There are two meanings of “base” that must not be conflated:

- The fixed legacy source `proposals/matematica_propuesta_CREDA.md`, accepted only by legacy `derive`/`derive_revision` in `.pi/extensions/proposal-workspace.ts:49,451,4970-4973,5020-5023`.
- Managed revision base `research-concept-r01.md`, parsed as lineage `ROOT`, revision `r01`, and explicitly blocked from withdrawal by `parseManagedRevisionFilename`/`discoverManagedRevision` at `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts:36-44,111-114`.

## Persistent state and current entities

### Public and derived lifecycle artifacts

For each managed revision, the lifecycle inventory is exactly three public artifacts, constructed by `lifecyclePublicRelativePaths()`:

```text
proposals/<managed-filename>
.paper-proposal-v2/state/<managed-filename>.json
.paper-proposal-v2/receipts/<managed-filename>.json
```

Evidence: `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts:47-55` and `.pi/extensions/paper-proposal-v2/derived-state-store.ts:5-7`.

Derived state is a manifest plus structural/reference/symbol/concept indexes. Its identity is bound to document filename, parser version, document SHA, index hashes, byte ranges, and entry text hashes. A committed state additionally requires a matching publication receipt. Evidence: `.pi/extensions/paper-proposal-v2/derived-state-store.ts:5-10`.

The document/state/receipt entities use these identifiers:

- `filename`: managed basename such as `research-concept-r01.md` or `research-concept-r02.md`.
- `lineage`: `ROOT` or the filename slug.
- `revision`: `r01`, `r02`, etc.
- `revisionNumber`: numeric suffix parsed from filename.
- `documentSha256`: complete managed document identity.
- `sourceFilename`/`sourceRevision`: predecessor identity recorded in successor receipts and withdrawal metadata.
- `operationId`: UUID for a withdrawal transaction, independent of the managed filename.
- Derived structural `entryId`s: content/index selectors, not lifecycle identities.

Types: `.pi/extensions/paper-proposal-v2/types.ts:35-72`; lifecycle identity parsing: `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts:11-20,36-44`.

### Withdrawn revision persistence

Withdrawals persist under:

```text
.paper-proposal-v2/withdrawn/<operation-id>/
  metadata.json
  audit-marker.json
  artifacts/
    proposals/<filename>
    .paper-proposal-v2/state/<filename>.json
    .paper-proposal-v2/receipts/<filename>.json
  public-backup/
    proposals/<filename>
    .paper-proposal-v2/state/<filename>.json
    .paper-proposal-v2/receipts/<filename>.json
```

Path constructors: `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts:57-62`; transaction paths and artifact moves: `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts:44-46,123-163`.

`metadata.json` persistently records `requestedFilename`, `revision`, `documentSha256`, `sourceFilename`, `sourceRevision`, reason, three artifact hashes, inventory digest, and `preWithdrawalLatestFilename`. Validation requires exact metadata keys and rejects `revisionNumber === 1`. Evidence: `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts:10,156-170`.

The current repository contains a completed withdrawal record:

```text
.paper-proposal-v2/withdrawn/1ebc189c-da54-4b94-9d26-ea3e68a71adb/
```

Its metadata identifies:

```text
operationId: 1ebc189c-da54-4b94-9d26-ea3e68a71adb
requestedFilename: research-concept-r02.md
revision: r02
sourceFilename: research-concept-r01.md
sourceRevision: r01
```

Its `audit-marker.json` is `WITHDRAW_REVISION`, `COMMITTED`, with both audit statuses `PASS` in the observed persisted artifact. The public repository currently exposes `proposals/research-concept-r01.md`; the r02 document/state/receipt appear in the withdrawal `artifacts/` and `public-backup/` trees rather than the public paths. The observed public r01 state is `.paper-proposal-v2/state/research-concept-r01.md.json`; the repository has no public r01 receipt at the queried path (`.paper-proposal-v2/receipts/research-concept-r01.md.json` returned `ENOENT`), which is compatible with the existing special allowance for initial `r01` in `runConsistencyAudit`.

### Scientific authoritative state

Scientific state is separate from document lifecycle state:

```text
.paper-proposal-v2/scientific/
  manifest.json
  snapshot.json
  events/<sequence>-<event-id>.json
  materializations/index.json
  materializations/<materialization-id>.json
  transactions/<transition-id>.json
  projections/entry-index.json
```

Layout: `.pi/extensions/paper-proposal-v2/scientific-state-store.ts:130-143`. The store validates versioned snapshot/events, causal continuity, transaction markers, materialization records, and projections on restart. It is project-level and does not belong to the three-artifact revision withdrawal inventory.

Scientific entities and identifiers include `ProjectEntry`, `ScientificThreadId`, `ScientificEventId`, `ScientificDecisionId`, `MaterializationId`, `RevisionEvidence { filename, revision, documentSha256 }`, and `MaterializationRecord`. Evidence: `.pi/extensions/paper-proposal-v2/scientific-domain.ts:14-18,103-129,139-169,192-204`; materialization layout and validation: `.pi/extensions/paper-proposal-v2/scientific-state-store.ts:130-143, readValidated()`.

## Current representation and resolution behavior

### Active and withdrawn revisions

`latestManagedFilename()` scans only public `proposals/` managed files and selects the greatest numeric revision, with filename lexical tie-breaking: `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts:100-108`.

`readCanonicalManagedRevisionInventory()` scans public managed documents, validates each public derived state, sorts them, and returns only the latest as `activeRevisions`; it always returns an empty `withdrawnRevisions` array: `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts:220-244`.

This means the current filesystem can contain a durable withdrawn r02 record while the canonical scientific inventory reports:

```text
activeRevisions: [r01]
withdrawnRevisions: []
```

The type and resolver support withdrawn evidence abstractly, but the filesystem adapter does not populate it. `ProjectEntryResolver` validates the supplied port, rejects more than one active revision, returns `ACTIVE_PROPOSAL` for one active revision, `WITHDRAWN_ONLY` only when the port reports withdrawn history with no active revision, and `EMPTY_PROJECT` otherwise: `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts:77-104,212-270`.

### First materialization versus successor creation

`MaterializationPlanner.sourceFor()` chooses operation from frozen decision revision evidence:

- all selected decisions have no `revisionEvidence` and no supplied document state → `CREATE_R01`;
- all selected decisions have the same revision evidence and the supplied state matches it exactly → `CREATE_SUCCESSOR`;
- mixed, missing, or mismatched evidence → blocked.

Evidence: `.pi/extensions/paper-proposal-v2/materialization-planner.ts:37-49,109-151`.

`CREATE_R01` is rendered by `InitialRevisionRenderer.render()`, which creates a new minimal Markdown document from canonical metadata and accepted claims, targeting exactly `research-concept-r01.md`/`r01`; it does not read or inherit the fixed CREDA base: `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts:15-43`.

`CREATE_SUCCESSOR` uses the supplied frozen `DocumentState` and exact `RevisionEvidence`, then creates an ordered patch payload: `.pi/extensions/paper-proposal-v2/successor-edit-planner.ts:20-49`; the candidate executor requires the exact source identity and applies patches in memory: `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts:35-46,62-105`.

Publication dispatches `CREATE_R01` to guarded `publishInitial()` and `CREATE_SUCCESSOR` to guarded `publishApprovedSuccessor()`: `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts:54-83`. Initial publication calls `createInitialProposal()` and only permits slug `r01`: `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts:21-66`; `.pi/extensions/proposal-workspace.ts:4336-4369`.

Successor publication derives the next filename from the source filename, requires a same-lineage valid transition, verifies latest source/SHA, and atomically creates a new target: `.pi/extensions/proposal-workspace.ts:4867-4871,4873-4952`; adapter entry: `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts:69-91`.

### Restore selection and `WITHDRAWAL_NOT_FOUND`

`findWithdrawal()` supports either a strict operation ID or a managed filename. Filename lookup scans `.paper-proposal-v2/withdrawn/`, validates each UUID directory, metadata, committed withdrawal marker, immutable artifact hashes, state identity, and receipt identity, then filters by `metadata.requestedFilename`: `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts:173-215`.

It returns:

- `WITHDRAWAL_IDENTITY_REQUIRED` when neither identity is supplied;
- `WITHDRAWAL_LOOKUP_AMBIGUOUS` when a filename matches multiple completed records;
- `WITHDRAWAL_NOT_FOUND` when the withdrawal root is absent or no valid record matches.

A base `r01` can pass the filename syntax parser in `findWithdrawal()`, but no valid withdrawal metadata can represent it because `validateWithdrawalMetadata()` rejects revision 1. Therefore a restore request aimed at `r01` reaches lookup and ends as `WITHDRAWAL_NOT_FOUND`, rather than a base/not-withdrawn-specific result.

`RevisionLifecycleTransaction.restore()` calls `findWithdrawal()` before acquiring the lifecycle mutation lock and before any public move; failed lookup is returned as a blocked result: `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts:183-190`.

### Restart behavior

The durable withdrawal operation ID, metadata, immutable artifacts, and marker survive a fresh transaction/runtime instance. `restore({ operationId })` can rediscover the record from disk. Existing lifecycle tests prove retry after rollback and exact restore, but they use temporary roots and do not exercise project-entry inventory reconstruction from the real withdrawn directory.

The scientific store also reloads authoritative state/materialization records from `.paper-proposal-v2/scientific/` on a fresh `ScientificWorkflowRuntime`: `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts:47-75,124-149`.

The gap is that restart/re-entry through `readCanonicalManagedRevisionInventory()` loses withdrawn-history visibility because it scans public files only. Thus lifecycle restore survives restart by operation ID, while scientific entry resolution does not retain the same withdrawn identity.

### Filename and identity dependencies

Current identity is mixed:

- withdrawal operation identity is a UUID directory plus metadata, independent of filename;
- withdrawal lookup by filename depends on `requestedFilename`;
- managed revision identity is parsed from filename (`lineage`, numeric suffix, predecessor filename);
- successor naming is derived from filename via `nextSuccessorTarget()`;
- scientific `RevisionEvidence` requires filename, revision, and document SHA;
- active selection is inferred from public filename sorting.

Consequently, the implementation has a persistent operation identity independent of filename, but the domain’s revision identity and active resolution remain filename-derived. Renaming a managed artifact is not an identity-preserving operation under the current contracts.

## Exact route that classifies a base artifact as restore

For an explicit request such as:

```text
{ operation: "RESTORE_WITHDRAWN_REVISION",
  sourceFilename: "research-concept-r01.md" }
```

or a request carrying a base filename plus restore language, the exact route is:

```text
paper_proposal_v2_execute
  -> proposal-workspace.ts:resolveGlobalRoute()
     explicitLifecycle = true because operation is in LIFECYCLE_OPERATIONS
     -> stage LIFECYCLE
  -> registered tool execute()
     lifecycle route is invoked outside productionRuntime.withContext()
  -> PaperProposalV2Orchestrator.execute()
     request.operation overrides resolveIntent()
     -> lifecycle branch before stateLoader/planner/roles/model
     -> sourceFilename syntax check accepts managed r01 form
     -> lifecycle.restore({ filename: "research-concept-r01.md" })
  -> RevisionLifecycleTransaction.restore()
  -> findWithdrawal({ projectRoot, filename: "research-concept-r01.md" })
     -> parseManagedRevisionFilename() accepts r01 syntax
     -> scan completed withdrawal records
     -> metadata.requestedFilename is r02, not r01
     -> matches.length === 0
     -> throw WITHDRAWAL_NOT_FOUND
  -> blocked lifecycle public projection
```

Source references: `.pi/extensions/proposal-workspace.ts:5333-5334,5378-5389,5480-5525`; `.pi/extensions/paper-proposal-v2/orchestrator.ts:13-36`; `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts:183-190`; `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts:36-44,173-215`.

Natural language alone does not classify a generic phrase such as “restore the base”: `intent-resolver.ts:lifecycleIntent` requires restore language plus a managed filename, revision reference, or operation ID at `.pi/extensions/paper-proposal-v2/intent-resolver.ts:8-16`. The explicit typed operation is what forces the base artifact through the restore route.

## Current-state machine

```text
                         explicit idea/act
        +------------------------------------------------+
        |                                                v
   EMPTY_PROJECT ------------------------------> SCIENTIFIC_ONLY
        |                                                |
        | explicit materialization, no revision evidence |
        v                                                v
   CREATE_R01 plan ---------------------------> ACTIVE r01
        ^                                                |
        |                                                | successor edit/materialization
        |                                                v
 fixed CREDA base --legacy derive----------> ACTIVE rNN (highest public file)
                                                     |
                       valid r02+ withdrawal         |
                                                     v
                                  WITHDRAWN(rNN, operationId, metadata, artifacts)
                                                     |
                                  restore by operationId or unique filename
                                                     v
                                  ACTIVE rNN restored; quarantine retained

 public scan with >1 managed revision ---> latest() chooses one highest file
 scientific inventory with >1 supplied active ---> MULTIPLE_ACTIVE_REVISIONS
 malformed authoritative evidence -------> INCONSISTENT_PROJECT
 missing active + withdrawn evidence ----> WITHDRAWN_ONLY (only if inventory port supplies it)
 missing withdrawal identity ------------> WITHDRAWAL_IDENTITY_REQUIRED
 base/non-withdrawn restore lookup ------> WITHDRAWAL_NOT_FOUND
```

Important current-state distinction: the fixed CREDA base is not a managed revision and is never a valid lifecycle withdrawal record. Managed r01 is the initial/base revision and is not withdrawable, but the explicit restore route can still classify its filename as restore before failing at withdrawal lookup.

## Current transition table

| Origin | Event | Condition | Current operation | Destination/result |
|---|---|---|---|---|
| Fixed CREDA base | Legacy derivation | `base === matematica_propuesta_CREDA.md`; bounded candidate valid | `derive` / `derive_revision` | New managed `research-concept-<slug>-rNN.md` public artifact; no lifecycle identity for the base |
| No managed revision, no scientific state | Scientific entry | validated absence | project entry resolution | `EMPTY_PROJECT` |
| No managed revision, scientific state present | Scientific entry | authoritative scientific records validate | project entry resolution | `SCIENTIFIC_ONLY` |
| Scientific-only accepted candidate | Explicit materialization | all selected decisions have no revision evidence | `CREATE_R01` | Frozen r01 candidate, then guarded initial publication |
| Exactly one active managed revision | Entry resolution | public inventory reports one active revision | project entry resolution | `ACTIVE_PROPOSAL` or `ACTIVE_SCIENTIFIC_PROJECT` |
| Active revision with matching frozen evidence | Explicit materialization | supplied source matches filename/revision/SHA | `CREATE_SUCCESSOR` | New same-lineage successor; prior public file remains present |
| Active r02+ revision | Withdrawal request | document/state/receipt/source/dependencies validate; no later dependent revision | `WITHDRAW_REVISION` | Three public artifacts moved to backup; immutable quarantine record committed; prior public revision becomes latest |
| Active r01/base revision | Withdrawal request | `revisionNumber === 1` | `WITHDRAW_REVISION` | Blocked `BASE_REVISION_WITHDRAWAL_BLOCKED`; no mutation |
| Withdrawn durable record | Restore request | operation ID or unique filename identifies a valid committed record | `RESTORE_WITHDRAWN_REVISION` | Exact three artifacts restored; quarantine retained; restored revision becomes latest |
| Base r01 or non-withdrawn filename | Restore request | syntax accepted but no matching completed withdrawal metadata | `RESTORE_WITHDRAWN_REVISION` | Blocked `WITHDRAWAL_NOT_FOUND` |
| Withdrawal root absent | Restore request | no operation ID and filename lookup cannot scan root | `RESTORE_WITHDRAWN_REVISION` | Blocked `WITHDRAWAL_NOT_FOUND` |
| Filename matches multiple withdrawal records | Restore request | filename lookup not unique | `RESTORE_WITHDRAWN_REVISION` | Ambiguous result; asks for exact operation ID |
| Public managed set contains several revisions | Latest resolution | current scanner sorts public filenames | `latestManagedFilename` / `PaperProposalV2Orchestrator.latest` | Highest numeric filename selected; no multiple-active state from the filesystem adapter |
| Inventory port reports >1 active | Scientific entry | resolver receives multiple active evidence | project entry resolution | `MULTIPLE_ACTIVE_REVISIONS` with recovery required |
| Active absent, withdrawn evidence supplied | Scientific entry | resolver receives non-empty `withdrawnRevisions` | project entry resolution | `WITHDRAWN_ONLY` |
| Active absent, withdrawn evidence omitted | Scientific entry | current filesystem inventory behavior | project entry resolution | `EMPTY_PROJECT` or `SCIENTIFIC_ONLY`, depending scientific state; withdrawn history is lost from entry resolution |

## Invariant gap assessment

| Invariant | Current observation | Assessment |
|---|---|---|
| Base != withdrawn revision | Withdrawal rejects r01 and metadata validation rejects revision 1. Restore syntax accepts r01 and only later fails lookup. Fixed base has no lifecycle record. | Partially enforced; base restore is misclassified and reports generic not-found rather than a domain distinction. |
| Restore needs persistent withdrawn identity | Operation ID and metadata persist and are validated; filename lookup can rediscover a valid record. | Satisfied for direct lifecycle restore; not integrated into canonical project-entry inventory. |
| First materialization from base with no active revision | `sourceFor()` selects `CREATE_R01` only with no revision evidence and no supplied source. Initial renderer creates a fresh r01 document from accepted claims/metadata, not from `matematica_propuesta_CREDA.md`. | Current behavior is “first materialization with no active managed revision,” not “materialization from the fixed base.” The distinction is undocumented in the runtime model and needs explicit product semantics. |
| Max one active revision | `ProjectEntryResolver` rejects >1 only if its port reports them. Filesystem inventory and `latest()` collapse public files to one highest filename, so they cannot detect multiple active revisions. | Gap in the filesystem authority; synthetic resolver tests do not prove the real inventory. |
| Identity independent of filename | Withdrawal UUID is independent of filename, but managed identity, predecessor, successor target, scientific revision evidence, and active selection all depend on filenames. | Partially satisfied only at operation-record level; not a general revision identity invariant. |
| Restart survives | Withdrawal record and scientific records are durable; restore by operation ID survives a new transaction/runtime. Public inventory after restart still ignores withdrawn records; in-memory `idempotencySelections` is only a session retry alias. | Lifecycle restore persistence is strong; project-entry/history reconstruction is incomplete. |

## Tests currently present, missing, or expected to expose the gaps

### Existing coverage

`tests/paper-proposal-v2-revision-lifecycle.test.mjs` covers lifecycle intent precedence, base withdrawal blocking, missing/inconsistent artifacts, missing source, dependent revisions, quarantine, exact restore, pending-audit markers, rollback injection, restore retry, public projection, and repository-fixture isolation. Relevant tests are at lines `83-100`, `102-130`, `145-175`, `177-205`, `207-318`, `320-395`, and `397-450`.

`tests/paper-proposal-v2-scientific-entry.test.mjs:55-63` covers resolver vocabulary using a mocked inventory, including `WITHDRAWN_ONLY` and `MULTIPLE_ACTIVE_REVISIONS`. It does not exercise `readCanonicalManagedRevisionInventory()` against a real withdrawn directory.

`tests/paper-proposal-v2-scientific-materialization.test.mjs:93-129` covers initial and successor planner selection, exact source evidence, stale-source blocking, and deterministic payloads. It does not test a fixed-base artifact as the first materialization source.

`tests/paper-proposal-v2-restart-persistence.test.mjs:3-5` covers fresh runtime reload and stale-source behavior for ordinary document publication, not withdrawn-history entry resolution or restore selection after process restart.

### Missing or expected-failing tests

The following focused tests are absent and would expose the lifecycle gaps:

1. **Real inventory includes withdrawn identity:** withdraw r02 in a temporary root, call `readCanonicalManagedRevisionInventory()`, and require `activeRevisions: [r01]` plus `withdrawnRevisions: [r02]`. Current implementation is expected to return an empty withdrawn list.
2. **Re-entry after restart preserves withdrawn-only/history state:** use a fresh `ProjectEntryResolver` with the real canonical inventory after withdrawal. Current adapter cannot report withdrawn history; it will resolve as active-only or empty/scientific-only depending public files.
3. **Base restore is rejected as base/not-withdrawn:** request `RESTORE_WITHDRAWN_REVISION` for `research-concept-r01.md`. Current behavior is expected to return `WITHDRAWAL_NOT_FOUND`, not a base-specific state/result.
4. **Fixed base versus managed r01:** with `matematica_propuesta_CREDA.md` present and no active managed revision, explicitly materialize and assert the intended source semantics. Current `CREATE_R01` path does not read the fixed base and would produce the renderer’s new minimal document.
5. **Multiple public active revisions are not collapsed:** create two valid independent public managed revisions and call the real canonical inventory. Current implementation is expected to return only the numerically latest revision rather than `MULTIPLE_ACTIVE_REVISIONS`.
6. **Filename-independent identity:** rename or alias a managed artifact while preserving bytes and persisted identity, then test whether it remains the same revision. Current filename validation and receipt/state binding are expected to reject it or treat it as a different/invalid identity.
7. **Fresh-process restore by filename and operation ID:** withdraw r02, construct a new lifecycle transaction/runtime, and restore once by operation ID and once by unique filename. Existing tests cover the same logical behavior but not a fresh process/re-entry inventory boundary.
8. **Scientific evidence after withdraw/restore:** attach a scientific thread to r02, withdraw it, restart, and verify the result blocks or explicitly reports withdrawn/stale evidence rather than silently treating the project as r01-only. Existing scientific audit tests cover stale hash evidence, but not the real withdrawal inventory transition.

No tests were executed in this exploration, so “expected-failing” means predicted from the inspected control flow, not a fresh test-run result.

## High-level corrected state machine (no implementation design)

```text
BASE_DOCUMENT
  | explicit first materialization
  v
ACTIVE_REVISION(r01)
  | explicit successor creation
  v
ACTIVE_REVISION(rN)
  | valid withdrawal of rN (never r01)
  v
WITHDRAWN_REVISION(identity = operationId + revision + filename + SHA)
  | restore only by persistent withdrawn identity
  v
ACTIVE_REVISION(same identity restored)

ACTIVE_REVISION(rN) --successor--> ACTIVE_REVISION(rN+1)

(no active revision + withdrawn history) --> WITHDRAWN_ONLY
(no active revision + no history)        --> EMPTY_PROJECT or SCIENTIFIC_ONLY
(more than one active revision)          --> MULTIPLE_ACTIVE_REVISIONS
(identity/evidence conflict)             --> INCONSISTENT_PROJECT
```

The corrected lifecycle vocabulary must keep the fixed base, managed r01, active revisions, withdrawn records, and scientific state as distinct concepts. Restore must select an existing persistent withdrawn identity; it must never turn a base artifact into a withdrawal record or infer restoration from a filename alone.

## Risks

- The current filesystem inventory can silently erase withdrawn history from scientific entry decisions while direct restore remains possible.
- A generic `WITHDRAWAL_NOT_FOUND` for base restore obscures whether the artifact was never withdrawable, was never withdrawn, or has lost its persistent record.
- Filename-derived identity makes rename/re-key behavior ambiguous and can attach scientific evidence to the wrong lifecycle concept if not blocked.
- The fixed CREDA base and managed r01 have different creation/lifecycle contracts but are both informally called “base,” creating product-state ambiguity.
- Existing tests are comprehensive for the original lifecycle feature but mostly use mocked inventory ports or same-process temporary fixtures, leaving the filesystem-to-project-entry boundary under-tested.
