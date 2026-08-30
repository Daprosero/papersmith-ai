# Design: maintenance-blocks-it-does-not-mix

## Technical Approach

One new ledger kind (`defect`), one new declaring verb (`defect`), one derived
predicate (`open_defects`), one refusal (`FORGE_DEFECT_OPEN`) inserted at a
fixed position in seven ladders, and one guarded `except Exception` arm in
`main()`. No new storage, no new file, no schema migration: `append_event` /
`read_events` (`.claude/skills/_core/implementation/impl_position.py`) are
already kind-agnostic, and no reader validates `kind` against an enum.

The whole mechanism reduces to **one comparison of two opaque equality
tokens produced by one function**. Everything below defends that sentence.

---

## Architecture Decisions

### Decision 1: Declaring against an already-absent path is REFUSED

**Choice**: `defect --file <path>` refuses `DEFECT_FILE_ABSENT` when no
regular file exists at the resolved path. Nothing is appended.

**Why this hole is real, and where it actually is.** The reported bypass —
"name a path that does not exist and the defect clears the instant it is
checked" — is not produced by the sentinel. Under a *symmetric* comparison
(`current_token(path) != recorded_token`) an already-absent declaration
records the sentinel, and at check time the path is still absent, so
`sentinel == sentinel` → the defect stays **open forever**, clearable only by
creating a file at a path that never existed. That is a deadlock, not a
bypass.

The bypass appears the moment clearing is written as a **special case**, which
is exactly what the spec's own prose invites: *"When the recorded path no
longer resolves … absence clears the defect."* An implementer reading that
writes `if not path.is_file(): return CLEARED`, and then a declaration against
a never-existing path clears on its first check. So the hole has two halves
and both must be closed:

- **Half A (the shape of the rule)**: clearing is ONE uniform comparison. There
  is no `if not exists` branch anywhere in the clearing path. Absence enters
  only as a value returned by `current_file_digest`. See Decision 3.
- **Half B (the declaration)**: refuse the declaration.

**Alternatives considered**

| Option | Consequence | Verdict |
|---|---|---|
| A. Refuse `DEFECT_FILE_ABSENT` at declaration | Bypass and deadlock both unreachable by construction; declarer learns at the one moment they can fix the path | **Chosen** |
| B. Record it, require something other than continued absence to clear | Introduces a *second* clearing semantics ("a file now exists here"), satisfiable by `touch` — a strictly weaker clear than the byte-edit the normal path demands — and arms an unbounded block on a path nobody will ever create | Rejected |
| C. Allow, let uniform comparison deadlock it | Honest but useless: a permanent block whose only exit is creating a file the forge does not have | Rejected |
| D. Allow, special-case absence to clear | The bypass as reported | Rejected |

**Rationale.** The `defect` command's own contract is *"computes `fileSha256`
from `--file`'s live bytes"*. There are no live bytes. Writing the sentinel
into that field at declaration time records a measurement nobody made — the
precise dishonesty `impl_position.derive`'s `unbacked` key exists to name
(`satisfied is None and mark == "x"`: a tick over a witness nothing measured).
A defect declaration is an assertion that some forge code is wrong; code that
is not there cannot be wrong in the way this mechanism blocks on. The honest
reading of an absent `--file` is a typo or a stale citation, and the honest
response is to say so immediately.

It costs nothing in expressive power. The genuine case — *"the forge is broken
because this module is missing"* — is declarable against the file that fails
to find it, which exists, and which is where the fix lands anyway.

It is also the *cheap* option: `DEFECT_FILE_NOT_FORGE_OWNED` already refuses
at this exact site for a path problem. `DEFECT_FILE_ABSENT` is the same
discipline, same ladder, same call frame, zero new machinery.

**Check order at declaration** (each answers a narrower question than the
last, the ordering discipline `_verify_gate_authorization`'s docstring states):

1. resolve the path (`Path(...).expanduser().resolve()`, non-strict)
2. **containment** → `DEFECT_FILE_NOT_FORGE_OWNED` if not under
   `impl_layout.FORGE_ROOT / ".claude" / "skills"`
3. **existence** → `DEFECT_FILE_ABSENT` if not `path.is_file()`
4. digest

Containment precedes existence deliberately: a path outside the forge tree is
refused as not-forge-owned whether or not it exists, so this command never
reports on the existence of anything outside `.claude/skills/`.

**Residual, stated rather than discovered later.** With Decision 1 in place the
only remaining route to a self-clearing declaration is: declare against a real
file, then delete it. That is the spec's decided behaviour (absence is the
strongest digest change) and is not reopened here. It is a narrow residual:
deleting a live forge file is itself a forge mutation, it is visible in
`git status`, and it will almost certainly make the next command crash — which
auto-records a fresh defect with no cooperation (Decision 6).

### Decision 2: The absent-file sentinel is the fixed non-hex string `"absent"`

**Choice**: `impl_position.ABSENT_FILE_DIGEST = "absent"`, written into
`fileSha256` like any other value.

**Alternatives considered**

| Option | Serialises as | A reader distinguishes it from a missing field by | Verdict |
|---|---|---|---|
| `None` | JSON `null` | `"fileSha256" in event` — and `.get()` returns `None` for BOTH cases | Rejected |
| Fixed non-hex string `"absent"` | `"absent"` | `.get()` alone: `None` now means exactly "key absent" | **Chosen** |
| Empty string `""` | `""` | `.get()` alone, but falsy — collapses under any `if not digest:` | Rejected |
| Separate boolean companion field | two fields | two fields that can disagree | Rejected |

**Rationale.** `append_event` writes `json.dumps(event, sort_keys=True)` — it
writes exactly the keys the dict carries. A key that was never written is
simply absent from the line. `read_events` returns plain dicts, so
`event.get("fileSha256")` collapses "the key is not there" and "the key is
`null`" into the same `None`. This repository has already been bitten by that
class and guards it explicitly by hand: `_derive_record` checks
`"recordFound" not in search` *before* it checks `found is None`, and
`_derive_shard`'s docstring spends a paragraph on `shardsCurrent is None`
meaning "the target declared no way to tell" rather than a value. Choosing
`None` here would add a seventh site where every future reader must remember
the `in` check. Choosing a string makes the field's type uniform — always a
string when present — so the two facts separate at `.get()` with nothing to
remember.

`"absent"` can never collide with a real digest for two independent reasons:
sha256 hex is exactly 64 characters and its alphabet is `[0-9a-f]`; `"absent"`
is 6 characters and contains `s`, `n`, `t`. Either fact alone suffices; both
are stated because one of them surviving a future change is enough.

**On the field name.** `fileSha256` holding a non-digest looks like a type lie.
It is not, because **nothing ever parses this field** — no caller hex-decodes
it, compares its length, or feeds it to anything. It is an opaque equality
token with one distinguished value, and the whole clearing rule is a single
`==` between two tokens from the same producer. The docstring says exactly
that.

**Missing key, fail closed.** A `kind: "defect"` event carrying no
`fileSha256` key at all can only be hand-written or truncated. It is treated
as **open**, with a detail naming its exit: append a fresh `defect` for the
same file (latest-wins supersedes it), which then clears by editing. Fail
closed, and the deadlock has a door.

### Decision 3: Clearing is one uniform comparison; absence is never a branch

**Choice**: exactly one producer,
`impl_position.current_file_digest(path) -> str`, returning
`digest_bytes(path.read_bytes())` for a regular file and `ABSENT_FILE_DIGEST`
otherwise. `open_defects` contains no existence test.

**Rationale.** `digest_bytes`'s own docstring already states the principle:
*"the two sides of a comparison call the identical function rather than each
computing a hash its own way and risking a mismatch that means nothing about
the bytes themselves."* Absence is not an exception to the comparison; it is a
value inside it. Structurally forbidding the `if not exists` branch is what
makes Half A of Decision 1 permanent rather than a rule someone must remember.
A `.pyc`-proof guard: the test in §Testing asserts the clearing path's source
contains no existence branch, and a behavioural test asserts a
never-existing path cannot be armed at all.

### Decision 4: Latest-wins is keyed on the forge-root-relative POSIX path

**Choice**: `file` is stored as the path relative to `impl_layout.FORGE_ROOT`
(e.g. `.claude/skills/proposal-implementation/scripts/implementation_cli.py`).
Re-resolved at check time as `FORGE_ROOT / event["file"]`. Grouping key for
latest-wins is that exact string.

**Alternatives considered**: absolute path (already precedented — `cmd_handoff`
returns `"target": str(target)`), or path relative to `.claude/skills/`.

**Rationale.** A relative path makes the block follow the *code*, not the
checkout: a ledger committed and read from a clone at a different absolute
path still names the same file. It also lets the containment invariant be
re-verified for free on the read side — a stored `file` that escapes
`.claude/skills/` (`..`, absolute) is rejected at read time, so a hand-written
ledger line cannot point the checker outside the forge. Storing relative to
`.claude/skills/` instead would lose the prefix that makes containment
self-evident in the record a human reads.

### Decision 5: Ladder placement — first, and precisely what "first" means

**Choice**: in each of `step`, `gate`, `offer`, `close`, `settle`, `apply`,
`admit`, insert `_require_no_open_defect(target, name)` **immediately after**
`resolve_target(args.target)` and `validate_name(args.name)`, and **before**
`require_clean_worktree` and every target read.

**Rationale.** "First check" cannot be literally first: the ledger lives at
`<target>/<name>/.implementation/position.jsonl`, so the check needs a
resolved target and a validated name to have a path to consult at all. Both
prerequisites are argv-shaped, cheap, and refuse for reasons that correctly
outrank a defect (`OUTSIDE_WORKSPACE`, `NOT_A_GIT_REPO`, name validation) — a
directory that is not a repository has no ledger. The insertion is the same two
lines in all seven; the heads are already uniform:
`cmd_apply` and `cmd_step` both open `resolve_target(args.target)` then
`validate_name(args.name)`, with `require_clean_worktree(target)` next in
`cmd_step`.

`defect` itself is **not** gated on `FORGE_DEFECT_OPEN` and calls no worktree
guard: declaring a second defect while one is open must stay possible, and the
worktree is likely dirty precisely when something is broken. Its append lands
under `.implementation/`, which `impl_guards._is_own_bookkeeping` already
excuses from `DIRTY_WORKTREE`.

### Decision 6: Crash capture that cannot swallow the original traceback

**Choice**: in `main()`, after the existing `except Refused` arm, add
`except Exception` whose entire body is wrapped in its own
`try: … except Exception: pass`, ending in a bare `raise`.

```
try:
    result = COMMANDS[args.command](args)
except Refused as refused:            # unchanged: exit 2, appends nothing
    ...
except Exception:                     # NOT BaseException
    try:
        _record_engine_defect(args, sys.exc_info()[1])
    except Exception:
        pass                          # a failed recorder must be invisible
    raise                             # original propagates unchanged
```

Seven hazards and how each is closed:

| Hazard | Closure |
|---|---|
| The recorder itself raises and becomes the reported error | Inner `except Exception: pass`. Precedent for a deliberately broad guard: `impl_position.write_spliced`'s `except BaseException: unlink; raise` |
| `finally` with a `return` swallows the exception | Never a `finally`; `except` + bare `raise` only |
| `SystemExit` from argparse, `KeyboardInterrupt` from the operator recorded as forge defects | `except Exception`, not `BaseException`. `Refused(Exception)` is caught first, so ordering is load-bearing |
| No `--name` (`env`, `compose`) or no `--target` (`name`) → no ledger path | `getattr(args, "name", None)` / `getattr(args, "target", None)`; either missing → record nothing, re-raise. **Stated limit**: the three structurally unaddressable commands are also structurally un-recordable |
| No `--session` (`apply`, `admit` take none) | `getattr(args, "session", None)`; when absent, **omit the key** rather than write `null` — Decision 2's discipline applied to every optional field |
| The deepest frame is stdlib, not forge code | Walk `exc.__traceback__.tb_next…` and take the **last** frame whose `co_filename` resolves under `FORGE_ROOT/.claude/skills`. `main()`'s own frame always qualifies in practice; the "no qualifying frame → record nothing" fallback exists anyway, because "always" is the kind of claim that ages |
| Recording recurses or dirties the tree | `append_event` only; its path is excused by `_is_own_bookkeeping`. A recurring crash appends a duplicate event, which latest-wins renders harmless |

Argparse failure is out of reach by construction: `parse_args` runs above the
`try`.

**Not changed**: the crash output shape. The exception propagates raw exactly
as it does today. Emitting a JSON envelope would be a second place to lose the
traceback, and it is a separate concern.

### Decision 7: `handoff` surfaces defects in a new key; its `status` is untouched

**Choice**: `cmd_handoff` gains `name = validate_name(args.name)` (argparse
already gives it `--name` via the `else` branch) and one new report key,
`openDefects: [{file, session, detail, at}]`. Its existing
`status: "clear"|"pending"` keeps meaning exactly what it means today —
findings routing.

**Rationale.** Folding forge health into `status` would silently change a
field whose current domain is about the paper's findings, for every existing
reader. A new key is additive. `handoff` performs a new ledger *read* and no
write, so it stays diagnostic.

### Decision 8: Core computes, CLI refuses

**Choice**: `impl_position` gains `ABSENT_FILE_DIGEST`, `current_file_digest`,
and `open_defects(events, forge_root) -> list[dict]`. The refusal wrapper
`_require_no_open_defect` and the crash recorder live in
`implementation_cli.py`.

**Rationale.** `impl_position`'s own doctrine (`locate_headings`: *"This module
stays ignorant of that caller's own refusal vocabulary entirely"*; `WITNESS_RE`:
*"a comment naming one of the caller's own directories teaches the next reader
that the core knows a layout it must always be handed"*). `forge_root` is
therefore an explicit argument, never imported. One derivation serves both the
guard and `handoff`, so the two can never disagree about what "open" means.

---

## Data Flow

```
declare:  defect --file F ──► resolve ──► containment? ──► is_file? ──► digest_bytes
                                 │             │              │             │
                          DEFECT_FILE_    DEFECT_FILE_    DEFECT_FILE_   append_event
                          (path junk)     NOT_FORGE_OWNED    ABSENT       kind:"defect"
                                                                          file: rel-path
                                                                          fileSha256: <hex>

check:   step|gate|offer|close|settle|apply|admit
              │
         resolve_target ─► validate_name ─► _require_no_open_defect ─► require_clean_worktree ─► …
                                                     │
                                            read_events ─► open_defects(events, FORGE_ROOT)
                                                     │
                                    for newest event per `file`:
                                      current_file_digest(FORGE_ROOT/file) == event.fileSha256
                                              │                    │
                                          equal → OPEN        differ → cleared
                                              │
                                       FORGE_DEFECT_OPEN

crash:   main() ─► COMMANDS[cmd](args)
                        │
                 ┌──────┴──────┐
             Refused        Exception
                │               │
          exit 2, no       guarded _record_engine_defect ─► raise (original, unchanged)
          append
```

---

## File Changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/_core/implementation/impl_position.py` | Modify | `ABSENT_FILE_DIGEST`, `current_file_digest`, `open_defects` |
| `.claude/skills/proposal-implementation/scripts/implementation_cli.py` | Modify | `cmd_defect`, `_require_no_open_defect`, `_record_engine_defect`, `_crashing_forge_file`, 7 ladder insertions, `cmd_handoff` `openDefects`, `COMMANDS` entry, argparse (`defect` joins the `--session` set, gains `--file`/`--detail`), `main()` crash arm |
| `.claude/skills/proposal-implementation/SKILL.md` | Modify | `defect` row in the `\| Command \| What it writes \| Refuses on \|` roster; the section that says when the flow stops; both stated limits |
| `.claude/skills/proposal-implementation/references/usage.md` | Modify | worked `implementation_cli.py defect …` invocation (required — see Products) |
| `tests/test_proposal_implementation.py` | Modify | new suites + `write_verbs` set update |

---

## Interfaces / Contracts

```python
# impl_position.py
ABSENT_FILE_DIGEST = "absent"   # 6 chars, non-hex alphabet: never a sha256

def current_file_digest(path: Path) -> str: ...
def open_defects(events: list[dict], forge_root: Path) -> list[dict]: ...
```

Ledger event:

```json
{"kind": "defect", "command": "step", "file": ".claude/skills/…/implementation_cli.py",
 "fileSha256": "<64 hex | absent>", "session": "<id>", "at": "<iso8601>",
 "detail": "<text>"}
```

`command` records the declaring subcommand (`"defect"`) or, for a crash, the
command that crashed. `session` and `detail` keys are **omitted**, never
`null`, when unavailable.

New refusal codes: `FORGE_DEFECT_OPEN`, `DEFECT_FILE_NOT_FORGE_OWNED`,
`DEFECT_FILE_ABSENT`.

---

## What Breaks

### Producers

| Site | Effect |
|---|---|
| `main()`'s dispatch | gains one `except Exception` arm |
| seven `cmd_*` heads | gain two lines each |
| `cmd_handoff` return dict | gains `openDefects` |
| `COMMANDS` | gains `defect` — must stay a **dict literal**, because `dict_literal_keys(CLI, "COMMANDS")` parses it by AST |

### Products (records already on disk under the old shape)

| Product | Where | Verdict |
|---|---|---|
| `implementations/Domain_Adaptation/MIL-CREDA/.implementation/position.jsonl` | on disk | **Untouched.** `kind: "defect"` did not exist, so `open_defects` returns `[]` and no live target becomes blocked by this change |
| `implementations/_ensayo_position/MIL-CREDA/.implementation/position.jsonl` | on disk | Untouched, same reason |
| `remote_cli._verify_launch_authorization`'s fold of the same file | `remote-execution/scripts/remote_cli.py` | Untouched: it selects `kind == "gate"` by exact string; a `defect` line is invisible to it |
| `CommandRosterTests.test_every_command_dispatched_is_accounted_for` | `tests/test_proposal_implementation.py` | **BREAKS.** It asserts `set(impl.COMMANDS) == DOCUMENTED_ELSEWHERE \| write_verbs` — an exact set equality. `defect` must join `write_verbs` **and** earn a row in SKILL.md's command roster |
| `test_every_command_the_cli_dispatches_has_a_worked_invocation` | same file | **BREAKS.** `references/usage.md` must carry a worked `implementation_cli.py defect …` block, and its flags must be accepted by the real parser |
| `test_the_only_things_doctrine_tells_the_agent_to_run_are_cli_commands` | same file | Safe — one-directional (`invoked ⊆ COMMANDS`) |
| README mermaid scan (`\b{command}\b` over `impl.COMMANDS`) | same file | Safe — only asserts the match set is non-empty. Noted because `defect` already occurs as ordinary prose in `cmd_probe`'s docstring, so once it is a command name every `COMMANDS`-driven word scan matches prose |
| `impl_availability.launch_available` call-count pinned at 2 | same file | Untouched: this change adds no call. `cmd_close`'s missing `POSITION_UNBACKED` belongs to `a-pilot-is-the-whole-flow-validated` and is neither designed nor contradicted here |
| Archived reports / manifests | — | None exist for this mechanism; stated rather than left implicit |

---

## Testing Strategy — `strict_tdd: true`

`openspec/config.yaml:1` sets `strict_tdd: true`. Every lock below needs an
observed RED before the guard exists. **A `FORGE_DEFECT_OPEN` that never fires
is byte-identical in every report to one that works**, so reachability is
designed, not assumed.

### The reachability instrument: arm/disarm, not source mutation

Source mutation is the wrong instrument here and is also unsafe: a
**same-size edit can reuse a stale `.pyc`**, so the mutated source never runs
and a dead lock reads as live. Every RED below instead uses **arm/disarm on a
real fixture**, which mutates no source at all:

- **ARMED**: append a real `defect` event for a real forge file at its real
  current digest → the command must refuse `FORGE_DEFECT_OPEN`.
- **DISARMED**: edit that file's bytes in the fixture forge copy (changing its
  size) → the same call must NOT return `FORGE_DEFECT_OPEN`.

Where a source mutation is unavoidable, the task MUST delete `__pycache__`
for the mutated module (or run with `PYTHONDONTWRITEBYTECODE=1`) and assert
the mutation is observable, before reading the verdict.

### Per-command RED: position is proven by which refusal wins

Each of the seven gets its **own** scenario, and each is armed so that a
*different, known* refusal would win if the insertion is missing or misplaced.
This proves "first in the ladder", not merely "present somewhere in it":

| Command | Fixture also arranged so that… | Missing/late insertion returns | Correct returns |
|---|---|---|---|
| `step` | worktree is dirty | `DIRTY_WORKTREE` | `FORGE_DEFECT_OPEN` |
| `gate` | `--authorization` omitted | `GATE_AUTHORIZATION_REQUIRED` | `FORGE_DEFECT_OPEN` |
| `offer` | `--answer` omitted | `OFFER_UNANSWERED` | `FORGE_DEFECT_OPEN` |
| `close` | `--revision` unreadable | `REVISION_UNREADABLE` | `FORGE_DEFECT_OPEN` |
| `settle` | `--under` names no heading | `SETTLE_HEADING_ABSENT` | `FORGE_DEFECT_OPEN` |
| `apply` | `--plan` path unreadable/stale | that plan refusal | `FORGE_DEFECT_OPEN` |
| `admit` | its own first-ladder refusal armed | that refusal | `FORGE_DEFECT_OPEN` |

`gate`'s row is the sharpest: `GATE_AUTHORIZATION_REQUIRED` is a pure-argv
check at the very top of `cmd_gate`'s own ladder, so this scenario fails
loudly for an insertion placed one line too low.

### Diagnostics: seven scenarios, each with a non-vacuity companion

`probe`, `verify`, `position`, `plan`, `compose`, `handoff`, `discuss` each get
their own test asserting a normal answer while a defect is open. **Every one
shares its fixture with an assertion that a spend command IS refused in that
same fixture.** Without that companion all seven pass on a fixture whose arm
never armed — which is exactly how this class of test goes vacuous.

### Clearing and declaration

| Scenario | Assertion |
|---|---|
| byte edit clears | current digest ≠ recorded → next spend call proceeds |
| asserting a fix does not clear | new `defect` with `--detail "fixed"`, bytes unchanged → still refused |
| repeat declaration appends | second event written, call not refused, event count +1 |
| `--file` outside `.claude/skills/` | `DEFECT_FILE_NOT_FORGE_OWNED`, ledger byte-identical |
| **`--file` never existed** | `DEFECT_FILE_ABSENT`, ledger byte-identical — the bypass, closed |
| outside-tree AND nonexistent | `DEFECT_FILE_NOT_FORGE_OWNED` (containment first) |
| deleted after declaration | current = `ABSENT_FILE_DIGEST` ≠ recorded hex → cleared |
| sentinel never equals a digest | `ABSENT_FILE_DIGEST` fails `^[0-9a-f]{64}$` |
| missing key ≠ `None` value | event without `fileSha256` → `.get()` is `None`; treated as OPEN; superseded by a fresh declaration |
| no existence branch | clearing path's source carries no `is_file`/`exists` test outside `current_file_digest` |

### Crash capture

| Scenario | Assertion |
|---|---|
| non-`Refused` crash records | monkeypatched `COMMANDS` entry raises → one `defect` event names the raising frame's forge module and its current digest |
| the original survives | the same exception type and message propagate; nothing is replaced |
| **a failing recorder is invisible** | `append_event` monkeypatched to raise → the ORIGINAL exception still propagates unchanged, and no second error is reported |
| `Refused` records nothing | every ordinary refusal → exit 2, zero `defect` events. **Highest-consequence test in the change**: a `Refused` leaking into the recorder would permanently block the flow on its own refusals |
| `KeyboardInterrupt` / `SystemExit` record nothing | `BaseException` path untouched |
| no `--name` → no record | a crash in `env` appends nothing and re-raises (the stated limit) |

### Per-target scope

An open defect under target A; a spend command against target B in the same
run → no refusal. Locks the non-goal as behaviour.

---

## Vocabulary Guard — EXECUTED

Both rules were **run**, not reasoned about, against the live tree.

**Rule B** (`ForgeVocabularyDerivedGuardTests.derived_denylist`): derived from
directory / package / module basenames under `implementations/`, camel- and
punctuation-split, length ≥ 3, minus `FORGE_LEXICON`. `_ensayo_position` is
skipped by the `startswith((".", "_"))` rule, so the live source is
`Domain_Adaptation` alone. Derived denylist, 10 words:

`bags, ceiling, conditional, contamination, creda, global, latent, mil, renyi, schedules`

**Rule C** (`FORGE_VOCABULARY_FLOOR`, `tests/test_proposal_implementation.py:76`,
word-boundary `\b{word}\b` at `:5215` and `:5258`):
`kaggle, t4, ceiling, ramp, transfer, creda, milcreda, latent`

Every identifier this design introduces, run against both:

`defect` · `FORGE_DEFECT_OPEN` · `DEFECT_FILE_NOT_FORGE_OWNED` ·
`DEFECT_FILE_ABSENT` · `fileSha256` · `ABSENT_FILE_DIGEST` · `"absent"` ·
`openDefects` · `open_defects` · `current_file_digest` ·
`_require_no_open_defect` · `_record_engine_defect` · `_crashing_forge_file`

**Result: zero hits under either rule.** No denylist or floor word occurs as a
`\b`-delimited word in any identifier, and none occurs even as a substring.

Two further notes the implementer needs:

- The one **substring** assertion (`assertNotIn(word, source.lower())`,
  `:10409`) is scoped to `cmd_env` + `manifest_provisioning`, neither of which
  this change touches.
- `global`, `conditional`, `schedules`, `bags` and `contamination` are on the
  live rule-B denylist and are ordinary English. Slice 3's prose in `SKILL.md`
  and `usage.md` is the real exposure; rule B must be re-run against the
  changed files after every prose edit, per the spec's verification
  requirement.

---

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|---|---|---|---|
| Documentation-like paths | **Applicable** — `--file` accepts any path and the engine reads its bytes | Containment to `FORGE_ROOT/.claude/skills` then `is_file()`; bytes are hashed, never executed, parsed or classified by extension | `DEFECT_FILE_NOT_FORGE_OWNED` for a path outside; `DEFECT_FILE_ABSENT` for a directory or nonexistent path; a `.md`/`.sh`/`.txt` under the tree is accepted and only hashed |
| Git repository selection | **Applicable** — the guard runs before `require_clean_worktree`, which shells `git status --porcelain` via `impl_gitops.git` | `resolve_target` (`OUTSIDE_WORKSPACE`, `NOT_A_GIT_REPO`) still precedes the defect check, so no ledger is consulted for a non-repository | armed defect + non-repository target → `NOT_A_GIT_REPO`, not `FORGE_DEFECT_OPEN` |
| Commit state | **Applicable** — every append dirties the worktree by one ledger line | `_is_own_bookkeeping` already excuses `.implementation/`; `defect` and the crash recorder rely on it and add no new exemption | `defect` then `step` in sequence → no `DIRTY_WORKTREE` from the defect's own line; a non-ledger dirty file still refuses |
| Push state | **N/A** — this change performs no push, fetch or remote operation | — | — |
| PR commands | **N/A** — no PR or `gh` automation; the only subprocess in reach is the pre-existing `git status` and `impl_steps.run_step`, neither altered | — | — |

---

## Migration / Rollout

No data migration: no existing ledger carries `kind: "defect"`.

Three slices, rollback per slice, revert-only (append-only ledger means an
already-written `defect` event survives a revert and is simply ignored by the
reverted engine — no in-place mutation to undo):

1. **Record and derive.** `ABSENT_FILE_DIGEST`, `current_file_digest`,
   `open_defects`, `cmd_defect`, both declaration refusals, argparse,
   `COMMANDS`, the SKILL.md roster row and the `usage.md` worked invocation
   (both mandatory in this slice — the two roster tests break the moment
   `COMMANDS` grows). **Inert: blocks nothing.**
2. **Wire the refusal.** `_require_no_open_defect` + seven insertions + the
   seven per-command REDs + seven diagnostic scenarios with their non-vacuity
   companions + `handoff`'s `openDefects`.
3. **Crash capture + docs.** `main()`'s guarded arm, `_record_engine_defect`,
   `_crashing_forge_file`, and the two stated limits written into SKILL.md.

`400-line budget risk: High` — chained PRs recommended, one per slice.

---

## Two Limits, Stated Plainly

**This does not PREVENT mid-flow forge repair; it makes one detected and
blocking.** Verified: `.claude/settings.json` carries one `PreToolUse` hook
owned by another skill and no `permissions.deny` key at all. This design adds
neither. An agent can still edit the forge mid-flow — and doing so now clears
any defect recorded against that file, which is the mechanism working as
specified, not a leak.

**Per-target scope is a non-goal, not an oversight.** A `defect` event is
scoped to the `<target>/<name>/.implementation/position.jsonl` it was appended
to. A shared forge bug blocks only sessions that declared it; a parallel
session on a different target running the identical broken code is not
protected and must rediscover it. Not a global kill switch.

---

## Open Questions

- [ ] `admit`'s own first-ladder refusal is named generically in the per-command
      RED table; the tasks phase must re-locate `cmd_admit`'s actual first
      refusal by name and pin the exact code, rather than inherit this
      placeholder.
- [ ] Slice ordering against `a-pilot-is-the-whole-flow-validated`: both touch
      `cmd_close`'s refusal ladder. Neither design contradicts the other
      (this one inserts above `cmd_close`'s existing head; that one adds
      `POSITION_UNBACKED` inside it), but they will conflict textually.
