
# Tasks: Automate Move 6, and widen what the eleven moves already reach

> **Stated exception to the 530-word cap**, for the reason every sibling
> artifact in this change already stated one: dropping a RED task or a
> threat-matrix row to meet a word budget is the exact overclaim defect this
> work exists to catch. Ten commits, three SDD changes, all owner-approved.
> A shared discipline block is written once instead of repeated ten times to
> keep the real cost proportional to the work, not to the prose about it.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 4,100–5,485 authored, across 10 commits / 3 changes |
| Effective budget (session preflight override) | 1,400 lines per commit — every commit forecast below stays under it |
| 400-line budget risk | High (against the generic 400-line default; 7 of 10 commits exceed it on their own) |
| Chained PRs recommended | Yes |
| Suggested split | 10 sequential commits, landed as Change A → Change B → Change C |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

The A/B/C routing question the design raised is **already answered** by the
owner — all three changes are approved. The remaining decision this forecast
surfaces is narrower: confirm stacked-to-main (sequential, each commit
mergeable and revertable on its own) rather than a single oversized PR.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 0 | Shared child-env helper, both sites purge bytecode | PR 1 (Change A) | `discover -k ChildEnv` | N/A — pure unit lock, no external service | Revert only together with a1+ (re-arms stale-`.pyc` trap alone) |
| a1 | `inversion` mechanism + doctrine, same commit | PR 2 (Change A) | `discover -k Inversion` | `.venv/bin/python scripts/audit_cli.py inversion --subject <fixture>` | Independent revert; drops the subcommand cleanly |
| a2 | Conditions 9/10, `example-report.md` re-sign | PR 3 (Change A) | `discover -k ReportSchema or -k Reachability` | `check-report` against `example-report.md` | Independent revert |
| b | Three widened recipes, no code | PR 4 (Change A) | `discover -k ProbeRecipeCoverage` | `roster` / `walkthrough` / `structure` against each widened recipe | Delete the 3 recipe files, revert rows |
| B1 | R6: box digest, `roots`, `readOnly` | PR 5 (Change B) | `discover -k WalkthroughDigest` | `walkthrough` against a 2-step fixture flow | Independent revert |
| B2 | R2+R3: `guardReach`, `identifier_variants`, rename probe | PR 6 (Change B) | `discover -k GuardReach or -k IdentityMeasured` | `roster` against a fixture guard | Independent revert |
| B3 | R5+R4: `structure` produced roster, `Demanded, not scaffolded` | PR 7 (Change B) | `discover -k ArtefactContent or -k DemandedNotScaffolded` | `structure` against a fixture from-zero drive | Independent revert |
| C1 | R7: `exits` subcommand, admission gate, box drive | PR 8 (Change C) | `discover -k Exits` | `.venv/bin/python scripts/audit_cli.py exits --subject <fixture>` | Independent revert; new subcommand only |
| C2 | R1: `ast` enumeration-reach subcommand | PR 9 (Change C) | `discover -k EnumerationReach` | `.venv/bin/python scripts/audit_cli.py <new-subcommand> --subject <fixture>` | Independent revert |

## Cross-cutting discipline (every RED and every GREEN task below)

- `PYTHONDONTWRITEBYTECODE=1` on every invocation; purge `__pycache__` before
  any mutation-based check — a same-size edit reuses a stale `.pyc` otherwise.
- After any source mutation, run `git diff --stat` and confirm the target
  file changed before trusting a red/green reading. An anchor that matched
  is not a mutation that ran.
- Never restore with `git checkout --`; `cp` a backup into the scratch dir
  first. This work destroyed 350 lines that way once already.
- A surviving mutation means a weak test OR a wrong claim about the code —
  measure the property before strengthening the assertion.
- At least one lock per guard must **execute** the guarded act, not merely
  assert a field's presence (R7's `published-and-ran` in particular).
- Run both suites, serially, never concurrently, every commit:
  `npm test && .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
  Capture stderr to a file; grep `^Ran |^OK|^FAILED`.
- Re-measure the baseline before the first RED of commit 0 (do not trust the
  brief's Python 2473/npm 386 figures — the design phase never ran a shell).
  Then confirm the Python `Ran` count rises by exactly the tests added, per
  commit.
- Use `.venv/bin/python` only; a bare `python3.12` under-reports (missing
  `requests`, `nbformat`/`jupyter`, `assets/requirements-dev.txt`, `torch`).
- Unique test class names; scratch paths carry `os.getpid()`; any toy target
  under `implementations/` is removed by its own test.
- `skill-audit` stays stdlib-only, no venv, no network, reports-never-repairs.
  Never execute, read from, or cite `implementations/` — `tests/forge_vocabulary.py`
  is the guarded floor; run the suites, never reason about it.
- A new subcommand ships its `SKILL.md` subcommands-table row, exit-code
  paragraph, and (if applicable) shipped-files row in the **same commit**.
  Doctrine counts in `SKILL.md`/`references/usage.md` move with any added
  key, status, or move, in that same commit.
- Conventional commits, no AI attribution.

---

## Change A — `skill-audit-move6-substitution-probe` (this folder, scope unchanged)

### Commit 0 — `a-driven-child-purges-its-own-bytecode` (forecast 150–195)

- [ ] 0.1 RED: lock asserting `run_box_step`'s driver-kind child env carries
      `PYTHONDONTWRITEBYTECODE=1` even when absent from the parent env
      (`tests/test_skill_audit.py`, new `ChildEnvTests`).
- [ ] 0.2 RED: lock asserting `run_sensitivity_drive`'s child env carries the
      same purge, independent of whether `run_box_step` ran in the process.
- [ ] 0.3 RED: lock asserting a `driver` step declaring
      `PYTHONDONTWRITEBYTECODE` in `env` is still refused `Unprobeable`
      (name stays out of `DRIVER_ENV_ALLOWLIST`).
- [ ] 0.4 RED: AST class-sweep lock proving no third `os.environ[...]`
      child-env comprehension exists outside `constructed_child_env`.
- [ ] 0.5 GREEN: add `constructed_child_env(names, label)` to
      `scripts/audit_cli.py`; wire both call sites in `run_box_step` and
      `run_sensitivity_drive` to it, dropping their duplicated dict-comps.
- [ ] 0.6 GREEN: `SKILL.md` allowlist doctrine paragraph states the name is
      injected, never inherited, never recipe-declarable; one `How the moves
      fail` row added.
- [ ] 0.7 Mutation-reachability proof: mutate the injection line, confirm
      0.1/0.2 go red for the stated reason, then restore via `cp` backup.

### Commit a1 — the `inversion` mechanism (forecast 760–950)

- [ ] a1.1 RED: baseline gate — a red-before-mutation subject refuses the
      whole sweep `kind=baseline-not-green`, no fact mutated, no finding
      emitted (spec condition 11, both scenarios).
- [ ] a1.2 RED: condition 1 — absent literal at `(file, line)` halts
      `Unprobeable` before any write.
- [ ] a1.3 RED: condition 2 — a no-op write (`sha256(before)==sha256(after)`)
      halts before the observing run ever executes.
- [ ] a1.4 RED: condition 3 — a same-length mutation still executes fresh
      source, never a cached `.pyc` (depends on commit 0's helper).
- [ ] a1.5 RED: condition 4 — literal present 0 times → `fact-absent`;
      present ≥2 times on the declared line → `fact-ambiguous`; neither
      substitutes.
- [ ] a1.6 RED: condition 5 — restore via `restore_exact_bytes` confirmed by
      sha256; a digest mismatch halts the sweep and the next fact is
      untouched. Separately lock that `git checkout --` is never invoked by
      this subcommand (grep-on-source lock).
- [ ] a1.7 RED: condition 6 — `COMPARISON_OPERATORS` stripped from
      `literal`/`replacement`; equal remainders refuse `kind=operator-flip`.
- [ ] a1.8 RED: condition 7 — the declared `observe.argv`/harness runs, never
      a hand-picked subset; a repo with two suites runs both, separately.
- [ ] a1.9 RED: condition 8 — a green mutation emits a `## Not adjudicable`
      finding with `- Move: 6`, `- Adjudication: not adjudicable`, and
      `- Remedy: undecided: <reason>` — never silently accepted.
- [ ] a1.10 RED: cap/overflow — a 10-fact recipe drives exactly 8, names the
      remaining 2 individually under `## Unchecked`.
- [ ] a1.11 RED: exit-code contract — all-obsolete drive exits `0`; a
      restore-digest mismatch on any one fact exits `2`.
- [ ] a1.12 RED: a recipe with no `mutations` block refuses, naming the
      missing block, never reporting zero facts.
- [ ] a1.13 RED: `build-escaped-the-box` — a drive writing outside the
      declared file exits `2`, sweep halts.
- [ ] a1.14 GREEN: implement `run_inversion` + fact resolution/write/observe/
      restore helpers in `scripts/audit_cli.py`; wire `build_parser` +
      `DISPATCH` for the `inversion` subcommand.
- [ ] a1.15 GREEN: same commit — subcommands-table row, exit-codes
      paragraph, shipped-files row for the new self-probe recipe, one worked
      `references/usage.md` invocation, moves-table row 6 `Ships as` moved
      off `doctrine`, Decision Gates rows, Move 6 detail rewritten to v1's
      actual scope (sources facts only from `mutations`, no AST classifier,
      emits only `undecided: <reason>`).
- [ ] a1.16 GREEN: add `references/probes/skill-audit.self-guarded-facts.json`
      per the `mutations` grammar (resolve under `--subject`, no absolute
      path, no `..`; 1-based `line`).
- [ ] a1.17 Verify: `roster` self-probe against `SKILL.md`'s shipped-files
      table shows no `unregistered` for the new recipe row.

### Commit a2 — the report side (forecast 165–245)

- [ ] a2.1 RED: condition 9 — a not-adjudicable Move-6 reason naming none of
      `UNDISTINGUISHED_CAUSES` (`"obsolete guard"`, `"equivalent mutant"`,
      `"degenerate fixture"`, `"none determined"`) fails `check-report`,
      stricter than today's any-non-empty-string acceptance.
- [ ] a2.2 RED: condition 10 — a report with a red Move-6 finding and no
      reachability-vs-coverage statement fails `check-report`.
- [ ] a2.3 RED: doctrine-agreement lock — every `UNDISTINGUISHED_CAUSES`
      member appears verbatim in `SKILL.md`'s `remedy` row (the
      `stage_model_total` idiom).
- [ ] a2.4 RED: `ReportSchemaSelfDescriptionTests`-style lock binding the new
      `reachability` `REPORT_SHAPE` key to its `SKILL.md` row, both
      directions.
- [ ] a2.5 GREEN: implement the condition-9 cause check inside the existing
      `undecided:` branch and the condition-10 `- Reachability: fires|silent:
      <what this does not prove>` per-finding field in `run_check_report`.
- [ ] a2.6 GREEN: add the `reachability` key to `REPORT_SHAPE` with its
      `SKILL.md` row, same commit.
- [ ] a2.7 GREEN: add a Move-6 not-adjudicable finding to
      `references/example-report.md` carrying a named cause and the
      reachability statement; recompute and update `- Self-digest:` in this
      same commit (`HistoricalReportRecordTests` stays untouched — this file
      is not the pinned one).
- [ ] a2.8 Verify: `check-report` validates `references/example-report.md`
      without further edits at read time.

### Commit b — `the-defects-already-within-reach` (forecast 215–275, no code)

- [ ] b.1 RED: `roster` recipe reaching the thrice-spelled constant via
      `restatement_of`/`duplicated`, *conditional* on a driveable producer
      whose refusal message emits the closed set. If none exists, the RED
      target is the `no-closed-roster` finding itself, not a silent skip.
- [ ] b.2 RED: `walkthrough` recipe naming, in documented order, the step
      whose expectation is sunk by an earlier step's own correct-in-isolation
      check, including the two-decisions-combine-to-a-false-refusal case.
- [ ] b.3 RED: `structure` from-zero recipe proving a declared requirement is
      never demanded of a repository built from nothing.
- [ ] b.4 GREEN: author/widen the three `references/probes/*.json` recipes
      only; add their shipped-files rows in the same commit. No edit to
      `scripts/audit_cli.py`.
- [ ] b.5 Verify: `roster`/`walkthrough`/`structure` self-probes stay clean
      against the widened recipes; `unregistered`/`phantom` remain empty.

---

## Change B — `the-audit-grades-what-a-step-wrote` (new SDD change, owner-approved)

### Commit B1 — R6 (forecast 370–500)

- [ ] B1.1 RED: box digest unchanged across a non-`readOnly` step → finding
      "step returned without producing".
- [ ] B1.2 RED: box digest changed entirely inside declared `roots` → clean,
      counts still reported.
- [ ] B1.3 RED: box digest changed partly/wholly outside declared `roots` →
      finding "wrote into a tree it does not own".
- [ ] B1.4 RED: box digest unchanged, step declared `readOnly` → no finding.
- [ ] B1.5 RED: **subject** digest changed across any step →
      `Unprobeable kind=step-escaped-the-box`, sweep halts (the gap
      `structure` already has at `audit_cli.py:1258-1266` and `walkthrough`
      does not).
- [ ] B1.6 GREEN: add per-step `tree_digest(box)` before/after and the
      subject-level escape gate to `run_walkthrough`; add `roots`/`readOnly`
      recipe fields. Reuse `tree_digest` verbatim (`SingleWalkTests` stays
      green with no edit).
- [ ] B1.7 GREEN: `SKILL.md` Move 8 detail states the box-not-subject
      digest scope and the new escape gate; subcommand doc updated.

### Commit B2 — R2+R3 (forecast 520–680)

- [ ] B2.1 RED: control gate — a guard that never fires reports
      `kind=guard-never-fires`, not eleven unreachable-variant findings.
- [ ] B2.2 RED: `identifier_variants` derives plural/underscore-joined/
      case-joined forms for a guarded member; a variant the guard's matcher
      cannot reach is named.
- [ ] B2.3 RED: no driveable guard on the subject → `kind=no-driveable-guard`
      with the searched range, never an empty roster.
- [ ] B2.4 RED (R3): rename probe — substitute the guarded member with a
      neutral token, leave every other byte alone, re-drive; result is one of
      exactly two values in `IDENTITY_MEASURED = ("identity-measured",
      "not-determined")`.
- [ ] B2.5 RED: cardinality lock on `IDENTITY_MEASURED` (exactly two
      members, no third value ever emitted).
- [ ] B2.6 RED: every R3 payload carries the permanent stated limit
      (`READING_DIFF_LIMIT` precedent) regardless of verdict.
- [ ] B2.7 GREEN: implement `guardReach` recipe block +
      `identifier_variants` (pure function) + the control-gate drive inside
      `roster`, reusing `probe_code_side` for the guarded-member producer
      side only (no new source parsing).
- [ ] B2.8 GREEN: implement the R3 rename-probe drive in `roster`, same
      loop, second transformation; add the carried-limit constant.
- [ ] B2.9 GREEN: `SKILL.md` Move 0 detail states both new checks and the
      identity-vs-content limit sentence.

### Commit B3 — R5+R4 (forecast 500–700)

- [ ] B3.1 RED: a produced artefact of zero length (`EMPTY_FILE_SHA256`
      constant) reports `produced-but-empty`, distinct from `absent`.
- [ ] B3.2 RED: an artefact kind with a recipe-declared `contentPattern`
      that the produced content does not match reports `carries-no-match`.
- [ ] B3.3 RED: an artefact kind with **no** declared `contentPattern`
      reports `content-not-declared`, never assumed full.
- [ ] B3.4 RED: `### Demanded, not scaffolded` under `## User drive` is
      required non-empty (or explicit `(none)`), enforced by the same
      pattern as `user_drive_declared_only_nonempty`
      (`audit_cli.py:2317`) — reuse, not reimplementation.
- [ ] B3.5 GREEN: `structure`'s `produced`/`produced-but-empty`/`absent`
      roster from the already-built `tree_digest(from_zero_root, exclude)`;
      add `EMPTY_FILE_SHA256` constant.
- [ ] B3.6 GREEN: add `### Demanded, not scaffolded` enforcement in
      `run_check_report`, item-conditional (no `REPORT_SHAPE` key, no door
      opened, no `example-report.md` re-sign needed).
- [ ] B3.7 GREEN: `SKILL.md` states R4's structural-only scope explicitly —
      an operator declaration, never a proof — and records the derived
      stronger form as deferred with its own name.

---

## Change C — `the-questions-the-eleven-moves-do-not-ask` (new SDD change, owner-approved)

### Commit C1 — R7: `exits` (forecast 720–980)

- [ ] C1.1 RED: `published-and-ran` — a well-formed act runs and its exit
      code is **not read** (reachability, not success); a lock proves this
      by asserting a *refusing* act still reports `published-and-ran`.
- [ ] C1.2 RED: at least one lock **executes** a published act end-to-end
      (not merely asserting a "carries a resolve key" field) — the
      guard-a-weaker-guard-survives requirement for this move specifically.
- [ ] C1.3 RED: admission gate — a shell-metacharacter act →
      `published-but-unparseable`, never passed to `shell=True`.
- [ ] C1.4 RED: `argv[0]` outside `--subject`/`--repo-root` and outside the
      recipe's declared interpreter allowlist → refused before any process
      starts.
- [ ] C1.5 RED: a missing binary → `published-but-not-executable`
      (`FileNotFoundError`); a hanging act → `published-but-timed-out`
      (per-act timeout).
- [ ] C1.6 RED: no published act, recipe/subject declares it a human
      judgement → `judgement`, reported, **not** a finding.
- [ ] C1.7 RED: no published act, nothing declared → `unstated`, a finding,
      with the driveable range searched.
- [ ] C1.8 RED: real-subject `tree_digest` before/after mismatch →
      `Unprobeable kind=exit-escaped-the-box`, sweep halts; `erase_box` still
      runs in `finally`.
- [ ] C1.9 GREEN: implement `run_exits`, the five-value closed roster, the
      admission gate, `materialize_subject_copy` (reused verbatim) for the
      act's own run, `constructed_child_env` (commit 0's helper) for its
      environment, `build_parser` + `DISPATCH`.
- [ ] C1.10 GREEN: same commit — moves-table row 11, subcommands row,
      exit-codes paragraph, shipped-files row, one `usage.md` invocation,
      `references/example-report.md` re-signature (an exit finding is an
      ordinary ranked finding carrying `- Move: 11`, adds **zero**
      `REPORT_SHAPE` keys — confirm `ReportSchemaSelfDescriptionTests` stays
      untouched).
- [ ] C1.11 GREEN: doctrine states the stated-out-of-reach item explicitly —
      the audit does not guess at an unpublished exit's identity; it reports
      `unstated` plus the searched range.

### Commit C2 — R1: enumeration-reach subcommand (forecast 700–960)

- [ ] C2.1 RED: a check whose stated claim is universal and whose
      enumeration source is a literal collection is reported with both facts
      side by side.
- [ ] C2.2 RED: a check whose enumeration source is computed from the
      subject is reported `derived`, not a finding.
- [ ] C2.3 RED: `single-namespace` and `filtered-subset` each classified
      correctly from a fixture AST (four-value closed roster:
      `derived`, `literal-collection`, `single-namespace`,
      `filtered-subset`).
- [ ] C2.4 RED: a non-Python subject's checks report
      `unreachable-for-this-language`, never guessed.
- [ ] C2.5 RED: AST-sweep lock proving this new subcommand does not fork a
      second code-side derivation inside `run_roster` (R1 stays out of
      `roster` entirely, per the design's own rejection of that placement).
- [ ] C2.6 GREEN: add `ast` to the import line (confirm still absent first);
      implement the new subcommand parsing the subject's own check source
      (`tests/test_skill_audit.py` sits at the repo root — reuse
      `resolve_site`'s `root: "repo"`, no new path grammar) and classifying
      each check's iteration source.
- [ ] C2.7 GREEN: same commit — moves-table row 12, subcommands row,
      exit-codes paragraph, shipped-files row, `usage.md` invocation,
      `references/example-report.md` re-signature.
- [ ] C2.8 GREEN: doctrine states the Python-only ceiling and the
      language-independence argument for why R1 could not live in `roster`.

---

## Measured errors found in this phase

1. **Line-count claim off by 15.** The brief states `spec.md` is 647 lines;
   read directly, it is 662 lines (confirmed by reading lines 640–662, the
   file's true end). Minor, but the corrections-count precedent set by this
   change means it gets stated rather than silently carried forward.
2. **A requirement the design's own narrowing note promised a home for has
   none.** `spec.md:322-328` (the `NARROWED` note on "No new code in this
   change") states that "per-step digests and a filesystem-versus-roster
   enumeration... move to `audit-scope-hardening` where they are implemented
   as code." Per-step digests became R6 (Move 8, Commit B1) — confirmed. The
   filesystem-versus-roster enumeration is
   **`spec.md:435–465`, "Artefacts on disk that the flow's declared roster
   never names"** — enumerate an artefact kind across the subject tree,
   subtract the flow's own declared roster, report the remainder. This
   requirement does **not** appear among `audit-scope-hardening`'s seven
   headings (verified: R1–R7 at `spec.md:475, 517, 539, 559, 583, 603, 632`
   are the complete list), and the design's re-forecast maps every one of
   R1–R7 to B1/B2/B3/C1/C2 with none left over. The requirement is real,
   distinct from R5 (which grades content of artefacts a drive *did*
   produce, not the existence of ones a flow never named), and currently
   has **no commit, no forecast, and no design decision**. Not added to any
   task list above — inventing its placement here would be the exact
   scope-smuggling this skill is built to catch. Flagged for the owner: it
   needs either an eighth requirement slot (closest fit is alongside B1,
   since both attach to `walkthrough`'s produced-artefact accounting) or an
   explicit, stated deferral before Change B's tasks are considered
   complete against the spec.

## Citations checked

Every symbol re-cited above (`run_box_step`, `run_sensitivity_drive`,
`run_walkthrough`, `probe_code_side`, `tree_digest`, `materialize_subject_copy`,
`restore_exact_bytes`, `report_identity_gate`, `resolve_site`, `resolve_under`,
`move_roster`, `stage_roster`, `erase_box`, `run_check_report`,
`READING_DIFF_LIMIT`, `DRIVER_ENV_ALLOWLIST`, `REPORT_SCHEMA_VERSION`,
`FORGE_LEXICON`, `dict_literal_keys`, `subcommand_surface`,
`ReportSchemaSelfDescriptionTests`, `HistoricalReportRecordTests`,
`test_every_row_ships_as_a_real_subcommand_or_as_doctrine`) was located by
name in `scripts/audit_cli.py` and `tests/test_skill_audit.py` before being
repeated here, not inherited by line number from the design.
