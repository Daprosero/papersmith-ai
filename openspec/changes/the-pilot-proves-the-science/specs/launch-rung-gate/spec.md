# Launch Rung Gate Specification

## Purpose

`launch_available`'s collective attainment condition — when it applies before a launch is
authorized, and where `RUNG_NOT_ATTAINED` sits in the refusal order.

## Requirements

### Requirement: `launch_available` accepts rung facts

`impl_availability.launch_available` MUST accept two additional required keyword arguments:
`levels: list[str]` (the target's declared rung ladder) and `attained_level: str | None`
(the caller's own `position_state(...)["attainedLevel"]`, already computed today and
discarded). Both callers (`cmd_gate`, `_offer_launch_action`) MUST pass them through
unchanged, never recomputed a second way.

#### Scenario: caller passes attainment through

- GIVEN `position_state(...)` returns `attainedLevel: "pilot"`
- WHEN `cmd_gate` calls `launch_available`
- THEN `attained_level="pilot"` reaches the call, never recomputed

### Requirement: `RUNG_NOT_ATTAINED` is checked last

`launch_available` MUST check `RUNG_NOT_ATTAINED` only after every existing check
(`POSITION_ABSENT`/`_STALE`/`_UNBACKED`/`_SHARDS_UNDECLARED`/`_DISAGREES`, `NOT_READY`,
`SEQUENCE_NOT_REACHED`) has already passed. No input that refuses today may change its
refusal code.

#### Scenario: an existing refusal keeps its code

- GIVEN a call that today refuses `NOT_READY`
- WHEN `levels`/`attained_level` are supplied
- THEN the call still refuses `NOT_READY`, never `RUNG_NOT_ATTAINED`

### Requirement: rung threshold

When `len(levels) >= 2`, `launch_available` MUST refuse `RUNG_NOT_ATTAINED` unless
`attained_level`'s index is `>= len(levels) - 2` (at or above `levels[-2]`). A two-rung
ladder is NOT exempt: there `levels[-2]` **is** the floor, so the check still applies and
fires only when `attained_level is None`. When `len(levels) < 2`, the check MUST NOT apply
— structurally unreachable, consistent with vacuous-ladder doctrine below.

#### Scenario: below-floor attainment on a 3-rung ladder

- GIVEN `levels=["floor","pilot","full"]`, `attained_level=None`, every earlier check honest
- WHEN `launch_available` runs
- THEN it refuses `RUNG_NOT_ATTAINED`

#### Scenario: floor attainment on a 2-rung ladder is sufficient

- GIVEN `levels=["floor","full"]`, `attained_level="floor"`
- WHEN `launch_available` runs
- THEN `available` is `True` — the floor equals `levels[-2]`

### Requirement: reachability preconditions (specified, not assumed)

`RUNG_NOT_ATTAINED` is reachable only when ALL hold: (1) `len(levels) >= 2`; (2)
`position_honest(...)` returns `honest=True` (present, current, backed, non-disagreeing);
(3) `ready is True`; (4) the job's sequence item exists with every earlier item ticked; (5)
`attained_level`'s index sits below `len(levels) - 2`, including `None`. `POSITION_ABSENT`
and every earlier check fire first, so an absent position's `attained_level: None` never
reaches this check.

### Requirement: vacuous attainment is unchanged

A sequence with zero leveled items attains the ladder's top rung vacuously, by
`attained_level`'s own existing doctrine. This requirement adds no check there —
`RUNG_NOT_ATTAINED` never fires for such a sequence, and this change alters nothing about
that outcome.

### Requirement: silent omission is preserved

`_offer_launch_action` MUST remain a silent omission: when `launch_available` returns
`RUNG_NOT_ATTAINED`, the action MUST return `None`, never raise.

### Requirement: `cmd_gate` raises loudly

`cmd_gate` MUST raise `Refused("RUNG_NOT_ATTAINED", ...)` when the verdict refuses with
that code, classified `WORK_STATE` in `GATING_REFUSALS`, with a resolution builder in
`_WORK_STATE_RESOLUTIONS` that names the next rung to attain, read from the target's own
`__levels__` at refusal time — never inventing a rung name.

#### Scenario: refusal names the next rung

- GIVEN attainment below `levels[-2]` on a declared ladder
- WHEN `cmd_gate` raises `RUNG_NOT_ATTAINED`
- THEN the published question names the rung the target's own `__levels__` declares next

### Requirement: roster stays exhaustive

Adding `RUNG_NOT_ATTAINED` to `GATING_REFUSALS` MUST move
`test_the_derivation_finds_the_measured_sixty_six` from 66 to 67, and MUST update the
spelled-out split in `SKILL.md`/`references/usage.md` — because `raised_refusal_codes`
walks `cmd_*` subtrees only, and `RUNG_NOT_ATTAINED` is raised inside `cmd_gate`, so it is
visible to that walk and must be classified.

### Requirement: existing instances keep working

A position block written before this change, and a target declaring fewer than two
`__levels__` rungs, MUST both keep their current verdict: the new check is structurally
unreachable for them (see reachability requirement), so no launch authorized before this
change becomes refused, and no launch refused before it becomes authorized. No migration is
required or possible — `launch_available` is pure and reads no stored artifact under an old
shape.
