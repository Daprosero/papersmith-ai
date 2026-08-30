# Proposal: A Pilot Is The Whole Flow, Validated

## Intent

`close` ends a session on evidence that a **step was reached**, never on what the step **produced**. `settle --about <witness>` binds an agreement to a witness identity, uses it for the collision search, records it only in `.implementation/position.jsonl`, and throws it away: `AGREEMENT_LINE` captures `mark` and `text` only, so after `settle` the line is bare `- [ ] <text>` and `agreements_state` has no notion of witness per item.

The problem is **not** vague agreements. In the reference target ~93 of 108 items (~86%) name a concrete checkable artifact; ~14 (~13%) are irreducible prose. None of the 86% is wired to anything.

Separately, `cmd_close`'s refusal ladder is `POSITION_ABSENT`/`POSITION_STALE`/`POSITION_DISAGREES`; `cmd_gate`'s adds `POSITION_UNBACKED`. Launch-time is protected against an unmeasured tick; finishing-time is not. This asymmetry is a **verified code fact but an unproven-reachable gap** — see Success Criteria.

## Scope

### In Scope
- **Three states, none collapsing into another**, mirroring `derive()` one level down: `unwitnessed` (no witness declared — a reported state, never a failure), `unmeasured` (declared, not evaluable this run), `disagrees` (declared, evaluated, contradicts — gates).
- **Persist the witness into the artifact line**, scoped strictly to the existing `test_<id>` pattern (`__provenance__["invariants"]` → `declared_invariants` → `test_<invariant>` in the suite). `settle --about` stops discarding its own binding.
- **Prose-only agreements**: always reported by exact text, never silently counted as passed, never gated.
- **Gating at write commands only** (`close`); `verify`/`probe` report and never refuse.
- **`close`/`unbacked` symmetry fix**, delivered with a reachability proof.

### Out of Scope
- Full static agreement↔code cross-reference (duplicates the provenance machinery this codebase refuses to duplicate).
- Any new `WITNESS_KINDS` member; field-witnesses, constant-witnesses.
- Retrofitting the target's already-settled items (target-side cost, quantified below).
- Gating on `verify` or `probe`.

## Capabilities

### New Capabilities
- `agreement-witness`: persisted per-item witness binding and its three-state report.
- `close-refusal-symmetry`: `close` refuses the same unmeasured-tick condition `gate` already refuses.

### Modified Capabilities
- None. `openspec/specs/` does not exist in this repository; capabilities are declared per change.

## Approach

1. **Slice A — symmetry.** Fold `unbacked` into `position_state`'s `status`, add `POSITION_UNBACKED` to `cmd_close` in `gate`'s order (immediately before `POSITION_DISAGREES`). `impl_availability.availability()` already holds the full four-code ladder; `close` reimplements a three-code subset. Prefer reuse over a fourth hand-written branch.
2. **Slice A — reachability proof (required, not optional).** Construct a state where a ticked item's witness **cannot be measured at all** (`unbacked: [...]`, `disagreements: []`) — not merely measured-and-contradicting. Clearing `Notebooks/verification.ipynb` outputs does **not** produce it: the witness is still measured (`sourcesMatch` → False) and yields `disagrees`, which `close` already refuses correctly. Show `close` succeeds on the unbacked state today, then refuses after the fix. If the state proves unconstructible, the branch is unreachable and the change must say so rather than ship a guard nothing can fire.
3. **Slice B — witness persistence.** Extend the agreement line grammar with an optional trailing witness token; `settle --about` writes it; `agreements_state` parses it beside `mark`/`text`; `verify` grows an agreement-level dimension reporting the three states; `close` refuses only on `disagrees`.
4. **Domain neutrality.** The mechanism asks two questions only: does the named test exist, did the externally-run suite pass it. It never interprets meaning.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `.claude/skills/proposal-implementation/scripts/implementation_cli.py` | Modified | `AGREEMENT_LINE`, `agreements_state`, `position_state`, `cmd_settle`, `cmd_close`, `cmd_verify` |
| `.claude/skills/_core/implementation/impl_position.py` | Modified | Witness token in the line grammar; `derive()` unchanged in spirit |
| `.claude/skills/_core/implementation/impl_availability.py` | Reused | Four-code ladder `close` should share |
| `.claude/skills/proposal-implementation/SKILL.md`, `references/usage.md` | Modified | `close` refusal set; the three states |
| `tests/test_proposal_implementation.py` | Modified | Reachability proof + three-state coverage |
| `implementations/Domain_Adaptation/MIL-CREDA/AGREED.md` | **Not touched** | Target-side retrofit is out of scope |

## Retrofit Cost — the operator must see this

This forge-side change **does not** make the target's existing agreements checked. It makes them *checkable*.

- 114 raw checklist lines in the target's `AGREED.md`; ~108 count as agreements once the position block is excluded.
- ~93 name a concrete artifact and could carry a witness. Each needs (a) a re-`settle` to write the binding, and (b) an existing or new `test_<invariant>` plus an `__provenance__["invariants"]` declaration.
- **How many of the 93 already have a matching `test_<invariant>` is unmeasured.** The honest bound is therefore **93 re-settles and between 0 and 93 new invariant tests**. Measuring this bound is the first task of any target-side follow-up, not part of this change.
- ~14 prose-only items are permanently `unwitnessed`. That is the correct end state, not debt.

## Review Workload Forecast

| Slice | Est. changed lines | Notes |
|-------|-------------------|-------|
| A — `close`/`unbacked` symmetry + reachability proof | ~120–200 | Small surface; the proof test dominates |
| B — witness persistence + three-state report | ~450–700 | Grammar, parser, `settle`, `verify`, docs, tests |
| **Total** | **~600–900** | This codebase's docstring density inflates line count |

**400-line budget risk: High.** **Chained PRs recommended: Yes** — Slice A first (independently deliverable, independently rollback-able, and its proof decides whether the guard is real); Slice B second, targeting Slice A's branch. Do not deliver as one PR.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| The `unbacked` state is unreachable at `close` | Medium | The reachability proof is a gate on Slice A, not a follow-up. An unreachable branch is reported, not shipped as a fix |
| Line-grammar change breaks existing bare agreement lines | Medium | Witness token strictly optional; bare lines must parse identically. Regression test over the target's real file |
| Forge picks up domain vocabulary | Low | `FORGE_VOCABULARY_FLOOR` (tests/test_proposal_implementation.py, tests/test_skill_audit.py) already enforces it across shipped `.md/.py/.json` |
| Operators read `unwitnessed` as passing | Medium | Never counted in a passed total; always printed by exact text |
| Witness binding becomes a second place for one fact to go stale | Medium | The binding names a test; the test is the single source. No copied assertion |

## Rollback Plan

- Slice B: revert the grammar/parser/`settle`/`verify` commit. Persisted witness tokens in a target's `AGREED.md` become ordinary trailing text under the restored `AGREEMENT_LINE` — no target file needs editing. Verify by re-running `verify` on the reference target.
- Slice A: revert the `cmd_close` and `position_state` commit. `close` returns to its three-code ladder; `gate` is untouched throughout.
- No migration, no persisted schema outside the two `.md` lines and the existing ledger.

## Dependencies

- Reference target `implementations/Domain_Adaptation/MIL-CREDA` must remain readable for the reachability proof and the regression test.
- The externally-run suite remains the only source of "did `test_<id>` pass"; this change does not run tests itself.

## Success Criteria

- [ ] The reachability of an `unbacked` tick at `close` is **proven or disproven by execution**, and the result is recorded either way.
- [ ] If reachable: `close` succeeds on that state before the fix and refuses `POSITION_UNBACKED` after it.
- [ ] `settle --about <witness>` writes a binding that survives into `AGREED.md` and is read back by `agreements_state`.
- [ ] `verify` reports `unwitnessed`/`unmeasured`/`disagrees` as three distinct counts; no state is folded into another.
- [ ] Every prose-only item appears by exact text in the report and in no passed total.
- [ ] `close` refuses on agreement `disagrees`; `verify` and `probe` never refuse.
- [ ] `FORGE_VOCABULARY_FLOOR` reports zero violations across shipped skill files.
- [ ] Bare `- [ ] <text>` lines parse byte-identically to today.
- [ ] The retrofit bound (how many of the ~93 already have `test_<invariant>`) is measured and reported, not estimated.
