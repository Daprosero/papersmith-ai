# Tasks: The Pilot Proves the Science

Precedence honored: design → spec → proposal → explore. Two commits on one branch, **B
before A**, one merge — the owner's decision, restated here because every phase boundary in
this checklist depends on it. Each commit must leave both suites green on its own: no commit
exists where the lock (slice A's gate) has no key (slice B's witness). `strict_tdd: true` —
every lock RED first, `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` purged before each reachable-
red run. No task writes under `implementations/`.

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | Slice B ≈ 850–890; Slice A ≈ 425–465; combined ≈ 1275–1355 |
| 1400-line budget risk | Medium — forecast sits under budget, but this file's own docstring density (verified: single functions with 60–110-line docstrings, e.g. `_skipped_rung_detail`, `undeclared_ladder_state`) means the real diff could run higher than any line-count model predicts from logic alone. Owner has already accepted growth past 1400 if it happens. |
| Chained commits recommended | Yes — two commits, one branch, one merge (owner's decision, not proposed here) |
| Suggested split | Commit 1 = Slice B (~850–890 lines); Commit 2 = Slice A (~425–465 lines), based on commit 1 |
| Delivery strategy | ask-on-risk |

### Suggested Work Units

| Unit | Goal | Commit | Focused test command | Trap(s) covered |
|---|---|---|---|---|
| B1–B8 | Slice B: the addressable witness (`__records__`, `_record_scale_level` refactor, `POSITION_RECORD_UNKNOWN`, `undeclaredRecords`) | Commit 1 (base: main) | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v` + `npm test` | 1, 4 |
| A1–A5 | Slice A: the gate (`launch_available` rung threshold, `RUNG_NOT_ATTAINED`) | Commit 2 (base: commit 1) | same two commands | 2, 3, 5 |

## Phase 0 — Baseline (non-negotiable, before the first RED)

- [x] 0.1 Measure both baselines on `main` at `f3517e8` before touching anything:
      `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests` (expect
      **2201 OK, skipped=3**) and `npm test` (expect **385/385**). No phase before this one
      ran a suite — exploration, proposal, spec and design all read source only, per design's
      own Open Questions. Record the exact output. A baseline taken after RED work begins
      cannot separate a pre-existing failure from one this change caused.
      **Depends on**: nothing. **Blocks**: every task below.

## Phase 1 — Slice B: the addressable witness (Commit 1)

Dependency shape measured directly from `implementation_cli.py`, not assumed from the design's
File Changes table:

- **B1, B2, B3 are mutually independent** — no shared logic, safe to sequence in any order
  (or split across writers if the shared-file conflict below is managed).
- **B4 depends on B3** (new `_record_scale_level` signature) — not on B1.
- **B5 depends on B4 and B1** (needs both the deriver's expected `evidence["records"]` shape
  and the resolver that fills it at each call site).
- **B6 and B7 depend on B1 only** — verified: `_record_operand_detail`'s natural insertion
  point in `cmd_position` sits *before* `evidence = _position_write_evidence(...)` is even
  built (between the existing `POSITION_LEVELS_UNDECLARED` check and that evidence build), so
  it needs only `items` and `resolve_records_declaration(...)` — not the arithmetic (B3/B4) or
  the evidence wiring (B5) at all. Same for `undeclared_records_state`, which mirrors
  `undeclared_ladder_state`'s shape (`target`, `name`, `records` only).
- **B8 depends on everything above** (a regression proof over the finished slice).

Caveat: B1/B3/B5/B6/B7 all touch `implementation_cli.py` and the single shared test file, so
literal simultaneous multi-writer authorship would just recreate merge conflicts even where
the logic above is independent. Recommend one writer working this dependency order
sequentially; the parallel marks below describe logical independence, not concurrent editing.

- [x] **B1 — Declaration surface** (design D1). `RECORDS_DECLARATION = "__records__"` +
      `resolve_records_declaration(target, name) -> dict`, mirroring `resolve_steps_declaration`
      exactly: `__init__.py` then `config.py`, `ast`-only, first file that answers wins,
      non-dict reads `{}`. Unit tests mirror `resolve_steps_declaration`'s own class (malformed
      value, missing bench root, `__init__.py`-wins-over-`config.py` precedence). Satisfies
      spec "`__records__` declaration". **∥ with B2, B3.** ~90 lines.
- [x] **B2 — Kit stub**. `assets/kit/src_benchmark/__init__.py` gains
      `__records__: dict = {}` plus a commented example — no entry name invented, mirroring
      `__levels__`'s `[]` stub exactly. Confirm no kit-materialization golden test needs a
      matching update beyond the stub's own presence. Satisfies spec "kit ships an empty stub
      only". **∥ with B1, B3.** ~20 lines.
- [x] **B3 — `_record_scale_level` signature refactor** (design D2/D3). Change
      `_record_scale_level(evidence, levels)` (reads `evidence["search"]`/
      `evidence["requiredScale"]` internally) to
      `_record_scale_level(record, required_scale, levels, *, measured_by)` — three explicit
      bindings, one arithmetic body, unchanged. Update the two existing call sites
      (`derive`'s bare/no-operand `@record:level` branch, `_derive_notebook_level`) to pass
      `evidence.get("search")`, `evidence.get("requiredScale")` and their own `measured_by`
      strings, so both stay **byte-identical** in behavior. Required mutation: swap which
      `measured_by` string binds to which call site and confirm a test catches it (a weaker
      lock — asserting only the returned rung, not `measured_by` — would survive that swap).
      **∥ with B1, B2.** ~100 lines.
- [x] **B4 — `_derive_record_level` + `derive()`'s record-branch routing** (design D2, spec
      "leveled derivation via existing arithmetic"). New `_derive_record_level(evidence,
      operand, levels)`, and `derive()`'s `kind == "record"` leveled branch now checks whether
      `operand` names an entry in `evidence.get("records", {})`: named → route through
      `_derive_record_level` (which resolves that entry's own found/scale state and calls the
      refactored `_record_scale_level`); unnamed/absent → unchanged fallthrough to the
      search-block default (byte-identical to today, satisfying "existing instances keep
      working"). A name absent from a declared `__records__` MUST derive `None`, never `False`
      (spec requirement, tested explicitly). **Depends on B3.** ~130 lines.
- [x] **B5 — `named_records_state` + evidence wiring, proved at all three sites** (design D4;
      constraint "Evidence wiring is three sites"). New `named_records_state(target, name,
      records, digest) -> dict` assembling `{name: {recordFound, recordCurrent,
      scaleSatisfied, requiredScale}}`, reusing `_record_scale`/`_scale_satisfied`/
      `_record_current` (no deriver opens a file — doctrine). Wire `evidence["records"]` at
      **all three** evidence builders: `_position_write_evidence`, `cmd_probe`'s inline dict,
      `cmd_verify`'s inline dict. Write one integration test that **proves** all three agree on
      `records` for an identical target state — not three separate assertions that happen to
      pass, one shared fixture read through all three builders. This is the exact defect class
      the design names: wiring only the shared helper previously left `probe`/`verify` saying
      `unmeasured` while `gate` said satisfied for `@shard`; do not repeat it for `@record`.
      **Depends on B4, B1.** ~190 lines.
- [x] **B6 — Trap 1: `POSITION_RECORD_UNKNOWN`, ordering, classification, roster** (design
      D5/D6; spec "`@record:level <name>` grammar" is unaffected, this is the operand-validity
      refusal). `_record_operand_detail(items, records) -> str | None`, mirroring
      `_step_operand_detail`'s shape (returns detail, caller raises). `raise
      Refused("POSITION_RECORD_UNKNOWN", ...)` inserted in `cmd_position`, **verified
      placement**: after the existing `POSITION_LEVELS_UNDECLARED` check, before
      `_skipped_rung_detail` is called — not after it, and not mirroring `@step`'s own
      position (which comes after `_skipped_rung_detail`). **Required RED proof, exact
      mutation named in the brief**: a fixture at `--target-level` equal to `levels[0]` (the
      floor) must survive the check being moved to the `@step` position (after
      `_skipped_rung_detail`); a fixture above the floor must NOT survive it — that is the
      mutation that proves the ordering claim, not merely that the code exists. Reason stated
      in the design: an unknown record name derives `None`, which sinks `attained_level`, so
      placed after `_skipped_rung_detail`, `POSITION_RUNG_SKIPPED` fires first and
      `POSITION_RECORD_UNKNOWN` becomes unreachable above the floor. Classify
      `POSITION_RECORD_UNKNOWN` as `WORK_STATE` in `GATING_REFUSALS`, add a resolution builder
      in `_WORK_STATE_RESOLUTIONS` (names the fact "declare the record", never invents a
      record name). Roster bookkeeping for this slice: `GATING_REFUSALS` moves 66 → 67;
      `SKILL.md` L2333 ("Sixty-six" → "Sixty-seven"), L2342/L2346 (34/32 → 34/33 — the new
      code is `WORK_STATE`, invocation-defect count unchanged); `references/usage.md`
      L1832/L1837 same split; rename
      `test_the_derivation_finds_the_measured_sixty_six` →
      `..._sixty_seven`, update its docstring and its `assertEqual(..., 67)`. `_ENGLISH_COUNTS`
      needs no change here — `67` already exists in the table (verified directly: 57, 63, 64,
      65, 66, 67 present; only `68` is missing, and that gap belongs to Slice A). **Depends on
      B1 only. ∥ with B4/B5 once B1 lands.** ~170 lines.
- [x] **B7 — Trap 4: `undeclaredRecords`, verify key, docs** (design D8; spec "absence is
      reported, never refused" + "from-zero"). `undeclared_records_state(target, name,
      records) -> dict | None`, mirroring `undeclared_ladder_state`'s shape and placement
      (top-level in `cmd_verify`'s return — `returned_keys` reads top-level dict literals
      only, nested ships invisible). Wire `"undeclaredRecords": undeclared_records_state(...)`
      into `cmd_verify`. Add a `SKILL.md` Output-Contract table row for `undeclaredRecords`
      (`VerifyStatusRosterTests` derives `cmd_verify`'s keys and cross-checks this table; slice
      B is red without the row — confirmed directly by reading `test_the_contract_names_every_
      status_verify_reports`). **Additional finding beyond the design's own File Changes
      table**: `SKILL.md` L2120's sentence "There are seventeen of them" is bound by a
      separate test (`test_the_contract_counts_the_statuses_it_lists`, confirmed by direct
      read) and must bump to "eighteen" in this same task — the design's "Measured facts"
      list named the row requirement but not this separate count sentence. Two scenarios from
      the spec need direct tests: absent declaration + no witness referencing it; absent
      declaration + a witness naming one (the witness itself derives `None`, `verify` still
      refuses nothing). **Depends on B1 only. ∥ with B4/B5/B6.** ~150 lines.
- [x] **B8 — Existing instances keep working (regression proof)**. A target with no
      `__records__` and a position block written before this change must keep deriving
      `@shard:level`, `@notebook:level` and bare `@record` exactly as before, and `verify` must
      report (never refuse) on such a target. One dedicated test fixture, not folded into B4's
      or B7's own tests, so this claim has its own named, traceable proof. **Depends on
      B1–B7.** ~40 lines.
- [x] **B9 — Slice B closeout**. Full suite run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m
      unittest discover -s tests -p 'test_*.py'` and `npm test`, both green, counts compared
      against Phase 0's baseline (net +N Python tests, node suite unaffected). Commit. This is
      the owner's non-negotiable "no commit exists where the lock has no key" — but slice B
      alone adds no lock, it is purely additive, so this checkpoint only confirms nothing
      regressed. **Depends on B1–B8.**

## Phase 2 — Slice A: the gate (Commit 2, base: Commit 1)

Dependency shape:

- **A1** has no dependency within this slice (pure `impl_availability.py` + its own unit
  tests), but per the owner's ordering, does not start until Commit 1 (Slice B) is merged.
- **A2 depends on A1** (new required kwargs must exist before callers can pass them).
- **A3 depends on A1, A2** (the code must actually be raised in `cmd_gate` before it can be
  classified in the roster).
- **A4 depends on A3**; **A5 depends on A4** — both edit the same roster-count test region
  (`test_the_doctrine_states_the_split_the_roster_actually_holds`), so treat as sequential in
  practice even though A5's fix (the assertion shape) is logically independent of A4's number.

- [x] **A1 — `launch_available` signature + `RUNG_NOT_ATTAINED`, checked last** (design D7;
      spec "accepts rung facts", "checked last", "rung threshold", "reachability
      preconditions", "vacuous attainment unchanged"). Add required kwargs `levels: list[str]`,
      `attained_level: str | None`. New check, ordered strictly after every existing one
      (`position_honest`'s five codes, `NOT_READY`, `SEQUENCE_NOT_REACHED`): when
      `len(levels) >= 2`, refuse `RUNG_NOT_ATTAINED` unless `attained_level`'s index is
      `>= len(levels) - 2`; when `len(levels) < 2`, structurally unreachable. Tests: threshold
      at 1/2/3-rung ladders and at `attained_level is None`; the 2-rung-floor-sufficient
      scenario (`levels[-2]` **is** the floor there, not exempt); vacuous-ladder doctrine
      unchanged (zero leveled items still attains the top trivially — this task adds no check
      there, only asserts the existing behavior survives). Required mutation lock: "an existing
      refusal keeps its code" — a call that today refuses `NOT_READY` must still refuse
      `NOT_READY` once `levels`/`attained_level` are supplied, proving the new check truly runs
      last and cannot move an earlier verdict. **∥ with nothing (foundational for this
      slice).** ~160 lines.
- [x] **A2 — Caller wiring**. Both callers already compute `position_state(...)` and discard
      `attainedLevel` — thread it through unchanged, never recomputed. `cmd_gate` gets a new
      explicit `if code == "RUNG_NOT_ATTAINED":` branch (verified: `cmd_gate`'s verdict-code
      dispatch, lines ~9319–9408, is a chain of explicit per-code `if` blocks, not a generic
      passthrough — the new code needs its own block mirroring the existing seven, raising
      `Refused("RUNG_NOT_ATTAINED", ...)`). `_offer_launch_action` needs **no logic change at
      all** — verified directly: its `if not verdict["available"]: return None` (line ~9565)
      already covers any new refusal code generically, so silent omission is preserved by
      construction, not by a new branch; only the two new kwargs need threading into its own
      `launch_available(...)` call. Test: one shared fixture, both callers, `cmd_gate` raises
      loudly and `_offer_launch_action` returns `None` on identical facts. **Depends on A1.**
      ~80 lines.
- [x] **A3 — Trap 5: `RUNG_NOT_ATTAINED` classification + resolution + deliberate
      reachability test**. Classify `WORK_STATE` in `GATING_REFUSALS`; resolution builder in
      `_WORK_STATE_RESOLUTIONS` names the next rung to attain, read from the target's own
      `__levels__` at refusal time, never inventing one. **The reachability nuance the brief
      names, confirmed by direct read of `cmd_gate`**: `GATE_AUTHORIZATION_REQUIRED` (token
      *presence*, line ~9292) is checked *before* `launch_available` runs (line ~9314);
      `_verify_gate_authorization` (token *validity*) runs last, "immediately before the
      record is appended" per `cmd_gate`'s own docstring. So a test reaches
      `RUNG_NOT_ATTAINED` with any non-empty `--authorization` string; in production it is
      reachable only on the regressed-evidence path (`offer` minted a token when attainment
      was sufficient, then attainment fell before `gate` ran). The test for this task MUST
      construct that state deliberately — mint via a fixture, then regress attainment, then
      gate — rather than assume the ordinary flow reaches it. **Depends on A1, A2.** ~100
      lines.
- [x] **A4 — Trap 2: `_ENGLISH_COUNTS` extension to 68 + roster count bump 67 → 68**.
      `_ENGLISH_COUNTS[68] = "Sixty-eight"` (confirmed by direct read: the table currently
      tops out at 67; `_english_count` raises `AssertionError` by design rather than silently
      widening, so this task is red without the entry). `SKILL.md` L2333/L2342/L2346 and
      `usage.md` L1832/L1837 move to 68/34/34 (invocation-defect count unchanged at 34,
      work-state moves 33 → 34). Rename
      `test_the_derivation_finds_the_measured_sixty_seven` → `..._sixty_eight`
      (already renamed once in B6; renamed a second time here), update docstring and
      `assertEqual(..., 68)`. **Depends on A3.** ~55 lines.
- [x] **A5 — Trap 3: strengthen the degenerating split assertion**. After A4, both roster
      counts read 34 (invocation) and 34 (work-state) — confirmed the collision is real: once
      equal, `test_the_doctrine_states_the_split_the_roster_actually_holds`'s
      `for count in set(counts.values())` collapses to one element (`{34}`), so a stale
      work-state sentence left in `usage.md` would pass green. Fix: replace the `set(...)`
      loop with two explicit per-kind assertions (`counts[impl.INVOCATION_DEFECT]`,
      `counts[impl.WORK_STATE]`), each checked against its own sentence in `usage.md`.
      **Required mutation proof, named in the brief**: leave a stale work-state count in
      `usage.md` (e.g. revert only that one number to 33) and confirm the strengthened test
      falls — proving the fix actually closes the gap, not merely that the assertion shape
      changed. **Depends on A4.** ~70 lines.
- [x] **A6 — Slice A closeout**. Full suite run, both green, counts compared against Slice B's
      close-out baseline (Phase 1 / B9) plus this slice's net additions. Merge to `main`.
      **Depends on A1–A5.**

## Non-Goals — the target's own contract (described, never scheduled)

Per the proposal's own "The contract the target must then meet": once `__records__` exists,
`implementations/Domain_Adaptation`'s own commit — its own session, never this change's —
must (1) declare `__records__` naming a record per leveled witness that will address one, (2)
verify each declared path against disk after a real run, (3) rewrite position items 4 and 5's
witnesses from `@shard:level`/`@notebook:level` to `@record:level <name>`, (4) re-derive the
block so header and marks rebind, (5) land as its own commit. No task above writes under
`implementations/`, touches `AGREED.md`, or invents a record name on the target's behalf — the
kit stub (B2) ships empty for the identical reason `__levels__`'s stub stays `[]`.

## Recorded, not fixed here (follow-on, out of scope)

`_record_scale_level` reads no currency at all (confirmed: neither the pre-refactor nor the
post-refactor signature takes a `currentWhen`/`recordCurrent`-style freshness argument), so
every leveled record rung stays currency-blind while the two-state `_derive_record` checks
`recordCurrent`. Inherited, not caused by this change. `__records__`'s shape is fixed at
`{path, requiredScale}`; a third key would be new surface area — do not widen this change to
add one.

## DoD (both commits)

`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` and
`npm test` both green at every commit boundary; `__pycache__` under
`.claude/skills/_core/implementation/` purged before each reachable-red run (same-size,
same-mtime edits reuse a stale `.pyc` and a dead lock reads as live). Every lock names the
mutation that proves it, and the mutation chosen is one a **weaker** lock would survive.
