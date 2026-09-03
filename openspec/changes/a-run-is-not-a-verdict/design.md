# Design: A Run Is Not A Verdict

## Technical Approach

Add a fifth `WITNESS_KINDS` member, `"step"`, whose derivation is a plain dict
read over `evidence["stepVerdicts"][operand]` — the exact shape
`_derive_rehearsal` already has against `smokeReady`. The ledger's existing
`kind: "step"` event grows one `suiteDigest` field; a shared fold in the CLI
turns ledger events plus a fresh `suite_digest(target)` into that dict. The
core learns no path, no ledger, no digest math (`_derive_shard`'s stated
layering). Realizes `specs/step-witness/spec.md`, all nine requirements.

## Architecture Decisions

### Decision: One field on the existing `step` event, not a sibling kind

**Choice**: `event["suiteDigest"] = suite_digest(target)`, written on every
resolved run, unconditionally.
**Alternatives**: a sibling `kind: "step-witness"` event; no digest.
**Rationale**: `cmd_step`'s "No digest field" paragraph is *scoped*, not
wrong — its own text names its premise ("a notebook"): a self-stamping
artifact already carries the digest (redundancy) and can be re-run outside
`step` (drift). Measured: the reference target's `steps.py` declares every
entry as a notebook runner, so the paragraph describes real steps. Neither
half survives for a bare runner — there is no artifact to carry the digest or
to drift against, so the ledger line is the only possible record. The sibling
kind was rejected on atomicity: outcome and the digest it was measured under
are one fact, and two lines create a join that can disagree with itself.
Written unconditionally because the forge cannot know which steps are bare
runners — that is the target's business; the field is a true statement about
every run, and only the position item decides whether it is read.

### Decision: The guard lives at the lookup, not as a fourth special case

**Choice**: in `derive()`, replace `_DERIVERS[kind]` / `_LEVEL_DERIVERS[kind]`
with one `.get()`-based resolver raising
`Refused("POSITION_WITNESS_NOT_LEVELABLE", ...)` naming the item and the kinds
that do carry a rung.
**Alternatives**: special-case `"step"` beside `record`; validate in
`parse_items`.
**Rationale**: a special case guards this kind; the lookup guards every future
one, and the same trap is live on the two-state arm too (a kind in
`WITNESS_KINDS` and in neither dict is already a bare `KeyError`). The
refusal is **deliberately not rostered**: `raised_refusal_codes` scans a
`cmd_*` subtree in `implementation_cli.py` only, so a core-raised code added
to `GATING_REFUSALS` would fail `roster - raised == []`. It joins the
settled non-rostered class `parse_items` already documents
(`POSITION_ITEM_MALFORMED`, `POSITION_WITNESS_UNKNOWN_KIND`), reaching exit 2
through `main()`'s `except Refused` with no wiring at any call site.
**Reachability, stated honestly**: the leveled arm is reachable from real
markdown (`@step:level run_suite`). The two-state arm is reachable only from
a direct `derive()` call — structural insurance, tested as a contract, never
claimed as a markdown-reachable guard.

### Decision: `suite_digest` walks `*.py`, not `test_*.py`

**Choice**: `rglob("*.py")` under both `src/` and `tests/`, skipping
`__pycache__` (`source_digest`'s own shape), then five fixed manifests folded
through `impl_position.current_file_digest`.
**Alternatives**: the spec's cited `test_function_names` shape.
**Rationale**: **measured correction** — `test_function_names` globs
`test_*.py`, which does not match `conftest.py`. The reference target has
`tests/conftest.py`, so the cited shape would exclude the very file the brief
says the walk already covers. `unparsable_tests` (`rglob("*.py")`) is the
right precedent. Manifests: no second absence check — one
`current_file_digest` call per name yields a real digest or
`ABSENT_FILE_DIGEST`, so declaring `tox.ini` later moves the digest.
Measured on the target: `requirements.txt`/`pyproject.toml`/`setup.cfg`
present, `tox.ini`/`pytest.ini` absent. No `package` argument — `source_digest`
carries one only for kit parity, and `suite_digest` has no kit counterpart.
`source_digest` is untouched.

### Decision: Stale beats red — digest compared before outcome

**Choice**: mismatched digest → `None` even when `outcome == "raised"`.
**Alternatives**: a stale red stays `False`.
**Rationale**: `_derive_record`/`_derive_shard` both state that a stale
measurement is unmeasured, never `False`. `False` would assert "the suite
fails now" about code nobody ran. Verified this loses no gating: `None` over a
ticked item is `unbacked` → `POSITION_UNBACKED`; over a blank item →
`SEQUENCE_NOT_REACHED`. Both still refuse.

### Decision: The new refusal is a work state, raised in `cmd_position`

**Choice**: `POSITION_STEP_UNKNOWN` → `WORK_STATE`, published as a question via
`_refusal_question` (two possible repairs; only a human picks). Detail built by
`_step_operand_detail(items, steps) -> str | None`; `raise` stays textually
inside `cmd_position` (`_skipped_rung_detail`'s proven shape). Second arm:
`@step` items with an empty `__steps__` reuse `STEPS_UNDECLARED` verbatim.
**Alternatives**: `INVOCATION_DEFECT`, per the proposal; raising in `cmd_gate`
or `cmd_step` too.
**Rationale**: **measured correction to the proposal.** `STEP_UNKNOWN` is an
invocation defect because `--step <name>` is an argument the caller typed. No
argument names a *position item's* operand — it lives in `AGREED.md`, and
clearing it means editing the document or declaring the step. That is the
roster's own derivable test, answered the other way. `cmd_position` is the sole
raise site by `POSITION_RUNG_SKIPPED`'s stated precedent: "decided where the
header is sealed, not where a later command reads it back". Readers stay safe
by default — an unvalidated operand derives `unmeasured`, which never satisfies
a tick. **Reachable**: `parse_items` validates the kind, never the operand.
Reusing `STEPS_UNDECLARED` costs no count — `gating_codes()` is a set union.

### Decision: All three evidence builders share one fold

**Choice**: `_step_verdicts(target, name)` called from
`_position_write_evidence`, `cmd_probe`'s inline dict, and `cmd_verify`'s
inline dict.
**Rationale**: **the proposal named only the first.** Three sites build the
dict handed to `position_state`; wiring one leaves `verify` and `probe`
reporting `unmeasured` forever while `gate` reports `True` — two places
disagreeing about "the suite is green", the exact defect the proposal's own
rejected alternative 3 names. Unlike `@shard`, no flag is missing here.
Short-circuits to `{}` when the ledger holds no `kind: "step"` event, so
`suite_digest` is never walked for a target that never ran `step`.

## Data Flow

    cmd_step ──run_step──→ outcome ──┐
                                     ├─→ position.jsonl {kind:"step", suiteDigest}
              suite_digest(target) ──┘            │
                                                  ▼
                          _step_verdicts (fold: latest-wins per step,
                                          digest vs fresh suite_digest)
                                                  │
                                                  ▼
                          evidence["stepVerdicts"]  ←── 3 builders
                                                  │
                                                  ▼
                          _derive_step (dict read only) ──→ derive()

## File Changes

| File | Action | Description |
|---|---|---|
| `_core/implementation/impl_position.py` | Modify | `"step"` into `WITNESS_KINDS` **and `OPERAND_REQUIRED_KINDS`**; `_derive_step` into `_DERIVERS`, none into `_LEVEL_DERIVERS`; `.get()` guard + `POSITION_WITNESS_NOT_LEVELABLE` at both lookups in `derive()` |
| `proposal-implementation/scripts/implementation_cli.py` | Modify | `suite_digest` (new, beside `source_digest`); `_step_verdicts` (new); `cmd_step` event + rewritten doctrine paragraph; `_position_write_evidence`, `cmd_probe`, `cmd_verify` evidence dicts; `_step_operand_detail` + raise in `cmd_position`; `GATING_REFUSALS` + `_WORK_STATE_RESOLUTIONS` |
| `proposal-implementation/SKILL.md` | Modify | Witness-kind grammar; `step` row's "No digest field"; counts `Sixty-five`→`Sixty-six` and work-state `31`→`32`; skip-laundering non-goal |
| `proposal-implementation/references/usage.md` | Modify | Same; `Thirty-one codes`→`Thirty-two codes` |
| `tests/test_implementation_core.py` | Modify | `_derive_step`, leveled guard, `OperandRequiredKindsTests` set |
| `tests/test_proposal_implementation.py` | Modify | Digest scope, ledger shape, fold, refusal, roster count + rename |
| `implementations/**` | Not touched | Fixture source only |

## What Breaks — Producers AND Products

| Class | Site | Verdict |
|---|---|---|
| Producer | `test_the_derivation_finds_the_measured_sixty_five` | 65→66; number is in the name — **rename required** |
| Producer | `test_the_doctrine_states_the_split_the_roster_actually_holds` | **Not in the brief.** Binds SKILL.md's spelled total *and* the 34/31 split *and* usage.md's spelled counts |
| Producer | `OperandRequiredKindsTests.test_record_is_excluded_the_rest_are_required` | **Not in the brief.** Pins the exact frozenset; moves when `"step"` joins |
| Producer | `test_the_roster_states_the_counts_it_actually_holds` | **Brief was wrong** — binds `len(COMMANDS)` (subcommands). No subcommand added; does not move |
| Producer | `test_every_gating_refusal_is_classified` | Both sides move together |
| Product | Existing `kind: "step"` ledger lines (no `suiteDigest`) | `.get()` → `None` ≠ current digest → verdict `None`. Never raises, never `True`. Remedy is a fresh append; the ledger is append-only |
| Product | Existing `kind: "step"` test fixtures | Six, all in `tests/test_implementation_core.py`, all `impl_guards` worktree-dirtiness fixtures that never reach derivation. **Untouched** — measured, not assumed |
| Product | Position blocks in `implementations/**` | Untouched — no `@step` witness exists in any AGREED.md today |
| Product | Notebook reports / `SOURCES-SHA256` stamps | Untouched — `source_digest` unchanged, so no report anywhere goes stale |
| Product | `cmd_step` response dict | Deliberately **not** given the new key, so every `returned_keys` lock stays green |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (core) | `_derive_step`; leveled guard | RED first. Mutations a weaker lock survives: missing verdict `None`→`False`; `raised` `False`→`None`; `.get()`→`[]` restores `KeyError` |
| Unit (CLI) | `suite_digest` scope | Add `tests/test_x.py` → moves; `source_digest` same tree unchanged. Create `tox.ini` → moves (absence was a value). Add `tests/conftest.py` → moves (kills the `test_*.py` glob) |
| Integration | Fold + currency | Ledger fixture: stale digest over `returned` → `None`; two events latest-wins; digestless event → `None`, no raise |
| Integration | Refusal | `@step nosuch` through `cmd_position` → `POSITION_STEP_UNKNOWN`, found by `raised_refusal_codes`, publishes a runnable `discuss` |
| Integration | Parity | All three evidence builders return the same `stepVerdicts` for one fixture |

Every lock runs with `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` purged — a
same-size mutation otherwise reuses a stale `.pyc` and the mutant never runs.

## Threat Matrix

**N/A** — no routing, shell, subprocess, VCS/PR automation, executable-file
classification, or process-integration boundary is added or changed. Adjacent
and explicitly untouched: `impl_steps.run_step`'s existing subprocess and
`PATH` composition. `suite_digest` reads only target-relative paths and five
fixed literal filenames; no caller input reaches a path.

## Migration / Rollout

No migration. Additive: no existing witness kind changes derivation, no event
loses a field, no `AGREED.md` byte changes, `source_digest` is untouched.
Revert restores four kinds; a `suiteDigest` field on an old event is ignored by
the old reader.

## Cross-Repository Contract (target, separate commit and session)

The target must declare a `__steps__` entry whose callable **raises on a red
suite** and produces no artifact of its own, then decide whether item 1's
witness migrates from `@notebook` to `@step`. Measured: `verification` exists
with `advances: 1`, but `steps.py` declares every entry a notebook runner, so
the suite-running entry is new work. The forge writes nothing under
`implementations/` and encodes no opinion on skip handling.

## Explicit Non-Goal

This closes assert-forgetting, **not** skip-laundering. `pytest` exits 0 with
skips, so `returned` grades green over a skipped suite exactly as today's
notebook does. Six skip sites measured on the reference target, one
module-level (`tests/test_distribute.py`, 15 tests vanish when the forge's
`packer.py` is not beside the target). Stated in `SKILL.md`, `usage.md` and the
`suite_digest` docstring in these words, never softened into an implied
guarantee.

## Review Workload Forecast

| Component | Est. |
|---|---|
| `impl_position.py` — kind, operand class, deriver, lookup guard | ~130 |
| `suite_digest` + docstring | ~90 |
| `cmd_step` event + rewritten doctrine paragraph | ~60 |
| `_step_verdicts` + three call sites | ~120 |
| Refusal + helper + roster + resolution | ~85 |
| `SKILL.md` + `usage.md` | ~95 |
| `tests/test_implementation_core.py` | ~200 |
| `tests/test_proposal_implementation.py` | ~340 |
| **Total** | **~1120** |

Revised up from the proposal's ~980 by this phase's three findings (three
evidence builders, `OPERAND_REQUIRED_KINDS`, the lookup guard).

`Decision needed before apply: No`
`Chained PRs recommended: No`
`400-line budget risk: High` — against the session's 1400: ~80% consumed, ~280
lines of headroom. No split leaves both halves deliverable: a witness kind
without its digest is a verdict that never expires. If apply passes 1400
materially, stop and re-decide with the owner.

## Open Questions

- [ ] **Neither suite has been run for this change by any phase.** No Bash tool
      in explore, proposal, spec, or design. `2144 OK skipped=3` and `385/385`
      are inherited, unverified numbers. `sdd-apply` must measure both baselines
      *before* the first RED, plus `FORGE_VOCABULARY_FLOOR` and the derived
      lexicon rule — run, never reasoned about.
- [ ] Confirm the `source_digest` whole-AST kit lock is unaffected by a new
      sibling function (expected: yes, its own AST is unchanged) — by running.
- [ ] Confirm `_refusal_question` builds cleanly from `cmd_position`'s args
      namespace (it has no `--about`); `refusal_resolution` is try/except-guarded,
      but `test_every_work_state_publishes_something_runnable` asserts content.
