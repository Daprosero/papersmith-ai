
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

### Commit 0 — `a-driven-child-purges-its-own-bytecode` (forecast 150–195) — **DONE**, commit `08428f1`, 210 lines

- [x] 0.1 RED: lock asserting `run_box_step`'s driver-kind child env carries
      `PYTHONDONTWRITEBYTECODE=1` even when absent from the parent env
      (`tests/test_skill_audit.py`, new `ChildEnvTests`).
- [x] 0.2 RED: lock asserting `run_sensitivity_drive`'s child env carries the
      same purge, independent of whether `run_box_step` ran in the process.
- [x] 0.3 RED: lock asserting a `driver` step declaring
      `PYTHONDONTWRITEBYTECODE` in `env` is still refused `Unprobeable`
      (name stays out of `DRIVER_ENV_ALLOWLIST`). Measured: this one already
      held against unmodified code (pre-existing behavior, not new); kept as
      a regression guard.
- [x] 0.4 RED: AST class-sweep lock proving no third `os.environ[...]`
      child-env comprehension exists outside `constructed_child_env`.
- [x] 0.5 GREEN: add `constructed_child_env(names, label, hint="")` to
      `scripts/audit_cli.py`; wire both call sites in `run_box_step` and
      `run_sensitivity_drive` to it, dropping their duplicated dict-comps.
- [x] 0.6 GREEN: `SKILL.md` allowlist doctrine paragraph states the name is
      injected, never inherited, never recipe-declarable; one `How the moves
      fail` row added.
- [x] 0.7 Mutation-reachability proof: mutated the injection line, confirmed
      0.1/0.2 go red for the stated reason, then restored via `cp` backup.

### Commit a1 — the `inversion` mechanism (forecast 760–950) — **DONE**, commit `b288981`, 880 lines

- [x] a1.1 RED: baseline gate — a red-before-mutation subject refuses the
      whole sweep `kind=baseline-not-green`, no fact mutated, no finding
      emitted (spec condition 11, both scenarios).
- [x] a1.2 RED: condition 1 — absent literal at `(file, line)` halts
      `Unprobeable` before any write.
- [x] a1.3 RED: condition 2 — a no-op write (`sha256(before)==sha256(after)`)
      halts before the observing run ever executes.
- [x] a1.4 RED: condition 3 — a same-length mutation still executes fresh
      source, never a cached `.pyc` (depends on commit 0's helper).
- [x] a1.5 RED: condition 4 — literal present 0 times → `fact-absent`;
      present ≥2 times on the declared line → `fact-ambiguous`; neither
      substitutes.
- [x] a1.6 RED: condition 5 — restore via `restore_exact_bytes` confirmed by
      sha256; a digest mismatch halts the sweep and the next fact is
      untouched. Separately locked that `git checkout --` is never invoked by
      this subcommand (grep-on-source lock, exact `ast.Constant` match).
- [x] a1.7 RED: condition 6 — `COMPARISON_OPERATORS` stripped from
      `literal`/`replacement`; equal remainders refuse `kind=operator-flip`.
      **Bug found by this exact RED test**: identical literal/replacement was
      misclassified as `operator-flip` instead of falling through to
      `no-op-write`; fixed with a `literal != replacement` guard.
- [x] a1.8 RED: condition 7 — the declared `observe.argv`/harness runs, never
      a hand-picked subset; a repo with two suites runs both, separately.
- [x] a1.9 RED: condition 8 — a green mutation emits a `## Not adjudicable`
      finding with `- Move: 6`, `- Adjudication: not adjudicable`, and
      `- Remedy: undecided: <reason>` — never silently accepted.
- [x] a1.10 RED: cap/overflow — a 10-fact recipe drives exactly 8, names the
      remaining 2 individually under `## Unchecked`.
- [x] a1.11 RED: exit-code contract — all-obsolete drive exits `0`; a
      restore-digest mismatch on any one fact exits `2`.
- [x] a1.12 RED: a recipe with no `mutations` block refuses, naming the
      missing block, never reporting zero facts.
- [x] a1.13 RED: `build-escaped-the-box` — a drive writing outside the
      declared file exits `2`, sweep halts.
- [x] a1.14 GREEN: implemented `run_inversion` + `run_inversion_observe` +
      `strip_comparison_operators` in `scripts/audit_cli.py`; wired
      `build_parser` + `DISPATCH` for the `inversion` subcommand.
- [x] a1.15 GREEN: same commit — subcommands-table row, exit-codes
      paragraph, shipped-files row for the new self-probe recipe, one worked
      `references/usage.md` invocation, moves-table row 6 `Ships as` moved
      off `doctrine`, Decision Gates rows, Move 6 detail rewritten to v1's
      actual scope (sources facts only from `mutations`, no AST classifier,
      emits only `undecided: <reason>`). The flat "obsolete guard" sentence
      was deliberately left untouched here — that correction is a2's job.
      Also required, discovered while running the full suite (not scoped to
      this feature): adding `run_inversion` to `NothingWasRepairedTests`'s
      box-lifecycle exemption with its own byte-identity proof test, and
      updating a pre-existing hardcoded subcommand list in
      `SelfAuditSubcommandRosterTests`.
- [x] a1.16 GREEN: added `references/probes/skill-audit.self-guarded-facts.json`
      per the `mutations` grammar, guarding `REPORT_SCHEMA_VERSION` against
      the real `SchemaVersionDerivationTests`. Its `line` field is brittle —
      shifted twice (2983→2992→3013) as code was inserted above it during
      this same commit and again during a2; re-derive before any future edit
      that adds code above `REPORT_SCHEMA_VERSION`.
- [x] a1.17 Verify: measured that `roster` against the shipped `structure.json`
      recipe does **not** actually check the shipped-files table (it returns
      `"no derivation available for this surface"`, vacuously empty
      `unregistered`/`phantom`) — a wording gap in this task, reported back.
      Verified manually instead via `audit_cli.markdown_table_rows` +
      `rglob` directly: zero `unregistered`, zero `phantom`.

### Commit a2 — the report side (forecast 165–245) — **DONE**, commit `8da9383`, 318 lines

- [x] a2.1 RED: condition 9 — a not-adjudicable Move-6 reason naming none of
      `UNDISTINGUISHED_CAUSES` (`"obsolete guard"`, `"equivalent mutant"`,
      `"degenerate fixture"`, `"none determined"`) fails `check-report`,
      stricter than today's any-non-empty-string acceptance.
- [x] a2.2 RED: condition 10 — a report with a red Move-6 finding and no
      reachability-vs-coverage statement fails `check-report`.
- [x] a2.3 RED: doctrine-agreement lock — every `UNDISTINGUISHED_CAUSES`
      member appears verbatim in `SKILL.md`'s `remedy` row (the
      `stage_model_total` idiom).
- [x] a2.4 RED: `ReportSchemaSelfDescriptionTests`-style lock binding the new
      `reachability` `REPORT_SHAPE` key to its `SKILL.md` row, both
      directions (plus reuse of the existing generic bidirectional test,
      which covers this automatically).
- [x] a2.5 GREEN: implemented the condition-9 cause check inside the existing
      `undecided:` branch and the condition-10 `- Reachability: fires|silent:
      <what this does not prove>` per-finding field in `run_check_report`,
      scoped to `- Move: 6` alone (never also gated on adjudication).
- [x] a2.6 GREEN: added the `reachability` key to `REPORT_SHAPE` with its
      `SKILL.md` row, same commit.
- [x] a2.7 GREEN: added a Move-6 not-adjudicable finding (F3) to
      `references/example-report.md` carrying a named cause and the
      reachability statement; recomputed `- Self-digest:` via
      `audit_cli.report_self_digest()` directly (`HistoricalReportRecordTests`
      untouched — different, pinned file). **Also required**, discovered by
      running the full suite: two pre-existing shared fixtures
      (`REMEDY_REPORT_BODY`, `REMEDY_REPORT_ONE_BUCKET_BODY`) needed
      `- Reachability:` lines added and one `undecided` reason corrected to
      name a real cause, or the new conditions would have broken them.
- [x] a2.8 Verify: `check-report` validates `references/example-report.md`
      without further edits at read time — confirmed, `{"violations": []}`.

### Commit b — `a-check-that-cannot-fire-says-so` (forecast 215–275, superseded) — **DONE**

The three recipe-widening recipes originally specced here were each measured
away rather than written: one target was already fixed earlier in this same
session (b.2), one would have manufactured a false-positive `duplicated`
finding against legitimate per-command documentation (b.1's first half), and
the third would have built a new probe rather than widened a shipped one,
contrary to this change's own cheaper-than-building rationale (b.3). Writing
any of them would have been theatre. What b.1's investigation found instead,
while it was blocked, was real and load-bearing for this skill's own subject:
**`skill-audit` ships a check that cannot fire.**

- [x] b.1 (superseded) RED/GREEN, **the real defect**: `run_roster`'s
      `restatementSearch` mechanism requires `len(duplicated) >= 2`
      independently matching sites before `duplicated` reports anything —
      correctly, since one restatement is not a duplication
      (`audit_cli.py`, was `if len(duplicated) < 2: duplicated = []`). Two
      shipped recipes declare exactly **one** `restatementSearch` path —
      `references/probes/remote-execution.accepted-operations.json`
      (quorum 4, one path: `SKILL.md`) and
      `references/probes/skill-audit.subcommands.json` (quorum 2, one
      path: `SKILL.md`) — so both are structurally incapable of ever
      producing a `duplicated` finding, regardless of what that one path
      holds. A third, `proposal-deliberation.accepted-operations.json`,
      declares three paths and can fire (confirmed:
      `DuplicatedTests` already exercises it green). Nothing said so on a
      run of either dead recipe; a green run read exactly like a run that
      searched and found nothing.
- [x] b.1a GREEN: added `RESTATEMENT_SITE_QUORUM = 2` as the single source
      for the runtime cutoff (`len(duplicated) < RESTATEMENT_SITE_QUORUM`)
      and the new note's own message, so the two never carry two spellings
      of one threshold — the exact defect class this repository has now
      been bitten by three times. Added a `restatement-search-cannot-fire`
      note, following the `comparison-not-run` precedent immediately below
      it in the same function: reported, never a refusal, naming the
      recipe's declared path count and the count the mechanism requires.
      Classified under `ESCALATION_BUCKETS["deterministic-exclusion"]` —
      there is no prose behind a too-short path list for a reader to
      escalate towards; it is a structural fact about the recipe's own
      declaration. **Consequence, measured**: inserting this code above
      `REPORT_SCHEMA_VERSION` shifted its line a third time (3013→3034,
      after a1/a2's own 2983→2992→3013) — a1.16's own documented
      brittleness fired exactly as predicted, caught by
      `NothingWasRepairedTests`/`UsageReferenceTests` going red on the
      first full-suite run, and fixed by re-deriving
      `skill-audit.self-guarded-facts.json`'s declared `line`, not by
      editing either test.
- [x] b.1b GREEN: `SKILL.md`'s Decision Gates table gains one row, in the
      register of the surrounding rows, immediately after "A set is
      restated by hand in more than one place": the row for what happens
      when the search cannot reach two matching sites at all.
- [x] b.1c RED, mutation-reachability proof: five new locks in
      `RestatementSearchCannotFireTests`. The discriminating one
      (`test_one_declared_path_cannot_reach_the_quorum`) uses a
      **non-empty** one-path fixture — the actual shipped shape — so a
      weaker guard proving only "a note fires when `paths` is empty" could
      not pass in its place; mutating the emission condition from
      `declared_paths < RESTATEMENT_SITE_QUORUM` to `declared_paths == 0`
      left exactly that one lock red while the rest of the suite (and the
      other four new locks) stayed green, confirmed by `git diff --stat`
      before and after, and restored by `cp` from a scratch backup,
      confirmed byte-identical by sha256, never `git checkout --`.
- [x] b.1d Verify: whether either dead recipe gains a real second path was
      measured, not assumed, for both. `remote-execution` has no
      `references/` directory at all and no other file restating its nine
      commands by hand within a bounded search — left alone.
      `skill-audit`'s own `tests/test_skill_audit.py` (resolvable via
      `resolve_site`'s `root: "repo"`, since the test file sits at the
      repository root) does contain a genuine hand-copied literal list of
      all seven subcommand names in
      `SelfAuditSubcommandRosterTests.test_the_subcommand_roster_reports_three_sets_and_no_boolean`
      — but measured against `restatement_of`'s crude "member is a
      substring of some line" matching, every one of those seven names
      already occurs 14–163 times throughout that ~5,700-line file as
      ordinary skill-audit vocabulary (`roster` alone: 163 times, first
      hit at line 3, nowhere near the genuine list at line 1139). Adding
      this file as a second path would report `duplicated` at a false
      line, for an incidental vocabulary-collision reason rather than
      because the genuine restatement was found — manufacturing a
      misleading positive of exactly the shape this skill exists to
      refuse, extending the caution b.1's own blocked investigation
      already established for a sibling skill's `usage.md`. Both recipes
      left unchanged; the note is the honest output for both.
- [x] b.2 (superseded, unchanged from the original investigation):
      `proposal-implementation`'s `position`/`gate`/`close` false
      `POSITION_UNBACKED` refusal is already fixed as
      `POSITION_SHARDS_UNDECLARED`; a `walkthrough` recipe reaching for it
      would prove nothing against current `SKILL.md`.
- [x] b.3 (superseded, unchanged): no `structure` recipe exists yet for
      either sibling subject; building one is building a new probe, not
      widening a shipped one, contrary to this commit's own rationale.

**Owner input no longer needed for this commit.** The original three-way
choice this section asked for is moot: b.1's real finding replaced the
blocked recipe work rather than requiring a decision between it.

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
