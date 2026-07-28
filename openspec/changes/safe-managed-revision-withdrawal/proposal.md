# Proposal: Safe Managed Revision Withdrawal

## Intent

Add two public Paper Proposal V2 operations, `WITHDRAW_REVISION` and `RESTORE_WITHDRAWN_REVISION`, so users can reversibly withdraw a managed revision without confusing the request with content deletion or risking an inconsistent proposal state.

An explicit request such as `Retira la revisión administrada \`research-concept-r02.md\`.` must resolve to `WITHDRAW_REVISION`, never `DELETE`. Because the filename identifies the target unambiguously, the operation must make zero model, planner, tutor, reviewer, or product-level subagent calls.

## Scope

### Withdrawal

- Classify natural-language withdrawal requests as `WITHDRAW_REVISION`.
- Do not provide a `DELETE` fallback for withdrawal requests.
- Permit withdrawal only for managed `r02+` revisions; `r01`/the base revision always blocks.
- Before changing anything, verify that:
  - the file exists;
  - its managed state and receipt exist;
  - filename, revision, and SHA agree across document, state, and receipt;
  - no later dependent revision exists; and
  - the prior source revision exists.
- Block without publication when any artifact is missing, inconsistent, dependent, or otherwise fails validation.
- Atomically quarantine all exclusive revision artifacts under `.paper-proposal-v2/withdrawn/<operation-id>/`.
- Preserve document/state/receipt/manifest-exclusive metadata and write `metadata.json` containing timestamp, SHA, source revision, and reason.
- Update the published/latest view coherently without irreversible deletion.
- Run `ConsistencyAudit` and `SelfAudit`; report success only when both pass.

### Restoration

- Add a public restore operation that restores the exact withdrawn revision and its metadata atomically.
- Preserve the same managed-state, receipt, manifest, and audit invariants as withdrawal.
- Expose only the defined public response fields for withdrawal: `status`, `operation`, `withdrawnFilename`, `restoredLatestFilename`, `artifactCount`, `backupLocation`, `auditStatus`, `selfAuditStatus`, and `warnings`.

### Testing

- Use temporary roots exclusively.
- Do not modify the real `proposals/` directory.
- Do not withdraw `research-concept-r02.md` during tests.
- Cover required cases 1–10, including:
  1. explicit filename classification as `WITHDRAW_REVISION`;
  2. explicit withdrawal performs no model/planner/tutor/reviewer/subagent calls;
  3. content request `elimina esta sección` remains `DELETE`;
  4. semantic request `retira la revisión r02` resolves to `WITHDRAW_REVISION`;
  5. `r01`/base withdrawal blocks;
  6. missing or inconsistent managed artifacts block;
  7. later dependent revisions block;
  8. successful withdrawal quarantines all exclusive artifacts, updates latest coherently, and passes both audits;
  9. deterministic move failure rolls back atomically with no partial quarantine/publication;
  10. restoration returns the exact revision and metadata atomically.

## Affected areas

- Paper Proposal V2 public operation classification and dispatch.
- Managed revision/state/receipt/manifest validation.
- Atomic quarantine, rollback, latest-revision publication, and restore transaction handling.
- `ConsistencyAudit` and `SelfAudit` integration and public response shaping.
- Temporary-root integration and regression tests for classification, isolation, failure recovery, withdrawal, and restoration.

## Risks and mitigations

- **Misclassification as deletion:** use explicit withdrawal intent and regression tests for both withdrawal and content-deletion language; never fall back to `DELETE`.
- **State divergence or data loss:** validate all cross-artifact identities before mutation, quarantine rather than delete, and use an atomic transaction with deterministic failure rollback.
- **Restoring the wrong revision:** bind the quarantine metadata to the original filename, revision, SHA, source revision, and operation ID; restore exact stored artifacts only.
- **Incomplete publication:** require both audits to pass before reporting success and preserve recovery information on failure.
- **Accidental production test mutation:** make all tests construct isolated temporary roots and explicitly guard against the real proposal path and the named r02 fixture.

## Rollback and recovery

Withdrawal rollback must restore every artifact and the latest pointer from the pre-operation state if validation, move, publication, `ConsistencyAudit`, or `SelfAudit` fails. A deterministic move-failure hook must prove that no partial quarantine or public-state update remains.

A completed withdrawal is reversible through `RESTORE_WITHDRAWN_REVISION`; restoration must itself be atomic and leave the quarantine copy/metadata available according to the managed recovery contract. No path may irreversibly delete the withdrawn revision.

## Acceptance criteria

1. The two operations are publicly callable and produce the specified operation names and response shape.
2. Explicit managed-filename withdrawal is deterministically classified as `WITHDRAW_REVISION`, never `DELETE`, and makes zero model/planner/tutor/reviewer/subagent calls.
3. Content deletion language remains `DELETE`; revision withdrawal language resolves to `WITHDRAW_REVISION`.
4. Withdrawal of base/r01, missing artifacts, cross-artifact mismatch, missing source revision, or dependent later revisions blocks without publication.
5. A valid r02+ withdrawal atomically quarantines every exclusive artifact below the operation-specific backup location, records the required metadata, updates latest coherently, and passes `ConsistencyAudit` and `SelfAudit`.
6. Move failure and any post-mutation audit failure leave the original public state intact with no partial quarantine.
7. Restoration atomically reinstates the exact withdrawn revision and metadata, with audits and receipt evidence confirming consistency.
8. The complete required test matrix runs only against temporary roots and does not alter `proposals/` or withdraw `research-concept-r02.md`.

## Explicit non-goals

- Irreversible deletion or garbage collection of withdrawn revisions.
- Withdrawal of the base/r01 revision.
- Withdrawal when dependent later revisions exist.
- Automatic repair or inference of missing/inconsistent document, state, receipt, manifest, or SHA data.
- Calling planners, tutors, reviewers, models, or subagents for explicit filename withdrawal.
- Changing unrelated `DELETE` semantics, proposal content editing behavior, or the real repository proposal fixtures.
- Reworking Paper Proposal V2 infrastructure, role contracts, or unrelated operations.

## Success criteria

The feature is successful when a valid managed r02+ revision can be withdrawn and restored losslessly, invalid or unsafe requests block without publication, explicit withdrawal never invokes delegated reasoning, all atomic failure paths recover cleanly, and the required temporary-root test matrix passes with both audits green on successful operations.
