# Tasks: The Audit That Escalates What It Cannot Decide

> Size-budget note: this checklist reports an overrun of the skill's 530-word
> guideline rather than shrinking scope silently, mirroring the proposal's own
> practice for the 800-line review budget. The change is six co-locked
> slices with explicit TDD-inversion steps per lock; compressing that below
> budget would drop exactly the specificity the design demands.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,210 (per proposal slice table) |
| 800-line session budget risk | High — forecast exceeds `review_budget_lines: 800` |
| 400-line per-slice budget risk | Low — every slice ≤ ~240 lines |
| Chained PRs recommended | No — settled scope: one change, ordered commits on `main`, no branches, no PRs |
| Suggested split | 6 ordered commits on `main`, slice order below |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

```text
Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low
```

`Decision needed before apply: Yes` per the `single-pr` mapping: the
orchestrator must still confirm `size:exception` before `sdd-apply`, even
though the proposal already reports the overrun as accepted rather than
silently shrunk.

### Suggested Work Units

| Unit | Goal | Commit (main, no PR) | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------------------|-----------------------|------------------|--------------------|
| 1 | Freeze: digest in every payload, `## Frozen`, re-derivation | Commit 1 | `python3 -m unittest tests.test_skill_audit.FrozenDigestTests tests.test_skill_audit.SuiteIntegrityTests` | Real `roster`/`structure`/`walkthrough`/`check-report` runs against `.claude/skills/skill-audit/` itself | Delete `frozen_digest`, `"frozen"` payload keys, `## Frozen` section |
| 2 | Step `kind`, `setup-failed` | Commit 2 | `python3 -m unittest tests.test_skill_audit.WalkthroughStepKindTests` | Real `walkthrough` run over `probes/skill-audit.first-run.json` | `kind` defaults to `"gate"`; revert leaves today's behavior intact |
| 3 | Escalatable partition, totality lock, escalation hint, `candidateGates` | Commit 3 | `python3 -m unittest tests.test_skill_audit.EscalationPartitionTests tests.test_skill_audit.ControlGateTests` | Real control-gate run: one live-refusal subject, one silent subject | Delete `ESCALATION_BUCKETS`, `note()`/`stalled()` revert to inline dicts, `candidateGates` block |
| 4 | `reading-diff` + move 9 + `usage.md` | Commit 4 | `python3 -m unittest tests.test_skill_audit.ReadingDiffTests tests.test_skill_audit.MovesTableTests` | Real `reading-diff` run over the shipped reading pair | Remove subcommand, move-9 row, roster-range revert |
| 5 | `- Found by:` + `## Disputed severity` | Commit 5 | `python3 -m unittest tests.test_skill_audit.FoundByTests tests.test_skill_audit.SeverityVocabularyTests` | Real `check-report` over both shipped reports | Remove field/section; both reports revert |
| 6 | `## Stage outcomes` + per-stage artifact demand + stages table | Commit 6 | `python3 -m unittest tests.test_skill_audit.StageOutcomesTests tests.test_skill_audit.FirstDamageReportTests` | Real `check-report` over both shipped reports, full zero-model self-audit | Remove stages table, `stage_roster`, conditional demands |

Report-file touch count, explicit: `references/example-report.md` and
`openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md`
are each co-edited exactly **4 times** — Commits 1, 4, 5, 6 — never in
Commits 2 or 3 (no report-shape addition lands in those two).

## Standing ritual (applies to every lock task below, not repeated per line)

For each `[LOCK]` task: (a) write the test, run it, paste the observed
FAILURE; (b) implement the minimal mechanism; run, paste PASS; (c) invert the
guarded fact exactly as named; run, confirm the lock fires RED; (d) restore
by **inverse patch** (never `git checkout --`, never a prepending
`str.replace("", ...)`); (e) confirm restore via `sha256sum` of the whole
file matching its pre-inversion value. Run
`python3 -m unittest tests.test_skill_audit.VocabularyTests` before every
commit in this list.

## Commit 1 — Freeze the subject (target: 1026 → ~1034, +8; actual: 1026 → 1037, +11)

- [x] 1.1 Add `frozen_digest(root, exclude)` in `audit_cli.py`: `sha256` over
      `tree_digest`'s sorted map, one line per path.
- [x] 1.2 [LOCK] `FrozenDigestTests.test_stable_digest_for_same_tree` and
      `test_digest_changes_with_exclusion`. Implement 1.1.
- [x] 1.3 Emit `"frozen": {"digest","exclude","subject"}` in `roster`,
      `structure`, `walkthrough` payloads. Test: all three payload shapes
      carry it.
- [x] 1.4 Add `## Frozen` (`- Digest:`, `- Subject:`, `- Exclude: (none)`
      when empty) to report rendering; add `- Digest:` to every `### F<n>.`
      finding block.
- [x] 1.5 [LOCK] `FrozenDigestTests.test_finding_digest_mismatch_rejected`
      (spec scenario: `## Frozen` names A, a finding names B →
      `check-report` rejects, names the finding). Invert: change one
      finding's digest post-implementation, confirm rejection fires; restore.
- [x] 1.6 Add `check-report --subject <path>`: re-derive from disk, compare,
      set `"rederived": bool`. Tests: match passes; mismatch rejected;
      flag omitted → `rederived: false`, only finding-vs-`## Frozen` checked.
- [x] 1.7 [LOCK] `SuiteIntegrityTests` — `ast`-scan `tests/test_skill_audit.py`
      for duplicate top-level class names and duplicate `test_` method names
      within a class. Invert by planting one duplicate `test_` name in a
      scratch copy of the file (never the tracked file), confirm the scan
      fires; discard the scratch copy (no restore needed — nothing tracked
      was touched).
- [x] 1.8 Confirm `SingleWalkTests` stays green: `frozen_digest` calls only
      `tree_digest`, no direct `rglob`/`walk`/`iterdir`/`scandir`/`glob`.
- [x] 1.9 `SKILL.md`: add the `frozen` `REPORT_SHAPE` row to
      "The shape of a report" doctrine table in the same commit
      (`ReportSchemaSelfDescriptionTests`).
- [x] 1.10 Co-edit `references/example-report.md` and
      `.../audit-proposal-deliberation-operations.md` with `## Frozen`
      (touch 1 of 4 for each file). Run `FirstDamageReportTests`.
- [x] 1.11 Verify count: baseline 1026 → target ~1034; confirm the rise
      equals tests actually added, not merely that the suite is green.
      Actual: 1026 → 1037 (+11: `FrozenDigestTests` ×3, `FrozenPayloadTests`
      ×3, `CheckReportSubjectTests` ×3, `SuiteIntegrityTests` ×2).

## Commit 2 — Setup is not a gate (target: ~1034 → ~1040, +6)

- [ ] 2.1 Add `kind: "setup" | "gate"` to the walkthrough step schema,
      default `"gate"` (precedent: `"reset": true`).
- [ ] 2.2 [LOCK] `WalkthroughStepKindTests.test_passing_setup_step_not_counted_as_passed_gate`
      (spec scenario). Implement gate/setup split in `walkthrough`.
- [ ] 2.3 [LOCK] `test_failing_setup_step_exits_2_as_setup_failed_never_stalled`
      (spec scenario). Emit `{"status":"setup-failed","index","name","detail"}`,
      `stall: null`, `unreached: []`, exit `2`. Invert: make the setup step
      fail after implementation and confirm it reports `setup-failed`, not
      `stalled`; restore the fixture.
- [ ] 2.4 [LOCK] `test_setup_step_declaring_expect_is_unprobeable` — a
      `kind: "setup"` step with an `expect` block raises `Unprobeable`.
- [ ] 2.5 `test_recipe_of_only_setup_steps_is_unprobeable` — zero gate steps
      asserts nothing about the subject.
- [ ] 2.6 Add `"gates": {"declared": n, "passed": m}` to the walkthrough
      payload, counting only `kind == "gate"` steps.
- [ ] 2.7 `probes/skill-audit.first-run.json`: declare step 0
      `"kind": "setup"` (no `expect` added — it needs none).
- [ ] 2.8 `references/usage.md`: document `setup-failed` in the exit table.
- [ ] 2.9 Verify count: ~1034 → target ~1040 (+6).

## Commit 3 — Escalatable partition, totality lock, routing (target: ~1040 → ~1053, +13)

- [ ] 3.1 Refactor all eight `"kind"`-carrying dict literals into a
      `note(kind, detail, path, searched)` constructor — the only way an
      entry enters `notes[]`. Sites: `run_roster` (`:700`, `:735`, `:752`),
      `normalize_declared_paths` (`:521`), `case_only_divergences` (`:547`),
      `run_walkthrough` (`:1028`, `:1037`, `:1054`).
- [ ] 3.2 Add `stalled(kind, index, detail)` as `note()`'s sibling for
      walkthrough verdicts, so its `"kind"` (a verdict) never collides with
      an undecidability kind.
- [ ] 3.3 Hoist `:723-734`'s inline dict into
      `DOCTRINE_SIDE_NOTES: {status: (kind, detail)}`.
- [ ] 3.4 Add `ESCALATION_BUCKETS = {"escalatable": (...), "consequence":
      (...), "deterministic-exclusion": (...)}` per the spec's four
      escalatable kinds, one consequence kind, two exclusion kinds.
- [ ] 3.5 [LOCK — strongest of this commit] `EscalationPartitionTests`: AST
      scan asserting (a) every constant string in a `note()` `kind` position
      plus every `DOCTRINE_SIDE_NOTES` value kind appears in exactly one
      bucket, (b) buckets are pairwise disjoint, (c) **no dict literal
      outside `stalled()` carries a `"kind"` key at all**. Invert by adding
      one new unclassified `"kind":` literal directly (bypassing `note()`);
      confirm the totality lock fires; restore by inverse patch; confirm
      whole-file `sha256` match.
- [ ] 3.6 `test_consequence_kind_not_independently_escalated` (spec scenario:
      `comparison-not-run` never appears as a second entry in the
      escalatable list).
- [ ] 3.7 Add `"escalation": {"rung","probe","needs","refusal"}` to each
      escalatable note; rung is `"probe"` only when the recipe declares
      `probe: "refusal"`.
- [ ] 3.8 Add `candidateGates` recipe block (`refusal`, `argv`, `candidates`);
      `{candidate}` valid only inside `candidateGates.argv`;
      `GATE_TOKENS = STRUCTURE_TOKENS | {"candidate"}`.
- [ ] 3.9 [LOCK] `ControlGateTests.test_live_refusal_channel_control_passes`
      and `test_dead_refusal_channel_stalls_at_control_candidates_unreached`
      (threat-matrix RED: silent subject → control stalls, no candidate
      reported accepted). Invert the live case by pointing the recipe at a
      subject that silently accepts unknown flags; confirm the stall;
      restore the fixture.
- [ ] 3.10 `test_candidategates_unknown_token_exits_2` and
      `test_candidate_with_shell_metacharacter_reaches_argv_literally`
      (subprocess-execution threat-matrix RED tests; `shell=False` unaffected).
- [ ] 3.11 [MOTIVATING CASE] `test_documented_flag_surface_rerouted_not_read`
      — a `no-closed-roster` note over a prose-stated flag list drives each
      flag as a `walkthrough` gate before any reader is invoked; proves the
      half-caught case from the proposal now closes end to end.
- [ ] 3.12 `probes/skill-audit.first-run.json`: add the `candidateGates`
      block (second edit to this file, after Commit 2's step-kind edit).
- [ ] 3.13 `SKILL.md`: escalation/routing Decision Gates, no `REPORT_SHAPE`
      row yet — `## Undecidable` enforcement is wired in Commit 6.
- [ ] 3.14 Verify count: ~1040 → target ~1053 (+13). No report co-edit this
      commit (confirms the 4-touch count above).

## Commit 4 — `reading-diff`, move 9 (target: ~1053 → ~1062, +9)

- [ ] 4.1 Add `run_reading_diff`: `--surface --reading --reading` (exactly
      two; any other count → `Unprobeable`). Emit `{surface, agreement,
      shared, onlyIn, comparison:"not-run", candidates, limit, frozen}`.
- [ ] 4.2 `ReadingDiffTests.test_two_readers_agree_reports_single_reading`
      and `test_divergent_readings_report_shared_and_only_in` (spec scenarios).
- [ ] 4.3 [LOCK — B3] `test_comparison_field_is_literal_not_run` — assert the
      constant, not a computed value.
- [ ] 4.4 [LOCK — B1, closed_seen barrier's strongest inversion, do this one
      with the full ritual] `test_run_reading_diff_never_calls_doctrine_side_probe_code_side_or_finish`
      — AST subtree scan. **Invert by planting a call from
      `run_reading_diff` into `doctrine_side`**, per the spec's own
      scenario. Confirm the AST lock fires RED. Restore by inverse patch;
      confirm whole-file `sha256` match against the pre-plant value.
- [ ] 4.5 [LOCK — B2, single-writer barrier] `test_closed_seen_assigned_at_exactly_one_site_fed_only_by_doctrine_side` —
      confirm `closed_seen = True` still occurs at exactly one site
      (`audit_cli.py:720`, inside `run_roster`, fed only by a
      `doctrine_side` status) after every edit in this commit. This is a
      structural confirmation, not a new mechanism — task it explicitly so
      the barrier is proven to hold, not assumed.
- [ ] 4.6 [LOCK — B4] `test_reading_superset_of_code_side_yields_no_unregistered_key`
      — behavioural, drives the real subcommand; asserts no `unregistered`
      key at all in the payload (not an empty one).
- [ ] 4.7 Add move 9 to `SKILL.md`'s moves table: `reading-diff`, comparing
      two supplied readings by mechanical diff.
- [ ] 4.8 Edit `MovesTableTests.test_one_row_per_move_and_one_for_the_textual_move`:
      `range(0, 9)` → `range(0, 10)` (`tests/test_skill_audit.py:417`), in
      the same commit as 4.7.
- [ ] 4.9 Confirm `test_every_row_ships_as_a_real_subcommand_or_as_doctrine`
      and `test_every_numbered_move_names_a_lock_that_is_on_disk` pass for
      the new row.
- [ ] 4.10 Extend `SelfAuditSubcommandRosterTests`
      (`tests/test_skill_audit.py:804-813`) to include `reading-diff`;
      confirm `test_the_roster_comes_from_argparse_and_not_from_a_list`
      still derives it rather than reading the extended literal.
- [ ] 4.11 Create `probes/skill-audit.reading-a.json` and
      `probes/skill-audit.reading-b.json` (the shipped reading pair);
      document a worked `reading-diff` invocation in `references/usage.md`.
- [ ] 4.12 Co-edit both shipped reports with the move-9 `## Move outcomes`
      row (touch 2 of 4 for each file); run `MoveOutcomesTests` and
      `FirstDamageReportTests`.
- [ ] 4.13 Verify count: ~1053 → target ~1062 (+9).

## Commit 5 — `Found by` and `Disputed severity` (target: ~1062 → ~1067, +5)

- [ ] 5.1 Add `- Found by:` (no default) alongside the existing evidence
      marker on every finding.
- [ ] 5.2 [LOCK] `FoundByTests.test_finding_without_found_by_is_rejected`
      (spec scenario). Invert by removing the field from one finding after
      implementation, confirm rejection; restore.
- [ ] 5.3 Add `## Disputed severity` (bare-heading; non-empty requires two
      `- Position:` lines per dispute, each with a `` `file:line` ``
      citation, verbatim, no ranking).
- [ ] 5.4 [LOCK] `SeverityVocabularyTests` — the only occurrences of
      `severity|CRITICAL|WARNING|SUGGESTION` in the whole skill directory
      are the `## Disputed severity` heading and its `REPORT_SHAPE` marker.
      Invert by adding one `- Severity:` field to a finding, confirm the
      guard fires; restore.
- [ ] 5.5 `SKILL.md`: `found-by` and `disputed-severity` `REPORT_SHAPE` rows
      in the same commit (`ReportSchemaSelfDescriptionTests`).
- [ ] 5.6 Co-edit both shipped reports with `- Found by:` on every finding
      and a `## Disputed severity` heading (touch 3 of 4 for each file);
      run `FirstDamageReportTests`.
- [ ] 5.7 Verify count: ~1062 → target ~1067 (+5).

## Commit 6 — Stage outcomes, per-stage demand, stages table (target: ~1067 → ~1076, +9)

- [ ] 6.1 Add the stages table to `SKILL.md`: `| Stage | Models | Demands |`,
      five rows, `Demands` cells holding `REPORT_SHAPE` keys (`frozen`,
      `undecidable`, `reading-diff`, `drives`, `found-by`) — no cardinal in
      the heading (`DoctrineNumeralTests.test_no_heading_carries_a_cardinal_at_all`).
      Write this wording check BEFORE the headings, per the design's own
      warning.
- [ ] 6.2 Add `stage_roster(text)` mirroring `move_roster`: column 0's
      leading digit is the id, column 2 is the key; no `textual` escape
      valve — malformed rows are `Unprobeable`.
- [ ] 6.3 `StageOutcomesTests.test_ran_stage_without_artifact_is_rejected`
      (spec scenario: stage 2 `ran`, no `## Reading diff` → rejected, names
      stage 2).
- [ ] 6.4 [LOCK] `test_zero_model_audit_is_valid` (spec scenario: stages
      0-1 `ran`, 2-4 `skipped: <reason>` → accepted). Invert by declaring
      stage 2 `ran` in that same fixture without its artifact and confirm
      rejection; restore.
- [ ] 6.5 Add `FIELD_NOT_RUN = {"found-by": "not-compared"}`; stage 4 `ran`
      tightens accepted `- Found by:` values.
- [ ] 6.6 `test_stage_3_asymmetry_rejects_skill_less_finding_against_subject`
      — a finding attributed to the skill-less drive naming the subject as
      its target is a category error, rejected structurally.
- [ ] 6.7 [LOCK] `test_undecidable_probe_rung_requires_its_move_to_have_run`
      — cross-section rule: `## Undecidable`'s `- Probe: <move>` demands
      that move's `## Move outcomes` row be `ran`. Invert by marking that
      move `skipped` while `- Probe:` still names it; confirm rejection;
      restore.
- [ ] 6.8 Add the "presence, never independence" sentence verbatim to the
      stages table's stage 2-4 row (spec's final scenario): isolation,
      blindness, no-contact are unfalsifiable from a `subprocess.run()`-only
      tool, and the row carries no lock, exactly as the moves table's
      textual row states.
- [ ] 6.9 State the five-model-run count in `SKILL.md` before any stage is
      launched (stages 2-4 cost 2+2+1 models).
- [ ] 6.10 Co-edit both shipped reports with `## Stage outcomes` (stages 0-1
      `ran`, 2-4 `skipped: <reason>`) and a (possibly empty) `## Undecidable`
      section — touch 4 of 4 for each file. Run `FirstDamageReportTests`
      and `ReportSchemaSelfDescriptionTests`.
- [ ] 6.11 Run the auditor against itself with the new subcommands
      (`roster`/`structure` over `.claude/skills/skill-audit/`); confirm its
      own subcommand roster still shows `unregistered` and `phantom` empty
      (success-criterion end-to-end proof).
- [ ] 6.12 Verify count: ~1067 → target ~1076 (+9); total rise from baseline
      1026 is +50, matched against tests actually added, not suite-green alone.

## Final gate (after Commit 6, before archiving)

- [ ] 7.1 Run `python3 -m unittest discover -s tests`; confirm exactly
      1076 tests (or the true count of everything added), OK, no duplicate
      class/`test_` names (`SuiteIntegrityTests`).
- [ ] 7.2 Confirm content manifest: no file under `implementations/`, no
      other skill, and not `openspec/config.yaml` was modified.
- [ ] 7.3 Confirm `NothingWasRepairedTests` passes with no exemption
      widening; if it needed one, name the function in
      `box_lifecycle_exemption` and add a behavioural lock driving the real
      subcommand and comparing subject bytes — do not widen silently.
- [ ] 7.4 Run `VocabularyTests` once more over the full skill tree (no
      forbidden vocabulary from either the Domain_Adaptation guard or the
      severity guard).
