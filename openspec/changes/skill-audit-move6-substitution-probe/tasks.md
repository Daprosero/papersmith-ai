# Tasks: Automate Move 6, and widen what already reaches

> **Stated exception to the 530-word tasks cap**, for the same reason
> proposal/spec/design took theirs: this change's subject is doctrine that
> overclaims relative to shipped code, and eleven soundness conditions each
> need their own RED before their GREEN under `strict_tdd: true`. Dropping a
> condition's task to fit a budget is the defect this skill hunts.

Four commits, one branch, `the-pilot-proves-the-science` precedent (folder
confirmed on disk: `openspec/changes/the-pilot-proves-the-science/`). Order:
**0 → a1 → a2**, strictly sequential (a1 needs 0's helper for conditions 3
and 11; a2 needs a1's `run_inversion` and its emitted fields). **b** has no
code dependency on 0/a1/a2 but ships last so its recipes target the shipped
`inversion` surface, not a moving one.

**Every RED/GREEN cycle, every commit**: purge `__pycache__` under
`.claude/skills/skill-audit/`, run with `PYTHONDONTWRITEBYTECODE=1`. After
any mutation-style edit inside a test, confirm the file actually changed via
`git diff --stat` before trusting the run — an anchor that matched is not a
mutation that ran. Both suites, serially, never concurrently:
`npm test && .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
Baseline on `main`: 2377 Python (skipped=3), 386 node — each commit's count
must **rise** by the number of tests it adds; a merely-green suite is not
evidence. Scratch fixtures use the existing `f"_{os.getpid()}"` suffix, never
a fixed name. A surviving mutation has two explanations, not one — a weak
test or a wrong claim about the code; measure before strengthening.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 0: 150–195 · a1: 760–950 · a2: 165–245 · b: 215–275 (design's own per-commit forecast; independently plausible against the file's measured shape) |
| Cached review budget this session | 1400 lines (overrides the skill's 400-line default; every commit sits at 6–68% of it) |
| 1400-line budget risk | Low — every commit is independently under budget; the widest, a1 at 950, still leaves 450 lines of headroom |
| Chained PRs recommended | No — the four-commit shape is already the split; no commit needs further slicing |
| Chain strategy | pending — not collected, and not needed: agreeing with the design's own forecast, the guard does not fire |
| Delivery strategy | ask-on-risk |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

**My forecast agrees with the design's.** I re-measured the concrete edit
surface for each commit (call sites, constant lists, REPORT_SHAPE keys,
SKILL.md sections, test count) against the live file rather than trusting
the range as given; nothing pushes any commit toward 1400. No exception
request, no chain-strategy question needed.

### Suggested Work Units

| Unit | Goal | Focused test command | Runtime harness | Rollback boundary |
|------|------|----------------------|------------------|--------------------|
| 0 | Bytecode purge, both sites | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_skill_audit -k ChildEnv` | N/A — pure unit-level env construction, no live driver needed | `constructed_child_env` + 2 call-site edits revert as one hunk; re-arms the `.pyc` trap if reverted alone after a1 lands |
| a1 | `inversion` mechanism + doctrine narrowing | `.venv/bin/python -m unittest tests.test_skill_audit -k Inversion` | `python3 scripts/audit_cli.py inversion --subject . --spec references/probes/skill-audit.inversion.json --repo-root .` | Whole subcommand + its SKILL.md rows revert as one unit; a2 cannot land without it |
| a2 | Report-shape conditions 9/10 | `.venv/bin/python -m unittest tests.test_skill_audit -k Reachability` | `python3 scripts/audit_cli.py check-report references/example-report.md` | `REPORT_SHAPE` key + validator branch + fixture revert together; a1 stays correct without it |
| b | Three widened recipes | per-recipe `roster`/`walkthrough`/`structure` invocation named in Phase 3 | Each recipe run live against its named subject | Each recipe file/row reverts independently; no code touched |

---

## Phase 0 — `a-driven-child-purges-its-own-bytecode` (150–195)

- [ ] 0.1 RED: add two locks in `tests/test_skill_audit.py` asserting `run_box_step`'s driver child-env and `run_sensitivity_drive`'s child-env both carry `PYTHONDONTWRITEBYTECODE=1` even with it absent from the parent env and undeclared by the recipe (spec scenarios "Purge holds regardless of parent environment" / "Both sites carry the purge, not one"). Confirm both fail for "helper/key missing", not an import error.
- [ ] 0.2 RED: add one AST lock proving no `{name: os.environ[name] for name in names if name in os.environ}`-shaped child-env comprehension exists outside a single shared helper (the class-sweep proof, mirrors the existing seven `ast.parse(CLI.read_text(encoding="utf-8"))` locks). Confirm it fails today (two sites, no shared helper).
- [ ] 0.3 GREEN: add `constructed_child_env(names, label)` to `.claude/skills/skill-audit/scripts/audit_cli.py` per design's code block; replace both call sites (`run_box_step`, `run_sensitivity_drive`) to call it. `git diff --stat` must show both call sites changed. Re-run 0.1–0.2 green.
- [ ] 0.4 Characterization (no code change expected): add/keep a lock that a `driver` step's `env` list naming `PYTHONDONTWRITEBYTECODE` still raises `Unprobeable` (spec scenario "An explicit declaration still refuses the step") — `DRIVER_ENV_ALLOWLIST` is untouched by 0.3, so this proves the doctrine holds, not a new capability.
- [ ] 0.5 Update `SKILL.md`'s `DRIVER_ENV_ALLOWLIST` doctrine paragraph: the name is injected, never inherited, never recipe-declarable. Add one `How the moves fail` row for the closed defect.
- [ ] 0.6 Run both suites serially; confirm Python count rose by exactly the locks added in 0.1–0.2; record the commit boundary.

## Phase 1 — `a1`: the `inversion` mechanism (760–950)

Depends on Phase 0. Conditions below are spec's 1–11; each RED must state
which condition it proves and fail for that reason, not a stub `NotImplementedError`.

- [ ] 1.1 RED+GREEN (condition 11, baseline gate): a red-baseline recipe refuses the whole sweep `Unprobeable kind=baseline-not-green`, mutates nothing, emits no finding (two spec scenarios); a green baseline is not itself a finding. Implement inside `run_inversion`, driven through 0.3's helper.
- [ ] 1.2 RED+GREEN (condition 1): an absent literal at the declared `(file, line)` halts `Unprobeable` before any write.
- [ ] 1.3 RED+GREEN (condition 4): a literal matching twice on the declared line halts `Unprobeable kind=fact-ambiguous`; zero matches reuses 1.2's path.
- [ ] 1.4 RED+GREEN (condition 6): deleting every `COMPARISON_OPERATORS` member from `literal` and `replacement` and comparing remainders; equal remainders refuse `kind=operator-flip`.
- [ ] 1.5 RED+GREEN (condition 2): write the replacement, assert `sha256(after) != sha256(before)` **before** the observing run; a no-op write halts and the run never executes.
- [ ] 1.6 RED+GREEN (condition 5 + Commit-state threat row): restore via recorded inverse patch, confirm by sha256 equality, never `git checkout --`; a digest mismatch halts the sweep and the next fact is untouched. Add the `tree_digest(subject)` before/after box-escape gate — mismatch is `kind=build-escaped-the-box`, never a finding.
- [ ] 1.7 RED+GREEN (condition 7 + Subprocess-composition threat row): the observing run executes the exact declared `argv`/`cwd`/`env` per fact, `shell=False`, per-step timeout, `assert_no_subject_reference`; a hang exits `2`; an `env` name outside `DRIVER_ENV_ALLOWLIST` exits `2`.
- [ ] 1.8 RED+GREEN (condition 3): a same-byte-length mutation still executes fresh source, proven by running the observing suite through 0.3's helper only — no independent child-env construction inside `inversion`.
- [ ] 1.9 RED+GREEN (Git-repository-selection threat row): an absolute `file` path and one containing `..` each exit `2` via `resolve_site`/`resolve_under`, matching `sensitivity`'s existing discipline.
- [ ] 1.10 RED+GREEN (condition 8): a fact whose mutation leaves its declared run green produces a `## Not adjudicable` finding carrying `- Move: 6`, `- Adjudication: not adjudicable`, `- Remedy: undecided: <reason>` (v1 has no classifier — never `delete`/`update`), never reported as clean.
- [ ] 1.11 RED+GREEN (cap/overflow): a 10-fact recipe yields 8 driven, 2 named individually under `## Unchecked`. Add `INVERSION_FACT_CAP = 8`.
- [ ] 1.12 RED+GREEN (v1 sourcing scope): a recipe with no `mutations` block refuses naming the missing block, never reports zero facts.
- [ ] 1.13 RED+GREEN (exit-code contract): an all-green-mutation drive still exits `0`; any `Unprobeable` path (1.2, 1.3, 1.4, 1.6, 1.12, missing block) exits `2`.
- [ ] 1.14 GREEN: wire `inversion` into `build_parser` + `DISPATCH`; author `references/probes/skill-audit.inversion.json` (self-probe recipe, naming inferred from the `skill-audit.<surface>.json` convention — confirm against `build_parser`'s exact subcommand name at write time). Same commit: subcommands-table row, exit-codes paragraph, shipped-files row, one worked `usage.md` invocation, moves-table row 6 `Ships as` cell.
- [ ] 1.15 RED+GREEN (`roster` self-probe): after 1.14, the skill's own `roster` self-probe against `SKILL.md`'s shipped-files table finds no `unregistered` gap for the new recipe.
- [ ] 1.16 Doctrine correction #1 (ships with the code it describes — this commit establishes v1 has no classifier): rewrite `SKILL.md`'s "Move 6, in detail" sourcing sentence (currently *"derived from the subject's own declared lock roster where one exists, otherwise from the probe recipe's declared `mutations` block"*) to state v1 sources only from `mutations`; replace the AST-classifier paragraph citing `check_citations.py`'s `symbols_in`/`repo_symbols` (confirmed absent from this repository) with a statement that v1 performs no AST-based delete/update classification and every v1 finding carries `undecided: <reason>`. RED: a doctrine-agreement lock asserting `SKILL.md` no longer names `check_citations.py`, `symbols_in`, or `repo_symbols`.

## Phase 2 — `a2`: the report side (165–245)

Depends on Phase 1 (`run_inversion`'s emitted fields).

- [ ] 2.1 RED (condition 9): a `- Remedy: undecided: <reason>` on a Move-6 not-adjudicable finding whose reason names none of the three causes fails `check-report`, stricter than today's any-non-empty-string acceptance.
- [ ] 2.2 GREEN: add `UNDISTINGUISHED_CAUSES = ("obsolete guard", "equivalent mutant", "degenerate fixture", "none determined")`; extend the existing `undecided:` branch (the `elif value == "undecided" or value.startswith("undecided:")` code path) to require the reason names one member.
- [ ] 2.3 RED (condition 10): a report with a red Move-6 finding and no reachability-vs-coverage statement anywhere fails `check-report`.
- [ ] 2.4 GREEN: add `"reachability": "- Reachability:"` to `REPORT_SHAPE` with its `SKILL.md` shape-table row; add `REACHABILITY_VALUES = ("fires", "silent")`; implement the bidirectional scope check (`- Reachability:` required iff `- Move: 6`, refused on every other finding) mirroring the existing `remedy_in_scope` pattern.
- [ ] 2.5 Doctrine correction #2 (ships with condition 9's code, which is what refutes it): rewrite `SKILL.md:160`'s flat *"A guarded fact whose mutation leaves the suite green is an obsolete guard"* into the three-way framing conditions 8/9 require. RED: extend `ReportSchemaSelfDescriptionTests`-style doctrine-agreement lock — each `UNDISTINGUISHED_CAUSES` member must appear verbatim in `SKILL.md`'s remedy row, the same discipline already covering `stage_model_total`/`REPORT_SCHEMA_VERSION`.
- [ ] 2.6 GREEN (no separate RED — reuses 2.1/2.3's locks as proof): add a Move-6 `## Not adjudicable` finding to `references/example-report.md` with `- Remedy: undecided: <reason naming one cause>` and `- Reachability: silent: <what this does not prove>`; recompute `- Self-digest:` in the same commit. Add/extend a test asserting `check-report` exits `0` with zero violations against the updated fixture.
- [ ] 2.7 Run both suites serially; confirm the count rose by exactly the locks added in 2.1–2.5.

## Phase 3 — `b`: three widened recipes, no code (215–275)

No dependency on Phases 0–2's code; ordered last per the constraint (target
the shipped `inversion` surface, not a moving one — relevant only if any
recipe here happened to touch `inversion`, which none do, but the ordering
is honored as stated regardless).

- [ ] 3.1 `roster`/`duplicated`: investigate whether any driveable surface's refusal message emits the closed set containing the thrice-spelled constant (`search.paths` + `search.quorum`), among `proposal-deliberation.accepted-operations.json`, `remote-execution.accepted-operations.json`, or `proposal-implementation.accepted-operations.json`'s subjects. IF found, widen that recipe's `restatement_of`/`duplicated` fields. IF NOT, ship `no-closed-roster` as the finding — not a silent omission.
- [ ] 3.2 `walkthrough`: no existing recipe drives this subcommand today (confirmed — no `references/probes/*.json` declares a `--spec` ordered-steps sequence). Author one against the subject carrying the two-decision false-refusal ordering defect, naming the sunk step and marking everything after it `unreached`.
- [ ] 3.3 `structure` from-zero stage: no existing structure recipe targets a subject other than `skill-audit` itself. Author one whose from-zero side proves the undemanded declaration surfaces as a finding.
- [ ] 3.4 Add each new/widened recipe's shipped-files row in the same commit as the file (the skill's own recorded defect: a probe file landing before its row).
- [ ] 3.5 Run both suites serially; run each new/widened recipe live against its named subject as the runtime harness; confirm the skill's own `structure`/`roster`/`walkthrough` self-probes over `.claude/skills/skill-audit/` itself stay clean.

## Measured corrections to the design/spec

1. **Condition 11 is mechanism work (a1), not report-shape (a2).** Spec
   places it under `Capability: substitution-probe`, not `report-shape`; it
   has no `REPORT_SHAPE` consequence of its own (the baseline result "MUST
   NOT be reported as a finding"). Design's Data Flow and Interfaces
   sections already carried it — the a1 forecast (760–950) already covered
   it before the spec amendment made it numbered condition 11. Filed as
   1.1, not folded into a2.
2. **The two doctrine corrections land in different commits, not one.**
   The brief's "the commit that ships the code they describe" resolves
   them apart: the sourcing/AST-classifier sentence is corrected in a1
   (the commit establishing v1 has no classifier); the "is an obsolete
   guard" flat assertion is corrected in a2 (condition 9's code is what
   refutes it). Design's commit table lumps "Move 6 detail rewritten" into
   a1's row without stating this split; both edits land in the same
   `SKILL.md` section but different commits.
3. **The self-probe recipe's filename is inferred, not cited.** Neither
   design nor proposal names it. `references/probes/skill-audit.inversion.json`
   follows the existing `skill-audit.<surface>.json` convention but must be
   confirmed against `build_parser`'s literal subcommand string at 1.14,
   not assumed.
4. **Change (b)'s `walkthrough` and `structure` targets need new files,
   not edits.** Measured: no existing `references/probes/*.json` declares
   a `--spec` ordered-steps sequence (`walkthrough`'s own grammar), and
   only `skill-audit.structure.json` exists for `structure` — none for the
   other three subjects. "Widened recipes" in the proposal's title
   undercounts two of the three as new files; scope is unchanged, but 3.2
   and 3.3 are authoring tasks, not edits.
5. **The `6d081be` baseline commit could not be verified.** No `git log`/
   `git show` access in this phase's toolset; the count (2377/386) is
   carried as given, not independently reproduced. Flagged for `sdd-apply`
   to confirm before trusting the delta check in 0.6/2.7/3.5.

Every other citation in the brief — seven `ast.parse` lock lines, the
`FORGE_LEXICON` `"inversion"` entry, `DRIVER_ENV_ALLOWLIST`,
`run_box_step`/`run_sensitivity_drive`/`restore_exact_bytes`,
`check_citations.py`'s absence, `SKILL.md:160`'s exact sentence,
`REPORT_SHAPE`'s current keys, `ReportSchemaSelfDescriptionTests`, and
`the-pilot-proves-the-science`'s folder — was re-resolved against the live
files in this session, by symbol/text, not inherited by line number.
