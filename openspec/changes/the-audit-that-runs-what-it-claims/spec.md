# Spec Delta: the-audit-that-runs-what-it-claims

Change: `the-audit-that-runs-what-it-claims` · Modifies capability: `skill-audit`
(`.claude/skills/skill-audit/`, `tests/test_skill_audit.py`) · Store: openspec.

No `openspec/specs/skill-audit/spec.md` exists; the prior change's
`openspec/changes/the-skill-that-audits-the-others/spec.md` is this capability's
baseline. This delta MODIFIES the moves-table and Handoff requirements from that
baseline, and ADDS `structure`, `walkthrough`, move outcomes, repair units, and
the walk/digest helper. **`slicing`** (pre-run surface selection, `## Scope, and
who chooses it`) is untouched; **repair unit** names only the new post-hoc
grouping of findings.

## MODIFIED Requirements

### Requirement: The moves table MUST be complete, typed, and never sized by an underived numeral

Doctrine MUST carry one parseable table with exactly one row per numbered move
— now 0 through 8 — plus exactly one row for the irreducibly textual move. Row
8 (the user-mode drive) MUST name `walkthrough`; rows 1-2 MUST describe what
`roster` actually derives (two flat string sets), never a filesystem walk.
`check-report`'s move-coverage check MUST derive the required roster of moves
by parsing `SKILL.md`'s own table, never from a literal list inside the tool.
(Previously: table sized 0-7 plus the textual row; rows 1-2 described structure
work `roster` does not perform; no move-coverage enforcement existed.)

#### Scenario: A move loses its row
- GIVEN move 8's row is deleted from the table
- WHEN `check-report` validates a report claiming full move coverage
- THEN it SHALL fail and SHALL name move 8 as missing

#### Scenario: The required roster is derived, not hardcoded
- GIVEN a ninth numbered move added to the table with no matching literal in `audit_cli.py`
- WHEN `check-report` runs against a report omitting that move
- THEN it SHALL require a row for it, proving the requirement came from `SKILL.md`

### Requirement: The Handoff prose MUST NOT promise a grouping the report shape does not enforce

`## Handoff` MUST describe the delivered report as carrying **repair units**
and the changed-line forecast, never "slicing".
(Previously: "with the slicing and the changed-line forecast already in it" —
a grouping `REPORT_SHAPE` never carried.)

#### Scenario: The corrected prose matches the shape
- GIVEN the delivered `SKILL.md`
- WHEN `## Handoff` is read against `REPORT_SHAPE`
- THEN every noun it uses for report content SHALL name a section `REPORT_SHAPE` enforces

## ADDED Requirements

### Requirement: `structure` MUST derive three sides and adjudicate which one is wrong arithmetically

`structure --subject <dir> --spec <recipe>` MUST derive `declared` (parsed
from the subject's structure table), `on-disk` (a walk of the target root),
and `from-zero` (a walk of the subject's own scaffold command's output, run
inside an empty box), and adjudicate arithmetically: declared==from-zero &
disk differs → disk stale; disk==declared & from-zero differs → builder
broken; disk==from-zero & declared differs → document wrong; all three differ
→ `three-way-divergence`, a first-class outcome ranked by the evidence ladder.
No fourth value MUST be added to `ADJUDICATIONS`.

#### Scenario: The disk is stale
- GIVEN declared and from-zero agree and on-disk differs
- WHEN `structure` runs
- THEN it SHALL report `disk stale` naming the differing path

#### Scenario: All three disagree
- GIVEN declared, on-disk, and from-zero all name different sets
- WHEN `structure` runs
- THEN it SHALL emit `three-way-divergence` and SHALL NOT emit any value outside the existing `ADJUDICATIONS`

#### Scenario: The auditor probes its own layout
- GIVEN `structure` run with a recipe pointed at the auditor's own file layout
- WHEN the comparison completes
- THEN it SHALL report a verdict without reading or editing any other skill

### Requirement: A side that cannot be derived MUST be `Unprobeable`, never an empty set

If the scaffold command is missing, refuses, or the target root does not
exist, `structure` MUST exit `2` and MUST NOT hand an empty set to the
comparison — an empty from-zero side would report "builder broken" over the
entire disk.

#### Scenario: The scaffold command is missing
- GIVEN a recipe whose scaffold command does not exist
- WHEN `structure` runs
- THEN it SHALL exit `2` and SHALL NOT report `builder broken`

### Requirement: `walkthrough` MUST drive an ordered sequence and name the index where it stalls

`walkthrough --subject <dir> --spec <recipe>` MUST run a recipe's ordered
sequence of invocations against a real box and, when one invocation does not
produce its expected outcome, MUST report the stall as one finding naming its
index. Every gate at or after the stall index MUST appear under
`## Unchecked`, never under `## Clean, stated as results`.

#### Scenario: A gate stalls midway
- GIVEN a five-gate sequence where gate 3 does not produce its expected outcome
- WHEN `walkthrough` runs
- THEN it SHALL report one finding naming index 3
- AND gates 4 and 5 SHALL appear under `## Unchecked`, never as clean

### Requirement: Every move MUST appear in `## Move outcomes`, ran or skipped-with-a-reason

`check-report` MUST require one row per move required by `SKILL.md`'s table,
each marked `ran` or `skipped: <reason>`. A move attempted zero times MUST be
distinguishable from a move that ran over a clean surface.

#### Scenario: A move never attempted
- GIVEN a report where move 3 was never run
- WHEN `check-report` validates it
- THEN it SHALL require move 3's row to read `skipped: <reason>`, never absent and never `ran`

#### Scenario: Zero findings is not zero attempts
- GIVEN two reports — one where move 2 ran and found nothing, one where move 2 never ran
- WHEN both are validated
- THEN their move-2 rows SHALL differ (`ran` vs `skipped: <reason>`)

### Requirement: The report MUST carry `## Repair units`, each naming its findings and a changed-line forecast

`check-report` MUST reject a report with no `## Repair units` section. Each
unit MUST name the findings it groups and its own changed-line forecast,
distinct from grouping by move or by adjudication.

#### Scenario: No repair units
- GIVEN a report with findings but no `## Repair units` section
- WHEN `check-report` runs
- THEN it SHALL reject the report and SHALL name the missing section

### Requirement: The path→sha256 walk helper MUST be the sole evidence for the disk side and for from-zero box cleanup

One internal helper MUST produce a sorted `path → sha256` map over a declared
root, used by `structure` both to derive the on-disk side and to prove a
from-zero box was removed by content after use. `git status` MUST NOT appear
as evidence for either.

#### Scenario: The box's cleanup is proven by content
- GIVEN a from-zero box created and then removed in cleanup
- WHEN the walk helper runs against the parent directory afterward
- THEN the box's paths SHALL be absent from the resulting map
- AND no assertion in the suite SHALL cite `git status` for this fact

#### Scenario: One changed byte is detected
- GIVEN a single byte altered inside a box before cleanup
- WHEN the walk helper runs before and after
- THEN the two maps SHALL differ at that path's digest

## Explicit non-goals

| Non-goal | Reason |
|---|---|
| A fourth `ADJUDICATIONS` value for three-way divergence | Ruled: it is a distinct outcome, not a softer verdict — folding it in widens a precise definition |
| Fixing `openspec/config.yaml`'s mismatched test selector | Recorded as a known finding for the first real audit, not hand-carried in |
| Repairing anything a new move finds | The report/repair wall is the product; unchanged by this delta |
| Editing `implementations/` or any other skill | Read-only from the forge; the auditor's own layout is its first `structure` subject |

## Acceptance

- `structure` names which side is wrong on each two-side-agreement case, and
  emits `three-way-divergence` when all three differ — each reachable-red by
  inversion, and no fourth `ADJUDICATIONS` value is added.
- A side that cannot be derived exits `2`; no code path hands an empty set to
  the comparison.
- `walkthrough` names the stall index against a real box, proven by planting a
  stall; unreached gates land in `## Unchecked`, never `## Clean`.
- `check-report` rejects a report missing any move from `## Move outcomes`
  (roster derived from `SKILL.md`, not listed in the tool) or missing
  `## Repair units`.
- `## Handoff` names repair units, not slicing; `slicing` keeps its existing
  meaning unchanged.
- `python3 -m unittest discover -s tests` count rises by exactly the number of
  tests added, measured before and after.
- No file under `implementations/` and no file in any other skill is modified.
