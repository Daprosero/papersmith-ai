# Proposal: The Pilot Proves the Science

## Intent

**Problem.** `impl_availability.launch_available(*, status, unbacked, disagreements, sequence,
ready, job, shards_declared)` takes no rung parameter. A fully ticked sequence plus
`ready=True` returns `{"available": True}` with attainment never consulted, so a remote launch is
authorized without the pilot ever being shown attained. Both callers — `cmd_gate` and
`_offer_launch_action` — already compute `position_state(...)`, which already returns
`attainedLevel` (`implementation_cli.py`, `position_state`). It is computed and thrown away.

**Why now.** The owner's rule: the pilot is the whole flow, not one notebook; the bar is not that a
step finished but that what it produced shows what was agreed. The gate is collective — one
condition over the flow, never per item.

**Why two halves.** Closing the gate alone deadlocks the reference target.
`_derive_shard_level` returns only `levels[0]` or `levels[-1]` — no middle rung, ever — and item 4
is witnessed by `@shard:level`. A shard only exists after a remote run; a remote run needs pilot
attained; pilot attainment needs item 4 above the floor. The gate would be a lock with no key.

## Scope

### In Scope

- **Half A — the collective gate.** `launch_available` gains required `levels` and `attained_level`;
  new refusal `RUNG_NOT_ATTAINED`, checked **last**, requiring attainment at or above
  `levels[-2]` when `len(levels) >= 2`.
- **Half B — the witness that opens it.** A new target-owned declaration `__records__` makes the
  leveled `@record` witness *addressable*: `@record:level <name>` derives its rung from that named
  record's own found/scale state through the existing `_record_scale_level` arithmetic.
- Kit scaffolding for `__records__` plus a report-when-absent state, modelled exactly on
  `undeclared_ladder_state`.
- The doctrine paragraph in `proposal-implementation/SKILL.md`: *the smoke proves the pipe, the
  pilot proves the science.*

### Out of Scope

- `classify_remote_necessity` — its docstring states why it does not inspect `smokeReady`; moving
  that check adds a second lock where one works.
- Anything under `implementations/`. The reference target's own `AGREED.md` and `__records__`
  declaration are **its** change, in its own commit and its own session.
- The ordinary-agreement witness mechanism — already shipped (`AGREEMENT_DISAGREES` is in
  `GATING_REFUSALS` and `_WORK_STATE_RESOLUTIONS`). Build on it.
- `_derive_shard_level` itself. It is correct for what it measures: shard transport.

## Capabilities

### New Capabilities

- `launch-rung-gate`: the collective attainment condition `launch_available` applies before a
  launch is authorized, and its position in the refusal order.
- `named-record-witness`: `__records__`, the addressable leveled `@record` witness, and the
  report-when-absent state for a target that declares none.

### Modified Capabilities

- `step-witness`: unchanged in behaviour; its doctrine gains the stated reason `@step` cannot carry
  a rung.

## Approach

**Half A.** New required kwargs, new check ordered after `SEQUENCE_NOT_REACHED`. Last position is
the only one that cannot move an existing verdict: any input refusing today keeps its current code.
Rejected — reading the header's `target=` (an aim, not a measurement; reopens the defect closed two
days ago) and a second parallel predicate (two "may this launch proceed" rules is the drift this
module exists to prevent).

**Half B.** `_record_scale_level` is already the one mechanism that expresses floor / *ran, short of
declared scale* / *met declared scale* honestly. It is bound to a single artefact — the `search`
block's. Lift the binding: a third top-level literal `__records__`, held apart from `__benchmark__`
exactly as `__levels__` and `__steps__` already are and read the same `ast`-only way, maps a
target-chosen name to `{path, requiredScale}`. `WITNESS_RE` already parses an optional operand for
every kind, so `@record:level <name>` costs no grammar change; a bare `@record` keeps its present
meaning.

Rejected — deriving item 4's middle rung from `stepVerdicts` via `__steps__`'s `advances`: it needs
no new declaration, but a step verdict says a step *finished*, which is precisely the bar the
owner's rule rejects, and it would make a shard witness report a step fact. Rejected — a local
shard: `_derive_shard_level` would read it at the **top** rung, worse than the floor.

**`@step` is not the answer.** `@step:level` refuses (`POSITION_WITNESS_NOT_LEVELABLE`, raised in
`_resolve_deriver`), `attained_level` excludes two-state items by construction, and — the reason
that survives redesign — `_derive_step` reads `run_step`'s `raised`/`returned`, which is identical
whether the callable ran at pilot or full scale. It cannot carry a rung because it measures
completion, not production.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `_core/implementation/impl_availability.py` | Modified | `launch_available` signature + `RUNG_NOT_ATTAINED` |
| `_core/implementation/impl_position.py` | Modified | addressable leveled `record` deriver; `OPERAND_REQUIRED_KINDS` comment |
| `proposal-implementation/scripts/implementation_cli.py` | Modified | 2 call sites, `cmd_gate` branch, `__records__` resolver + state, `GATING_REFUSALS`, `_WORK_STATE_RESOLUTIONS` |
| `proposal-implementation/assets/kit/src_benchmark/__init__.py` | Modified | `__records__: dict = {}` + commented example |
| `proposal-implementation/SKILL.md`, `references/usage.md` | Modified | doctrine; spelled-out roster counts |
| `tests/test_proposal_implementation.py` | Modified | 66 → 67; new RED/GREEN pairs |
| `implementations/**` | **None** | read-only |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Half A lands without Half B → deadlock | High if unsliced | Chain **B first, then A**. B alone is additive and harmless; A alone is the lock with no key |
| Roster churn breaks three test-bound counts | High | Expected: `test_the_derivation_finds_the_measured_sixty_six` and `test_the_doctrine_states_the_split_the_roster_actually_holds` fail loudly, never silently |
| A refusal that cannot fire | Medium | `RUNG_NOT_ATTAINED` is reachable only for a target with ≥2 rungs, a present/current/backed position, `ready is True`, every earlier item ticked, and one leveled item below `levels[-2]`. State that input in the spec |
| Vacuous attainment | Accepted | A sequence with zero leveled items attains the top by existing doctrine; this gate adds nothing there. Say so, do not patch it |
| `_offer_launch_action` raises instead of omitting | Medium | Its contract is silent omission — it returns `None` |
| Forge picks up target vocabulary | Low | Every rung and record name is the target's; **run** `FORGE_VOCABULARY_FLOOR` and the lexicon rule, never reason about them |
| ~1010–1250 changed lines vs 1400 budget | Medium | Two chained PRs, ≈700 (B) and ≈400 (A) |

## Rollback Plan

Half A: revert the two kwargs, the `RUNG_NOT_ATTAINED` branch, the two call-site arguments, and the
roster/count entries. Nothing persists — `launch_available` is pure and `_offer_launch_action`
omits rather than records. Half B: revert the resolver, state, deriver routing and kit line. A
target that never declared `__records__` is unaffected either way; one that did keeps a literal no
reader consults.

## Dependencies

- Half B must land before Half A.
- The target's own change (below) must land before the reference target can pass the new gate. It
  is **not scheduled by this proposal**.

## The contract the target must then meet

1. Declare `__records__` in `src/<Package>_Benchmark/__init__.py`: one named entry per record a
   leveled witness will address, each `{path, requiredScale}` in the target's own words.
2. Verify each declared path against disk after a real run — `search_state`'s own lesson is that
   two agreeing declarations prove only that someone typed the string twice.
3. Rewrite position item 4's witness from `@shard:level s00` to `@record:level <its own name>`, and
   rewrite the prose that currently documents the gap this removes.
4. Re-derive the block so header and marks rebind.
5. Its own commit, its own session.

## Success Criteria

- [ ] `launch_available` refuses `RUNG_NOT_ATTAINED` for a ≥2-rung ladder whose attainment sits
      below `levels[-2]`, and every input that refuses today keeps its current code.
- [ ] `@record:level <name>` derives floor / middle / top from a declared named record; a bare
      `@record` is byte-identical to today.
- [ ] A target declaring no `__records__` is reported, never refused.
- [ ] The doctrine paragraph is in `SKILL.md` and bound by a test.
- [ ] RED before GREEN, `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` purged; each mutation is one a
      weaker lock would survive.
- [ ] Baseline preserved: 2201 Python OK (skipped=3), node 385/385.

## Proposal question round

Asked here because this phase runs without a direct channel to the user. Four questions; none
blocks specs, all could reshape them.

1. **Half B's declaration surface.** `__records__` as a third top-level literal follows the
   `__levels__` / `__steps__` precedent exactly. The alternative is extending `records` inside
   `__benchmark__` to accept mapping entries. Is the standing "seven blocks" invariant reason
   enough to keep it apart, or do you want one declaration instead of three?
2. **Item 5, unnamed in the brief.** Every leveled `@notebook` grades against the *search* record
   (`_record_scale_level` reads `evidence["search"]`; `requiredScale` is
   `declared_required_scale(search)`). The reference target's item 5 claims to read the merged
   record and cites the 60-vs-1800 incident. Same class of gap as item 4. In scope for this change,
   or its own?
3. **Rung threshold.** `levels[-2]` is positional and names nothing. On a 2-rung ladder that means
   attainment at the floor suffices, and `RUNG_NOT_ATTAINED` fires only on `attained_level is None`.
   Correct, or should a 2-rung ladder be exempt entirely?
4. **Slice order.** B then A, two PRs, is what keeps the deadlock unreachable at every commit. Is a
   single 1250-line PR preferable given both halves are one idea?
