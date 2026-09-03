# Exploration: `launch_available` has no notion of rung — a remote launch can be authorized without pilot ever being attained

> **Materialized retroactively.** The exploration phase ran without a `Write` tool, so only
> the Engram leg persisted. This file is the OpenSpec leg of the same artifact, restored at
> proposal time from Engram `sdd/explore/pilot-attained-gates-remote-launch` (observation
> #1394, project `papersmith-ai`). The body below is that observation, unchanged. The
> appendix at the end is new: it records what the proposal phase re-measured and corrected.
>
> Note the topic key: the exploration was saved as `sdd/explore/pilot-attained-gates-remote-launch`,
> not `sdd/the-pilot-proves-the-science/explore`. Downstream phases searching the
> conventional key will not find it.

Baseline measured: `main`, working tree as read via the Read tool (matches memories #1389/#1391 —
both already landed on disk: `_skipped_rung_detail` already reads `attained_level`,
`undeclaredLadder` already ships in `cmd_verify`).

## Current State

Two independent mechanisms exist and must not be confused:

1. **Sequence completeness** (`position["sequence"]`, `impl_availability.launch_available`'s
   `SEQUENCE_NOT_REACHED`/`STEP_SEQUENCE_NOT_REACHED`): ordinal position only — "is every item
   strictly before mine ticked". Cares nothing about WHAT rung those ticks were derived against.
2. **Rung attainment** (`impl_position.attained_level`, consumed by `_skipped_rung_detail` /
   `_resolve_position_rung_skipped` inside `cmd_position` only): "the highest rung at which every
   LEVELED item grades satisfied". Two-state items (steps, `@record`, `@notebook` without
   `:level`) never participate — confirmed structurally in `attained_level`'s own loop, which only
   ever iterates `evidence["levels"]` and grades leveled items.

`impl_availability.launch_available(*, status, unbacked, disagreements, sequence, ready, job,
shards_declared)` — read in full — has **no `levels` or `attained_level` parameter at all**. It
cannot check rung attainment even in principle; this is a signature-level absence, not an edge
case. Both its callers (`cmd_gate`, `_offer_launch_action`, in `implementation_cli.py`) already
compute `position = position_state(...)`, which already carries `position["attainedLevel"]` —
computed and discarded, never passed through.

**The concrete, code-grounded exploit.** For a LEVELED item, `derive()`'s
`satisfied = derived_index >= target_index`, where `target_index` comes from the position block's
own header `target=` field (whatever rung was last named at `position --target-level <X>`). If the
header's `target=` is the ladder's floor, every leveled item's `satisfied` becomes true almost
vacuously (`derived_index >= 0` is true for any derived rung, including the floor itself). None of
`POSITION_UNBACKED` / `POSITION_DISAGREES` / `SEQUENCE_NOT_REACHED` inspect `target=` or
`attainedLevel` — they only check `mark == "x"` and internal consistency. So a fully, honestly
ticked sequence derived against a low `target=` sails through `launch_available` exactly as it
would if derived against the middle rung; `attained_level` would report the floor or nothing, but
nothing at `gate`/`offer` ever asks it.

Measured directly on the reference target's real position block
(`implementations/Domain_Adaptation/MIL-CREDA/AGREED.md`): header already carries `target=pilot`;
items are `@notebook` (2-state), `@record` (2-state), `@notebook:level`, `@shard:level`,
`@notebook:level`, `@notebook:level` (4 leveled). Item 4 (`@shard:level s00`, gating the local
campaign) is honestly documented in its own prose as structurally unable to show "ran locally at
pilot scale" — `_derive_shard_level` can only return the ladder's floor or its top (never a middle
rung), so a LOCAL pilot-scale campaign run always reads as the floor on this witness. This is a
genuine, target-authored, already-acknowledged gap in the witness choice.

**A recent, adjacent, already-landed change exists and must not be duplicated.**
`openspec/changes/a-pilot-is-the-whole-flow-validated/` is a DIFFERENT axis: ordinary-agreement
witness persistence (`settle --witness test_<id>`, `close`'s new `AGREEMENT_DISAGREES`). Confirmed
shipped in code (`AGREEMENT_DISAGREES` in `GATING_REFUSALS` and `_WORK_STATE_RESOLUTIONS`,
`position_honest` / `POSITION_SHARDS_UNDECLARED` in `impl_availability.py`). It does **not** touch
`launch_available`, `gate`, or rung/level checking at all. The brief's premise that "the
ordinary-agreements composition was deliberately deferred" is therefore STALE — that deferred work
already shipped, under a name a new change must not reuse.

## Affected Areas

- `.claude/skills/_core/implementation/impl_availability.py` — `launch_available` needs new
  required kwargs (`levels`, `attained_level`) and a new check.
- `.claude/skills/proposal-implementation/scripts/implementation_cli.py` — `cmd_gate` (new refusal
  branch), `_offer_launch_action` (pass-through only, silent omission), `GATING_REFUSALS` (+1),
  `_WORK_STATE_RESOLUTIONS` (+1), spelled-out counts in `SKILL.md` / `references/usage.md`.
- `tests/test_proposal_implementation.py` — `test_the_derivation_finds_the_measured_sixty_six`
  moves to 67; new RED/GREEN pairs.
- NOT affected: `implementations/Domain_Adaptation/**` (read-only, per the maintenance boundary);
  `classify_remote_necessity`.

## Approaches

1. **Extend `launch_available` with `levels`/`attained_level`, gate on "one rung below the ladder's
   top".** New required kwargs. New check: when `len(levels) >= 2`, require
   `level_index(levels, attained_level) >= len(levels) - 2`, else new code `RUNG_NOT_ATTAINED`.
   Short-circuits to no requirement when the ladder has fewer than 2 rungs.
   - Pros: uses only facts both callers already compute; zero new target declarations; purely
     positional, so the forge names no target vocabulary; small and additive, matching the module's
     documented growth pattern (`shards_declared` was added the same way).
   - Cons: does not fix the reference target's item-4 witness design flaw.
   - Effort: Medium.
2. **A wholly separate pure predicate called explicitly by both callers.**
   - Cons: two separate "may this launch proceed" predicates now have to be called together at
     every call site — exactly the drift `launch_available`'s own docstring says this module exists
     to prevent. Rejected.
3. **Compare against the header's own recorded `target=` instead of `attained_level`.**
   - Cons: **wrong on the evidence.** `target=` is an aim, not a measurement — precisely the defect
     memory #1389 already fixed one layer up. Rejected.

## Recommendation

Approach 1.

## Risks

- Roster-count churn moves `test_the_derivation_finds_the_measured_sixty_six` (66 → 67) and the
  spelled-out split in both `SKILL.md` and `references/usage.md`.
- `_offer_launch_action` must stay a silent omission (never raise) for the new fact too.
- The reference target's item-4 witness cannot currently demonstrate local-pilot attainment at all.
- Vacuous attainment: a sequence with zero leveled items attains the top trivially.
- Naming collision: do not reuse `a-pilot-is-the-whole-flow-validated`.

## Ready for Proposal

Yes.

---

## Appendix — corrections measured at proposal time (2026-09-03)

Re-measured against `main` at `f3517e8`. Four corrections; none reverses the recommendation.

1. **"the five existing `launch_available`-native codes" is wrong.** `launch_available` raises
   exactly **two** codes of its own — `NOT_READY` and `SEQUENCE_NOT_REACHED`. The other five
   (`POSITION_ABSENT`, `POSITION_STALE`, `POSITION_UNBACKED`, `POSITION_SHARDS_UNDECLARED`,
   `POSITION_DISAGREES`) are returned by `position_honest`, which `launch_available` calls first
   and forwards unchanged. This matters for where the new check goes and how its docstring reads.
2. **The leveled-deriver inventory is incomplete.** `_LEVEL_DERIVERS` has three entries, but
   `derive` special-cases `kind == "record"` to `_record_scale_level` — so there are **four**
   leveled paths, and `_derive_notebook_level` delegates to `_record_scale_level` and therefore
   *can* express a middle rung. The deadlock is confined to `@shard:level`, which alone returns
   only `levels[0]` or `levels[-1]`.
3. **The vacuous-`target=` exploit is not live on the reference target.** Its header already reads
   `target=pilot`. What is live is the plain signature-level absence: no rung fact reaches
   `launch_available` on any input. Both halves of the reasoning hold; the floor-header case is a
   hypothesis about a possible target, not a description of this one.
4. **A second instance of the same gap, in the same block, unnamed by the exploration.**
   `_derive_notebook_level` grades every leveled `@notebook` against the **search** record:
   `_record_scale_level` reads `evidence["search"]`, and `_position_write_evidence` sets
   `"requiredScale": declared_required_scale(search)`. The reference target's item 5 declares in
   its own prose that it "reads the merged record", citing the sixty-runs-beside-eighteen-hundred
   incident — a campaign-record fact — but its rung is computed from `ceilings.json` against
   `{"epochs": 20, "trials": 30}`, the search's scale. Item 4 is not the only leveled item whose
   witness cannot see what it claims to describe.
