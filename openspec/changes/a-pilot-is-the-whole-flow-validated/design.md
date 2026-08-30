# Design: a-pilot-is-the-whole-flow-validated

Store: hybrid (Engram `sdd/a-pilot-is-the-whole-flow-validated/design`, mirrored here). Implements `openspec/changes/a-pilot-is-the-whole-flow-validated/spec.md`.

**Citations checked.** Every symbol below was re-located by name in the source during this phase, not inherited. Three inherited claims were corrected and are marked `[CORRECTED]`.

---

## Technical Approach

Two independent slices over the same three modules. Slice A removes `cmd_close`'s hand-rolled status ladder and adds the refusal the ladder already knows; Slice B adds a per-agreement witness that survives into the artifact and a three-state read of it. Slice A is deliverable and revertible alone; Slice B targets Slice A's branch.

---

## D1 — `POSITION_UNBACKED` at `close` is REACHABLE, and the construction needs no hand edit

Reachability is settled by reading the two functions that produce the state. It is still owed an executed proof (task, not assumption), but the construction is no longer a search.

`_position_write_evidence(target, name)` takes `shards_root` as a third argument that only `position` ever supplies — its own docstring states `discuss`, `gate` and `close` declare no `--shards` flag, and `cmd_close` calls it with two arguments. So at `close`, `shardsArrived is None`. `impl_position._derive_shard` returns `(None, ...)` whenever `arrived is None`. `impl_position.derive` then sets `satisfied = None`, and `unbacked = satisfied is None and item["mark"] == "x"`.

**Construction R (primary, no destruction, no hand edit):**

| Step | Command | Result |
|---|---|---|
| 1 | position block holds a `@shard <id>` item; the shard has arrived and is current | — |
| 2 | `position --shards <root>` | `_derive_shard` → `True` → refresh writes `[x]` |
| 3 | `close` (no `--shards` exists on it) | `_derive_shard` → `None` → `unbacked` non-empty, `disagreements` empty |
| 4 | today | `cmd_close` tests `before["status"]` and `before["disagreements"]` only → **succeeds** |
| 5 | after the fix | refuses `POSITION_UNBACKED` |

The same state makes `cmd_gate` refuse `POSITION_UNBACKED` already, so one fixture exhibits the asymmetry through two commands.

**Construction N (fallback):** tick a `@notebook <path>` item, then remove the notebook file. `_derive_notebook` returns `None` when no report matches the operand. This is materially different from clearing a notebook's outputs, which yields `sourcesMatch: False` — a definite `False` → `disagrees`, exactly as already measured on the reference target.

`[CORRECTED]` The proposal's lead — `cmd_close`'s refresh and the never-re-checked `after` — is **not needed and is not the path**. The unbacked tick is present in `before`, which `close` already reads. `cmd_position`'s refresh loop `continue`s on `result["derived"] is None`, leaving the mark untouched; its own comment says a refresh "corrects a contradicted mark and leaves an unbacked one exactly where it was." The `after` state is therefore identical, not newly created. `cmd_close`'s docstring claim that the refresh "can only ever ADD ticks" is true only because the disagreement check precedes it — the loop does write `" "` for a measured-and-unsatisfied item. Worth a docstring correction in the same slice.

**Consequence:** the `POSITION_UNBACKED` refusal branch ships. The spec's "Unreachable" scenario does not fire.

---

## D2 — Extract the honesty prefix; do not call `launch_available` from `close`

| Option | Tradeoff | Decision |
|---|---|---|
| `close` calls `launch_available` with sentinel `ready`/`job` | Reaches `NOT_READY`/`SEQUENCE_NOT_REACHED`, codes `close` must then discard; the module's own docstring warns that a `False` where a `None` belongs silently widens the rule | Rejected |
| A fourth hand-written branch in `cmd_close` | The duplication the spec forbids | Rejected |
| Extract `impl_availability.position_honest(*, status, unbacked, disagreements)` returning `{"honest", "code", "facts"}`; `launch_available` calls it first, then continues | One rule, one order, two questions; `gate`/`offer` answers cannot move because the first four checks are the same code in the same order | **Chosen** |

`close` raises its own prose for each code, as `cmd_gate` already does — `impl_availability`'s docstring forbids the module composing a caller's sentence.

---

## D3 — The pinned count becomes a named call-site set

`tests/test_proposal_implementation.py::test_gate_and_offer_call_the_identical_shared_availability_symbol` asserts `source.count("impl_availability.launch_available(") == 2`. A literal count passes if both calls move into one function, or into the wrong ones; it proves less than it appears to.

**Chosen:** replace the count with an `ast` walk of the CLI that maps each call to `impl_availability.*` to its enclosing function, asserting exactly `{"cmd_gate", "_offer_launch_action"}` for `launch_available` and `{"cmd_gate", "cmd_close"}`— via `launch_available` and directly — for `position_honest`'s CLI-side call sites. Its reachable-red is free: before `cmd_close` routes through the ladder, `cmd_close` is absent from the set. A docstring mention cannot satisfy an AST walk, which the substring count could.

---

## D4 — The agreement-line grammar

```
AGREEMENT_LINE = ^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)(?:\s+`(?P<witness>test_[A-Za-z0-9_]+)`)?\s*$
```

Backticked and end-anchored, mirroring `impl_position.WITNESS_RE`'s own convention. It names `test_<id>` directly and therefore adds no `WITNESS_KINDS` member — `WITNESS_KINDS` is `{record, notebook, rehearsal, shard}` and is read only by the position grammar and `_resolve_discuss_about`.

**Byte preservation** rests on two facts, one structural and one measured:
- The position block's own item lines are excised by `_agreement_scan_text` before either `agreements_state` or `_agreement_collides` sees a line, so this grammar never touches them.
- A pre-existing bare line whose text already ENDS in a backticked `test_...` would silently re-parse with shortened `text`. **This must be measured, not assumed**, by scanning every holder markdown under the reference target before the grammar lands. Non-zero hits switch the token to the HTML-comment form `<!-- witness: test_<id> -->`, which cannot collide with prose.

---

## D5 — `settle --about test_<id>` is not implementable; the flag is `--witness`

`[CORRECTED]` `_resolve_discuss_about` accepts an ordinal or `kind [operand]` and raises `POSITION_WITNESS_UNKNOWN_KIND` for anything outside `WITNESS_KINDS`. `--about` is the *position* witness identity used for the discussion match and `_agreement_collides`; it cannot carry `test_<id>`.

`cmd_settle` gains one optional `--witness test_<id>`. Its write becomes `- [ ] {text} \`{witness}\`` when given and stays byte-identical to `- [ ] {text}` when omitted. `settle` remains the only command that writes the segment, and no `patch`/`edit` subcommand is added. A lock asserts by AST that the only construction of a witness segment in the CLI is enclosed by `cmd_settle`.

---

## D6 — The three states, from machinery that exists

`[CORRECTED]` The CLI **runs no tests**. `cmd_verify` calls `test_function_names(target / "tests")` (an `ast` walk) and nothing anywhere reads a suite result. The proposal's "did the externally-run suite pass it" is not answerable by this code, and the design says so rather than implying an outcome check.

| State | Rule |
|---|---|
| `unwitnessed` | the line carries no token |
| `unmeasured` | token present, but `tests/` is absent or `unparsable_tests(target / "tests")` is non-empty — the collector silently skips a file that fails `ast.parse`, so "absent" and "unreadable" are genuinely indistinguishable |
| `disagrees` | token present, `tests/` readable and fully parsed, mark is `x`, and `test_<id>` ∉ `test_function_names(...)` |

**One-directional, unlike `derive()`.** An unticked agreement whose test exists is **not** a disagreement. `settle` always writes `[ ]`, and an agreement is ticked by human review, never by evidence; the symmetric rule would flag every freshly settled agreement whose test already exists.

**`__provenance__["invariants"]` is reported, never gating.** `migration_state` requires both `test_<id>` and the declaration; requiring the declaration here would make the agreements permanently disagreeing, because the spec's own measurement says the 32 declared invariants cover the method's mathematics and the agreements cover the benchmark's protocol, with no overlap.

`close` gains `AGREEMENT_DISAGREES`, naming the item by exact text. `verify`/`probe` report and never refuse.

---

## D7 — "N of M witnessed" is a JSON field, not a printed line

`main()` emits `json.dump(result, ...)` and nothing else; a prose line would be a second output shape. The announcement is `agreements.witness.summary: "0 of 108 witnessed"`, present on **every** branch of `agreements_state` including `absent` (`"0 of 0 witnessed"`) — `position_state`'s docstring states the uniform-key-set rule that `returned_keys` enforces.

---

## Data Flow

```
settle --about <kind[ operand]> --witness test_<id>
        │  discussion match (ledger)     └─→ AGREED.md line: - [ ] <text> `test_<id>`
        ↓
agreements_state ──→ per-item {mark, text, witness}
        │                    │
        │                    ├─→ test_function_names / unparsable_tests
        │                    ↓
        │            {unwitnessed | unmeasured | disagrees} + summary
        ├─→ verify  : reports all three, exits 0
        └─→ close   : refuses AGREEMENT_DISAGREES only

position_state ──→ {status, unbacked, disagreements}
        └─→ impl_availability.position_honest ──→ ABSENT|STALE|UNBACKED|DISAGREES
                    ├─→ cmd_close        (new)
                    └─→ launch_available ──→ + NOT_READY|SEQUENCE_NOT_REACHED
                                ├─→ cmd_gate
                                └─→ _offer_launch_action
```

---

## File Changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/_core/implementation/impl_availability.py` | Modify | Extract `position_honest`; `launch_available` delegates to it |
| `.claude/skills/proposal-implementation/scripts/implementation_cli.py` | Modify | `cmd_close` (ladder + `POSITION_UNBACKED` + `AGREEMENT_DISAGREES` + docstring correction); `AGREEMENT_LINE`; `agreements_state`; `cmd_settle` + `--witness` argparse; `cmd_verify` witness dimension |
| `.claude/skills/proposal-implementation/SKILL.md` | Modify | `close` refusal row; `verify` status table row for the witness dimension; the hand-editing doctrine paragraph |
| `.claude/skills/proposal-implementation/references/usage.md` | Modify | Same two refusal sets; the three states |
| `tests/test_proposal_implementation.py` | Modify | Call-site lock (D3); reachability proof; grammar round-trip; three-state coverage; single-write-path lock |
| `tests/test_implementation_core.py` | Modify | `position_honest` unit coverage |
| `implementations/Domain_Adaptation/MIL-CREDA/AGREED.md` | **Not touched** | Byte-identical; the retrofit is a separate prior pass |

---

## What Breaks

**Producers.** `cmd_close`'s three-code branch (replaced). The pinned count test (replaced, D3). The `close` refusal set in `SKILL.md` and `usage.md` (two doctrine tables, held to the code by `returned_keys` + `markdown_table_rows`). `agreements_state`'s key set on **every** branch including `absent`. `cmd_verify`'s top-level keys are held against a `SKILL.md` status table — the witness dimension therefore nests **inside** the existing `agreements` key and adds no top-level key.

**Products** — records already written under the old shape:

| Instance | Verdict |
|---|---|
| `AGREED.md` checklist lines in the reference target (114 raw, ~108 agreements) | Untouched and still valid; all report `unwitnessed`. **At risk only if a line already ends in a backticked `test_...`** — the D4 scan decides, and it is a gating task |
| Position block item lines in the same file | Untouched: excised by `_agreement_scan_text` before this grammar is applied |
| `.implementation/position.jsonl` `settle` events | Older events carry no witness field; readers treat absent as `unwitnessed`. No event is rewritten |
| Archived `verify` JSON | Falls out of domain — these are transient command output, never persisted by this CLI |
| Any other file carrying the agreement-line shape | **None exist.** `AGREEMENTS_GLOB` is `*.md` at the top of one product folder only |

---

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | `position_honest` four-code order; `launch_available` unchanged over all six | `tests/test_implementation_core.py`, table-driven |
| Unit | Grammar: bare line round-trip, witness round-trip, trailing-backtick collision | Isolated fixtures, never the target's own file |
| Integration | Construction R end to end: `position --shards` → `close` succeeds pre-fix, refuses post-fix | Real subprocess against a scratch target |
| Integration | Three states; `verify` exit 0 on `disagrees`; `close` refuses `AGREEMENT_DISAGREES` | Scratch target |
| Structural | Call-site set (D3); single write path; `agreements_state` uniform keys across branches | `ast` over the CLI source |

**Reachable-red under `strict_tdd: true`.** Every lock green on first run is inverted, observed red, restored by inverse patch, and confirmed by content comparison. Two traps are designed against explicitly: (a) never invert with a same-size edit, and (b) run every inversion with `PYTHONDONTWRITEBYTECODE=1` after deleting `__pycache__` under `.claude/skills/_core/implementation/` — `impl_availability` and `impl_position` are imported modules and a stale `.pyc` makes a live lock read dead.

**Cross-cutting.** `FORGE_VOCABULARY_FLOOR` runs with `\b`-anchored matching over this change's shipped `.md`/`.py`; `FORGE_LEXICON` rule B is executed against the target's live module basenames at verification time, never a copied list.

---

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary is added. `cmd_close` already calls `cmd_position` in-process and no new process is spawned. `write_spliced`'s existing compare-and-swap covers the only new write.

---

## Migration / Rollout

No migration. Two chained PRs: Slice A (D1–D3, ~150–250 lines) to the feature branch; Slice B (D4–D7) targeting Slice A's branch. `400-line budget risk: High` for the pair, `Low` for Slice A alone. Rollback: reverting Slice B turns any persisted token into ordinary trailing text under the restored grammar — no target file needs editing.

---

## Open Questions

- [ ] Does any existing agreement line in the reference target's holder markdown already end in a backticked `test_...`? Gates D4's token form. Measured, not estimated, before the grammar lands.
- [ ] Is `AGREEMENT_DISAGREES` the right code spelling, or should it reuse a `POSITION_`-prefixed name? Non-blocking; the refusal itself is decided.
