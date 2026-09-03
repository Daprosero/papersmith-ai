# Design: The Pilot Proves the Science

## Technical Approach

Two commits on one branch, **B then A**, one merge. Neither half adds arithmetic: A passes
`launch_available` a fact both callers already compute and discard; B feeds the existing
`_record_scale_level` a record other than the `search` block's. Half B gains one refusal —
the owner's decision that a witness naming an undeclared record is refused, not reported —
modelled on `POSITION_STEP_UNKNOWN` (helper returns a detail string; `raise Refused(...)`
sits textually in `cmd_position`, where `raised_refusal_codes` can see it).

## Architecture Decisions

| # | Decision | Rejected alternative | Rationale |
|---|---|---|---|
| D1 | `RECORDS_DECLARATION = "__records__"`; `resolve_records_declaration(target, name) -> dict` mirrors `resolve_steps_declaration` exactly (`__init__.py`, then `config.py`; `ast`-only; first file that answers wins; non-dict reads `{}`) | mapping entries under `__benchmark__` | `_declaration_is_blank`'s seven-block invariant; a target names a record long before it answers seven blocks |
| D2 | `_record_scale_level(record, required_scale, levels, *, measured_by)` — the same body, fed explicitly. Three bindings: `derive`'s bare `@record:level`, `_derive_notebook_level`, and the new `_derive_record_level` | a second `_named_record_level` beside it | one arithmetic, three visible bindings; two functions drift |
| D3 | `_derive_notebook_level` keeps grading against the `search` block, unchanged in behaviour — its binding merely becomes visible at the call site | teaching `@notebook:level` a record operand | new grammar, out of scope; the spec's own follow-on rewrites item 5 to `@record:level` in the target's commit |
| D4 | Caller assembles `evidence["records"]`: `{name: {recordFound, recordCurrent, scaleSatisfied, requiredScale}}` via a new `named_records_state`, reusing `_record_scale`/`_scale_satisfied`/`_record_current` | deriver opens files | all derivers are plain dict readers by stated doctrine |
| D5 | One new code, `POSITION_RECORD_UNKNOWN` (`WORK_STATE`), raised in `cmd_position` **before** `_skipped_rung_detail` | after it, mirroring the `@step` check's position | an unknown name derives `None`, which sinks `attained_level`; placed after, `POSITION_RUNG_SKIPPED` fires first and the specific refusal is unreachable above the floor. `@step` has no such trap — two-state items never reach `attained_level` |
| D6 | The same code covers "`__records__` declares nothing" and "declares others, not this one"; the detail distinguishes them | a second `RECORDS_UNDECLARED` mirroring `STEPS_UNDECLARED` | no existing code to reuse verbatim; one exit (declare the record), so two classifications for one fact |
| D7 | `launch_available` gains required `levels`/`attained_level`; `RUNG_NOT_ATTAINED` checked last | header `target=`; a second predicate | last position cannot move an existing verdict; `target=` is an aim, and the drift `impl_availability` exists to prevent |
| D8 | `verify` gains top-level `undeclaredRecords` via `undeclared_records_state`, modelled on `undeclared_ladder_state` | nesting it | `returned_keys` reads top-level dict literals only; nested ships invisible |

## Data Flow

    __records__ ──resolve_records_declaration──┐
                                               ├─ named_records_state ──→ evidence["records"]
    product/<path> + requiredScale ────────────┘                                │
                                                                                ▼
    @record:level <name> ──→ _derive_record_level ──→ _record_scale_level ──→ rung
                                                                                │
    position_state ──→ attainedLevel ──┐                                        │
    evidence["levels"] ────────────────┴──→ launch_available ──→ RUNG_NOT_ATTAINED

## File Changes

| File | Action | Slice |
|---|---|---|
| `_core/implementation/impl_position.py` | Modify — `_record_scale_level` signature, `_derive_record_level`, `_LEVEL_DERIVERS`, `derive`'s record branch | B |
| `_core/implementation/impl_availability.py` | Modify — two kwargs, `RUNG_NOT_ATTAINED` | A |
| `proposal-implementation/scripts/implementation_cli.py` | Modify — resolver, `named_records_state`, `undeclared_records_state`, `_record_operand_detail`, `cmd_position` branch, `_position_write_evidence` + the two inline evidence dicts, `cmd_verify` key, roster, resolutions | B, A |
| `assets/kit/src_benchmark/__init__.py` | Modify — `__records__: dict = {}` + commented example, no name invented | B |
| `proposal-implementation/SKILL.md` | Modify — Output-Contract row, roster counts, doctrine paragraph | B, A |
| `references/usage.md` | Modify — `undeclaredRecords` bullet, both spelled counts | B, A |
| `tests/test_proposal_implementation.py` | Modify — new classes; `_ENGLISH_COUNTS` needs `68` | B, A |

## Interfaces

```python
def resolve_records_declaration(target: Path, name: str) -> dict          # {name: {path, requiredScale}}
def named_records_state(target: Path, name: str, records: dict, digest: str) -> dict
def undeclared_records_state(target: Path, name: str, records: dict) -> dict | None
def _record_operand_detail(items: list[dict], records: dict) -> str | None
def launch_available(*, ..., levels: list[str], attained_level: str | None) -> dict
```

`__records__` carries no `currentWhen`: `_record_scale_level` already reads no currency, so a
named record inherits today's arithmetic exactly. Measured asymmetry, inherited not caused:
two-state `@record` checks `recordCurrent`; the leveled path never has.

## What Breaks

| Class | Instance | Verdict |
|---|---|---|
| Producers | `_record_scale_level` callers (2), `launch_available` callers (2), roster counts in 2 documents, `_ENGLISH_COUNTS` | updated in the same commit |
| Products | `AGREED.md` position blocks on disk | untouched — no existing block carries `@record:level <name>` |
| Products | `.implementation/position.jsonl` events | untouched — no new field, none re-read |
| Products | authorization tokens already minted by `offer` | not invalidated; `gate` may now refuse before validating one. Token stays unconsumed and re-usable once the rung is attained |
| Products | targets with no `__records__` | reported by `verify`, refused by nothing |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | `_record_scale_level` under three bindings; `launch_available`'s threshold at 1/2/3 rungs and `None` | direct calls, no fixture target |
| Unit | `POSITION_RECORD_UNKNOWN` reachable **above the floor** | fixture with `target-level` above `levels[0]`; mutation: move the check after `_skipped_rung_detail` and watch it survive a weaker lock |
| Integration | evidence parity across all three builders | `_position_write_evidence`, `cmd_probe`, `cmd_verify` asserted to agree on `records` per site — proved, never asserted once |
| Integration | `cmd_gate` raises, `_offer_launch_action` returns `None`, on identical facts | one fixture, both callers |
| Roster | 66 → 67 (B) → 68 (A); `SKILL.md`/`usage.md` splits | existing derivation tests |

Strict TDD: every lock RED first, `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` purged.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or
process-integration boundary is added. `named_records_state` reads a target-declared relative
path under the product directory, the identical read `search_state` already performs for
`search.record`; no new boundary.

## Migration / Rollout

None possible and none required: both halves are pure readers. B is additive; A is
structurally unreachable for a target with fewer than two rungs.

## Open Questions

- [ ] `usage.md`'s two count sentences collapse to one distinct value (34/34) after A, so the
      existing assertion can no longer catch a stale work-state sentence. Recommend
      strengthening it to two per-kind assertions in slice A.
