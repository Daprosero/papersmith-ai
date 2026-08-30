# Spec Delta: a-pilot-is-the-whole-flow-validated

Change: `a-pilot-is-the-whole-flow-validated` · Capabilities: `agreement-witness`, `close-refusal-symmetry` (`.claude/skills/proposal-implementation/scripts/implementation_cli.py`, `.claude/skills/_core/implementation/impl_position.py`, `.claude/skills/_core/implementation/impl_availability.py`) · Store: hybrid (Engram primary, mirrored here).

No prior spec exists for either capability in `openspec/specs/` (it does not exist in this repository), so every requirement below is ADDED and self-contained.

**Terminology.** A **witness** names one `test_<id>` in the declared-invariants suite. The **three states** are `unwitnessed` (no witness declared — reported, never a failure), `unmeasured` (a witness is declared but this run could not evaluate it), `disagrees` (declared, evaluated, contradicts the tick — this is the only state that gates). A **decision point** is a write command; `close` is the only decision point this change gates. `verify`/`probe` are reads and never refuse.

**Corrected evidence** (the proposal's inherited "~86%/~14%" is superseded by direct measurement of all 99 ticked agreements in `implementations/Domain_Adaptation/MIL-CREDA/AGREED.md`): the real split is **~95 witnessable, ~4 irreducible**. The target already ships 296 `test_<id>` functions and 32 declared invariants across 10 modules of `src/MIL_CREDA/`, but those 32 cover the method's mathematics, not the benchmark's protocol the agreements state — the two sets do not overlap, so the retrofit is mostly "bind an agreement to a test that already exists," not "write 95 tests." How many of the ~95 already have a matching test is unmeasured and is **not** established by this change.

---

## Group 1 — The retrofit is one bounded pass, never wired incrementally

### ADDED Requirement: This change MUST NOT touch `AGREED.md`, and retrofitting MUST run as one prior, bounded pass

Wiring an already-settled agreement to a witness MUST NOT happen as a side effect of any flow reaching it. This change MUST leave `implementations/Domain_Adaptation/MIL-CREDA/AGREED.md` byte-identical. Retrofitting the target's existing settled agreements MUST be scoped as a separate target-side pass that completes (or explicitly stops) before any clean-room pilot run begins, never interleaved with in-progress flow work.

#### Scenario: No incremental wiring lands with this change

- GIVEN this change applied
- WHEN `AGREED.md`'s existing lines are inspected
- THEN none SHALL carry a witness token as a side effect of this change
- AND a manifest diff against the pre-change file SHALL be empty.

#### Scenario: The retrofit precedes the pilot

- GIVEN a future target-side retrofit pass
- WHEN it runs
- THEN it SHALL complete or explicitly stop before a clean-room pilot starts
- AND it SHALL NOT be triggered by a flow encountering an unwired agreement mid-run.

---

## Group 2 — `close`/`unbacked` symmetry

### ADDED Requirement: `close` MUST stop hand-rolling the ladder, independent of reachability

`close`'s status derivation MUST route through `impl_availability`'s four-code ladder (`POSITION_ABSENT`/`POSITION_STALE`/`POSITION_UNBACKED`/`POSITION_DISAGREES`) instead of a hand-rolled three-code subset. This duplication fix MUST land regardless of whether `POSITION_UNBACKED` proves reachable at `close`. The existing regression test pinning the ladder's call count at exactly two callers (`gate`, `offer`) MUST be updated to the new count once `close` becomes a third caller.

#### Scenario: Duplication removed unconditionally

- GIVEN `close`'s status derivation after this change
- WHEN its source is read
- THEN it SHALL contain no independent three-code branch
- AND it SHALL call the shared ladder function.

#### Scenario: The pinned call count is updated, not left stale

- GIVEN the existing test asserting the ladder function is called exactly twice
- WHEN `close` becomes a third caller
- THEN that test SHALL assert the new count
- AND SHALL fail if left asserting two.

### ADDED Requirement: `close` MUST refuse `POSITION_UNBACKED` only if reachability is proven by execution

The reachability of an unbacked tick at `close` MUST be proven or disproven by an executed construction, and the result MUST be recorded regardless of outcome. IF a state is constructed where a ticked item's witness cannot be measured at all (`unbacked` non-empty, `disagreements` empty), `close` MUST succeed on that state before the fix and refuse `POSITION_UNBACKED` on the identical state after it. IF no such state is constructible, `close` MUST NOT gain a `POSITION_UNBACKED` refusal branch, and the record MUST state the branch is unreachable rather than shipping a guard nothing can fire.

#### Scenario: Reachable

- GIVEN a constructed unbacked-at-close state
- WHEN `close` runs pre-fix
- THEN it SHALL succeed
- WHEN `close` runs post-fix on the same state
- THEN it SHALL refuse, naming `POSITION_UNBACKED`.

#### Scenario: Unreachable

- GIVEN no unbacked-at-close state is constructible by execution
- WHEN the change is delivered
- THEN no `POSITION_UNBACKED` refusal branch SHALL be added to `close`
- AND the change's record SHALL state the branch is unreachable.

---

## Group 3 — Witness persistence (existing instances and new grammar)

### ADDED Requirement: `AGREEMENT_LINE` MUST gain an optional trailing witness token; bare lines MUST parse byte-identically

The grammar MUST add an optional trailing witness token scoped strictly to the existing `test_<id>` pattern. A bare `- [ ] <text>` line, with or without a mark, MUST parse identically to today.

#### Scenario: A pre-existing bare line is untouched

- GIVEN an `AGREED.md` line written before this grammar existed, carrying no witness token
- WHEN `agreements_state` parses it after this change
- THEN it SHALL parse to the same `mark`/`text` as before
- AND it SHALL report state `unwitnessed`, never invalid, never edited to add a token.

#### Scenario: A witness token round-trips

- GIVEN a line carrying a valid witness token
- WHEN it is written and re-parsed
- THEN `mark`, `text`, and the witness SHALL all be recovered unchanged.

### ADDED Requirement: `settle --about <witness>` MUST persist its binding into the agreement line

`settle --about` currently uses the witness only for the collision search, records it solely in `.implementation/position.jsonl`, and discards it from the artifact. It MUST instead write the binding into the `AGREED.md` line, and `agreements_state` MUST read it back exposing witness per item.

#### Scenario: The binding survives the write

- GIVEN `settle --about test_<id>` on an item
- WHEN `AGREED.md` is re-read
- THEN that item's witness SHALL equal `test_<id>`
- AND SHALL be recoverable by `agreements_state` without consulting the ledger.

### ADDED Requirement: `verify` MUST report the three witness states as distinct counts

`verify` MUST grow an agreement-level dimension reporting `unwitnessed`, `unmeasured`, and `disagrees` as three separate counts; none MUST fold into another. A prose-only agreement MUST always appear by its exact text under `unwitnessed` and MUST NEVER be counted in a passed total.

#### Scenario: A contradicting witness is isolated

- GIVEN an agreement whose declared witness test fails in the externally-run suite
- WHEN `verify` runs
- THEN it SHALL count that item under `disagrees` only.

#### Scenario: A prose-only item is never silently passed

- GIVEN an irreducible prose agreement with no nameable artifact
- WHEN `verify` runs
- THEN it SHALL print the item by exact text under `unwitnessed`
- AND it SHALL NOT appear in any passed count.

### ADDED Requirement: Gating stays at `close`; `verify`/`probe` MUST never refuse

`close` MUST refuse when any agreement's witness state is `disagrees`. `verify` and `probe` MUST report all three states and MUST NOT exit non-zero or refuse on any of them.

#### Scenario: `close` refuses on disagreement

- GIVEN an agreement in state `disagrees`
- WHEN `close` runs
- THEN it SHALL refuse and name the disagreeing agreement.

#### Scenario: `verify` reports without gating

- GIVEN the same disagreeing agreement
- WHEN `verify` runs
- THEN it SHALL report `disagrees` for that item
- AND SHALL exit zero.

---

## Group 4 — `verify` MUST announce the witness count from day one

### ADDED Requirement: The witnessed count MUST be printed on every run, including zero

`verify`'s agreement dimension MUST print an explicit "N of M witnessed" line on every run, including a target with zero witnesses declared anywhere. Silence MUST NOT stand in for "no witnesses exist."

#### Scenario: Zero witnesses is still announced

- GIVEN a target where no agreement carries a witness token
- WHEN `verify` runs
- THEN output SHALL contain an explicit "0 of M witnessed" line, not an omitted dimension.

#### Scenario: The count matches the parsed state

- GIVEN a target with some declared witnesses
- WHEN `verify` runs
- THEN the printed count SHALL equal the number of agreements whose state is not `unwitnessed`.

---

## Group 5 — The witness token has exactly one write path

### ADDED Requirement: `settle --about` MUST be the only command that writes a witness token

The CLI MUST expose no separate edit or patch command for the witness segment of an agreement line. Documentation MUST state that manually typing a witness token into `AGREED.md` is unsupported, because the parser cannot and MUST NOT distinguish a skill-written token from a hand-typed one — provenance is a documentation guarantee, not a parsed fact.

#### Scenario: One write path exists

- GIVEN the CLI's full command surface
- WHEN it is enumerated
- THEN `settle --about` SHALL be the only command that writes a witness token.

#### Scenario: A hand-edited token is evaluated, not silently trusted or rejected

- GIVEN an operator manually inserts a syntactically valid witness token
- WHEN `verify` runs
- THEN it SHALL evaluate that token exactly as it would a skill-written one
- AND doctrine SHALL name this as the reason hand-editing is unsupported, never claim technical prevention that does not exist.

---

## Cross-cutting requirements

### ADDED Requirement: `FORGE_VOCABULARY_FLOOR` MUST match on a word boundary; `FORGE_LEXICON` rule B MUST be run, not declared

Verification of this change's own shipped `.md`/`.py` files MUST use a word-boundary regex for `FORGE_VOCABULARY_FLOOR`, not a bare substring match. `FORGE_LEXICON` rule B — deriving the forbidden lexicon from the target's live module basenames — MUST actually execute against the target's current module set as part of this change's verification, not be asserted from a stale or hard-coded list.

#### Scenario: A containing word is not a false violation

- GIVEN a shipped file containing a word that merely contains the forbidden substring
- WHEN `FORGE_VOCABULARY_FLOOR` runs with word-boundary matching
- THEN it SHALL NOT report a violation for that word.

#### Scenario: Rule B is executed, not assumed

- GIVEN the target's current module basenames under `src/MIL_CREDA/`
- WHEN `FORGE_LEXICON` rule B runs as part of this change's verification
- THEN it SHALL derive the forbidden set from those live basenames
- AND SHALL report zero violations across shipped skill files.

### ADDED Requirement: Every new lock MUST be proven reachable-red

Under this project's `strict_tdd` setting, every lock that passes on its first run MUST be proven reachable-red by inversion, restored by inverse patch, and confirmed by content comparison.

#### Scenario: A lock's reachable-red proof

- GIVEN a new lock that passes on first run
- WHEN the fact it guards is inverted
- THEN the lock SHALL fail
- AND restoring by inverse patch SHALL return it to green with no other file altered.

---

## Explicit non-goals

| Non-goal | Reason |
|---|---|
| Retrofitting the target's already-settled agreements | Decided as a separate, prior, bounded target-side pass (Group 1) |
| Measuring how many of the ~95 witnessable agreements already have a matching test | First task of that separate retrofit pass, not this forge-side change |
| Full static agreement↔code cross-reference | Duplicates provenance machinery this codebase already refuses to duplicate |
| Any new `WITNESS_KINDS` member (field- or constant-witnesses) | Out of scope; only the existing `test_<id>` pattern is reused |
| Gating on `verify` or `probe` | Gating stays at `close` only, by this codebase's own convention |

## Acceptance

- The reachability of `POSITION_UNBACKED` at `close` is proven or disproven by execution; the result is recorded either way; `close`'s ladder duplication is removed regardless of that result.
- `settle --about <witness>` writes a binding that survives into `AGREED.md` and is read back by `agreements_state`; bare pre-existing lines remain valid and report `unwitnessed`.
- `verify` prints `unwitnessed`/`unmeasured`/`disagrees` as three distinct counts on every run, including "0 of M witnessed" on a target with no witnesses.
- `close` refuses only on `disagrees`; `verify`/`probe` never refuse.
- `settle --about` is the only command that writes a witness token; no other CLI surface edits one.
- `FORGE_VOCABULARY_FLOOR` matches on a word boundary and reports zero violations across shipped skill files; `FORGE_LEXICON` rule B is executed against the target's live module basenames.
- `AGREED.md` is byte-identical before and after this change; the retrofit is not part of it.
