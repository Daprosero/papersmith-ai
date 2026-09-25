# Proposal: The Holder Each Skill Declares

## Intent

### The problem

`proposal-implementation` and `experimental-implementation` are twins over one
shared engine (`skills/_core/implementation/engine/implementation_engine.py`),
and their launchers are byte-identical. Because `product = target / name`, two
skills invoked with the same `--name` scan the same product folder — and the
checklist holder inside it is resolved **by shape, never by name**
(`implementation_engine.py:381-385`, restated at `:644-646` and `:12090-12092`).
The profiles disagree about how many documents a revision is: `proposal` declares
1, `experimental` declares 2.

The consequence is measured, not hypothetical: a `documents=` header group
written into a shared holder by the two-document profile permanently poisons that
holder for the one-document profile. `cmd_position` refuses
`POSITION_HEADER_DOCUMENT_COUNT_MISMATCH` (`:12126-12133`), the refusal is
classified `WORK_STATE`, and **`--replace` cannot rescue it** — the check runs
inside the holder sweep (`:12093-12134`), before the `--replace` branch at
`:12157-12162` is ever reached. The engine admits the asymmetry in its own
comment at `:12121-12125`: a block with no `documents=` group, read under a
two-document profile, "gets the group added on the next write". One direction
migrates silently; the other is a wall.

### Why now

Nothing in the engine prevents the collision, and nothing in the engine can: the
holder is chosen by a `*.md` glob (`AGREEMENTS_GLOB`, `:293`) plus an
item-holding test. The filename is the one piece of the domain the profile seam
never took ownership of, while every neighbouring value did — `kit.root`,
`cli.path`, `objective`, `documents[N].directory`, `documents[N].block_locator`.
The residue shows: `AGREED.md` is named in engine prose **15 times**
(`implementation_engine.py`) plus **3 times** in `impl_position.py`, including
four docstrings that assert the holder *is* `<Name>/AGREED.md` as fact (`:575`,
`:12005`, `:18946`, `:18992`) while the code beneath them resolves by shape and
would happily pick `TASKS.md`. That is the documented shape of a defect this
project has already named twice — prose that outlived its mechanism, and a rule
living in prose with nothing to hold it.

### What success looks like

- Each skill declares its own holder filename in its own `PROFILE`; the engine
  hardcodes none and defaults to none.
- The two skills can never land in the same holder, so the poisoning path is
  structurally closed rather than guarded.
- A target that was adopted with its own arbitrarily-named checklist is still
  **found and read** — the concern the by-shape doctrine was written to protect
  is preserved verbatim.
- No target's existing checklist is ever forked into two files, and no
  ambiguous situation is resolved by a guess.

## Scope

### In Scope

1. **An 8th `PROFILE` key: the declared holder.** A required leaf (name, plus
   the heading scaffold a created holder is born with) validated by
   `impl_domain_profile.py`'s existing required tier, refusing
   `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` by its exact leaf name when absent.
   **No engine-side default literal** — the `implementation-per-document-vocabulary`
   precedent is explicit that "a leaf the engine may fall back from is a leaf the
   engine still hardcodes".
2. **Both skills declare it (D1).** `proposal-implementation` declares
   `AGREED.md` — its live target's holder already carries 107 hand-curated items,
   so this is a zero-migration declaration of what is already true.
   `experimental-implementation` declares `Experimental_AGREED.md`.
3. **Resolution order (D3).** Declared name first. If absent, fall back to the
   existing by-shape scan **for reading**. **Refuse to write** into a holder that
   was not found by the declared name, naming both exits: create the skill's own
   declared holder, or rename the existing one.
4. **Create-on-absent.** When the target has no holder at all, the skill creates
   its declared one, with its declared heading scaffold and **no checklist
   items**.
5. **The declared holder counts as the holder before it holds any item.** A
   consequence that must be built deliberately: today `agreements_state`'s
   `holders` list is defined by *holding checklist items* (`:436-449`), so a
   freshly created, item-less holder would be invisible to the two consumers that
   read that list (`_chosen_holder` `:11842`, `cmd_settle` `:14368`) and both
   would still refuse absent. Declared-name identity must be independent of the
   item-holding test.
6. **The doctrine amendments, on the record.** All 7 restatements of "never
   invents a file" and all 3 by-shape comments are amended, narrowed, or left
   standing explicitly (table below), plus the 18 prose mentions of the literal
   `AGREED.md` in the two shared modules.
7. **The document-count comparison, extracted as a shared predicate.** Today the
   `len(DOCUMENTS)`-vs-`documents=` comparison exists only inline in
   `cmd_position`'s sweep. It becomes a named helper, because D4's repair path
   needs exactly that comparison to decide anything.
8. **D4: repair-or-create for an already-poisoned target.** A target poisoned
   before this ships may be repaired or given its own declared holder; **where the
   correct action is ambiguous the mechanism stops and surfaces a human
   decision**, never guesses. No silent automatic repair.
9. **The structural gap in the second skill.** `experimental-implementation`
   gains `references/usage.md` covering its holder obligations. Measured today:
   `AGREED.md` appears 15× in `skills/proposal-implementation/references/usage.md`,
   13× in its `SKILL.md`, 1× in its `impl_profile.py`; it appears **zero** times
   anywhere under `skills/experimental-implementation/`, which has no
   `references/` directory at all. (This refines the brief's "12 mentions"
   figure with a fresh measurement.)
10. **The pinned refusal-code count.** `test_the_derivation_finds_the_measured_
    one_hundred_and_thirteen` (`tests/test_proposal_implementation.py:32285-32309`)
    pins 113 and moves with every code added or retired. Re-measuring it is a
    required mechanical step of this change, not a surprise at the end.
11. **The seal deltas.** `proposal-implementation`'s 28 sealed digests must stay
    byte-identical (it declares the name it already uses). `tests/experiments_seal/`
    writes `Trial/AGREED.md` (`corpus.py:344`) and the holder path reaches stdout
    (`position_state` emits `"holder": str(path.relative_to(target))`, `:777`;
    `cmd_position` at `:12376/:12404/:12411`; `cmd_settle` at `:14610/:14615`), so
    the fixture rename moves experiments-seal digests. That movement is declared
    as a sanctioned delta under `implementation-cli-seal`'s existing
    declared-delta discipline — never absorbed silently.

### Out of Scope

- **The read-side document-count check in `position_state` (finding 4).** Out,
  with the reason argued in "The read-side gap" below. The *predicate* is in
  scope (item 7); wiring it into `position_state`'s returned status for the other
  six commands is not.
- **Retiring `AGREEMENTS_GLOB`'s by-shape scan.** It stays; it is the read
  fall-back D3 depends on.
- **Any change to the `documents=` header grammar, the scalar→pair revision
  shape, or `_AUTHORIZATION_BINDING_KEYS`.** Governed by
  `implementation-document-binding`, untouched here.
- **Making `experimental-implementation` a full structural twin** (`assets/kit/`,
  `materialize.py`, a second seal corpus beyond what exists). Only the holder
  obligations of `references/usage.md` are in scope.
- **Editing any committed artifact to satisfy the new shape.** No
  `position.jsonl` event, `admissibility.json`, or existing header is rewritten
  by this change except through D4's explicit, human-visible repair path.
- **Touching the two already-active changes** `_measurements` and
  `tikz-optimizer-and-figure-audit`.

## Capabilities

### New Capabilities

- `implementation-declared-holder`: the per-skill declared holder filename and
  heading scaffold as a required `PROFILE` leaf; the declared→shape-read→
  refuse-to-write resolution order; create-on-absent; declared-name identity
  independent of the item-holding test; and the amended never-invents doctrine.
- `implementation-holder-repair`: the D4 path for a target poisoned before this
  ships — repair or create, with a named human stop whenever the correct action
  is not determined by the evidence.

### Modified Capabilities

- `experimental-implementation-skill`: its "Requirement: The Skill Declares Its
  Own Domain Profile" enumerates exactly seven sections (`kit`, `cli`,
  `objective`, `provenance`, `findings`, `vocabulary`, `documents`). That
  enumeration gains the holder leaf. The skill's `references/` obligation is
  added here too.
- `implementation-engine-neutrality`: the holder filename joins the
  profile-supplied set, and the engine's own prose stops asserting a literal
  holder filename as fact.
- `implementation-cli-seal`: the experiments-seal fixture rename and its declared
  digest delta; the proposal seal's zero-delta assertion.

## Approach

### Resolution order (D3), stated once

| Declared name present on disk? | Other item-holding `*.md` present? | Read | Write |
|---|---|---|---|
| yes | — | the declared file | the declared file |
| no | yes | by-shape scan, as today | **refuse**, naming both exits |
| no | no | nothing to read | **create** the declared file |

The middle row is the whole crux. The operator's accepted rationale:
unconditional create-on-absent would fork an adopted target's real checklist
(e.g. a pre-existing `TASKS.md`) into two files — worse than today's misreported
absence. A plain fall-back-and-use would let the experimental skill land on the
proposal's `AGREED.md` and poison it again — the very defect. Read-but-never-write
is the only rule that neither poisons nor forks.

### Reconciling D3 with the seven restatements of "never invents a file"

This change reverts a written promise. Each statement is argued with here, on the
record; none is quietly deleted.

The promise's own stated reason is narrower than its wording. `agreements_state`
says: *"A fixed filename would decide for the repository and then report `absent`
over whatever the repository actually called it — which is not a missing file, it
is an absence nobody went looking for, dressed as a finding."* That reason is
about **reading**. D3 preserves it exactly: the by-shape scan still answers every
read, so a target that calls its checklist anything at all is still found and
still reported. What changes is who owns the *write* target, and the honest
re-wording is: **the engine still invents no filename — the skill declares one.**
A declared holder is the same kind of value as `kit.root`, `cli.path`, and
`documents[N].directory`: the skill's own artifact, declared in the skill's own
file, never chosen by the engine on the repository's behalf.

| # | Site | Verdict | Why |
|---|---|---|---|
| A1 | `agreements_state` root doctrine, `implementation_engine.py:381-385` | **narrowed** | Keeps "found by shape" as the **read** rule verbatim, including its stated reason. Gains the write rule: the declared name owns writes, and the engine invents no filename because it holds none. |
| A2 | `_chosen_holder` raise `POSITION_HOLDER_ABSENT`, `:11844-11848` | **amended (behaviour)** | Its "no candidates at all" case becomes the create path. Its docstring's cross-reference to the doctrine ("`:11839-11840`, lines 140-145") is repointed — it currently cites line numbers that no longer name the doctrine. |
| A3 | `cmd_settle` raise `SETTLE_HOLDER_ABSENT`, `:14369-14373` | **amended (behaviour)** | Same: "settle never invents a file to write into" becomes "settle writes only into the holder this skill declares", and absence is created rather than refused. |
| A4 | `cmd_settle` docstring enumeration item 12, `:14149-14154` | **amended (prose)** | It enumerates `SETTLE_HOLDER_ABSENT`'s contract and explicitly cites "the same doctrine `_chosen_holder` already states". Both halves move together or the enumeration lies about the code under it. |
| A5 | Interactive question `SETTLE_HOLDER_ABSENT`, `:19284-19287` | **amended (prose)**, or retired with its code | Its question — "which file holds the agreements, and why?" — is answered by the declaration, so it stops being a question. If the code goes unreachable the entry goes with it; if the code survives for a narrower case, the question is re-authored for that case. Decided by measurement in the design phase, never predicted. |
| A6 | Interactive question `POSITION_HOLDER_ABSENT`, `:19334-19337` | **amended (prose)**, or retired with its code | Identical reasoning to A5. |
| A7 | `tests/test_implementation_pair.py:477-482` fixture comment | **amended** | It asserts "an empty product dir refuses `POSITION_HOLDER_ABSENT` before the install below ever gets to write anything" — which becomes false. The fixture also pre-writes `AGREED.md` under a two-document profile, i.e. the fixture itself encodes today's collision; it must move to the experimental declared name. |

Three adjacent by-shape statements, not in the operator's count of seven, and
equally load-bearing:

| # | Site | Verdict |
|---|---|---|
| B1 | `position_state` comment, `:644-646` ("never a fixed filename that would decide for the repository") | **narrowed** — it describes the read path, which is unchanged; gains a pointer to the declared-name write rule. |
| B2 | `cmd_position` holder-sweep comment, `:12090-12092` | **amended** — the sweep gains the declared-name lookup ahead of the glob. |
| B3 | `cmd_position` docstring, `:12036-12041` ("The holder, found by shape for a refresh or a reconcile… For a fresh install or a fresh reconcile, chosen by `_chosen_holder`") | **amended** — this is the sentence that describes the mechanism being changed. |

And the literal-filename prose: 15 mentions of `AGREED.md` in
`implementation_engine.py` and 3 in `impl_position.py`. Four are docstring
*assertions of fact* (`:575` "read from `<Name>/AGREED.md`", `:12005` "The only
writer into `<Name>/AGREED.md`'s position section", `:18946`, `:18992`) and must
name the declared leaf instead — they are already false today for any target that
named its checklist differently, and would be false for
`experimental-implementation` the moment it declares its own name. The remainder
are illustrative and get the same treatment where they read as the engine's own
naming and are left standing where they are quoting a skill's own artifact.

### The created holder's heading (the `SETTLE_HEADING_ABSENT` doctrine)

`settle`'s create path refuses `SETTLE_HEADING_ABSENT` when the heading a write
goes under occurs in no holder, and its question says: *"settle never invents one;
which existing heading holds it, or should the holder gain that heading first?"*
(`:19298-19302`, enumerated at `:14155-14160`, raised near `:14553-14566`). A
holder created empty would therefore be born unusable, and the very next `settle`
would refuse.

The resolution is the identical narrowing the filename gets: **the engine invents
no heading — the skill declares the scaffold its holder is born with.** The
holder leaf carries the heading scaffold alongside the filename, so a created
holder arrives with its declared heading(s) and **zero checklist items**. An item
would be the engine inventing an agreement, which is the one thing
`agreements_state`'s docstring is most emphatic about ("deliberately not a plan of
work") and which nothing here touches. `SETTLE_HEADING_ABSENT` is therefore
**left standing, unamended**: after a create, the declared heading exists; for any
other heading the refusal fires exactly as it does today, with the same question.

This is also where in-scope item 5 bites: an item-less created holder is
invisible to the item-holding `holders` scan, so declared-name identity must not
be derived from that scan. A design that creates the file and leaves the
`holders` derivation alone ships a holder that every consumer still reports
absent.

### The read-side gap (finding 4): OUT, and what that leaves broken

`position_state` (`:572-660`, `:737-738`) never compares the header's `documents=`
group count against `len(DOCUMENTS)`. It is called by `verify`, `probe`,
`discuss`, `gate`, `offer`, `close`, and `step`; only `cmd_position`'s write path
catches the mismatch. Six of seven commands are blind.

Out of this change, for three reasons:

1. **The right read-side treatment is not a refusal, and this change has no
   mandate to design it.** `implementation-document-binding` states the standing
   position explicitly: *"`cmd_verify`'s per-document fidelity fold MUST NOT
   refuse for the identical condition — it already answers the named status
   `unknown`, preserving `revision_discovery`'s standing 'reported, never
   refused; verify is a reader' position."* Adding a refusal to `position_state`
   would turn seven readers into refusers and contradict a live requirement.
   Adding a *reported status* instead means a new key on a uniform-key-set return
   that six commands print — a different change, with its own digest movement
   across both seals.
2. **After this change the condition is unreachable for new work.** Two skills
   can no longer land in one holder, so a read-side check would guard only
   targets poisoned before this ships — which is precisely what D4 addresses,
   inside this change, at the one moment a human is already looking at such a
   target.
3. **Budget.** Both reasons above are additive to a change that already exceeds
   the 400-line budget (below).

What deferring leaves broken, stated plainly: **a target poisoned before this
ships continues to read as if its header were fine under `verify`, `probe`,
`discuss`, `gate`, `offer`, `close`, and `step`, and refuses only at
`position`.** That window closes by repair (D4), not by a seventh refusal. The
comparison predicate is extracted here (in-scope item 7) so the follow-on change
wires an existing, tested helper rather than re-deriving it — and so D4 is not
built on an inline expression buried in a write path.

### Refusal-code arithmetic (mechanical, measured, never predicted)

`test_the_derivation_finds_the_measured_one_hundred_and_thirteen` pins 113 and
its own docstring states the convention: *"measured here, never predicted"*. This
change moves it. Candidate movements:

- **Added**: a write-into-undeclared-holder refusal (the D3 middle row), and D4's
  ambiguous-repair human stop.
- **Possibly retired**: `POSITION_HOLDER_ABSENT` and `SETTLE_HOLDER_ABSENT`, if
  the create path leaves them with no reachable configuration. `POSITION_HOLDER_
  AMBIGUOUS` stays — the read fall-back can still find more than one block.
- **Per-code follow-through**: `reachable_refusal_codes`'s derived roster, the
  `_refusal_question` table, and the `WORK_STATE`/classification roster. This
  project has already measured that adding one refusal code touches six places;
  the denylist and the roster are computed before the first code is written, not
  after.

The design phase measures the new number by running the derivation. The proposal
commits only to this: the number moves, and re-measuring it is a named task.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `skills/_core/implementation/impl_domain_profile.py` | Modified | 8th required leaf joins the required tier (`_REQUIRED_PRESENCE`/`_REQUIRED_NESTED`, `:59-97`, validated at `:238`); refuses by exact leaf name |
| `skills/_core/implementation/engine/implementation_engine.py` | Modified | Declared-name resolution; `agreements_state` `:362-449`; `position_state` `:572-660`; `_chosen_holder` `:11830-11856`; `cmd_position` sweep `:12093-12134`; `cmd_settle` `:14368-14373`; refusal-question table `:19284-19337`; 15 `AGREED.md` prose mentions |
| `skills/_core/implementation/impl_position.py` | Modified | 3 `AGREED.md` prose mentions (`:20`, `:270`, `:1139`) |
| `skills/proposal-implementation/impl_profile.py` | Modified | Declares `AGREED.md` + heading scaffold (zero behavioural delta — it is the name already in use) |
| `skills/experimental-implementation/impl_profile.py` | Modified | Declares `Experimental_AGREED.md` + heading scaffold |
| `skills/experimental-implementation/references/usage.md` | New | The skill's holder obligations (today: no `references/` directory exists) |
| `skills/{proposal,experimental}-implementation/SKILL.md` | Modified | Holder naming follows the declaration |
| `tests/test_proposal_implementation.py` | Modified | ~9 holder/document-count assertion sites (`~:20053-24281`); pinned count `:32285-32309` |
| `tests/test_implementation_pair.py` | Modified | Doctrine fixture comment + holder name `:460-490` |
| `tests/seal/corpus.py` | Unchanged bytes, re-asserted | `Seal/AGREED.md` `:272` stays; 28 digests must not move |
| `tests/experiments_seal/corpus.py` | Modified | `Trial/AGREED.md` `:344` → declared experimental name; declared digest delta |
| `tests/test_implementation_core.py` | Modified | 2 `AGREED` references |
| `openspec/specs/` | Modified | 3 delta specs + 2 new capability specs (spec phase) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `proposal-implementation`'s 28 sealed digests move | Med | The declaration is the name already in use, so the intended delta is zero. Assert it as a hard gate per slice, not once at the end. |
| A created holder is invisible to `agreements_state["holders"]` and every consumer still reports absent | **High** | In-scope item 5: declared-name identity is independent of the item-holding test, with a test that creates a holder and then reads it back through `_chosen_holder` and `cmd_settle`. |
| The declared-name lookup lands but one of the write sites keeps globbing | Med | The `implementation-block-locator` precedent applies: repoint every reader together, and add the comparison test that reddens when one site disagrees with the others. |
| A doctrine restatement is left standing over changed behaviour | **High** (this project has measured four such instances in one session) | The 7+3 table above is a checklist in the spec, and each row is verified against the shipped bytes, not against intent. |
| The pinned 113 is updated by editing the number to whatever the run prints, rather than by understanding the movement | Med | Each added/retired code is named in `tasks.md` with the site that raises it; the count is reconciled against that list. |
| D4's repair guesses on an ambiguous target | Med | D4's human stop is a refusal with a code and a question, proven reachable by mutation (this project's standing rule: inverting the guard is the only reachability proof). |
| A new refusal code ships unreachable, or reachable and unclassified | Med | `reachable_refusal_codes`'s derived roster reddens on an unclassified code; a mutation must make each new refusal fire. |
| The experimental skill's `references/usage.md` drifts from its twin | Low | Scope it to the holder obligations only; do not mirror the whole twin document. |

## Rollback Plan

The change is sliced so that each slice is independently revertable, and only
slices 3 and 4 write into a target repository.

- **Slices 1–2 (declaration + resolution)**: `git revert` the slice commits. The
  declared leaf becomes unread and then unrequired; by-shape resolution is
  restored exactly, since it was never removed — it remains the read fall-back.
  Nothing has been written into any target that the reverted code cannot read.
- **Slice 3 (create-on-absent)**: revert restores the `POSITION_HOLDER_ABSENT` /
  `SETTLE_HOLDER_ABSENT` refusals. A holder already created in a live target
  survives the revert and is picked up again by the by-shape scan, because it is
  a real `*.md` file holding checklist items — it does not become invalid.
- **Slice 4 (D4 repair)**: the repair path never edits without a human decision,
  so a revert leaves at most targets whose headers a human explicitly chose to
  repair. Those repairs are ordinary committed content in the target repository
  and are reverted there, by that repository's own history, not by this one.
- **Seals**: the experiments-seal delta is declared, so reverting the slice
  reverts the fixture name and the digests together; a reverted fixture with
  unreverted goldens is caught by the seal's own coverage check.
- **The live target** (`implementations/…/AGREED.md`, 107 items) is verified
  clean today: it carries a position block and no `documents=` group, so no
  slice of this change needs to touch it, and no rollback needs to restore it.

## Dependencies

- None external. No new package, service, or interpreter.
- `openspec/config.yaml` sets `strict_tdd: true` and `test_command: npm run
  test:all`. Both suites are required: this repository has already measured that
  running only one hides a 13-test regression (`npm test` **and** `pytest`).
- The engine suite needs dependencies nothing declares; a bare `python3.12` run
  yields ~29 environmental failures. Use `.venv/bin/python` and date any
  pre-existing failure before attributing it to this change.
- Must not disturb the two active changes `_measurements` and
  `tikz-optimizer-and-figure-audit`.

## Size Forecast And Delivery

Authored changed lines (additions + deletions, goldens excluded), forecast from
the scope above:

| Slice | Content | Forecast |
|---|---|---|
| 1 | The 8th `PROFILE` leaf: resolver required tier + both skills declare it. No behaviour change, no digest movement. | ~150–200 |
| 2 | Declared-name lookup, read fall-back, the write refusal; the 7+3 doctrine amendments and the 18 literal-filename prose sites; experiments-seal fixture rename + declared delta; re-measured refusal count. | ~250–320 |
| 3 | Create-on-absent with the declared heading scaffold; declared-name identity independent of the item-holding test. | ~150–200 |
| 4 | D4: repair-or-create with the ambiguous-case human stop; the extracted document-count predicate. | ~150–220 |
| 5 | `experimental-implementation/references/usage.md` (holder obligations) + both `SKILL.md` updates. | ~100–150 |
| | **Total** | **~800–1090** |

```
Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: High
```

The forecast is roughly 2–2.7× the fixed 400-line budget, so this change **must
be split**. The five slices above are the proposed boundaries; each has a clear
start and finish, autonomous scope, its own verification, and the rollback stated
above. Slice 1 is deliberately behaviour-free so the declaration and the
resolution change never land in one reviewable unit. Slices 2–4 are strictly
ordered (2 before 3 before 4); slice 5 depends only on slice 1.

Delivery strategy for this session is `ask-on-risk`, and the forecast exceeds the
budget, so the chain strategy (`stacked-to-main` or `feature-branch-chain`) is a
user decision the orchestrator must obtain before apply. This proposal does not
choose it.

## Success Criteria

- [ ] Both skills' `PROFILE` declares its own holder name and heading scaffold;
      omitting the leaf refuses `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming
      that exact leaf.
- [ ] No holder filename literal remains in `implementation_engine.py` or
      `impl_position.py` as an engine-side default or fallback — grep-provable.
- [ ] Declared name present → both reads and writes use it.
- [ ] Declared name absent, another item-holding `*.md` present → reads succeed
      by shape; the write refuses by a named code whose message names **both**
      exits (create the declared holder, or rename the existing one), proven
      reachable by mutating the guard away.
- [ ] Declared name absent and no candidate present → the declared holder is
      created, with its declared heading(s) and zero checklist items, and is
      immediately visible to `_chosen_holder` and `cmd_settle`.
- [ ] `SETTLE_HEADING_ABSENT` still fires for any heading the declaration does
      not carry — unamended, proven by mutation.
- [ ] Running the experimental skill against a target holding the proposal
      skill's declared holder can no longer write a `documents=` group into it:
      the collision configuration is reproduced as a test and refuses.
- [ ] All 7 "never invents a file" restatements and all 3 by-shape comments are
      verified against the shipped bytes; none asserts behaviour the code no
      longer has.
- [ ] The four docstrings asserting the holder *is* `<Name>/AGREED.md` name the
      declared leaf instead.
- [ ] `tests/seal/`'s 28 `proposal-implementation` digests are byte-identical.
- [ ] `tests/experiments_seal/`'s moved digests are declared deltas with reasons,
      re-captured, and covered.
- [ ] The pinned refusal-code count is **re-measured** by running the derivation,
      and every added or retired code is named with the site that raises it.
- [ ] `skills/experimental-implementation/references/usage.md` exists and states
      the same holder obligations its twin's `references/usage.md` states.
- [ ] A target poisoned before this change can be repaired or given its own
      declared holder; where the correct action is ambiguous, the mechanism stops
      with a named human decision and writes nothing.
- [ ] `npm run test:all` (both suites) is green, with any pre-existing
      environmental failure dated and named rather than absorbed.

## Open Questions

Only one. D1–D4 are settled and are not re-opened here.

1. **Chain strategy.** The forecast exceeds the 400-line budget under
   `ask-on-risk`, so the user must choose `stacked-to-main` or
   `feature-branch-chain` before apply. Returned to the orchestrator; not chosen
   by this proposal.
