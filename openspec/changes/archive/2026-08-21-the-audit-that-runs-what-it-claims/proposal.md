# Proposal: the-audit-that-runs-what-it-claims

Change: `the-audit-that-runs-what-it-claims` · Subject: `skill-audit` (the auditor itself) · Store: openspec

## Intent

`skill-audit` ships a doctrine that describes an end-to-end audit and a mechanism that
performs a string-set comparison. Four gaps, all read off disk, all inside the skill:

| # | Gap | Evidence |
|---|---|---|
| A | Moves 1 and 2 over-declare | `SKILL.md:51-52` both say `Ships as: roster`. `run_roster` (`audit_cli.py:424-509`) derives two flat sets of strings — `probe_code_side` (`:300-364`) comma-splits a refusal message, `doctrine_side` (`:84-127`) reads one markdown column. Nothing walks a filesystem, lists a directory, or compares paths. Row 1's own text ("Build the expected artifact from the documentation alone") and row 2's ("Drive the subject as it exists on disk") describe structure work `roster` does not do |
| B | User mode is **absent**, not unmechanized | No move, no doctrine sentence, no recipe shape, no lock. Every `user` in `SKILL.md` (`:28,35,157,213,244,247`) is the audit's own operator or the `user-invocable` frontmatter field. Recipes (`references/probes/*.json`) carry a single `argv`/`extract` pair, never an ordered sequence |
| C | `## Handoff` promises a grouping nothing enforces | `SKILL.md:247-248` says the report lands "with the slicing and the changed-line forecast already in it". `REPORT_SHAPE` (`audit_cli.py:536-545`) carries neither. `ReportSchemaSelfDescriptionTests` (`tests/test_skill_audit.py:1462-1487`) proves dict and table agree — they are silent on it **together** |
| D | A skipped move disappears | `move-number` is enforced **per finding** (`audit_cli.py:631-634`): it records which move produced a finding already written down. `## Unchecked` (`:182`, enforced at `:617-619` as bare heading presence) names *surfaces*, not moves. An agent can run move 0 only, emit a schema-valid report, never attempt moves 3-7, and `check-report` exits `0` |

The consequence is the defect this skill exists to find, in the skill that exists to find it:
a closed set (the moves) stated by hand in doctrine and never derived from what ran.

## Scope

### In scope

| Deliverable | Files |
|---|---|
| A `structure` subcommand — declared vs. on-disk vs. from-zero, with arithmetic adjudication | `.claude/skills/skill-audit/scripts/audit_cli.py` |
| A `walkthrough` subcommand — an ordered user-mode drive of the subject's own flow, gate by gate | same |
| Per-move outcome record in the enforced report shape: every move appears, ran or skipped-with-a-reason | same, `SKILL.md` |
| A repair-unit grouping in the enforced report shape, and the `## Handoff` prose corrected to match | same, `SKILL.md` |
| Two recipe shapes (structure recipe, walkthrough recipe) and one worked example each | `.claude/skills/skill-audit/references/probes/`, `references/usage.md` |
| Locks and inversions for all of it | `tests/test_skill_audit.py` |

### Out of scope — with reasons

- **Every open item in `proposal-implementation` and `remote-execution`.** Nine and several
  respectively, known, real. They are not hand-carried into the auditor's own change. When this
  skill meets its objectives they will surface **because a real audit found them**, which is
  also the only way we learn whether the mechanism works.
- **Any edit under `implementations/`.** Read-only from the forge, always.
- **`manifest` and `counts` as subcommands.** Still owned by
  `the-manifest-that-proves-containment`. See §The `manifest` question.
- **Repairing anything this change's own new moves find.** The wall between reporting and
  repairing is the product (`SKILL.md:238-241`).
- **Auditing a second subject.** The auditor is its own first subject here.

## Capabilities

**New:** none. **Modified:** none. `openspec/specs/` holds no capability this change alters;
the prior change put its spec at the change root and this one follows.

## Approach

### The general/specific split, applied twice

The prior change declined move 1 as a script, arguing a general "build the product from zero"
tool is overbuild because the precedent (`doctrine_scaffold`) is subject-specific
(`the-skill-that-audits-the-others/proposal.md:129`). That reason is still true, and the
answer is the split this skill already proved: **a recipe carries the subject-specific bits,
the machinery stays general.**

**`structure --subject <dir> --spec <recipe>`** derives three sides and diffs them:

| Side | Derivation | Subject-specific part |
|---|---|---|
| declared | parse the subject's structure table, reusing `markdown_table_rows` | which table, which column |
| on-disk | walk the target root | which root, which exclusions |
| from-zero | run the subject's own scaffold command inside an **empty** box, then walk the result | which command |

Adjudication falls out **arithmetically**, not by judgement — this is the "which side is wrong"
the user asked for, and the reason a three-way beats a two-way:

| Agreement | Verdict |
|---|---|
| declared == from-zero, disk differs | the disk is stale |
| disk == declared, from-zero differs | the builder is broken |
| disk == from-zero, declared differs | the document is wrong |
| all three differ | no arithmetic winner; emit `three-way-divergence` as a first-class outcome and let the auditor rank it by the evidence ladder (`SKILL.md:124-140`). **Recommended: add no fourth adjudication value** — `ADJUDICATIONS` (`audit_cli.py:547`) stays as it is |

A side that **cannot be derived** — the scaffold command is missing, refuses, or the root does
not exist — is `Unprobeable`, exit `2`, never an empty set. An empty from-zero side would print
"the builder is broken" over the entire disk, which is a broken probe wearing a result's
clothes (`audit_cli.py:5-13`).

**`walkthrough --subject <dir> --spec <recipe>`** runs a recipe declaring an **ordered**
sequence of invocations, each with `argv` and an expected outcome, against a real box, and
records where the sequence stalls. General: the runner, the stall detection, the finding
shape. Specific: the sequence. This closes B and is what "close the cycle" means — the gates
are driven in the order a user meets them, and the first gate that will not open is named at
its own index.

### The two report-shape items

Both are fully general and carry no subject surface.

- **`move-outcomes`** — `## Move outcomes`, one row per move, each `ran` or
  `skipped: <reason>`. Enforced by `check-report`. The move roster **must be derived, not
  listed**: recommended shape is `check-report` resolving `SKILL.md` relative to `__file__`
  (`scripts/../SKILL.md`) and requiring one row per numbered move in the moves table. A
  hand-written move list inside the tool would ship the exact defect this change is closing.
  Fallback if that coupling is rejected in design: an optional `--moves <path>`.
- **`repair-units`** — `## Repair units`, grouping findings into units a downstream SDD change
  can take whole, each naming its findings and its own changed-line forecast. This closes C.

**The word `slicing` is already taken.** Everywhere else in this skill (`SKILL.md:31-41`,
plus the prior change's `proposal.md:223,381`, `design.md:247`, `spec.md:513`) it means
choosing which closed surface to audit **before** running. Reusing it for post-hoc grouping
makes one word mean two things in one doctrine — the drift this forge polices. **Proposed
name: repair unit**, and `SKILL.md:247-248` is corrected from "with the slicing and the
changed-line forecast already in it" to name repair units instead. `## Scope, and who chooses
it` keeps `slicing` untouched.

### The `manifest` question, answered

Neither absorbed nor duplicated: **this change ships the primitive, the follow-up ships the
subcommand.** `structure` needs a disk walk, and its from-zero side needs a throwaway box
whose cleanup must be proven by content, never by `git status` (`SKILL.md:119`). So this
change adds one internal helper — a sorted `path → sha256` map over a declared root — used by
`structure` for both the walk and the containment proof. `the-manifest-that-proves-containment`
then ships `manifest --root --baseline` as a thin subcommand over that same helper and adds
`added`/`removed`/`changed`. **This change does not depend on that one and does not block it.**
Recording the contract here is what stops the follow-up writing a second walk.

## Slicing and budget

Forecast **≈1,030 authored lines** against `review_budget_lines: 800`. **It does not fit.** The
session's cached `delivery_strategy` is `single-pr`; this proposal reports the overrun rather
than assuming an exception, and recommends a chain.

| # | Slice | Depends on | Lines (est.) |
|---|---|---|---|
| 1 | Report shape: `move-outcomes` + `repair-units` + `## Handoff` prose correction | — | ~250 |
| 2 | `structure` + the walk/digest helper + moves rows 1-2 corrected | 1 | ~420 |
| 3 | `walkthrough` + its move row + `usage.md` worked invocations | 1 | ~360 |

Slice 1 goes first for a structural reason, not for size: its move roster is **derived from the
moves table**, so slices 2 and 3 add their rows and are covered automatically. Land it last and
it must be edited twice. Slices 2 and 3 touch disjoint subcommands and disjoint test classes
and can land in either order.

`Decision needed before apply: Yes`
`Chained PRs recommended: Yes`
`800-line budget risk: High — forecast exceeds it`
`400-line per-PR budget risk: Medium — slice 2 is ~420 and splits at the seam between the walk helper and the three-way diff if it grows`

## Affected areas

| Area | Impact | Description |
|---|---|---|
| `.claude/skills/skill-audit/SKILL.md` | Modified | Moves rows 1-2 re-declared; one new numbered move for user mode; two report-shape rows; `## Handoff` prose; new Decision Gates for the empty box and the underivable side |
| `.claude/skills/skill-audit/scripts/audit_cli.py` | Modified | `structure`, `walkthrough`, walk/digest helper, two `REPORT_SHAPE` entries, move-coverage enforcement |
| `.claude/skills/skill-audit/references/probes/` | New | One structure recipe and one walkthrough recipe, both pointed at the auditor itself |
| `.claude/skills/skill-audit/references/usage.md` | Modified | A worked, runnable invocation per new subcommand; the exit-code table extended |
| `tests/test_skill_audit.py` | Modified | New locks; four existing locks co-edited (below) |

### Locks that must be co-edited in the same commit

These are guards **in favour of** the fix; each fails by design until its literal is extended.

| Lock | Why it fires |
|---|---|
| `SelfAuditSubcommandRosterTests.test_the_subcommand_roster_reports_three_sets_and_no_boolean` (`:804-813`) | hardcodes `["check-report", "roster"]` |
| `MovesTableTests.test_one_row_per_move_and_one_for_the_textual_move` (`:388-403`) | hardcodes `range(0, 8)` plus exactly one textual row |
| `MovesTableTests.test_every_row_ships_as_a_real_subcommand_or_as_doctrine` (`:405-419`) and `test_every_numbered_move_names_a_lock_that_is_on_disk` (`:433-446`) | reject a row naming a subcommand `build_parser` does not declare, or a lock not on disk — code and doctrine must land together |
| `ReportSchemaSelfDescriptionTests` (`:1462-1487`) | rejects a report-shape addition made to only one side |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **R1 — the from-zero box leaks or is not proven clean.** The box is real and is written to | Med | Under `implementations/_<name>`, never the system temp directory (`SKILL.md:225`); removed in `addCleanup`; cleanup **proven by the sha256 walk helper** this change ships, never by `git status` |
| **R2 — `check-report` reading its own `SKILL.md` couples validator to doctrine file** | Med | It is derivation, which is the point; the coupling is one resolved path with a named fallback flag. Design decides |
| **R3 — the chain is recommended and `single-pr` is cached** | High | Reported here, not worked around. The user decides before apply; both prior changes in this repo overran and no `size:exception` was ever accepted |
| **R4 — `openspec/config.yaml:19,21` runs `unittest discover -s tests -p 'test_extract_pdf.py'`,** which does **not** match `test_skill_audit.py` | High | Every new lock must be run and counted under `python3 -m unittest discover -s tests`, the command the prior change used. Verify by **test counts rising by the number added**, never by a suite staying green |
| **R5 — a new lock passes on first run and is never proven reachable** | Med | `strict_tdd: true`. Every mechanism lands with a lock **seen to fail first**; restore by inverse patch, never `git checkout --` (`SKILL.md:122`) |
| **R6 — "repair unit" is a coined term the user may not want** | Med | Named as a proposal, not a decision; question 1 below |
| **R7 — a `walkthrough` recipe hardcodes the auditor's own flow and generalizes to nothing** | Med | The first recipe targets the auditor; the shape is reviewed against at least one other skill's flow **on paper** before the runner is written, without editing that skill |

## Rollback

Purely additive to one skill plus its suite. Each slice is one commit and reverts
independently, in reverse order (3 and 2 before 1). No existing subcommand's behaviour is
removed; `roster` and `check-report` keep their contracts, so reverting any slice cannot
disturb the existing baseline. Slice 1 reverts by deleting two `REPORT_SHAPE` entries, two
`SKILL.md` rows, and restoring one `## Handoff` sentence.

## Success criteria

- [ ] `structure` derives three sides and, on each of the three two-side-agreement cases, names **which side is wrong** — each proven reachable-red by inversion.
- [ ] A side that cannot be derived exits `2`, and no code path can hand an empty set to the comparison.
- [ ] `walkthrough` drives an ordered sequence against a real box and names the index where it stalls, proven by planting a stall.
- [ ] `check-report` rejects a report that omits any move from `## Move outcomes`, with the move roster **derived from the moves table**, not listed in the tool.
- [ ] `check-report` rejects a report carrying no `## Repair units`, and `## Handoff` no longer promises a "slicing".
- [ ] The auditor is run against the auditor with the new subcommands, and its own subcommand roster still shows `unregistered` and `phantom` empty.
- [ ] The Python suite's test count has **risen by the number of tests added**, measured, with no duplicate class name silently disabling any of them.
- [ ] No file under `implementations/` and no file in any other skill was modified — proven by content manifest.

## Proposal question round

These shape the proposal, not the harness. Answer, skip, correct the framing, or ask for a
second round.

1. **The name for the grouping.** `slicing` is taken by pre-run surface selection, so the
   post-hoc grouping of findings into hand-off-able chunks needs its own word. *Proposed:
   **repair unit**.* Alternatives considered: "work unit" (already SDD's word for a task), "remedy
   group", "repair batch". Is `repair unit` right?
2. **When all three structure sides differ.** The arithmetic picks no winner. *Proposed: emit
   `three-way-divergence` as a first-class outcome, add no fourth adjudication value, and let the
   evidence ladder rank it.* The alternative is a fourth adjudication, which ripples through
   `ADJUDICATIONS` and the whole report doctrine. Accept the proposal?
3. **What a `walkthrough` stall is worth.** When gate 3 of 5 will not open, gates 4 and 5 were
   never reached. *Proposed: report the stall as one finding and mark the unreached gates in
   `## Unchecked`, never as clean.* Is a stall a finding on its own, or only when the gate was
   documented as passable?
4. **The chain.** The forecast is ~1,030 against 800, in three slices. *Proposed: chain
   1 → (2 ‖ 3), each slice its own PR.* Do you want the chain, or a single PR with an accepted
   exception?
5. **How far the auditor drives itself.** Slice 2's from-zero side needs a subject with a
   scaffold command. *Assumed: the auditor is the first subject for `structure` too, using its
   own file layout.* If you want the first real `structure` recipe pointed at a different skill,
   say which — noting that reading it is allowed and editing it is not.
