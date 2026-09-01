# Design: Nothing Agreed Stays In The Conversation

## Technical Approach

One reader (`_open_discussions`) and one command builder (`_discuss_command`) added to
`implementation_cli.py`; `import shlex` added. Half 1 wires the reader into `cmd_close`.
Half 2 wires the builder into three sites. No ledger schema change, no
`_core/implementation/` change.

**Non-goal, unsoftened:** the gate proves a decision reached the record. It never proves
the operator authored it. Half 2 makes self-answering easier, not harder.

## Frequencies, measured — they settle three questions

| Signal | Live | Consequence |
|---|---|---|
| `prose.unresolvedSymbols` | 158 | Excluded on evidence. A flood trains the reader to dismiss the surface. |
| `prose.staleRevisions` | 1 | Excluded with it; the engine's own docstring declines to judge these. |
| `agreements.witness.unwitnessed` | 18 | Excluded. `agreements_state` calls it "reported, never a failure" — a resting state. |
| `localRemediesNotWritten` | 0 | **Included on structure, not plausibility** — see D3. |
| `nextStep` / `results.status` | `search-first` / `absent` | `piloted` is unobservable here — see D4. |

## Architecture Decisions

### D1 — Publication surface: a new top-level `toDiscuss` key on `probe`/`verify`; the refusal message for `settle`

| Option | Tradeoff | Verdict |
|---|---|---|
| More `offer` actions | `ACTION_IDS` is a closed forge-owned vocabulary pinned by `OfferCommandTests` against `cmd_offer`'s own `"id"` literals. The three sites are not `offer`. | Rejected |
| Nested under `audit` | Invisible to `returned_keys` (top-level dict literals only), so it ships undocumented. | Rejected |
| **New top-level `toDiscuss`** | Trips `VerifyStatusRosterTests` / `ProbeReportedFactsRosterTests`, forcing a `SKILL.md` row and a `usage.md` mention. | **Chosen** |

Rationale: the roster cost *is* the benefit. It converts "a key nobody documented" into a
compile-time obligation — the exact defect those rosters were written for. It also honours
the convention the prompt names: `verify`/`probe` **report**, and a published command is a
report of an available action, not a gate. `settle` has no success return on the collision
path, so its command goes in the `Refused` text, identical to Half 1's `close` refusal.

Shape, deliberately without an `"id"` key so the two vocabularies stay disjoint:
`{"about": {...}, "question": <text>, "command": <string>}`.

### D2 — One quoting path

`_discuss_command(target, name, *, about, question, answer=None)` builds every published
string; all four sites call it. `shlex.quote` on every embedded value. 3 of 12 live texts
carry an apostrophe; `expand-contract`'s hardcoded single-quoting survives only because its
fixed text has none, and is left alone (out of scope).

Half 1's retirement command carries a quoted placeholder `--answer`. Alternative `--answer -`
(stdin) was rejected: under an empty stdin it records `status: "open"`, so the spec's
"executed as a subprocess, appends an answered event" scenario would pass vacuously.
**Cost, stated:** the placeholder puts a garbage answer one keystroke away.

### D3 — `localRemediesNotWritten` is included despite 0 observations

Not on plausibility. The two failures a zero-observation design risks are *unbounded volume*
and *an unreachable guard*; both are decidable from code shape here. It is a plain list
comprehension over `findings` with no preemption ladder, bounded by findings count, and its
question text is a finding id — an identifier, not a measurement. **Obligation:** tasks must
record the live findings cardinality before apply.

### D4 — `piloted` ships only with a reachability proof, or it is deleted

`probe_state` sets `piloted` only when `status == "current"` **and** `belowTargetScale` is
non-empty; then seven `elif` branches can overwrite `next_step`. Measured: `search-first`
does **not** structurally preempt it — `search.requiredScale` and `probe_state`'s
`targetScale` are separate declarations from separate sources, held apart on purpose
(`SEARCH_DECLARATION`'s own docstring: folding them "would let one silently gate the other").
So it is reachable in principle and unreachable on this target today.

Requirement: a fixture satisfying all seven non-downgrade conditions. If it cannot be built,
the point is **deleted, not shipped decorative**.

### D5 — Stable text derives from identity, never from a count or state

| Site | Stable source | Excluded |
|---|---|---|
| settle collision | operand + sorted colliding texts | `len(collides)` |
| probe piloted | target/name + `belowTargetScale[k]["declared"]`, axes sorted | `["ran"]` |
| verify remedy | finding id | any count |

A new colliding agreement changes the text — correct, because it is a different decision.

## Data Flow

    ledger.jsonl ──→ _open_discussions ──→ cmd_close (refuse, before refresh)
                                     │
    _agreement_collides ─┐           └──→ _discuss_command ──→ printed string
    belowTargetScale ────┼──→ toDiscuss ──→ probe/verify JSON
    localRemedies... ────┘

## File Changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/proposal-implementation/scripts/implementation_cli.py` | Modify | `import shlex`; `_open_discussions`, `_discuss_command`; `cmd_close` axis 3; `SETTLE_COLLIDES_UNNAMED` text; `toDiscuss` on `cmd_probe`/`cmd_verify` |
| `.claude/skills/proposal-implementation/SKILL.md` | Modify | Non-goal verbatim; `toDiscuss` row in both roster tables |
| `.claude/skills/proposal-implementation/references/usage.md` | Modify | `toDiscuss` under `## Reading \`verify\``; collision wording |
| `tests/test_proposal_implementation.py` | Modify | 7 mutation proofs + reachability fixtures |

## What Breaks — Producers AND Products

| Class | Item | Verdict |
|---|---|---|
| Producer | `test_settle_refuses_collides_unnamed` | Asserts `code` only, **not** wording — survives. Enumerated by grep across `*.py`: no test asserts `"existing agreement(s)"`. |
| Producer | `VerifyStatusRosterTests`, `ProbeReportedFactsRosterTests` | Fail until `SKILL.md`/`usage.md` rows exist. Intended. |
| Producer | `ACTION_IDS` / `OfferCommandTests` | Untouched — no new `"id"` literal. |
| **Product** | Live `discuss` events (27, 12 texts) | Read, never rewritten. 0 open → `close` behaviour unchanged. |
| **Product** | Archived `offer`/`settle` events | Untouched; `collides`/`actions` shapes unchanged. |
| **Product** | Records carrying `toDiscuss` | **None exist.** New key; nothing on disk is judged by it. |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | Bucketing, last-word ordering | 7-event fixture (5 open / 2 answered) → not open |
| Mutation | Spec's 7 proofs | Each must fail the weaker build |
| E2E | Every published string | Executed as subprocess, `expand-contract`'s discipline |
| Reachability | `piloted`, remedy | Fixture must reach the branch, else delete the point |
| Red-first | All | `git stash` production file only, keep tests, re-run |

## Threat Matrix

| Boundary | Applicability | Response | RED test |
|---|---|---|---|
| Documentation-like paths | N/A — no file classification | — | — |
| Git repository selection | N/A — `--target` via existing `resolve_target` | — | — |
| Commit state | N/A — no VCS automation | — | — |
| Push state | N/A — no VCS automation | — | — |
| **Composed commands** | **Applicable** — derived text into a runnable string | Single `shlex.quote` path; no naive interpolation | Apostrophe-bearing text executed as subprocess at all publication points |

## Migration / Rollout

No data migration. Documentation rows land in the same commit as the keys, or the rosters
stay red.

## Open Questions

- [ ] Does a `piloted` fixture satisfying all seven non-downgrade conditions exist? If not, delete the point.
- [ ] Live findings cardinality for `localRemediesNotWritten` — measure before apply.

## Citation Check

Every symbol above was re-located by name in the source this phase (`grep`), not inherited:
`cmd_close`, `cmd_settle`, `cmd_probe`, `cmd_verify`, `cmd_offer`, `cmd_discuss`,
`agreements_state`, `prose_state`, `_agreement_collides`, `_settle_discussed_events`,
`probe_state`, `declared_required_scale`, `ACTION_IDS`, `returned_keys`,
`VerifyStatusRosterTests`, `ProbeReportedFactsRosterTests`,
`test_settle_refuses_collides_unnamed`. `shlex` confirmed absent from the module imports.
Line numbers are deliberately omitted. The suite was not run (no shell in this phase).
