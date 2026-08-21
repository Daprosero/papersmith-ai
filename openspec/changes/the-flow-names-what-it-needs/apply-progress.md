# Apply progress: the-flow-names-what-it-needs

Scope of this launch: Phase 0 and commits 1, 2, 3. Store: engram MCP disconnected —
this file is the progress record.

Baseline: `main` at `7b89dd6`, clean. 402 in `tests.test_proposal_implementation`,
743 across `discover -s tests`.

---

## Phase 0 — the forge lexicon (blocking)

### 0.1 Derivation script

`<scratchpad>/derive_rule_b.py` — read-only. Enumerates `implementations/*`
directory names, `src/*` package names and `*.py` module basenames, splits on
non-alphanumerics and camel-case boundaries, drops tokens of 2 characters or
fewer, then searches the four guarded forge surfaces (`SKILL.md`,
`references/usage.md`, `assets/**`, `scripts/**`) with `\bword\b`,
case-insensitive. Nothing under `implementations/` was written.

### 0.2 One derivation run — the verbatim hit list

34 words derived:

    adaptation artifacts attention bag bags benchmark conditional confidence
    config creda digest domain figures global harness init kernel kernels latent
    local mil models objective pipeline renyi report schedules shard shards
    tables term training verdict wiring

27 of them hit a guarded surface. 7 were clean: `bags`, `conditional`, `creda`,
`global`, `mil`, `renyi`, `schedules`.

| word | hits | first places |
|---|---|---|
| adaptation | 5 | `SKILL.md:1487`, `usage.md:311`, `cli:2669` |
| artifacts | 2 | `usage.md:127`, `:129` |
| attention | 3 | `SKILL.md:588`, `:595`, `:1138` |
| bag | 1 | `assets/kit/nb/probe.ipynb:128` |
| benchmark | 110 | `SKILL.md:93` … |
| confidence | 2 | `usage.md:400`, `:488` |
| config | 33 | `SKILL.md:42` … |
| digest | 14 | `assets/kit/nb/report_digest.py:26` … |
| domain | 1 | `cli:1686` |
| figures | 26 | `SKILL.md:901` … |
| harness | 34 | `SKILL.md:217` … |
| init | 2 | `SKILL.md:442`, `usage.md:25` |
| kernel | 2 | `usage.md:248`, `:252` |
| kernels | 1 | `assets/kit/nb/benchmark.py:137` |
| **latent** | **6** | `SKILL.md:1236`, `:1240`, `cli:2725`, `:3365`, `:4039`, `:5114` |
| local | 34 | `SKILL.md:42` … |
| models | 16 | `SKILL.md:326` … |
| objective | 17 | `SKILL.md:1235` … |
| pipeline | 2 | `SKILL.md:1476`, `:1588` |
| report | 190 | `SKILL.md:32` … |
| shard | 12 | `SKILL.md:933` … |
| shards | 6 | `SKILL.md:1560` … |
| tables | 18 | `SKILL.md:899` … |
| term | 27 | `SKILL.md:127` … |
| training | 10 | `SKILL.md:65` … |
| verdict | 53 | `SKILL.md:181` … |
| wiring | 46 | `SKILL.md:225` … |

### 0.3 Triage — every hit exactly once

**(a) `FORGE_LEXICON` — 26 words.** Each carries a reviewed one-line reason in
`tests/test_proposal_implementation.py`. Every one of them was read at its hit
site before being admitted; the borderline ones are recorded here:

- `adaptation` — `SKILL.md:1487` "the arm with its adaptation switched off" and
  `usage.md:311` / `cli:2669` `adaptation(w) == adaptation(w)`, the forge's own
  worked example of an assertion that cannot fail. Ordinary English.
- `attention` — `SKILL.md:588` "spends the reader's attention". Ordinary English.
- `bag` — `probe.ipynb:128` "if one predicts per instance and the other per bag",
  the canonical illustration of two incomparable statistical units.
- `domain` — `cli:1686`, an `ENVIRONMENT_HINTS` entry beside `dataset`, `task`
  and `corpus`. Generic dataset vocabulary, not a target's name.
- `kernel`/`kernels` — `benchmark.py:137` "CUDA and MPS queue their kernels";
  `usage.md:248` invents `src/Example_Method/kernel.py`.
- `artifacts` — `usage.md:127` invents `src/Example_Method/artifacts.py`.
- `harness` — `probe` returns a `harness` key (`cli:2123`) and the doctrine says
  the harness refuses. This is why rule B **cannot** catch
  `harness.render_panorama`, and why rule A exists.
- `tables`/`figures` — also rule A's allowlist; the kit's own report modules.

**(b) Leak, repaired by commit 1 — one word: `latent`.** Six sites, exactly the
six the design lists. It is the live target's own module (`src/MIL_CREDA_Benchmark/
latent.py`) and its own record filename (`__init__.py:142`).

**(c) Rule-C floor.** `latent` is added to the existing fixed list at
`tests:4716-4717`. It is therefore **not** in `FORGE_LEXICON`; the disjointness
meta-test makes that structural.

**Also repaired by hand in commit 1, not derivable by any word rule** (leaked
*attribute* names, confirmed read-only against the target):
`tables.conclusion_rungs` (`cli:2724` ← `tables.py:629`),
`tables.conclusion_geometry` (`SKILL.md:1233` ← `tables.py:809`),
`geometry.ratio` and `domainSeparability` (`cli:5114` ← `__init__.py:184,187`).

### 0.4 Confirming re-run

Run after commit 1's repairs — see the commit 1 section. No third derivation
round was needed.

### Rule A, scoped and measured before it was written

A global scan for quoted `a.b` tokens over the guarded surfaces produced 60+
hits, nearly all real filenames (`README.md`, `poetry.lock`, `google.colab`).
Scoping the rule to lines that also carry a report-declaration key
(`renderers`, `conclusions`, `conclusionEntry`, `objectiveEntry`, `figures`,
`record`) produced exactly 23 dotted names, 7 of them violations and **zero**
false positives:

    LEAK SKILL.md:1232 harness.render_panorama
    LEAK SKILL.md:1236 latent.grid
    LEAK SKILL.md:1240 latent.json
    LEAK scripts/implementation_cli.py:2723 harness.render_panorama
    LEAK scripts/implementation_cli.py:2725 latent.grid
    LEAK scripts/implementation_cli.py:3365 latent.json
    LEAK scripts/implementation_cli.py:4039 latent.json

That measurement is why rule A is line-scoped rather than global.

---

## Commit 1 — F7 leak + derived guard · `5602818`

Tasks 1.1–1.12 all `[x]`. Files: `SKILL.md`, `scripts/implementation_cli.py`,
`tests/test_proposal_implementation.py` (+426/-17 across three files).

### RED, task 1.1 — rule B with an empty lexicon

    FAIL: test_rule_b_finds_no_target_vocabulary_in_the_forge
    AssertionError: {'SKILL.md': ['adaptation', 'attention', …]} != {}
    : these words belong to a repository under implementations/ and are
      neither in FORGE_LEXICON nor repaired

Fired across 13 forge files on 27 derived words — exactly Phase 0's hit list.

### RED, task 1.2 — rule A

    FAIL: test_rule_a_lets_a_worked_example_draw_from_two_module_names
    - [('SKILL.md', 1232, 'harness.render_panorama'),
    -  ('SKILL.md', 1236, 'latent.grid'),
    -  ('SKILL.md', 1240, 'latent.json'),
    -  ('scripts/implementation_cli.py', 2723, 'harness.render_panorama'),
    -  ('scripts/implementation_cli.py', 2725, 'latent.grid'),
    -  ('scripts/implementation_cli.py', 3365, 'latent.json'),
    -  ('scripts/implementation_cli.py', 4039, 'latent.json')]

Named the five sites task 1.2 predicted, plus both defaults. The sixth site
(`cli:5114`) is out of rule A's unit and was caught by rule B.

### The six repairs

| Site | Before | After |
|---|---|---|
| `SKILL.md` worked example | `harness.render_panorama`, `tables.conclusion_geometry`, `latent.grid`, `"latent.json"` | `tables.render_summary`, `tables.conclusion_scale`, `figures.grid`, `"tables.json"` + a paragraph stating the two-name rule |
| `cli:2723-2725` comment | `harness.render_panorama`, `tables.conclusion_rungs`, `latent.grid` | same invented names |
| `cli:5114` comment | "latent-analysis quantities (e.g. `geometry.ratio`, `domainSeparability`)" | "quantities that never sit on a shard — derived readings computed once over everything a campaign produced" |
| `cli:3365` | `contract.get("record") or "latent.json"` | `contract.get("record") or ""`, `in` operator byte-identical |
| `cli:4039` | `contract.get("record") or "latent.json"` | `contract.get("record")` |

### The guard as built

- **Rule A** `test_rule_a_lets_a_worked_example_draw_from_two_module_names` —
  line-scoped to report-declaration keys, allowlist `{"tables", "figures"}`.
- **Rule B** `test_rule_b_finds_no_target_vocabulary_in_the_forge` — derived
  denylist minus a 26-word `FORGE_LEXICON`, each entry with a reviewed reason.
- **Rule C** the existing fixed list, now the named constant
  `FORGE_VOCABULARY_FLOOR`, stated once and gaining `latent`.
- **Meta-tests** `test_every_lexicon_entry_costs_an_argument` (reason ≥ 4 words)
  and `test_the_lexicon_cannot_silence_a_leak_already_found` (disjoint).
- **Silence is announced** — `test_a_clone_with_no_target_skips_instead_of_passing`.

### Inversions actually run

**1.9 — disjointness.** Added `creda` to `FORGE_LEXICON`:

    FAIL: test_the_lexicon_cannot_silence_a_leak_already_found
    AssertionError: Lists differ: ['creda'] != []
    : a word on the floor is a leak somebody already found

Restored by inverse patch; `sha256` back to
`271f6c23df8ba78a854f4c50a2622e4c565cee9809728ef36ee229e3c51352b5`, `cmp` clean.

**1.10 — rule A.** Two purpose-built trees rather than one:
`test_rule_a_names_the_file_a_planted_example_leak_is_in` asserts exactly
`[("scripts/leaky.py", 1, "latent.grid")]`, and
`test_rule_a_objects_to_a_module_the_forge_legitimately_owns` proves the claim
rule A exists for — rule B returns `{}` on a planted `harness.render_panorama`
because `harness` is in the lexicon, and rule A still names it.

**The design's `record` correction, proven rather than accepted.** Inverted
`cli:3365` to `or None` and ran the runtime harness:

    File ".../implementation_cli.py", line 3369, in <genexpr>
        if p.name in (contract.get("record") or None)), None)
    TypeError: argument of type 'NoneType' is not iterable

on a target that declares no record. Restored by inverse patch; `sha256` back to
`922c99b1b3c7d7e3aceb3890cbde1bd4d70c2a70d5c6ad2a7436bad41bcdd08c`, `cmp` clean.

**The skip.** Disabled the `if not targets` guard:
`AssertionError: SkipTest not raised`. Restored by inverse patch, `cmp` clean.

### Task 1.11 — runtime harness

`UndeclaredRecordEndToEndTests`: a real `implementations/_norecord_<pid>` with
`git init`, a declaration with no `record`, one JSON under the product so the
membership test is actually reached, and the CLI run as a process.
`proc.stderr == ""` and `report["status"] == "drift"`. Deleted in `addCleanup`;
a second test calls `doCleanups()` and asserts nothing is left behind.

**Suites**: 411 in `tests.test_proposal_implementation`, 752 across
`discover -s tests`. Both OK. `git status --porcelain implementations/` empty.

---

## Commit 2 — F1, the ask · `866ea79`

Tasks 2.1–2.7 all `[x]`. Files: `SKILL.md`, `tests/test_proposal_implementation.py`.

### RED, tasks 2.1 and 2.2

    FAIL: test_every_declaration_block_has_a_row
    AssertionError: 0 != 1 : the declaration's blocks are stated in no
      parseable table, so which step fills each one is prose and drifts unobserved

    FAIL: test_flow_a_asks_for_the_revision_and_the_premises
    AssertionError: '`revision`' not found in '8. Present the object → module
      map. Wait for approval. Only then write code.'

### GREEN

Step 8 gains the ask, behind step 7's existing gate. No new gate, no
renumbering. `revision` proposed as step 1's `latest` and confirmed inside the
approval; `premises` carried field-for-field from the gate's protocol draft
using the kit's names (`prediction`, `statisticalUnit`, `metric`, `direction`).
The declaration section gains a `| Block | Filled by | When |` table.

**One correction found while writing it.** The first draft's `arms` row said
"Flow A step 9", and `test_every_flow_a_cell_names_a_step_that_mentions_its_block`
fired: `[('arms', 'step 9 never mentions it')]`. That was the test being right —
the doctrine says Flow A stops at the empty container for all four of the
work-read blocks. The row now names Flow B's `wiring-first` rung.

### Inversion 2.6

Changed the `premises` cell to `Flow A step 99`:

    AssertionError: Lists differ: [('premises', 'step 99 does not exist')] != []

Restored by inverse patch, `cmp` against the pre-inversion copy clean.

**Stated limitation, in the class docstring**: Flow A is prose executed by an
agent, so this lock is prose matching and has no behavioural partner. It is the
weakest lock in the change and is labelled as one, in the docstring and in the
commit body.

**Suites**: 415 / 756. Both OK.

---

## Commit 3 — F5, the status roster · `27348f2`

Tasks 3.1–3.7 all `[x]`. Files: `SKILL.md`, `references/usage.md`,
`tests/test_proposal_implementation.py`.

### RED, task 3.2

    AssertionError: 0 != 1 : `verify`'s statuses are stated in no parseable
      table, so the Output Contract cannot be held to what the command returns
    AssertionError: '`coupling`' not found in '## Reading `verify`…'

`returned_keys(CLI, "cmd_verify")` derives 16 keys; minus the three identity
keys that is 13 statuses against the contract's 11. Missing: `coupling`, `lfs`.

### GREEN

- `returned_keys(source, function)` at module level: `ast`, every dict `Return`
  of the named function, nested definitions not descended into, and an
  all-returns-agree assertion.
- Output Contract's inline parenthesised list → a 13-row
  `| Status | What it reports | Gates? |` table; `coupling` documented as
  reported and **never** gating; `lfs` added.
- `usage.md`'s "Reading `verify`" gains both, with what to do about each.

### Task 3.5 — measured, not assumed

No surviving hardcoded eleven-status list existed in the suite. There was
nothing to delete, and that is recorded rather than claimed as work.

### Task 3.6 — the message probe, post-green

Renamed `lfs` → `largeFiles` in a scratch copy of the parsed source:

    Lists differ: ['largeFiles'] != []
      : `verify` returns these and the Output Contract names them nowhere
    Lists differ: ['lfs'] != []
      : the Output Contract names these and `verify` returns no such key

Both sides are named. `test_the_roster_names_a_renamed_key` keeps this in the
suite rather than leaving it as a one-off observation.

### The helper is ready for 4 and 7 — checked, not assumed

    distribution_state RAISES: distribution_state's dict returns do not agree
      on their keys … ['…', 'shardsDisagree', 'status', 'unpartitioned'] vs […]
    remote_execution_jobs_state 3 ['jobs', 'services', 'smokeReady']
    cmd_probe 17 [… 'coupling', … 'remoteExecution', …]

D9 is RED-by-construction as designed: commit 7 gets its lock for free.

**Suites**: 419 / 760. Both OK.

---

# Launch 2 — commits 4, 5, 6, 7 and Phase 8

Scope: commits 4–7 plus Phase 8's closing checks. Store: engram MCP still
disconnected — this file remains the progress record.

Baseline for this launch: `main` at `27348f2`, clean. 419 in
`tests.test_proposal_implementation`, 760 across `discover -s tests`.

**One deviation from the tasks artifact, directed by the orchestrator and
recorded here rather than absorbed silently.** The tasks file assigned F6
(`remote_cli reconcile` named at three ends) to commit 5 and the subcommand
roster to commit 6. The launch prompt reassigned commit 5 to a finding the
design never carried — `usage.md` promises that everything below it is a real
invocation and works none for `probe` — and folded F6 into commit 6, where the
roster makes `reconcile` a required row anyway. Nothing from the design was
dropped: F6 landed in commit 6 with both doctrine ends and the Decision Gates
rows, and one additional finding was repaired.

---

## Commit 4 — F3, `smokeReady`/staleness + the `cmd_probe` roster · `c754996`

Tasks 4.1–4.7 all `[x]`. Files: `SKILL.md` (+55), `references/usage.md` (+29),
`tests/test_proposal_implementation.py` (+273). 357 authored lines.

The orchestrator's decision was taken as given: commit 4 absorbs the `cmd_probe`
status roster, which design D7 had already anticipated ("two new Output Contract
tables"). Identity keys for `probe` are `{status, target, name, kind}` — the
first and the last are string literals in the return, identical for every target
that reaches it — leaving 13 reported facts.

### RED, tasks 4.1 and 4.2

    AssertionError: 0 != 1 : `probe`'s reported facts are stated in no parseable
      table, so the doctrine cannot be held to what the command returns

    AssertionError: 0 != 1 : the job-folder facts folded into `remoteExecution`
      are stated in no parseable sub-table, so nothing holds them to the
      function that computes them

    AssertionError: 'smokeReady' not found in 'No repository yet\nRepository
      empty\n…\nTarget outside `implementations/`, or dirty tree' : no gate row
      tells a reader to read a job that never rehearsed before offering a
      campaign

    ValueError: substring not found          (`## Reading `probe`` in usage.md)

Four failures and one error across five tests.

### GREEN

- `### What `probe` reports, and why none of the job facts is a gate` in the
  Output Contract: a 13-row `| Fact | What it reports | Gates? |` table derived
  against `cmd_probe`'s own return, plus a 3-row
  `| Job fact | What it reports | Gates? |` sub-table derived against
  `remote_execution_jobs_state`.
- Two Decision Gates rows: `smokeReady: false` and `staleness: drift`.
- `## Reading `probe`` in `usage.md`, naming all four staleness verdicts
  including `unreadable`.

### The behavioural partner — and one thing the fixture had to be corrected for

First attempt reused the `poll-first` end-to-end shape and answered
`report-first`, not `benchmark`. That is a real property of every existing probe
fixture in the suite: none of them reaches `benchmark`, because `report_state`
needs a live interpreter and a full report contract. Asserting against a
`report-first` fixture would have made task 4.5 unfalsifiable by construction —
the ladder's rung is guarded by `next_step in ("benchmark", "piloted")`, so an
inversion could not have fired.

So the fixture was built properly: `config.py`, a `tables.py` whose `conclude`
moves with its input, a record on disk, a declared `components` block, and a
`.venv/bin/python` symlinked to the running interpreter. `report: ok`,
`nextStep: benchmark`. A pole test asserts that before any job folder exists.

### Task 4.5 — the inversion, and it fired

Added to `cmd_probe`'s chain, directly after `poll-first`:

    elif next_step in ("benchmark", "piloted") and not all(
            (remote_execution_jobs_state(target).get("smokeReady") or {}).values()):
        next_step = "smoke-first"

Result:

    FAIL: test_a_job_that_never_rehearsed_still_reaches_the_benchmark_offer
    AssertionError: 'smoke-first' != 'benchmark'

    FAIL: test_a_job_pinned_to_a_commit_that_is_not_in_the_history_still_offers_the_run
    AssertionError: 'smoke-first' != 'benchmark'

The pole test stayed green — no job folder means `smokeReady == {}` and
`all({}.values())` is `True` — which is itself the shape of the conflation D5
names. Removed by inverse patch; `sha256` back to
`922c99b1b3c7d7e3aceb3890cbde1bd4d70c2a70d5c6ad2a7436bad41bcdd08c`, `cmp`
clean, `git diff --stat` empty.

**D5 is a decision, not an undefended omission.** Task 4.6's argument and its
falsifier are in the class docstring and in the doctrine.

**Suites**: 428 / 769. Both OK.

---

## Commit 5 — the reference that works no `probe` invocation · `686e5e0`

Tasks 5.1–5.4 all `[x]` (against the reassigned finding). Files:
`references/usage.md` (+73), `tests/test_proposal_implementation.py` (+101).
174 authored lines.

Measured before it was written: `usage.md` carries invocations for `env`,
`plan`, `apply`, `verify`, `admit` and `handoff`, and none for `probe`, `name`
or `compose` — three of the nine commands `COMMANDS` dispatches.

### RED, task 5.1

    AssertionError: Lists differ: ['compose', 'name', 'probe'] != []
    : the CLI dispatches these and `usage.md` works none of them, though it
      opens by saying everything below it is a real invocation

    ValueError: substring not found          (the `## Probe` section)

### GREEN

Three sections, each with the invocation and the shape of the answer:
`name` (the one command with no `--target`), `probe` (with the ten `nextStep`
values, seven prescriptive and three deliberately without a section), and
`compose` (with its three named refusals).

The lock is a roster: `dict_literal_keys(CLI, "COMMANDS")` derives the command
list from the dispatch table, so a command added there fails the suite until
somebody has shown how to run it. `probe`'s invocation is handed to the **real
process** with a target that does not exist: a guard refusal proves argparse
accepted every flag, and an unrecognized flag never gets that far.

### Inversion 5.3

Removed the fenced `probe` invocation:

    AssertionError: Lists differ: ['probe'] != []
    AssertionError: 'implementation_cli.py probe' not found in '## Probe — …'

Restored by inverse patch; `sha256` back to
`8f0da325d0cba14fff6160b889146dfa89a39c36218be471b7f0a76d761e9aac`, `cmp` clean.

**One correction found while writing it.** The first draft said "Eight values
are possible" and then listed ten. `ProbeNextStepSectionTests`'s own derivation
(`all_next_steps()`) has the authoritative set; the prose now splits it seven
prescriptive / three without a section, matching `NO_SECTION`.

**Suites**: 431 / 772. Both OK.

---

## Commit 6 — #8 the seam, and F6 folded into it · `065df8e`

Tasks 6.1–6.7 all `[x]`, plus the whole of Phase 5's `reconcile` work. Files:
`SKILL.md` (+46/-5), `references/usage.md` (+36),
`tests/test_proposal_implementation.py` (+186). 263 authored lines.

`subcommand_surface(source, function)` walks `_build_parser`'s assignments,
following `add_subparsers` groups, and returns **leaves only** with their
declared flags. `smoke` is a group whose subcommand is `required=True`, so
typing it alone is refused and it names no invocation; the leaf is `smoke
record`. Eight entries:

    fetch, generate-job, poll, readiness, reconcile, smoke record, status, submit

### RED, tasks 6.1 and 6.2

    AssertionError: 0 != 1 : the remote-execution subcommands are stated in no
      parseable table, so nothing holds this flow to the CLI it depends on

    AssertionError: '`remote_cli reconcile`' not found in '### `nextStep:
      "poll-first"` …the fix is reconciling the ledger by hand…'

    AssertionError: '`remote_cli generate-job`' not found in '**And `tools/`
      exists for the same reason, reached the same way.** …'

### GREEN

- `### The remote-execution seam — which subcommand answers which reported
  state`, placed immediately after the rung that tells a reader to wait: an
  8-row `| Subcommand | The reported state that routes here | Where the flags
  are documented |` table.
- The drift paragraph now names `remote_cli reconcile` and says what it does,
  in place of "reconciling the ledger by hand".
- Two Decision Gates rows, for `remoteExecution: "drift"` and `"unreliable"`.
- The `tools/` paragraph names `remote_cli generate-job` and the
  `tools/<service>/<job-name>/` shape. No scaffold step, no kit template.
- `## The remote-execution seam` in `usage.md`: three invocations only.

**The no-duplicated-flags rule is measured, not promised.** For each of `poll`,
`reconcile` and `generate-job`, the flags the section shows must be a **proper
subset** of what the parser declares: 2 of 3, 4 of 6, 10 of 17.

### Inversion 6.6

Dropped the `poll` row:

    AssertionError: Lists differ: ['poll'] != []
    : the remote-execution CLI declares these and this skill names them nowhere

    AssertionError: 'poll' not found in {'submit': …, 'status': …, 'fetch': …}

Restored by inverse patch; `sha256` back to
`6aa44d9caba2284bdffa9b0ae74aba1668bde1f8b8994cf02ef4b525a15f92e8`, `cmp` clean.

**Suites**: 436 / 777. Both OK.

---

## Commit 7 — F2, the shard refusal · `21a0064`

Tasks 7.1–7.10 all `[x]`. Files: `SKILL.md` (+18), `references/usage.md` (+32),
`scripts/implementation_cli.py` (+75/-3),
`tests/test_proposal_implementation.py` (+229). 351 authored lines.

### RED, task 7.1 — by construction, as D9 predicted

    AssertionError: distribution_state's dict returns do not agree on their
      keys, so the key set a caller gets depends on which branch answered:
      [… 'note', 'shardsDisagree', 'status', 'unpartitioned'] vs
      [… 'note', 'shardsDisagree', 'status', 'unpartitioned'] vs
      [… 'shardsArrived', 'shardsDisagree', 'status', 'unpartitioned']

**One correction to the design, found by running the lock rather than reading
it.** D9 says the fix is that the early returns gain `shardsArrived`. That is
half of it: the early returns also carry `note`, which the late one does not, so
`shardsArrived` alone leaves the helper red. Full symmetry was the actual
repair — the declared branch gains `"note": None`, which is the honest value
for a distribution that was read and has nothing to explain away. Widening in
both directions; no consumer can break on a key appearing.

### RED, task 7.3

    implementation_cli: error: unrecognized arguments: --shards /var/folders/…
    returncode 2

### GREEN

- `REMOTE_EXECUTION_SHARD_IO_SCRIPT` + `_load_remote_execution_shard_io()`,
  loaded **directly** (D6). No `sys.modules` key, unlike the other two loaders,
  and the docstring says why: they cache because a second copy would break an
  `isinstance`, and `shard_io.py` defines no class at all.
- The `:38-52` import comment widened from two files to three.
- `cmd_verify` builds `merged` inside the `--shards` branch only, reading the
  flag with `getattr(args, "shards", None)`. No test call site edited.
- `main()` adds `--shards` to the `verify` subparser alone.

### The locks, all read off the command's own stdout

| Test | What it proves |
|---|---|
| disagreeing shards | `shardsDisagree == ["epochs"]`, `shardsArrived == ["a","b"]`, `status incomplete` |
| agreeing shards | `shardsDisagree == []`, and the status equals the same target's status with no `--shards` |
| flag omitted | every key but the three the flag moves is byte-equal between the two runs |
| absent directory | `shardsArrived == []`, `shardsDisagree == []` — a smaller campaign |
| malformed `shard.json` | the `JSONDecodeError` propagates out of `read_shards`; exit 1, not a silent absence |
| undeclared distribution | both keys present, `status none` — the symmetry fix, end to end |

**Two fixture corrections, recorded rather than smoothed over.** The agreeing
case first asserted `status == "ok"` and got `incomplete`: this fixture declares
dimensions no `config.py` names, so `notADimension` is non-empty for a reason
that has nothing to do with what came back. The assertion now compares against
the same target with no shards. And the malformed-shard assertion looked for
`shard.json` in the traceback, which carries `read_shards` and the source line
but not the filename.

### Task 7.8 — behavioural variation, not inversion

One shard directory deleted between two runs of the same command over the same
target:

    ["a", "b", "c"]  →  ["a", "c"]

The number moves with the disk, which is the whole objection.

### Task 7.9

`SKILL.md` names `verify --shards <dir>` inside the "Not averages — refuses"
paragraph and states the division of labour explicitly: this skill refuses and
stops, and **never averages, pools or merges** — that is the repository's own
question, answered in its own harness with its own vocabulary. `usage.md` gains
the invocation and the boundary behaviour.

**Suites**: 448 / 789. Both OK.

---

## Phase 8 — closing checks

- **8.1** `eza -a implementations/` shows no `_*` directory. `git status
  --porcelain implementations/` is empty. Every throwaway target
  (`_smokebox_*`, `_shardbox_*`) is deleted in `addCleanup`, and both classes
  carry a `doCleanups()` test asserting nothing is left behind.
- **8.2** Full skill suite green with rules A/B/C active. Measured directly:
  one target on disk (`Domain_Adaptation`), derived denylist of 8 words
  (`bags`, `conditional`, `creda`, `global`, `latent`, `mil`, `renyi`,
  `schedules`), **zero leaks** across all 13 guarded surfaces. All seven words
  the launch flagged as at risk stayed clean across ~1145 new lines of doctrine
  and test prose, so **no lexicon entry was needed and none was added**. Rule A
  reports zero violations. `FORGE_LEXICON` and `FORGE_VOCABULARY_FLOOR` remain
  disjoint.
- **8.3** Seven commits on `main`, `5602818 → 21a0064`. No branch was created
  and none was checked out; the branches in `git branch -a` all predate this
  change. No PR. A scan of all seven subjects and bodies for
  `co-authored-by|generated with|claude|anthropic|ai-assisted` returns nothing.
  Worktree clean.

## Final state

`main` at `21a0064`. **448** in `tests.test_proposal_implementation`, **789**
across `discover -s tests`. Both OK.

Authored lines this launch: 357 + 174 + 263 + 351 = **1145**, against a session
budget of 1200. Every commit is under the 400-line per-unit default and
`git revert`-able alone.

---

# Launch 3 — verify remediation, one test-only commit

Store: Engram MCP disconnected, so this file is the artifact. Prior launches
(commits 1–7, all 31 boxes) are above and unchanged; nothing here supersedes
them.

Work order: the verify report's single CRITICAL — **rule B has no standing
reachability test**. Test-only. No production code and no guard rule touched.

## The gap, restated from the report

The C1 vocabulary guard has three rules. Rule A has
`test_rule_a_names_the_file_a_planted_example_leak_is_in` and rule C has
`test_a_leak_into_a_script_is_caught`; both build a scratch tree, plant a leak,
and read back the file and the word. Rule B — the derived denylist, the entire
subject of Group 1's ADDED requirement — was only ever asserted against the live
checkout, where it is green because nothing is wrong. The verifier proved the
gap by mutation rather than by reading: neutering `leaks`'s matcher left
`Ran 448 tests … OK`.

## What was added

`tests/test_proposal_implementation.py`, inside
`ForgeVocabularyDerivedGuardTests`, +59 lines, two members:

| Member | What it does |
|---|---|
| `scratch_targets()` | Builds an `implementations/`-shaped root owning `Nimbus_Benchmark/src/nimbus_benchmark/{__init__,config,paddock}.py`. Invented names; `addCleanup(shutil.rmtree)`. |
| `test_rule_b_names_the_file_and_the_word_a_planted_leak_is_in` | Asserts `paddock` is in neither `FORGE_LEXICON` nor `FORGE_VOCABULARY_FLOOR`; asserts the derived denylist is exactly `["nimbus", "paddock"]` (so the lexicon subtraction of `benchmark`, `config`, `init` is stated, not assumed); plants `paddock` in one file of a `scratch_forge()` tree and asserts `leaks(...) == {"scripts/leaky.py": ["paddock"]}`. |

Two properties chosen deliberately, both stated in the docstring:

- `paddock` is on no fixed list, so **no fixed-list rule could have caught it** —
  which is the difference between rule B and rule C.
- `paddock` is derived from a **module basename**, not the target's directory
  name, so a rule reading only the top level of `implementations/` would also
  miss it. The test therefore exercises the deep half of `target_words`.

Both helpers already accepted a `root` override (`derived_denylist(root)` for the
target tree, `leaks(denylist, root)` for the forge tree), so **no production code
and no guard rule needed changing** — the parameterization the other two rules
use was already there for rule B.

Rule B's announced silence on a target-free clone is already locked by
`test_a_clone_with_no_target_skips_instead_of_passing`, which asserts the
`SkipTest` and both halves of its reason. Nothing to add; nothing touched.

## RED — the mutation, and what it caught

`tests/test_proposal_implementation.py:8147` (rule B's matcher inside `leaks`):

    -                    if re.search(rf"\b{re.escape(word)}\b", text)]
    +                    if re.search(rf"\bZZZ{re.escape(word)}ZZZ\b", text)]

`python3 -m unittest tests.test_proposal_implementation`:

    FAIL: test_rule_b_names_the_file_and_the_word_a_planted_leak_is_in
          (tests.test_proposal_implementation.ForgeVocabularyDerivedGuardTests)
    AssertionError: {} != {'scripts/leaky.py': ['paddock']}
    - {}
    + {'scripts/leaky.py': ['paddock']} : rule B has to name the file and the
      word, because a guard that reports only that something is wrong repairs
      nothing

    Ran 449 tests in 16.936s
    FAILED (failures=1)

The contrast is the finding closed: the identical mutation was `Ran 448 tests …
OK` before this commit.

## Restore — inverse patch, never `git checkout --`

    $ diff -u tests/test_proposal_implementation.py scratchpad/pristine.py > inverse.patch
    @@ -8144,7 +8144,7 @@
             hits = [word for word in denylist
    -                    if re.search(rf"\bZZZ{re.escape(word)}ZZZ\b", text)]
    +                    if re.search(rf"\b{re.escape(word)}\b", text)]

    $ patch tests/test_proposal_implementation.py < inverse.patch
    patching file 'tests/test_proposal_implementation.py'
    $ cmp tests/test_proposal_implementation.py scratchpad/pristine.py
    (silent — identical)
    $ shasum -a 256 tests/test_proposal_implementation.py scratchpad/pristine.py
    9fb3e7ee3fd8134817db3b061f501e4c1f2ca91218298ac9aec34a1bbbb4aaa9  tests/test_proposal_implementation.py
    9fb3e7ee3fd8134817db3b061f501e4c1f2ca91218298ac9aec34a1bbbb4aaa9  scratchpad/pristine.py
    $ rg -c ZZZ tests/test_proposal_implementation.py   # exit 1, none left

## GREEN

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_proposal_implementation.ForgeVocabularyDerivedGuardTests` | `Ran 8 tests` — OK |
| `python3 -m unittest tests.test_proposal_implementation` | **`Ran 449 tests` — OK** (was 448) |
| `python3 -m unittest discover -s tests` | **`Ran 790 tests` — OK** (was 789) |

## Constraints

- **C1 — the forge stays general.** The suite is green with rules A, B and C
  active, so rule B scanned the change and objected to nothing. Independently,
  the diff's added lines were scanned for all 8 live derived words (`bags`,
  `conditional`, `creda`, `global`, `latent`, `mil`, `renyi`, `schedules`) and
  all 8 floor words: **no match**. `nimbus` and `paddock` appear nowhere else in
  the repository — confirmed with `rg --no-ignore -i` across the whole tree
  before they were chosen.
- **C2 — nothing under `implementations/` edited.** Proven by manifest, not by
  `git status`: `implementations/*` is gitignored, so a clean porcelain there is
  empty by construction. A 51,558-entry manifest (path, mode, size, sha256 for
  every file under 2 MB, symlink target hashed) was taken before any work and
  again after all suite runs. **Byte-identical**, both
  `192ccab41a5ef426e276fa75b89de1cbdec279daf952cf724df28e49107ebeb5`, `diff`
  produces zero lines. `eza -a implementations/` afterwards shows only `.gitkeep`
  and `Domain_Adaptation` — every throwaway target cleaned up.
- **C3 — RED before GREEN.** Transcripts above. The lock could not fail before it
  existed, so the RED is the mutation, and it fires on the new test alone.
- **C4 — one commit on `main`.** `e21f46c`, `test(proposal-implementation): the
  derived guard could be switched off and all 448 tests stayed green`. No branch,
  no PR, nothing pushed (`ahead 8` of `origin/main`). Subject and body scanned
  for `co-authored-by|generated with|claude|anthropic|ai-assisted`: **nothing**.
  Worktree clean.

## Review budget

59 added lines, 0 deleted, one file, one commit. Well inside the 400-line
per-unit default and the 1,200-line session budget. `git revert e21f46c` removes
it alone and restores the pre-remediation state exactly.

## Deviations

None. The remedy is the shape the verify report prescribed and the shape rules A
and C already use. No design decision was taken and no rule was changed.

## Not addressed, by scope

The four WARNINGs and three SUGGESTIONs in the verify report are untouched: the
work order was the CRITICAL alone, and every one of the others is either a
process note (WARNING-1), a documented structural limit (WARNING-2,
SUGGESTION-1, SUGGESTION-2, SUGGESTION-3), a design-record staleness to
reconcile at archive (WARNING-3), or a platform the suite cannot reach
(WARNING-4).
