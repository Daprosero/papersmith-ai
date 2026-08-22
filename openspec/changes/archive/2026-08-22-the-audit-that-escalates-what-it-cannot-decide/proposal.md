# Proposal: the-audit-that-escalates-what-it-cannot-decide

Change: `the-audit-that-escalates-what-it-cannot-decide` · Subject: `skill-audit` (the auditor
itself, again) · Store: openspec · Baseline: HEAD `4f3c59b`, suite `1026 tests, OK`

## Intent

The finished auditor was driven read-only against `.claude/skills/paper-ingestion/`, against
three defects a separate two-judge review had already confirmed. The mechanism did not fail —
it stopped, correctly, at the exact place its doctrine tells it to stop.

| Confirmed defect | Result | What the stop cost |
|---|---|---|
| Documented flags `argparse` never defines | **half-caught**. `roster` derived the true code side from the program's own refusal, then refused to adjudicate: both documented sites state the set in prose, so `no-closed-roster`, `comparison: not-run`, ranges named. It handed over evidence and stopped | The fact was *decidable* — by driving each documented flag as a gate. Nothing routed it there |
| A predicate strands an input permanently | **caught cleanly** by a `walkthrough` recipe: stall at index 3, `kind: contradiction`, the program contradicting itself one command apart in its own words | — |
| Tests never exercise two of the module's entry points | **not caught**. Move 7's `counts` mechanism is deferred to `the-manifest-that-proves-containment` | Out of scope here |

Using it also exposed a fourth gap, in the tool: the recipe's step 0 was **setup**, not a gate,
and `walkthrough` counted it as a gate that passed. A fixture that happened to work was recorded
as evidence about the subject.

The defect, stated once: **a surface the tool cannot derive terminates the audit instead of
being routed to something that can.** `comparison: not-run` is a truthful admission and a dead
end, and a dead end is where a real defect survives a real audit.

## The constraint everything else follows from

`audit_cli.py` can only ever call `subprocess.run()`. **It cannot spawn agents.** So a
multi-agent protocol is categorically orchestrator work, not skill work. This skill can shape
what each stage receives and consume what each returns; it cannot run a stage.

What it *can* do is the trick `## Move outcomes` already ships: **refuse a report that lies
about them.** A report declares which stages ran; for each stage declared `ran`, `check-report`
demands the artifact only that stage produces, and rejects the report otherwise.

The honest limit, stated here so it is stated in doctrine too: the shape can force an
artifact's **presence and structure** — a set-diff needs two sets; a finding attributed to the
skill-less drive must be filed against the skill — and it can never force **independence**.
Blindness and no-contact are unfalsifiable from inside the tool. A stage row is an operator's
declaration, and the doctrine must say it carries no lock, exactly as the moves table's textual
row does.

## Scope

### In scope

| Deliverable | Files |
|---|---|
| A frozen `tree_digest` of the subject in every subcommand payload, a `## Frozen` report item, and `check-report` re-deriving it | `scripts/audit_cli.py`, `SKILL.md` |
| A `kind: "setup" \| "gate"` field per walkthrough step, defaulting to `"gate"`, and `setup-failed` as an inability to look | same |
| A named, emission-site-total partition of note kinds into escalatable / consequence / deterministic-exclusion, plus an `escalation` hint per escalatable note | same |
| A `reading-diff` subcommand comparing two supplied readings of one prose surface, and one new numbered move for it | same, `references/usage.md` |
| A `- Found by:` axis per finding and a `## Disputed severity` section | same, both shipped reports |
| `## Stage outcomes` plus per-stage artifact enforcement, the stage roster derived from a stages table | same, both shipped reports |
| Locks and inversions for all of it | `tests/test_skill_audit.py` |

### Out of scope — with reasons

- **How the orchestrator launches stages that need models.** This is the scope fork, and it is
  decided below rather than deferred silently: the **enforceable** half is in, the **launch
  conventions** are out. Isolation, blindness, and no-contact belong wherever this repository's
  orchestrator conventions live. A skill that cannot spawn an agent must not carry prose
  claiming it does.
- **Any severity vocabulary.** See §Disputed severity.
- **`manifest` and `counts`.** Still `the-manifest-that-proves-containment`.
- **Repairing anything found.** The wall between reporting and repairing is the product.
- **`openspec/config.yaml`.** Its `test_command` pins `test_extract_pdf.py` and never runs
  `tests/test_skill_audit.py`. That is a real defect, **deliberately left standing** for a real
  audit to find. Touching it destroys the only unfaked catch this repository has left.
- **Any file under `implementations/`, and any other skill.** `paper-ingestion` is a read-only
  subject, never a repair target.

## Capabilities

**New:** none. **Modified:** none. `openspec/specs/` holds no capability this change alters;
the prior two changes put their spec at the change root and this one follows.

## Approach

### The invariant

**Never replace a decidable fact with a vote.** Voting is for judgement; rigour comes from
routing. That makes the escalation rule two-runged, not one:

1. **Re-route to another zero-model probe.** A prose-stated flag roster is not undecidable — it
   is undecidable *by `roster`*. Each documented flag becomes a `walkthrough` gate expecting the
   program not to refuse it, and the fact comes back by execution. This rung alone closes the
   half-caught case above, at zero model cost.
2. **Only when no probe applies** does the surface reach readers, and even then they return a
   *reading*, never a verdict.

### The stages, and what each owes

Numbers live in cells, never in headings: `DoctrineNumeralTests.test_no_heading_carries_a_cardinal_at_all`
(`tests/test_skill_audit.py:497-511`) rejects any `#` line containing a cardinal, and table rows
are exempt — the same reason move numbering already lives in a table.

| Stage | Models | Artifact demanded when its row says `ran` |
|---|---|---|
| 0. Freeze the subject | 0 | `## Frozen`, carrying the digest; every finding's digest must equal it, and a mismatched finding is rejected |
| 1. Decide by tool | 0 | `## Undecidable`, the machine-produced escalatable list, each entry naming its emitting note kind and its escalation rung |
| 2. Two blind readings, only over that list | 2 | `## Reading diff`, the `reading-diff` output over exactly stage 1's escalatable surfaces |
| 3. Differential drive, one box with the skill and one without | 2 | `## Drives`, one row per box naming what it obtained by execution |
| 4. Partition the two transcripts | 1 | No finding may carry `- Found by: not-compared` |

Stages 0–1 are non-negotiable and cost zero models. Stages 2–4 fire when stage 1 leaves
something escalatable, or on an explicit full pass: **a full audit is five model runs**, and the
doctrine says so in that many words before any of them is launched.

Stage 3's asymmetry is the point. The skill-less drive's exclusive findings are a **blind spot in
the skill**, filed against the skill, never against the subject. `check-report` can enforce that
structurally, because a finding attributed to that drive naming the subject as its target is a
category error the tool can see.

### The rigour guard, which is not negotiable

A supplied reading MUST NEVER set `closed_seen` (`audit_cli.py:719-721`). That boolean turns on
the `unregistered` direction — code accepted but undocumented. If a model's reading of prose
could flip it, a guess would start generating findings **against the code**: authority
inversion, and the worst possible failure for an auditor.

Therefore `reading-diff` is a **separate subcommand that never calls `doctrine_side`**, and
`comparison` stays `not-run` for that surface forever. Two readers agreeing proves the prose has
**one reading** — a weaker and different claim than "closed", and the report must word it that
way. The lock is an AST scan, the precedent being the from-zero soundness condition already
enforced by parsing a derivation function's syntax tree.

### The escalatable list must partition, not unify

| Note kind | Bucket | Why |
|---|---|---|
| `no-closed-roster`, `heading-not-found`, `scope-claimed-without-heading`, `no derivation available for this surface` | **escalatable** | Prose exists and could not be derived. Something else can look |
| `comparison-not-run` | **consequence** | Produced *by* the above. Escalating it double-counts one surface |
| `shape-not-walkable`, `case-only-divergence` | **deterministic exclusion** | The tool excluded these on purpose. There is no prose to re-read; escalating them is nonsense |

The filter is a named constant, and its lock is **totality against actual emission sites**: a
scan of `audit_cli.py` for every emitted `"kind":` literal, asserting each is classified in
exactly one bucket — the way `FORBIDDEN_SUPPORT` and `ADJUDICATIONS` are held. A hand-maintained
second roster inside the tool would ship the defect the tool exists to find.

### Setup is not a gate

A `kind` field per step, `"setup" | "gate"`, defaulting to `"gate"`. The shipped recipe has zero
setup steps and needs zero edits; `"reset": true` is the existing precedent for a declarative
step field. Rejected: *"the first step is never a gate"* — setup spans multiple steps, and
argv[0]-missing-at-index-0 is a real load-bearing gate. Rejected: *inferring setup from command
shape* — a heuristic guess is exactly what this doctrine forbids.

Follow-through, decided: a setup step needs no `expect` (it asserts nothing about the subject),
and a setup step that fails exits `2` as **`setup-failed`**, never `stalled`. A broken fixture is
a defect in the recipe, and an inability to look is never a finding.

### Disputed severity

Severity **does not exist in this skill** — zero matches for `severity|WARNING|CRITICAL|SUGGESTION`
across the whole skill directory. Decided: **its own section, and no severity vocabulary.**

A per-finding `- Severity:` field would force every finding in every report to carry a value
from a ladder nothing derives — a closed set stated by hand, in the validator, which is the most
embarrassing possible place to ship one. `## Disputed severity` demands nothing of undisputed
findings, mirrors how `not adjudicable` earned its own section, and records **both positions
verbatim with their sources** rather than resolving them into a coined scale.

The other axis costs almost nothing, because **it already ships**: `obtained` is the existing
`evidence-marker` (`CONFIRMED by execution` / `read-only`). Only `- Found by: both | one |
not-compared` is new, with no default, exactly as `evidence-marker` has none.

### Is any of this a new move?

Decided explicitly, all three ways:

- **Stages 0–1 add no move.** They are refinements of `roster`, `structure`, `walkthrough` and
  `check-report` plumbing that already exists.
- **Stages 2–4 are categorically not moves.** They cannot satisfy
  `MovesTableTests.test_every_row_ships_as_a_real_subcommand_or_as_doctrine`, and reusing the
  textual row's escape valve for a different reason is itself the drift this forge polices.
- **The comparison of two supplied readings is one new numbered move**, shipping as
  `reading-diff`. It is real code, zero models, and it satisfies the moves table's own framing —
  *a way of getting a fact that reading cannot give you*. One reader cannot discover that prose
  has more than one reading; it takes two independent readings and a mechanical diff. It also
  offers an adjudication move 0's stop does not.

## Slicing and budget

Forecast **≈1,210 authored lines** against `review_budget_lines: 800`. **It does not fit.** The
session's cached `delivery_strategy` is `single-pr`; this proposal reports the overrun rather
than assuming an exception.

| # | Slice | Depends on | Lines (est.) |
|---|---|---|---|
| 1 | Freeze: digest in every payload, `## Frozen`, `check-report` re-derivation | — | ~240 |
| 2 | Step `kind` and `setup-failed` | — | ~140 |
| 3 | Escalatable partition, totality lock, `escalation` hint, routing doctrine | — | ~190 |
| 4 | `reading-diff` + its move row + `usage.md` | 3 | ~230 |
| 5 | `- Found by:` + `## Disputed severity` | 4 | ~180 |
| 6 | `## Stage outcomes` + per-stage artifact demand + stages table | 1, 3, 4, 5 | ~230 |

Slices 1, 2 and 3 are independent and immediately valuable. Slice 3 has **no consumer until 4**,
so they ship adjacently or 3 ships a field nothing reads. Slice 5 before 4 would be the
"declared, never consumed" shape the doctrine itself calls out. Slice 6 last, because it is the
only one that demands the others' artifacts.

`Decision needed before apply: Yes`
`Chained PRs recommended: Yes`
`800-line budget risk: High — forecast exceeds it`
`400-line per-PR budget risk: Low — every slice is under 400`

## Affected areas

| Area | Impact | Description |
|---|---|---|
| `.claude/skills/skill-audit/SKILL.md` | Modified | Stages table; one new numbered move row; routing/escalation Decision Gates; setup-vs-gate gates; report-shape rows; the five-model-run statement; the "presence, never independence" limit |
| `.claude/skills/skill-audit/scripts/audit_cli.py` | Modified | Digest emission, `reading-diff`, step `kind`, escalatable constant, `REPORT_SHAPE` additions, stage-roster derivation |
| `.claude/skills/skill-audit/references/usage.md` | Modified | A worked invocation for `reading-diff`; exit table extended |
| `.claude/skills/skill-audit/references/probes/` | Modified | The walkthrough recipe gains a declared setup step; a `reading-diff` input pair |
| `.claude/skills/skill-audit/references/example-report.md` | Modified | Co-edited per report-shape addition |
| `openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md` | Modified | Same; `FirstDamageReportTests` (`tests/test_skill_audit.py:1715-1724`) runs `check-report` over it |
| `tests/test_skill_audit.py` | Modified | New locks; the locks below co-edited |

**Correction to the brief:** the second shipped report is **not** in the archive. It is
`openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md`,
in a still-active change folder, and it is the one `FirstDamageReportTests` validates. The
archived change folder carries no report `check-report` reads.

### Locks that must be co-edited in the same commit

| Lock | Why it fires |
|---|---|
| `ReportSchemaSelfDescriptionTests` (`:1462-1487`) | Every `REPORT_SHAPE` addition must land in the dict and the doctrine table in one commit |
| `MoveOutcomesTests` (`:1526-…`) and both shipped reports | A new numbered move makes every existing `## Move outcomes` incomplete |
| `MovesTableTests.test_one_row_per_move_and_one_for_the_textual_move` (`:388-403`) | Hardcodes the numbered range |
| `MovesTableTests.test_every_row_ships_as_a_real_subcommand_or_as_doctrine` (`:405-419`), `test_every_numbered_move_names_a_lock_that_is_on_disk` (`:433-446`) | Reject a row naming a subcommand `build_parser` does not declare |
| `SelfAuditSubcommandRosterTests` (`:804-813`) | Hardcodes the subcommand roster |
| `SingleWalkTests` | AST-scans for `rglob`/`walk`/`iterdir`/`scandir`/`glob` outside `tree_digest`. Anything new calls `tree_digest`, never walks again |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **R1 — the shape forces presence, never independence.** A single agent can produce two "blind" readings | High | Stated in doctrine in its own words, at the stage row, exactly as the textual move row states it has no lock. Not papered over with a check that cannot exist |
| **R2 — authority inversion.** A supplied reading reaching `closed_seen` would generate findings against the code from a guess | Med | `reading-diff` is a separate subcommand; an AST lock asserts it never calls `doctrine_side`; `comparison` stays `not-run` for that surface. Proven reachable-red by inversion |
| **R3 — a protocol nobody runs.** Stages 2–4 need an orchestrator this change does not ship | Med | Every stage row may be `skipped: <reason>`, so a zero-model audit stays valid. The shape costs nothing until a stage is claimed |
| **R4 — `openspec/config.yaml:19,21` never runs `test_skill_audit.py`** | High | **Do not fix it.** Run `python3 -m unittest discover -s tests` by hand; verify by **test counts rising by the number added**, never by a suite staying green |
| **R5 — a new lock passes on first run and is never proven reachable** | Med | `strict_tdd: true`. Every lock seen to fail first; restore by inverse patch, confirmed by sha256, never `git checkout --` |
| **R6 — `## Disputed severity` is a section nothing ever fills** | Med | It is a bare-heading requirement, the shape `## Unchecked` already uses. An empty section and a surface nobody looked at must not look the same |
| **R7 — five model runs is a real cost** | Med | Conditional firing, and the count is declared before launch, not discovered afterwards |
| **R8 — the chain is recommended and `single-pr` is cached** | High | Reported here, not worked around. All three prior changes in this repository overran and no `size:exception` was ever accepted |

## Rollback

Purely additive to one skill plus its suite. Each slice is one commit and reverts independently
in reverse order (6, 5, 4, 3, 2, 1). No existing subcommand loses behaviour: `roster`,
`structure`, `walkthrough` and `check-report` keep their contracts, and the step `kind` field
defaults to today's behaviour, so a reverted slice cannot disturb the baseline. A reverted
report-shape slice deletes its `REPORT_SHAPE` entries, its doctrine rows, and its lines from
both shipped reports.

## Success criteria

- [ ] A `no-closed-roster` surface emits an `escalation` hint naming a zero-model probe, and driving that probe returns the fact the stop withheld — proven end to end on the case that motivated this change.
- [ ] Every note kind emitted anywhere in `audit_cli.py` is classified in exactly one bucket, proven by a totality lock that fails when a new kind is emitted and left unclassified.
- [ ] `reading-diff` reports agreement or divergence between two supplied readings and **cannot** set `closed_seen`, proven by an AST lock seen to fail when the call is planted.
- [ ] A walkthrough recipe with a failing setup step exits `2` as `setup-failed`, and a passing setup step is never counted as a gate that passed.
- [ ] Every finding carries a digest, and a finding whose digest does not match `## Frozen` is rejected.
- [ ] `check-report` rejects a report declaring a stage `ran` without that stage's artifact, with the stage roster **derived from the stages table**, not listed in the tool.
- [ ] The auditor is run against the auditor with the new subcommands, and its own subcommand roster still shows `unregistered` and `phantom` empty.
- [ ] The Python suite's test count has risen from **1026** by exactly the number of tests added, measured, with no duplicate class name silently disabling any of them.
- [ ] No file under `implementations/`, no other skill, and not `openspec/config.yaml` was modified — proven by content manifest.

## Proposal question round

These shape the proposal, not the harness. Answer, skip, correct the framing, or ask for a
second round.

1. **The scope fork, item 6.** *Decided: split it.* The enforceable half — `## Stage outcomes`
   and the per-stage artifact demand — comes inside this change, because it is real code with a
   real lock. The launch conventions (isolation, blindness, no-contact) stay out, because a
   skill that cannot spawn an agent must not carry prose claiming it does. Accept the split, or
   do you want the full protocol written as doctrine here anyway?
2. **One change or two.** Six slices, ~1,210 lines. The natural seam is 3|4: slices 1–3 are
   independent tool fixes; 4–6 are the multi-reading arc. *Proposed: one change, chained PRs*,
   because slice 3 has no consumer until 4. The alternative is two changes and slice 3 shipping
   a field nothing reads for a while. Which?
3. **The escalation's first rung.** *Proposed: an escalatable surface routes to another
   zero-model probe first, and reaches readers only when no probe applies.* This closes the
   motivating case at zero model cost and makes "rigour comes from routing" literal rather than
   aspirational. Does that match your intent, or should every escalation reach the readers?
4. **Disputed severity.** *Decided: its own section, both positions recorded verbatim, and no
   severity vocabulary anywhere.* Inventing `CRITICAL/WARNING/SUGGESTION` here would be a closed
   set stated by hand inside the validator. Accept, or do you want a ranked scale?
5. **The chain.** ~1,210 against 800, six slices, each under 400. *Proposed: chain
   (1 ‖ 2 ‖ 3) → 4 → 5 → 6.* Do you want the chain, or a single PR with an accepted exception?
