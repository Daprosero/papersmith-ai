# Design: The Holder Each Skill Declares

## Technical Approach

The proposal's settled decisions (D1–D4) are architecturally one move: **the
write target of the checklist holder stops being a by-product of a reading
function and becomes a declared value with its own resolver.**

Today there is no holder resolution. There are four independent glob-by-shape
scans that each re-derive a candidate set, and two of them agree only by
having been written from each other:

| site | what it globs | what it decides |
|---|---|---|
| `agreements_state` | `product.glob(AGREEMENTS_GLOB)` (`implementation_engine.py:424-425`) | `holders` = files *holding checklist items* (`:482-483`) |
| `position_state` | `product.glob("*.md")` (`:648`) | the one file carrying a `<!-- position -->` block (`:653-660`) |
| `_chosen_holder` | `agreements_state(...)["holders"]` (`:11842`) | which file receives a FRESH block (`:11843-11856`) |
| `cmd_settle` | `agreements_state(...)["holders"]` (`:14368`) | every file `settle` may write into (`:14369-14373`) |
| `cmd_position` | `product.glob("*.md")` (`:12093-12094`) | the existing block's holder + the pre-image digests (`:12109-12142`) |

No `PROFILE` key is read by any of them. Verified: `PROFILE` is consumed only
at `:99-100`, `:108-138`, `:148-184`, `:11101` — none of those names a holder.
So this is new engine logic, not a config flip.

The approach adds exactly one new function — a total, never-raising
`holder_resolution(target, name)` placed immediately after `agreements_state`
— and repoints all five sites at it. `agreements_state`'s *code* is not
touched at all; only its docstring is narrowed. That single constraint is what
keeps `tests/seal/`'s 28 digests still (see D11) and what keeps the by-shape
doctrine's stated reason true verbatim (see D12).

Maps to the proposal's Approach section: the D3 table becomes
`holder_resolution`'s four `action` values; item 5 becomes D3 below; item 7
becomes D8; item 8 becomes D6/D7.

**Stale-pin correction, measured before designing anything.** The proposal and
the launch brief both say the pinned reachable-refusal count is 113. It is
**118**: `tests/test_proposal_implementation.py:32324` asserts
`len(reachable_refusal_codes()) == 118`, while the test's own *name* at
`:32285` still reads `test_the_derivation_finds_the_measured_one_hundred_and_
thirteen` and its docstring narrates up to 118. The name is five generations
stale — the exact "prose that outlived its mechanism" shape this project has
measured repeatedly. All arithmetic below starts from 118, and renaming that
test is a named task, not an afterthought.

## Architecture Decisions

### Decision D1: The leaf is an 8th top-level `holder` section with three leaves

**Choice.** `PROFILE["holder"]` = `{"filename": str, "headings": tuple[str, ...],
"scaffold": str}`. Three pairs appended to `_REQUIRED_PRESENCE`
(`impl_domain_profile.py:67-90`): `("holder", "filename")`,
`("holder", "headings")`, `("holder", "scaffold")`. Presence is validated by
the existing loop at `:238-241`, which refuses
`IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming the exact dotted leaf
(`:334-337`). A new shape tier below the presence loop refuses
`IMPLEMENTATION_DOMAIN_PROFILE_INVALID_HOLDER`.

**Alternatives considered.**
- `_REQUIRED_NESTED` (`:59`). Rejected: that tuple is walked by the
  `..._UNSAFE_PATH` check (`:483-485`), which demands *absolute and existing
  on disk*. A holder filename is deliberately relative, single-component, and
  usually non-existent — the exact inverse.
- A scalar `PROFILE["holder"] = "AGREED.md"` with the heading inferred.
  Rejected under D4.
- Reusing `..._UNSAFE_PATH` for the shape refusal. Rejected: its message says
  "must be absolute and exist on disk", which would be false. The established
  convention for shape-beyond-presence in this file is a distinct
  `..._INVALID_<THING>` code — `..._INVALID_CITATION_PATTERN` (`:358-366`),
  `..._INVALID_BLOCK_LOCATOR` (`:384-410`),
  `..._INVALID_CROSS_CITATION_PATTERN` (`:433-442`). Join that family.

**Rationale.** A top-level section makes the proposal's "8th `PROFILE` key"
literal and makes `experimental-implementation-skill`'s spec enumeration
(`openspec/specs/experimental-implementation-skill/spec.md:20-21`, "its own
`kit`, `cli`, `objective`, `provenance`, `findings`, `vocabulary`, and exactly
one `documents` entry") gain a nameable eighth member rather than a leaf
smuggled into an existing section.

**Consequence the implementer must not be surprised by.**
`ImplementationProfileError` is *not* `Refused`, and
`impl_domain_profile.py:20-25` states the property deliberately: a distinctly
named exception is invisible to `reachable_refusal_codes()`'s walk. So
`..._INVALID_HOLDER` does **not** move the 118.

### Decision D2: One new total resolver, `holder_resolution`; `agreements_state`'s code is untouched

**Choice.** A module-level function placed directly after `agreements_state`
(i.e. after `:510`), returning a uniform key set on every branch and **never
raising**:

```python
def holder_resolution(target: Path, name: str) -> dict:
    # {"declared": str,            # HOLDER_FILENAME, always
    #  "path": Path | None,        # the declared file, iff it is_file()
    #  "byShape": list[str],       # agreements_state(...)["holders"], verbatim
    #  "read": Path | None,        # declared, else the single by-shape candidate
    #  "write": Path | None,       # declared path, or the path to create
    #  "create": bool,             # write target does not exist yet
    #  "action": str}              # "declared" | "create" | "undeclared" | "ambiguous"
```

Callers turn `action` into their own refusal. The function names no refusal
code.

**Alternatives considered.**
- Widen `agreements_state`'s `holders` list to include the declared file even
  when it holds no items. **Rejected, and this is the decision the proposal
  flagged as most likely to be got wrong.** `agreements_state`'s `status` is
  derived from the same list: `if not holding: return {... "status": "absent"
  ...}` (`:487-493`) and otherwise `"open" if open_items or unparsed else
  "settled"` (`:497`). A freshly created, item-less holder would therefore
  report `status: "settled"` over a document in which nothing has been
  settled — manufacturing a false green in the one function whose docstring is
  most emphatic that it is "deliberately not a plan of work" (`:373-375`). It
  would also move `holders`/`status` on stdout for any target carrying an
  item-less `AGREED.md`, which is a seal exposure for no gain.
- Add a new key (`declaredHolder`) to `agreements_state`'s return. Rejected:
  that return is printed by `verify` and friends, and the file's own
  uniform-key-set doctrine (`:421-421`, `position_state:582-588`) means a new
  key appears on **every** branch — moving digests in *both* seals to carry a
  value only three write sites read. It also buys nothing over a separate
  function.
- Inline the declared lookup at each of the five sites. Rejected by the
  `implementation-block-locator` precedent the proposal cites: five copies is
  how one site keeps globbing after the other four were repointed.

**Rationale.** Totality (never raising) is the property `locate_headings`
already argues for at `impl_position.py:357-364` — "a heading belongs to the
caller's own vocabulary, not this module's, so 'none found' and 'found more
than once' are read off this list's own length by whoever asked". Holder
resolution has the identical shape: three commands need the same facts and
name three different refusals over them.

### Decision D3: Declared-name identity is `name == declared and is_file()`, and it lives only in the new resolver

**Choice.** A file is the declared holder iff `(product / HOLDER_FILENAME)`
`.is_file()`. Nothing else about it is examined — not its item count, not
whether it carries a block, not its size. `agreements_state`'s item-holding
test is left exactly as it is and continues to answer a different question
(*what holds agreements*), which is the question `verify` prints.

**Alternatives considered.** "Any `.md` in the product folder with a
declared heading counts." Rejected: that is the "every empty `.md` becomes a
holder" failure mode in a thinner disguise, and it makes holder identity
depend on document *content* again.

**Rationale.** This is what makes item 5 true: `holders` stays the
item-holding scan, and the two consumers that refused absent (`_chosen_holder`
`:11842-11848`, `cmd_settle` `:14368-14373`) now read `holder_resolution`
instead, so a created, item-less holder is visible to them the instant the
file exists. Exactly one file in the product folder can satisfy two
conditions — a name equal to the declaration, and existing — so nothing else
is promoted.

**Explicitly not promoted:** a declared name that does *not* exist on disk is
never reported as a holder anywhere. `holder_resolution` returns `path: None`
for it. This is load-bearing for `tests/seal/`'s `verify-t` case
(`tests/seal/cases.json:173-174`), whose fixture `_build_fixture_t`
(`tests/seal/corpus.py:283-295`) writes no `AGREED.md` at all: a resolver that
listed a nonexistent declared path would move that digest.

### Decision D4: The scaffold is verbatim declared bytes plus a declared heading roster, validated against each other

**Choice.**

```python
"holder": {
    "filename": "AGREED.md",                       # proposal-implementation
    "headings": ("# Agreed", "## Ladder"),
    "scaffold": "# Agreed\n\n## Ladder\n",
},
```

```python
"holder": {
    "filename": "Experimental_AGREED.md",          # experimental-implementation
    "headings": ("# Agreed", "## Ladder"),
    "scaffold": "# Agreed\n\n## Ladder\n",
},
```

A created holder contains `HOLDER_SCAFFOLD.encode("utf-8")` and **nothing
else** — byte for byte, no trailing-newline normalization, no name
interpolation, no title composition, zero checklist items.

Resolver shape tier (`..._INVALID_HOLDER`), four checks:
1. `filename` is exactly one path component: non-empty, no `/` or `\`, not
   `.`/`..`, no NUL, no newline, and `Path(filename).name == filename`.
2. `filename` ends `.md` — `AGREEMENTS_GLOB` is `"*.md"` (`:293`) and the read
   fall-back would not see a holder the write side created under another
   suffix.
3. `headings` is a non-empty sequence of `str`.
4. **Every entry of `headings` occurs in `scaffold` as a full line whose
   stripped text equals it, outside a fenced region** — the exact matching
   rule `locate_headings` implements (`impl_position.py:366-389`: `stripped !=
   heading` skips, and a ``` ``` ``/`~~~` line toggles `fenced`). A profile
   whose promise its own bytes do not keep is refused, naming the entry that
   does not occur.

**Alternatives considered.**
- `scaffold` alone (no `headings`). Rejected: nothing is checkable. A profile
  declaring a scaffold with no heading ships a holder born unusable, and the
  very next `settle --under` refuses `SETTLE_HEADING_ABSENT` — the failure
  this whole sub-decision exists to prevent (`:19298-19302`, enumerated
  `:14155-14160`, raised `:14559-14563`).
- `headings` alone, engine composes the bytes. Rejected: choosing the
  separator, the blank lines, and the ordering *is* the engine authoring
  document content — precisely the thing being narrowed away.
- A default scaffold in the engine. Rejected by the
  `implementation-per-document-vocabulary` precedent the proposal quotes: "a
  leaf the engine may fall back from is a leaf the engine still hardcodes".

**Rationale.** Declaring the bytes and separately declaring what those bytes
promise, then validating the two against each other at resolve time, is not a
new pattern here — it is exactly `documents[N].block_locator`'s
`pattern`/`identity` pair, cross-validated at `impl_domain_profile.py:379-410`
(`identity_fields != ["value"]`). The skill owns the bytes; the resolver holds
the skill to its own promise.

**`SETTLE_HEADING_ABSENT` is left standing, unamended.** After a create, the
declared headings exist; for any heading the declaration does not carry, the
refusal fires with the same code, the same message, and the same question it
has today. Its docstring gains no new sentence, which is the cleanest possible
proof that this design did not weaken it.

**Both skills may declare identical headings** (`# Agreed` / `## Ladder`)
without any ambiguity risk, *because* of D10: `settle`'s search narrows to the
single resolved write holder, so two files carrying `## Ladder` can never both
be in one search. The two holders are distinguished by filename, which is the
whole point of the change.

### Decision D5: Creation is a separate, explicit write of the scaffold; the caller's own splice then runs unchanged; never `mkdir`

**Choice.** When `action == "create"`, the resolver's caller writes
`HOLDER_SCAFFOLD` to `resolution["write"]` via
`impl_position.write_spliced(path, scaffold_bytes, expect_digest=impl_position.digest_bytes(b""))`
**before** any block or item splice. The subsequent write then proceeds
against ordinary on-disk bytes with an ordinary pre-image digest.

Creation happens **only when `product.is_dir()`**. The engine never creates
`<Name>/`.

**Alternatives considered.**
- Let `cmd_position` splice the position block straight into a nonexistent
  path. Mechanically this already works — `before_bytes = target_path
  .read_bytes() if target_path.exists() else b""` (`:12387`), and the digest
  lookup already falls back to `digest_bytes(b"")` (`:12399`), with the
  comment at `:12394-12396` explicitly anticipating "a brand-new file
  `_chosen_holder` could in principle name". Rejected because the file would
  then be born as a bare position block with **no heading at all**, and the
  very next `settle --under` refuses. Two writes, not one clever splice.
- `product.mkdir(parents=True)` on absent. **Rejected firmly.** Product-tree
  scaffolding belongs to `materialize`/`structure`, and creating `<Name>/`
  here would let a typo'd `--name` silently open a second product tree — the
  exact condition `require_named_product_dir` exists to refuse
  (`:2760-2779`). Verified reachable: `require_named_product_dir` returns
  without refusing when `<name>/` is simply absent and no other directory
  holds `PRODUCT_DIRS` (`:2769-2771`).

**Rationale.** `write_spliced`'s absent-path tolerance is documented, not
incidental (`impl_position.py:1219-1226`, `:1233`), so creation needs no new
write primitive and inherits the compare-and-swap, same-directory-temp-file,
`os.replace` guarantees unchanged. Reusing it also means a concurrent writer
that creates the file first is caught by `POSITION_HOLDER_MOVED` rather than
silently overwritten.

**Direct consequence for D9:** because creation requires `product.is_dir()`,
the "there is no folder to create a holder in" case survives — which is why
`POSITION_HOLDER_ABSENT` and `SETTLE_HOLDER_ABSENT` are narrowed, not retired.

### Decision D6: D4's repair is `position --repair-header`, not a new command

**Choice.** A new flag on `position`. Mutually exclusive with `--sequence`,
`--reconcile` and `--replace`, refused by a hand-raised
`POSITION_REPAIR_CONFLICT` in the same shape as
`POSITION_SEQUENCE_AND_RECONCILE` (`:12070-12075`).

**Alternatives considered.**
- A new `holder` command. **Rejected on measured cost.** A new command joins
  `COMMANDS`, and `SealMembershipTests` holds `sealed ∪ unsealed == cases` and
  `commands == COMMANDS` (`tests/test_implementation_seal.py:531-533`). That
  forces a new case in `tests/seal/cases.json` and a new entry in
  `tests/seal/digests.json` — i.e. it forces an edit to the proposal seal in a
  change whose hardest gate is that the proposal seal does not move. It drags
  `tests/experiments_seal/` identically.
- A flag on `settle`. Rejected: `settle` writes items, never headers.

**Rationale.** `cmd_position` is already documented as "the only writer into
… the position section" (`:12005`) and is already the only place the mismatch
is detected (`:12126-12133`). Repair is a header write. It belongs to the one
writer, and putting it anywhere else would create a second header writer,
which is the defect `:12005` exists to deny.

Adding an argparse flag moves no digest: the seal digests **normalized stdout
plus exit status only** (`tests/seal/harness.py:218-226`,
`digest_result` = `sha256(stdout)` + `bytes` + `exit`), and no sealed case
invokes `--help` (verified: `tests/seal/cases.json` contains no `help`/`usage`
token; `tests/seal/unsealed.json` records only `propose`'s timestamp
non-determinism).

### Decision D7: What repair may do silently, and what stops for a human

`--repair-header` repairs **only** when all four hold:

1. `action == "declared"` — the poisoned file is the declared holder. (A
   shape-found holder cannot be written into at all; `HOLDER_UNDECLARED`
   fires first and its two exits are the answer.)
2. `impl_position.locate_block(data, allow_legacy=True)` returns a block
   rather than raising.
3. `_header_document_count_detail(block)` is not `None` — the target really is
   in the refused state.
4. **Every entry of `block["documents"]` either carries no `revision`, or
   carries a `label` this profile's `DOCUMENTS` does not declare.** The group's
   entry shape is `{label, revision, revisionSha256}`
   (`_position_extra_documents`, `:5356-5358`).

Repair = re-render the header **without** the `documents=` group, keeping
`revision`, `revisionSha256`, `derivedAt`, `session` and `target` unchanged
and the block body byte-identical. `render` already omits the group when the
key is absent or empty, "byte for byte" identical to its pre-Cut-3 output
(`impl_position.py:1106-1115`). Nothing recorded is lost, because every
discarded entry named a document this profile has no reader for.

Anything else raises **`HOLDER_REPAIR_AMBIGUOUS`** (`WORK_STATE`), naming the
decoded group entries, which labels this profile declares, and asking: *does
this header's recorded binding still mean something under this profile —
repair it by dropping the group, or give this target its own declared holder?*
Concretely ambiguous:

- an entry carries a non-empty `revision` for a label this profile **does**
  declare (dropping it would discard a recorded binding);
- `block["legacy"]` is true — `target` is `None` there
  (`impl_position.py:241`) and repair would have to invent a rung, which
  `POSITION_TARGET_LEVEL_REQUIRED` (`:12248-12253`) says the engine never
  does;
- more than one `*.md` carries a block — `POSITION_HOLDER_AMBIGUOUS` already
  owns that (`:12135-12140`), and repair must not become a second answer to it.

**Rationale.** The unambiguous case is defined by *evidence*, not by
confidence: the discarded bytes provably name nothing this profile reads. Every
case where the header records something this profile could still mean stops.
That is D4's "never guesses" as a checkable predicate rather than a promise.

### Decision D8: The extracted predicate stays asymmetric, deliberately

**Choice.** `_header_document_count_detail(block: dict) -> str | None`,
placed beside `_bound_to` (`:538-551`), whose docstring already states the
extraction rule this follows: "extracted so the identical arithmetic serves
every declared document … never a second copy drifting beside it". Returns the
refusal detail string, or `None`. Callers: `cmd_position`'s sweep (replacing
the inline condition at `:12126`) and D7's repair gate.

It encodes **exactly today's condition** — `block.get("documents") is not None
and len(DOCUMENTS) <= 1` — and nothing more.

**Alternatives considered.** A symmetric helper that also detects "no
`documents=` group under a multi-document profile". **Rejected, and this is
the trap in this decision.** That direction is the deliberate silent-migration
case (`:12116-12125`: it "still opens, with `revision`/`sha256` meaning
document 0 exactly as today, and gets the group added on the next write"). A
symmetric helper would make `cmd_position` start refusing it — a behaviour
change, a digest mover in both seals, and a contradiction of
`implementation-document-binding`'s standing "reported, never refused" position
which the proposal quotes.

**Rationale.** `str | None` rather than `bool` is this file's established shape
for "the caller raises": `_record_operand_detail` (`:12279-12281`),
`_record_shape_detail` (`:12289-12291`), `_step_operand_detail`
(`:12320-12322`), `_skipped_rung_detail` (`:12306-12309`). Following it keeps
the detail text at the one site that owns the wording.

### Decision D9: One unprefixed `HOLDER_UNDECLARED`; the two `..._HOLDER_ABSENT` codes are narrowed, not retired

**Choice — three codes added, none retired.**

| code | raised at | class | why |
|---|---|---|---|
| `HOLDER_UNDECLARED` | `_chosen_holder`, `cmd_settle`, `cmd_position` sweep | `WORK_STATE` | the D3 middle row |
| `HOLDER_REPAIR_AMBIGUOUS` | `cmd_position --repair-header` | `WORK_STATE` | D7's human stop |
| `POSITION_REPAIR_CONFLICT` | `cmd_position` flag guard | `INVOCATION_DEFECT` | D6 |

**One code, not two, for the D3 middle row.** The existing split
(`POSITION_HOLDER_ABSENT` at `:11844` vs `SETTLE_HOLDER_ABSENT` at `:14370`
for the identical condition) is history, not doctrine; the file states its
actual preference at `:14169-14170` and `:14179-14182` — "Reused codes, not
minted twice". `HOLDER_UNDECLARED` carries no command prefix because the
condition is a property of the **target** (its checklist is named something
this skill did not declare), not of the command, and both commands' exits are
the same two sentences. It joins the family of unprefixed target-property
codes: `PRODUCT_DIR_MISNAMED` (raised by nine write verbs, `:32298-32299`),
`DIRTY_WORKTREE`, `REVISION_UNREADABLE`, `FORGE_DEFECT_OPEN`.

**Its message names both exits, and neither of them forks the checklist:**

1. rename `<found>` to `<declared>` in the target repository, or
2. declare `<found>`'s own name in this skill's
   `PROFILE["holder"]["filename"]`.

Exit 2 is the sharper one and it is *why* this change does not betray the
doctrine it amends. `agreements_state`'s stated reason is that a fixed
filename "would decide for the repository" (`:381-385`). Exit 2 is the
repository's own name winning — it just has to be said out loud, in the
skill's own file, where `kit.root` and `documents[N].directory` already live.
The message must also state exit 2's scope honestly: the declaration serves
every target this skill is run against, so exit 2 is right only when the
repository's name should become this skill's convention.

**Narrowed, not retired — correcting the proposal's own guess.** The proposal
lists `POSITION_HOLDER_ABSENT`/`SETTLE_HOLDER_ABSENT` as "possibly retired if
the create path leaves them with no reachable configuration". Measured: D5
forbids `mkdir`, so **the product folder itself being absent is still a
reachable refusal** for both commands. `cmd_position` reads `md_files = ... if
product.is_dir() else []` (`:12093-12094`) and `require_named_product_dir`
does not refuse a merely-absent `<name>/` (`:2769-2771`); `cmd_settle` calls
the same guard at `:14248` and then `agreements_state(...)["holders"]` at
`:14368`. Both codes therefore survive for exactly one narrower case and their
messages and interactive questions (`:19284-19287`, `:19334-19337`) are
re-authored for it. Proposal table rows **A5 and A6 resolve to "amended
(prose), re-authored for the narrower case"**, not "retired with its code".

This also avoids the opposite defect: `reachable_refusal_codes()` derives from
**source**, not runtime reachability, so retiring a code means *deleting* its
raise site. Deleting a raise site whose case is still reachable would leave a
real state with nothing published beside it — the defect `GATING_REFUSALS`'
own docstring says the roster exists to make impossible (`:18379-18392`).

**Arithmetic: 118 + 3 − 0 = 121, predicted here and re-measured by running
the derivation.** The number in the assertion is whatever
`len(reachable_refusal_codes())` prints; it is never edited to match a
prediction. Per-code follow-through, six places, computed before the first
code is written:
`Refused(...)` raise site → `GATING_REFUSALS` (`:18402-18521`) →
`_refusal_question`/`_refusal_command` table (`:19274-19347`) →
`test_the_roster_classifies_every_reachable_code` (`:32242-32247`) → the count
assertion (`:32324`) → a mutation test proving the guard fires.
And: **rename `test_the_derivation_finds_the_measured_one_hundred_and_
thirteen` (`:32285`) to the number it actually asserts**, appending this
change's own sentence to its narrated history.

### Decision D10: `settle`'s write set narrows from "every holder" to "the one resolved holder"

**Choice.** All five `settle` modes (create, `--attach`, `--remove`,
`--reverse`, `--done`) write, so all five resolve through
`holder_resolution` and search exactly one file. The heading search
(`:14552-14570`) and the text search (`:14380-14398`, and the `--remove`/
`--reverse`/`--done` copies) iterate `[resolution["write"]]`.

**Alternatives considered.** Keep the modifying modes searching every
by-shape holder, and narrow only the create mode. Rejected: `--attach` and
`--done` write bytes into whichever file the line was found in. On a target
adopted with `TASKS.md`, that is a write into a holder this skill did not
declare — the D3 middle row, reached through the back door.

**Rationale and its cost, stated rather than hidden.** On a target whose
checklist is named something this skill did not declare, `settle --done` can
no longer tick an existing item; it refuses `HOLDER_UNDECLARED` and names the
two exits. That is D3 applied consistently, and it is a real narrowing of
today's behaviour.

Secondary effect: `SETTLE_TEXT_AMBIGUOUS` (`:14392-14397`) and
`SETTLE_HEADING_AMBIGUOUS` (`:14564-14569`) become reachable only from
duplicates *within one file*, and their messages currently interpolate
`len(holders)` ("across N holder(s)"). Both messages must be re-authored for a
single holder. No sealed case reaches either code, and `tests/seal`'s `settle`
case has exactly one holder (`Seal/AGREED.md`,
`tests/seal/corpus.py:272`), so no digest moves — but the message change is
real and must be asserted.

### Decision D11: Seal strategy — the proposal seal's zero delta is enforced by never recapturing it

**The two corpora are asymmetric and the asymmetry is mechanical, not a
judgement call.** Both seals digest normalized stdout + exit status only
(`tests/seal/harness.py:215-226`) — never the target tree. And both pin their
corpus builder's own bytes: `CORPUS_FINGERPRINT_SOURCE = Path(__file__)`
(`tests/seal/corpus.py:342`, `tests/experiments_seal/corpus.py:460`), asserted
at `tests/test_implementation_seal.py:519-522` and
`tests/test_experiments_seal.py:151-155`.

Therefore `tests/seal/`'s 28 digests can move through exactly three channels,
and all three are closed by construction:

| channel | closed by |
|---|---|
| the printed `holder` path (`position_state:777`; `cmd_position:12376/12404/12411`; `cmd_settle:14610/14615`) | `proposal-implementation` declares `AGREED.md` — the name its fixture and its live target already use (`tests/seal/corpus.py:272`) |
| a refusal message or `resolve` text a sealed case reaches | no sealed case reaches any holder code — `HOLDER_ABSENT` appears nowhere under `tests/seal/` or `tests/experiments_seal/` (grep-verified; only `tests/test_*.py:20061, 22968, 23510, 23756, 24008, 24281` and `test_implementation_pair.py:481`) |
| `tests/seal/corpus.py`'s own bytes | that file is **not edited by this change** |

A fourth channel must be actively declined: `agreements_state`'s `searched`
value is `f"{name}/*.md"` (`:488`, `:499`) and reaches stdout via `verify`.
**It stays exactly as it is.** The read really does still scan `*.md`, so the
honest string and the zero-delta gate happen to agree.

**Order of operations, and the one prohibition that protects the 28:**

1. Land the declaration (slice 1, behaviour-free). Run both seals. Both green,
   **no recapture of either**. Gate: `digests.json` unchanged in both
   directories. Neither fingerprint covers `impl_profile.py`, so this step
   cannot move either seal.
2. Bring the resolution change **and** `tests/experiments_seal/corpus.py:344`'s
   rename (`Trial/AGREED.md` → `Trial/Experimental_AGREED.md`) into **one**
   commit. They cannot be split: landing the resolution alone makes every
   experiments-seal write case refuse `HOLDER_UNDECLARED` against its own
   fixture, producing an intermediate digest set nobody wants captured.
3. At that state, **before any recapture**, run
   `.venv/bin/python -m pytest tests/test_experiments_seal.py`. Record the
   exact failing case ids plus the fingerprint failure. **That list is the
   declared delta** — recorded from the failure set, not discovered after the
   recapture.
4. At the **same** unrecaptured state, run
   `.venv/bin/python -m pytest tests/test_implementation_seal.py`. It must be
   **green**. This is the zero-delta gate, and it must run at every commit of
   slices 2–5, not once at the end — running it only after a recapture would
   hide exactly the movement it exists to catch.
5. Recapture the experiments seal only:
   `.venv/bin/python tests/experiments_seal_capture.py`.
6. Assert the recaptured moved set **equals** the list recorded in step 3.

**Prohibition (the single strongest protection for the 28):
`tests/seal_capture.py` MUST NOT be run at any point in this change.** It is
the only thing that can absorb a proposal-side movement silently, and its
own docstring says it is "invoked by hand … only when the roster or the
sealed behaviour has genuinely changed". Here, neither has.

**The declared delta is also recorded as a check, not only as prose.** A new
test in `tests/test_experiments_seal.py` asserts the *reason*: every case whose
output carries a holder path carries `Trial/Experimental_AGREED.md` and never
`Trial/AGREED.md`. This turns "the digests moved" from an unexplained fact
into a checked claim — the shape this project already requires ("an anchor
that matched is not a mutation that ran").

### Decision D12: The doctrine edit surface, per site

Verdicts for the proposal's 7 + 3 table, resolved by measurement:

| # | Site | Verdict | Resolution |
|---|---|---|---|
| A1 | `agreements_state` doctrine `:381-385` | **narrowed** | "Found by shape, never by name" and its whole stated reason are kept **verbatim** as the READ rule — they remain literally true, because the code beneath them is unchanged (D2/D3). One paragraph is added: the declared name owns WRITES, and the engine invents no filename because it holds none. |
| A2 | `_chosen_holder` `POSITION_HOLDER_ABSENT` `:11844-11848` | **amended (behaviour)** | Body becomes a `holder_resolution` dispatch (D2). The code survives, narrowed to "no product folder to create a holder in" (D9). Its docstring's stale cross-reference to "140-145" (`:11839-11840`) is repointed at `agreements_state`'s real doctrine lines and at `holder_resolution`. |
| A3 | `cmd_settle` `SETTLE_HOLDER_ABSENT` `:14369-14373` | **amended (behaviour)** | "settle never invents a file to write into" → "settle writes only into the holder this skill declares, and creates that one when the product folder holds none". Narrowed identically. |
| A4 | `cmd_settle` docstring item 12 `:14149-14154` | **amended (prose)** | It enumerates the contract and cites "the same doctrine `_chosen_holder` already states". Both halves move in the same commit or the enumeration lies about the code under it. |
| A5 | question `SETTLE_HOLDER_ABSENT` `:19284-19287` | **amended (prose)** — *not* retired | Re-authored for D9's narrow case. "Which file holds the agreements?" is answered by the declaration; the surviving question is about the product folder. |
| A6 | question `POSITION_HOLDER_ABSENT` `:19334-19337` | **amended (prose)** — *not* retired | Identical. |
| A7 | `tests/test_implementation_pair.py:477-485` | **amended** | Its comment asserts "an empty product dir refuses `POSITION_HOLDER_ABSENT` before the install below ever gets to write anything" — false after D5. The fixture pre-writes `AGREED.md` under the **two-document** profile (`:483-485`), i.e. it encodes today's collision; it moves to `Experimental_AGREED.md`. |
| B1 | `position_state` comment `:644-646` | **narrowed** | Describes the read path, which is unchanged; gains a pointer to the declared-name write rule. |
| B2 | `cmd_position` sweep comment `:12090-12092` | **amended** | The sweep gains the declared lookup ahead of the glob. The glob itself survives — `holder_digests` needs a pre-image per candidate (`:12095-12108`), which is a different requirement from choosing a holder. |
| B3 | `cmd_position` docstring `:12036-12041` | **amended** | This is the sentence describing the mechanism being changed. |

The 18 literal `AGREED.md` mentions, verified by grep as 15 in
`implementation_engine.py` (`:304, 575, 2388, 4887, 5029, 11083, 12005, 13892,
15746, 18501, 18866, 18916, 18946, 18986, 18992`) and 3 in `impl_position.py`
(`:20, 270, 1139`):

- **Amend to name the declared leaf (7) — the four assertions of fact plus
  three engine-voice namings:** `:575`, `:2388`, `:12005`, `:18501`,
  `:18946`, `:18986`, `:18992`. These read as the engine naming a file, and
  each is already false today for any target that named its checklist
  differently.
- **Amend, and verify the seal first (2):** `:4887` and `:5029` are inside a
  **template string written into a target's `__init__.py`**, not a docstring.
  Editing them changes emitted file bytes. The seals digest stdout only
  (`harness.py:218-226`), so the expectation is no movement — but that is a
  measurement, not a claim: re-run both seals after this edit before
  committing it, and if a digest does move, the movement belongs to the
  experiments seal's declared-delta list and to nothing else.
- **Leave standing (9) — each quotes a specific target's own artifact or a
  dated measurement against it:** `:304` (a scan of one target's `AGREED.md`,
  "zero hits across 114 checklist lines"), `:11083`, `:13892`, `:15746`,
  `:18866`, `:18916`, and `impl_position.py:20, 270, 1139` (`:270` is dated
  "2026-08-29"; `:1139` cites that document's own `\tag{}` bytes). Rewriting a
  dated measurement of a named file to name a leaf instead would destroy the
  evidence, not generalize it.

**Success criterion this makes checkable.** "No holder filename literal
remains as an engine-side default or fallback — grep-provable" is satisfied by
the *amend* set, not by the *leave-standing* set: the surviving mentions are
quotations with a named subject, never a value any code reads. The test is a
grep for `AGREED` in a **code** context (a string assigned, compared, or
joined into a path), not a grep for the word.

## Data Flow

```
PROFILE["holder"]  ──resolve──→  impl_domain_profile._resolve()
  {filename, headings,           presence tier (:238-241)
   scaffold}                     + shape tier (D4, new)
        │                                 │ refuses ..._INCOMPLETE / ..._INVALID_HOLDER
        ↓                                 ↓ (ImplementationProfileError — invisible to the 118)
  HOLDER_FILENAME / HOLDER_HEADINGS / HOLDER_SCAFFOLD   (engine, beside DOCUMENTS :176)
        │
        ↓
  holder_resolution(target, name)   ← agreements_state(...)["holders"]  (verbatim, unchanged)
        │                              product.glob("*.md")  (by-shape, kept)
        │
        ├─ action="declared"  ──→ read & write the declared file
        ├─ action="create"    ──→ write HOLDER_SCAFFOLD, then the caller's splice
        ├─ action="undeclared"──→ read by shape;  WRITE ⇒ HOLDER_UNDECLARED (2 exits)
        └─ action="ambiguous" ──→ POSITION_HOLDER_AMBIGUOUS (unchanged)
        │
        ├──→ _chosen_holder (:11830)        ├──→ cmd_settle (:14368, :14380, :14552)
        ├──→ cmd_position sweep (:12093)    └──→ position_state (:648)
        │
        ↓  --repair-header
  _header_document_count_detail(block)  ──→ repairable? ──yes──→ re-render header w/o documents=
        (asymmetric, D8)                        └──no───────────→ HOLDER_REPAIR_AMBIGUOUS
```

## File Changes

| File | Action | Description |
|---|---|---|
| `skills/_core/implementation/impl_domain_profile.py` | Modify | 3 pairs into `_REQUIRED_PRESENCE` (`:67-90`); new shape tier + `..._INVALID_HOLDER` after the presence loop |
| `skills/_core/implementation/engine/implementation_engine.py` | Modify | `HOLDER_*` constants beside `DOCUMENTS` (`:176`); new `holder_resolution` after `:510`; new `_header_document_count_detail` beside `_bound_to` (`:538`); `position_state` `:644-660`; `_chosen_holder` `:11830-11856`; `cmd_position` sweep `:12090-12142` + `--repair-header`; `cmd_settle` `:14368-14373`, `:14380-14398`, `:14552-14570`; `GATING_REFUSALS` `:18402-18521`; question table `:19274-19347`; doctrine + 9 prose sites per D12 |
| `skills/_core/implementation/impl_position.py` | Modify | nothing functional — `:20`, `:270`, `:1139` all **leave standing** per D12 |
| `skills/proposal-implementation/impl_profile.py` | Modify | declares `AGREED.md` + `("# Agreed", "## Ladder")` + `"# Agreed\n\n## Ladder\n"` |
| `skills/experimental-implementation/impl_profile.py` | Modify | declares `Experimental_AGREED.md` + the same scaffold |
| `tests/fixtures/two_documents/impl_profile.py` | Modify | must declare the leaf or every test loading it dies at import |
| `skills/experimental-implementation/references/usage.md` | Create | holder obligations only; no `references/` exists today |
| `skills/{proposal,experimental}-implementation/SKILL.md` | Modify | holder naming follows the declaration |
| `tests/test_implementation_profile.py` | Modify | `_cut2_profile` (`:556-614`) gains the section; `_CUT2_LEAVES` (`:477-508`) gains 3 entries; `_without_leaf` (`:638-654`) handles them (plain `section.key` — no indexed branch needed) |
| `tests/test_experimental_implementation.py` | Modify | its `_to_source` profile builders (`:162`, `:220`, `:438`) gain the section |
| `tests/test_implementation_domain_mutation.py` | Modify | the inline `PROFILE = {` fixture at `:652` |
| `tests/test_proposal_implementation.py` | Modify | 6 `*_HOLDER_ABSENT` assertions (`:20061, 22968, 23510, 23756, 24008, 24281`) move to the narrow case or to `HOLDER_UNDECLARED`; roster/count (`:32242-32324`); **rename** the count test (`:32285`) |
| `tests/test_implementation_pair.py` | Modify | A7: comment `:477-482` + holder name `:483-485` |
| `tests/test_implementation_core.py` | Modify | 2 `AGREED` references |
| `tests/experiments_seal/corpus.py` | Modify | `:344` rename → declared delta + fingerprint movement |
| `tests/experiments_seal/digests.json` | Regenerate | step 5 of D11, once |
| `tests/test_experiments_seal.py` | Modify | new declared-delta reason test (D11) |
| `tests/seal/corpus.py`, `tests/seal/digests.json`, `tests/seal_capture.py` | **Unchanged — hard gate** | D11's prohibition |
| `openspec/specs/` | Modify | 2 new capability specs + 3 delta specs (spec phase, in flight) |

## Interfaces / Contracts

```python
# skills/_core/implementation/impl_domain_profile.py  — added to _REQUIRED_PRESENCE
("holder", "filename")    # str: exactly one path component, ends ".md"
("holder", "headings")    # non-empty sequence[str]: full heading lines
("holder", "scaffold")    # str: the created holder's bytes, verbatim

# shape tier, refusing IMPLEMENTATION_DOMAIN_PROFILE_INVALID_HOLDER:
#   filename: non-empty, Path(f).name == f, no "/" "\\" NUL newline, not "." ".."
#   filename: endswith(".md")
#   headings: non-empty, every entry a str
#   every heading occurs in scaffold as a full line, stripped-equal, unfenced
#     (locate_headings' own rule, impl_position.py:366-389)


# skills/_core/implementation/engine/implementation_engine.py
HOLDER_FILENAME = PROFILE["holder"]["filename"]
HOLDER_HEADINGS = tuple(PROFILE["holder"]["headings"])
HOLDER_SCAFFOLD = PROFILE["holder"]["scaffold"]


def holder_resolution(target: Path, name: str) -> dict:
    """Total. Never raises. Uniform key set on every branch.

    D3's table, as data:
      declared exists            -> action "declared", write = that path
      declared absent, byShape=0, product.is_dir()      -> "create"
      declared absent, byShape=0, not product.is_dir()  -> "absent"
      declared absent, byShape>=1                       -> "undeclared"
      more than one candidate for the caller's own question -> "ambiguous"
    """


def _header_document_count_detail(block: dict) -> str | None:
    """Today's ASYMMETRIC condition, extracted verbatim from cmd_position's
    sweep (:12126-12133). None when they agree. Never symmetric -- the
    opposite direction is the deliberate silent migration (:12116-12125)."""
```

New refusal codes and their classifications (`GATING_REFUSALS`, `:18402`):

```
HOLDER_UNDECLARED          WORK_STATE        # no flag names a holder
HOLDER_REPAIR_AMBIGUOUS    WORK_STATE        # a human decides what the group means
POSITION_REPAIR_CONFLICT   INVOCATION_DEFECT # drop one of the two flags
```

## Testing Strategy

**TDD mode: ON.** `openspec/config.yaml:1` declares `strict_tdd: true`;
`rules.apply.test_command` and `rules.verify.test_command` both name
`npm run test:all` (`:18`, `:20`), which is
`npm run test:node && npm run test:py` (`package.json:11`) — Node `node --test`
plus `pytest`. Both suites are required: this repository has measured that
running one hides a 13-test regression. Use `.venv/bin/python -m pytest`; a
bare `python3.12` yields ~29 environmental failures.

| Layer | What to test | Approach |
|---|---|---|
| Unit — resolver | each of the 3 leaves missing refuses `..._INCOMPLETE` naming it | `_CUT2_LEAVES` + `_without_leaf`, the existing per-leaf walk (`test_implementation_profile.py:681-690`) |
| Unit — resolver shape | `../x.md`, `/abs/x.md`, `a/b.md`, `""`, `.`, `..`, `x.md\n`, `x.sh`, `AGREED` (no suffix) each refuse `..._INVALID_HOLDER` | one `subTest` per adversarial value (threat-matrix row 1) |
| Unit — scaffold agreement | a `headings` entry absent from `scaffold`; one present only inside a ``` ``` ``` fence; one present only as a substring | RED first; each refuses naming the entry |
| Unit — resolution | D3's five `action` outcomes, one test each, from a built product folder | direct `holder_resolution` calls |
| Unit — predicate | `_header_document_count_detail` returns a detail for group-present-under-1-doc and `None` for group-absent-under-2-docs | the asymmetry asserted in **both** directions, so a symmetric "fix" reddens |
| Integration — create | declared absent, no candidate, product dir exists → file created with **exactly** `HOLDER_SCAFFOLD` bytes and zero checklist items, then **read back** through `_chosen_holder` **and** `cmd_settle` | the proposal's High risk; byte-equality, not `assertIn` |
| Integration — create refused | declared absent, no candidate, product dir **absent** → the narrowed `POSITION_HOLDER_ABSENT` / `SETTLE_HOLDER_ABSENT`, and nothing on disk | proves D9's narrowing rather than assuming it |
| Integration — the middle row | declared absent, `TASKS.md` holds items → `verify` reads it by shape; `position`/`settle` refuse `HOLDER_UNDECLARED` with **both** exits in the message | one test per command; assert both exit sentences |
| Integration — the collision | run the experimental profile against a target holding `AGREED.md` → can no longer write a `documents=` group into it | reproduces the measured defect as a test |
| Integration — heading doctrine | after a create, `settle --under "## Ladder"` succeeds; `settle --under "## Nope"` refuses `SETTLE_HEADING_ABSENT` unchanged | proves the doctrine was not weakened |
| Integration — D7 repair | repairable case: group dropped, `revision`/`sha`/`target` and body byte-identical. Ambiguous cases (declared label + revision; legacy block) → `HOLDER_REPAIR_AMBIGUOUS`, nothing written | byte-compare before/after |
| Mutation (reachability) | invert each of the 3 new guards; each must fire. Then delete the declared lookup at **one** of the five sites and assert a comparison test reddens | the standing rule: inverting the guard is the only reachability proof. Beware the same-size `.pyc` trap — assert the mutated anchor count, never `git diff --stat` |
| Roster | `reachable_refusal_codes()` classifies all 3; the count is re-measured and the test renamed | `:32242-32324` |
| Seal | D11 steps 1–6, with step 4 (`test_implementation_seal.py` green, unrecaptured) run at **every** commit | never `tests/seal_capture.py` |

**Known-environmental failures — do not chase these.** Present on the base and
unrelated to this change: `test_forge_gate::GateInterpreterTests` ×3,
`test_papersmith_kit::KitTests` ×3, `test_papersmith_bridges` ×1,
`test_papersmith_executor` ×1,
`test_paper_writing::GroundingThresholdObligationTests`,
`test_papersmith_yamllite::test_repo_papersmith_yaml_parses`,
`test_proposal_implementation::ForgeVocabularyDerivedGuardTests::test_rule_b_
finds_no_target_vocabulary_in_the_forge`. Date any *other* failure before
attributing it to this change.

**A vocabulary caution, not a task.** `ForgeVocabularyDerivedGuardTests`' rule
B derives target vocabulary from `src/` basenames and reads the target from
disk; this project has measured that naming a target module can redden the
forge. The declared values here (`AGREED.md`, `Experimental_AGREED.md`,
`# Agreed`, `## Ladder`) are forge-side artifact names, and `AGREED` is
already present in the engine 15 times — but the new literals live in *skill*
files, which `LockB` scans for engine neutrality. Run the lock family after
the declarations land, before building on them.

## Threat Matrix

This design introduces a profile-declared value joined into a filesystem path
and profile-declared bytes written verbatim into a target file, so the matrix
is applicable — on one row.

| Boundary | Minimum adversarial cases | Applicability | Design response | Planned RED tests |
|---|---|---|---|---|
| Documentation-like paths | `../../AGREED.md`, `/etc/AGREED.md`, `a/b.md`, `""`, `.`, `..`, `AGREED.md\n`, `AGREED\x00.md`, `AGREED.sh`, `requirements.txt`, `AGREED` | **Applicable** — `HOLDER_FILENAME` is joined as `product / filename` and the engine now creates that file | Resolver shape tier (D4/D1): exactly one path component, `Path(f).name == f`, no separator/NUL/newline, not `.`/`..`, must end `.md`. Refuses `..._INVALID_HOLDER` at import, before any command runs. Scaffold bytes are written verbatim — never `eval`, `%`, `.format`, or f-string composition, the same discipline `block_locator.identity` already keeps (`impl_domain_profile.py:376-378`) | One `subTest` per listed value; plus a test that a traversal filename never creates a file outside `product/` |
| Git repository selection | `git -C`, relative, absolute | **N/A** — the target is resolved by `resolve_target` and `require_named_product_dir` unchanged; this change adds no repository or cwd selector | — | — |
| Commit state | staged, `commit -a`, empty index | **N/A** — `require_clean_worktree` already runs ahead of every write verb; creation adds an untracked file inside an already-authorized write, and this change invokes no git | — | — |
| Push state | tracking branch, first push, refspec | **N/A** — no push, ref, or remote | — | — |
| PR commands | `--head`, env prefix, composed | **N/A** — no PR automation | — | — |

## Migration / Rollout

**Delivery: one unsplit PR under the accepted `size:exception`** (tolerance
~1600 authored lines; forecast ~800–1090). The proposal's five slices are an
**implementation ordering hint only** — not PR boundaries. No chaining is
designed.

Ordering constraints that are real regardless of PR shape:

1. The declaration lands first and is behaviour-free — nothing reads the leaf.
   Every profile on disk **and** every test-synthesized profile gains it in
   this step, or the suite dies at import.
2. The resolution change and `tests/experiments_seal/corpus.py`'s rename land
   **together** (D11 step 2). They cannot be split.
3. Create-on-absent lands after resolution; D7's repair lands after the
   extracted predicate.
4. `references/usage.md` and the two `SKILL.md` edits depend only on step 1.

**No committed artifact is rewritten to satisfy the new shape.** No
`position.jsonl` event, no `admissibility.json`, no existing header — except
through `--repair-header`'s explicit, human-visible path.

**The live target is verified clean and needs no migration:**
`implementations/…/AGREED.md` carries 107 hand-curated items, a position
block, and **no** `documents=` group, and `proposal-implementation` declares
the name it already uses. No step of this change touches it.

**Rollback.** Reverting the declaration makes the leaf unread and then
unrequired; by-shape resolution is restored exactly, because it was never
removed — it remains the read fall-back (`AGREEMENTS_GLOB`, `:293`,
`agreements_state:424-425`). A holder already created in a live target
survives a revert and is picked up again by the by-shape scan the moment it
holds its first item; before that it is an item-less markdown file, which is
the state a target with no checklist has always had. Reverting the experiments
seal reverts fixture and digests together, and a mismatch is caught by that
seal's own fingerprint check (`test_experiments_seal.py:151-155`).

## Open Questions

None. D1–D4 and the delivery decision are settled, and the two questions the
proposal left to measurement are answered here by measurement:

- **A5/A6 (retire vs re-author):** re-authored for a narrower case, not
  retired — D5 forbids `mkdir`, so the "no product folder" case stays
  reachable for both codes (D9).
- **The refusal count:** 118 is the live pin (`:32324`), not 113; predicted
  121 after +3 codes and no retirements; **re-measured by running the
  derivation**, never by editing the assertion to match this prediction.

One finding for the implementer that is not a question:
`test_the_derivation_finds_the_measured_one_hundred_and_thirteen` (`:32285`)
asserts 118. Rename it to whatever this change measures, and append this
change's sentence to its narrated history — or the next reader inherits a
sixth-generation stale name.
