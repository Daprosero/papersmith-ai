# Tasks: The Audit That Runs What It Claims

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1,030 (Slice 1 ~250, Slice 2 ~420, Slice 3 ~360) |
| 400-line budget risk | High |
| Chained PRs recommended | No — no branches/PRs in this repo; three ordered commits in one change on `main` |
| Suggested split | Commit 1 (report shape) → Commit 2 (structure) ‖ Commit 3 (walkthrough) |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

Session `review_budget_lines` = 800; forecast ~1,030 exceeds it. Per the settled rulings, the overrun is already acknowledged and accepted as `size:exception` — three ordered commits, no branches, no PRs.

Baseline (measured): `python3 -m unittest discover -s tests` = 973 OK; `-p 'test_skill_audit.py'` = 71 OK. Each slice must state its own expected post-slice counts and pass only if counts RISE by that number; also check no test-name/class-name collision (`SuiteIntegrityTests`).

### Suggested Work Units

| Unit | Goal | Commit | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | `## Move outcomes` + `## Repair units` shape, derived move roster, `## Handoff` correction | Commit 1 | `python3 -m unittest tests.test_skill_audit -k "ReportSchema or MoveOutcomes or RepairUnit or MovesTable or FirstDamageReport"` | `check-report` over `references/example-report.md` and the shipped Slice-1-updated report | Delete 2 `REPORT_SHAPE` keys, 2 `SKILL.md` rows, restore `## Handoff` sentence |
| 2 | `structure`, `tree_digest`, box lifecycle, three-way adjudication | Commit 2 | `python3 -m unittest tests.test_skill_audit -k "Structure or TreeDigest or SingleWalk or Box"` | `structure --subject .claude/skills/skill-audit --spec references/probes/skill-audit.structure.json` | Remove `structure`/`tree_digest`, revert moves row 1, delete recipe |
| 3 | `walkthrough`, ordered-sequence stall detection | Commit 3 | `python3 -m unittest tests.test_skill_audit -k Walkthrough` | `walkthrough --subject .claude/skills/skill-audit --spec references/probes/skill-audit.first-run.json` | Remove `walkthrough`, move-8 row, walkthrough recipe |

## Slice 1 — Report shape (first: move roster must derive from `## The moves`)

- [x] 1.1 RED: add test asserting `check-report` requires one `## Move outcomes` row per move parsed out of `SKILL.md`'s moves table (never a literal list). Run, confirm fail.
- [x] 1.2 GREEN: `audit_cli.py` — add `move_roster()` via `markdown_table_rows` over `## The moves`; add `move-outcomes` to `REPORT_SHAPE`; `run_check_report` requires `- Move: N: ran|skipped: <reason>` per parsed move, non-empty reason.
- [x] 1.3 RED: add test asserting `check-report` rejects a report with no `## Repair units` table or a finding label in no unit. Run, confirm fail.
- [x] 1.4 GREEN: add `repair-units` to `REPORT_SHAPE`; enforce `| Unit | Findings | Changed lines |`, every `F<n>` covered exactly once, forecast cell integer.
- [x] 1.5 Co-edit `ReportSchemaSelfDescriptionTests` companions: land both new `REPORT_SHAPE` keys and their `SKILL.md` shape-table rows together.
- [x] 1.6 `SKILL.md` `## Handoff`: replace "with the slicing and the changed-line forecast" with repair-units wording; leave `## Scope, and who chooses it` untouched.
- [x] 1.7 `SKILL.md` shape table: add `## Move outcomes` and `## Repair units` rows; no new heading may carry a cardinal (`DoctrineNumeralTests`).
- [x] 1.8 Update `references/example-report.md`: add `## Move outcomes` and `## Repair units` so it keeps validating.
- [x] 1.9 Update `openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md`: add the same two sections so `FirstDamageReportTests.test_the_shipped_report_validates` stays green.
- [x] 1.10 Confirm `SelfAuditSubcommandRosterTests` literal `["check-report", "roster"]` still passes unchanged (no new subcommand this slice).
- [x] 1.11 Inversion: delete one moves-table row, confirm `check-report` fails naming that move; restore by inverse patch; confirm restore by content comparison, never `git checkout --`.
- [x] 1.12 Run `VocabularyTests` over every file this slice touches.
- [x] 1.13 Verify: both suite counts rise by exactly this slice's added-test count.

## Slice 2 — `structure` (order-free vs. Slice 3)

- [x] 2.1 RED: add `tree_digest(root, exclude)` tests — sorted path→sha256, files only, one changed byte changes the digest; add the `ast` lock asserting `rglob/walk/iterdir/scandir/glob` occur only inside `tree_digest`. Confirm fail.
- [x] 2.2 GREEN: implement `tree_digest` in the code-side section, below the `ast`-guarded divider.
- [x] 2.3 RED: add normalisation tests — POSIX separators, `./` stripped, no trailing slash, files-only, case preserved; `shape-not-walkable`/`case-only-divergence` notes; any zero-member side → `Unprobeable` exit 2. Confirm fail.
- [x] 2.4 GREEN: implement normalisation and `declared`/`disk`/`fromZero` side derivation.
- [x] 2.5 RED: add outcome tests — each two-side-agreement case names the differing side (`disk-stale`/`builder-broken`/`document-wrong`); `three-way-divergence` when all differ; no new `ADJUDICATIONS` value. Confirm fail.
- [x] 2.6 GREEN: implement outcome arithmetic and `onlyIn`/`missingFrom` sets.
- [x] 2.7 RED: add box tests — box at `<repoRoot>/implementations/_structure_<surface>`; non-empty pre-box → exit 2; subject digest change during build → exit 2 `build-escaped-the-box`; cleanup proven by `tree_digest`, never `git status`. Confirm fail.
- [x] 2.8 GREEN: implement box create/run-steps/before-after digest/`finally` cleanup; only `{repoRoot}/{subject}/{box}` interpolate, `shell=False`, unknown token → exit 2.
- [x] 2.9 Add `structure` to `build_parser` and `DISPATCH`.
- [x] 2.10 `SKILL.md`: correct moves row 1 → `Ships as: structure`; add `structure` subcommand row; add box/underivable-side Decision Gates; add `## The shipped files` declared-side table (no cardinal in heading).
- [x] 2.11 Create `references/probes/skill-audit.structure.json`: subject = the auditor, `fromZero.steps` = `git archive HEAD:.claude/skills/skill-audit` piped through `tar -x`.
- [x] 2.12 `references/usage.md`: one worked `structure` invocation; extend exit-code table.
- [x] 2.13 Co-edit `SelfAuditSubcommandRosterTests` literal to include `"structure"`.
- [x] 2.14 `tests/test_skill_audit.py:1527`: delete the private `tree_digest` copy; import the shipped one from `audit_cli`.
- [x] 2.15 Inversion: for each outcome, the escape case, and the underivable case — break the guarded fact, confirm the lock fires, restore by inverse patch, confirm by content comparison.
- [x] 2.16 Run `VocabularyTests` over every file this slice touches.
- [x] 2.17 Verify: both suite counts rise by exactly this slice's added-test count.

## Slice 3 — `walkthrough` (order-free vs. Slice 2)

- [x] 3.1 RED: add step-shape tests — no `expect` → `Unprobeable`; missing `argv[0]` at index 0 → `Unprobeable`; missing `argv[0]` at index >0 → stall. Confirm fail.
- [x] 3.2 GREEN: implement step-shape validation.
- [x] 3.3 RED: add stall tests — plant a stall mid-sequence; one finding names that index; later gates land in `## Unchecked`, never clean; exit `0` for any verdict, `2` only for inability. Confirm fail.
- [x] 3.4 GREEN: implement the ordered runner; stall = first observation contradicting its `expect`; timeout → stall kind `timeout`.
- [x] 3.5 RED: add box-sharing tests — one box for the whole sequence; a step declaring `"reset": true` gets a fresh empty box; same box helper/cleanup proof as `structure`. Confirm fail.
- [x] 3.6 GREEN: implement box reuse/reset.
- [x] 3.7 Add `walkthrough` to `build_parser` and `DISPATCH`.
- [x] 3.8 `SKILL.md`: append move 8 (`Ships as: walkthrough`) — appended, not inserted; add `walkthrough` subcommand row.
- [x] 3.9 Create `references/probes/skill-audit.first-run.json`: ordered recipe over the auditor's own first-run flow.
- [x] 3.10 `references/usage.md`: one worked `walkthrough` invocation; extend exit-code table.
- [x] 3.11 Co-edit `SelfAuditSubcommandRosterTests` literal to its final set: `["check-report", "roster", "structure", "walkthrough"]`.
- [x] 3.12 Inversion: plant/clear the stall, confirm the lock fires; restore by inverse patch, confirm by content comparison.
- [x] 3.13 Run `VocabularyTests` over every file this slice touches.
- [x] 3.14 Verify: both suite counts rise by exactly this slice's added-test count.

## Phase 4: Final cross-slice check (after all three land)

- [x] 4.1 Run the auditor against itself: `unregistered: []`, `phantom: []` for the final subcommand set.
- [x] 4.2 Confirm no file under `implementations/` and no other skill changed, by `tree_digest` before/after comparison.
- [x] 4.3 Confirm final counts: `python3 -m unittest discover -s tests` = 973 + total added; `-p 'test_skill_audit.py'` = 71 + total added; no duplicate class/test name anywhere in the file.
