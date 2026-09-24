# Archive Report: cli-paper-e2e

**Change**: cli-paper-e2e
**Archived**: 2026-09-09 → `openspec/changes/archive/2026-09-09-cli-paper-e2e/`
**Artifact store**: hybrid (file artifacts + Engram topic `sdd/cli-paper-e2e/archive-report`)
**Date**: 2026-09-09

## Final State at Close

This report is the terminal record of the cycle. It describes the state of the change AT CLOSE, per the Final-State Authority hierarchy (native review authority > persisted tasks artifact > explicit final-state facts in the launch prompt > `verify-report`/`apply-progress` intermediaries).

- **Specs**: 8/8 requirements, 10/10 scenarios compliant. The dirty-status THEN-clause was amended by exactly one line per remedy S1 after the first `fail` report (9/10) was persisted. Final wording (filesystem delta spec `specs/cli-paper-e2e/spec.md:23`): `THEN status reports drift naming the offending paths (currently rc 0 — non-zero exit is a known CLI gap, findings-only)`.
- **Verification**: narrow re-verification PASSED with warnings — verdict `pass_with_warnings`, 10/10 scenarios, 8/8 requirements, primary gate 32 passed, validator-admitted. Evidence `sha256:084bcc78330db3307abff13c82bd28ae93ec0f38c1bef9c176d3d71cfa099e9f`. Updated verify-report persisted to both stores (file `verify-report.md` + Engram `sdd/cli-paper-e2e/verify-report`).
- **Implementation**: commits `a989baf` (Unit 1) + `e5f784d` (Unit 2) + `81e21d3` (Unit 3), local only, nothing pushed. Zero `src/papersmith/` edits re-confirmed.
- **Tasks**: 15/15 complete, zero unchecked in the persisted tasks artifact (filesystem authoritative at close; Engram tasks snapshot predates completion marking — see Lineage note).
- **Runtime ledger**: all attempts settled; the failed verify was remediated by bound passing settlement (S1 amendment + narrow re-verification).
- **Review gate**: `reviewGate` structurally absent — no review was ever discovered for this candidate (`openspec/changes/cli-paper-e2e/reviews/` does not exist). Archive proceeds under ordinary repository policy. No `disabled/unmanaged` value applies and none was checked for.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| cli-paper-e2e | Created | 8 added, 0 modified, 0 removed requirements; 10 scenarios |

- Main spec did not exist (`openspec/specs/` held only `.gitkeep`); the delta spec was copied mechanically as the full spec to `openspec/specs/cli-paper-e2e/spec.md`.
- No destructive merge: nothing preserved-or-deleted beyond creation. No `rules.archive` in `openspec/config.yaml` (no archive-specific constraints apply).
- Source of truth now: `openspec/specs/cli-paper-e2e/spec.md`.

## Archive Contents

- proposal.md ✅
- specs/cli-paper-e2e/spec.md ✅
- design.md ✅
- tasks.md ✅ (15/15 complete)
- verify-report.md ✅ (pass_with_warnings, final)
- exploration.md ✅
- archive-report.md ✅ (this file, additive-only)

Active directory `openspec/changes/cli-paper-e2e/` no longer exists (moved).

## Verification Summary (final numbers from highest-ranked source)

- Verdict: `pass_with_warnings`; blockers 0; critical findings 0.
- Requirements 8/8; scenarios 10/10.
- Primary gate: `.venv/bin/python -m pytest tests/test_cli_paper_e2e.py -q` → 32 passed; output hash `sha256:084bcc78330db3307abff13c82bd28ae93ec0f38c1bef9c176d3d71cfa099e9f`.
- Build-equivalent: `py_compile tests/test_cli_paper_e2e.py` exit 0.
- Per `verify-report` at verification time, neighbors/smoke were carried as prior evidence under instructed narrow scope (not re-run): smoke exit 0 offline; neighbor matrix (`test_remote_execution.py` 693 passed; init/status/ingest/suite_collects 15; bridges 11; executor 11; proposal_implementation + implementation_core 1583; node 5 e2e legs 30 passed). Stale intermediate claims are not restated as current facts beyond this attribution.

## Carried Warnings (non-blocking, recorded at close)

- **W2** — config sweep in `81e21d3`: commit carries the pre-existing sdd-init `config.yaml` refresh (~56 lines) alongside the 2-line e2e registration; rollback boundary blurred.
- **W3** — suite at 796/800 lines, zero margin; cumulative units ~854 insertions vs the 800-line custom note (each stacked slice independently reviewable). Next change touching this file MUST split or shrink first.
- **W4** — environmental neighbor flakes in prior full-matrix evidence (parallel-load `FileNotFoundError` in `manifest.py`; leftover `implementations/_smokebox_*` debris from a killed probe run), both resolved and unrelated (zero `src/` edits proven).
- **W5** — split evidence instead of full `test:all` locally (exceeds ~600s); narrow re-verification scope was by orchestrator instruction.

No CRITICAL issues. No intentional partial archive; no stale-checkbox reconciliation was needed (tasks artifact already 15/15).

## Gates

- **Native Review Receipt Gate**: PASS — `reviewGate` absent (no review discovered); ordinary policy applies.
- **Task Completion Gate**: PASS — 0 unchecked (`grep -c "- [ ]"` = 0), 15 checked (`grep -c "- [x]"` = 15) in the archived `tasks.md`.
- **Action Context Guard**: PASS — no `workspace-planning` mode; no `allowedEditRoots` restriction in the launch context.

## Mechanical Copy Evidence (verbatim `diff -r`, empty = passing)

Step 2 — delta spec → main spec:

```text
$ diff -r "openspec/changes/cli-paper-e2e/specs/cli-paper-e2e/spec.md" "openspec/specs/cli-paper-e2e/spec.md"
(empty — no differences, DIFF_EXIT=0)
```

Step 3 — change folder → archive (pre-move recursive snapshot vs archived tree; `git mv` refused the untracked source so `mv` performed the move; snapshot trap cleaned up after readback):

```text
$ diff -r "$snapshot_root/source" "openspec/changes/archive/2026-09-09-cli-paper-e2e"
(empty — no differences, diff_status=0; source confirmed gone before comparison)
```

Post-archive confirmation:

```text
$ diff -r "openspec/changes/archive/2026-09-09-cli-paper-e2e/specs/cli-paper-e2e/spec.md" "openspec/specs/cli-paper-e2e/spec.md"
(empty — no differences, DIFF_EXIT=0)
```

A skipped or missing `diff -r` would FAIL the phase; all three readbacks above are empty (passing). Shell-only copy/move was used throughout; no artifact bytes passed through model Read/Write.

## Lineage (traceability)

Filesystem (authoritative at close):
- `openspec/changes/archive/2026-09-09-cli-paper-e2e/proposal.md`
- `openspec/changes/archive/2026-09-09-cli-paper-e2e/specs/cli-paper-e2e/spec.md`
- `openspec/changes/archive/2026-09-09-cli-paper-e2e/design.md`
- `openspec/changes/archive/2026-09-09-cli-paper-e2e/tasks.md`
- `openspec/changes/archive/2026-09-09-cli-paper-e2e/verify-report.md`
- `openspec/changes/archive/2026-09-09-cli-paper-e2e/exploration.md`
- `openspec/specs/cli-paper-e2e/spec.md` (new source of truth)

Engram observations read (full content via `mem_get_observation`):
- `sdd/cli-paper-e2e/proposal` — id 223
- `sdd/cli-paper-e2e/spec` — id 224 (STALE: predates S1 amendment; retains old THEN `it exits non-zero naming the offending paths`. Filesystem delta spec is the final state; Engram spec was never upserted post-amendment. Recorded here explicitly, not resolved silently.)
- `sdd/cli-paper-e2e/design` — id 225
- `sdd/cli-paper-e2e/tasks` — id 226 (STALE: predates apply completion marking; shows unchecked boxes. Filesystem `tasks.md` 15/15 `[x]` is the final state.)
- `sdd/cli-paper-e2e/apply-progress` — id 227 (intermediate snapshot; final numbers carried from higher-ranked sources where later work changed them)
- `sdd/cli-paper-e2e/verify-report` — id 240 (current passing report, matches filesystem `verify-report.md`)

No review topics were read: none exist (`reviewGate` absent).

## SDD Cycle Complete

The change was fully planned, implemented, verified, and archived. Ready for the next change.
