# Spec Delta: the-flow-names-what-it-needs

Change: `the-flow-names-what-it-needs` · Domain: `proposal-implementation` (the forge: `SKILL.md`, `references/usage.md`, `scripts/`, `assets/kit/`, `tests/`) · Store: engram (MCP down — mirrored to scratchpad).

No prior spec exists for this capability in the store, so every MODIFIED block below is stated in full and is self-contained. Requirement groups map one-to-one onto the proposal's seven commits and are independently satisfiable in that order.

Terminology used throughout: an **agreement test** derives a list from code (AST or filesystem) and holds it to a parseable table in doctrine. **Doctrine** means `SKILL.md` and `references/usage.md`. A **target** is any repository under `implementations/`.

---

## Group 1 — Vocabulary (F7, commit 1)

### MODIFIED Requirement: The forge MUST NOT guess a target's report record name

The forge MUST NOT supply any target-derived filename as a default when a report contract declares no `record`. Where a record name is undeclared, the value MUST be absent and downstream reporting-cell classification MUST treat absence as "not a record cell" rather than substituting a name. Every worked example in doctrine MUST use invented names consistent with the forge's own vocabulary and MUST NOT reproduce a target's module, file, or function names.

#### Scenario: Undeclared record yields no guessed name

- GIVEN a report contract that declares no `record` key
- WHEN the forge classifies reporting cells
- THEN no target-derived filename SHALL be substituted
- AND the cell SHALL be classified as not a record cell.

#### Scenario: Declared record is honoured unchanged

- GIVEN a report contract that declares a `record`
- WHEN the forge classifies reporting cells
- THEN behaviour SHALL be identical to before this change.

### ADDED Requirement: A derived guard MUST catch target vocabulary the forge never listed

The test suite MUST enumerate the vocabulary of every target present under `implementations/` (directory names, source package names, module basenames), subtract a declared forge lexicon of words the forge legitimately owns, and fail when any remaining word appears in a forge file. The failure message MUST name the offending file and word. The guard MUST read `implementations/` read-only and MUST NOT create, modify, or delete anything there. The existing fixed word list MUST remain as a floor. The forge lexicon MUST be an explicit, reviewable declaration.

#### Scenario: An unlisted target word planted in a forge file is caught

- GIVEN a scratch tree whose target owns a word absent from the forge lexicon and from the fixed list
- WHEN that word is planted in one forge file and the guard runs
- THEN the guard SHALL fail
- AND the message SHALL name that exact file and word.

#### Scenario: No target present means silence, not failure

- GIVEN a clone with no repository under `implementations/`
- WHEN the guard runs
- THEN it SHALL skip with an explicit message
- AND it SHALL NOT fail and SHALL NOT report a leak.

#### Scenario: Legitimate forge vocabulary does not fire

- GIVEN a word in the declared forge lexicon that a target also happens to use
- WHEN the guard runs
- THEN that word SHALL NOT be reported as a leak.

---

## Group 2 — The ask (F1, commit 2)

### MODIFIED Requirement: Flow A MUST record the declaration's `revision` and `premises`

Flow A step 8 MUST, behind step 7's existing authorization gate, record the declaration's `revision` and `premises` into the target's declaration before any code that gate authorized is written. `premises` MUST be recorded from the answers the gate already produced — prediction, statistical unit, metric, and direction — using the field names the kit declares, and MUST NOT be invented. `revision` MUST be proposed (default `latest`) and confirmed inside the approval already being requested, never fabricated silently. No new gate SHALL be added and Flow A steps SHALL NOT be renumbered.

#### Scenario: The gate's answers reach the declaration

- GIVEN Flow A has passed step 7's gate
- WHEN step 8 runs
- THEN `revision` and `premises` SHALL be written to the declaration before authorized code is written
- AND `premises` field names SHALL match the kit's declared names.

#### Scenario: The three assertions resolve

- GIVEN doctrine and the kit assert that this flow asks for `revision` and `premises`
- WHEN a reader follows those assertions
- THEN each SHALL resolve to an existing Flow A step that names both fields.

#### Scenario: A first pass no longer dead-ends

- GIVEN a new target that completed Flow A
- WHEN the `declare-first` condition is evaluated
- THEN its named remedy SHALL correspond to a step that exists and has already run.

### ADDED Requirement: A declaration-block roster MUST hold blocks to filling steps

The suite MUST derive the kit declaration's top-level blocks from code and hold them to a parseable block-to-"filled by" table in doctrine. Every table cell naming a Flow A step MUST resolve to a step that exists and names that block. Residual prose matching in that resolution MUST be stated as a known limitation, not claimed away.

#### Scenario: A block nothing fills is caught

- GIVEN a declaration block whose table row names no step, or names a deleted or renumbered step
- WHEN the roster test runs
- THEN it SHALL fail and SHALL name the unfilled block.

---

## Group 3 — `verify` statuses (F5, commit 3)

### MODIFIED Requirement: The Output Contract MUST enumerate every status `verify` reports

The Output Contract MUST present `verify`'s reported statuses as a parseable table, one row per top-level status, stating what it reports and whether it gates. The table MUST include `coupling` and `lfs`. `coupling` MUST be documented as reported and never gating.

#### Scenario: The table matches what the command returns

- GIVEN the statuses derived from `verify`'s returned top-level keys
- WHEN they are compared to the Output Contract table
- THEN the two sets SHALL be equal.

### ADDED Requirement: A status roster MUST hold each documented command's statuses to its table

For each documented command, the suite MUST derive its returned top-level status keys from code (excluding envelope keys such as command, target, and name) and compare them to that command's doctrine table. Divergence in either direction MUST fail and MUST name the diverging keys. The roster MUST demand documentation, not consumption: a status that is documented as never gating MUST pass.

#### Scenario: A status the code returns and the table omits

- GIVEN a status key present in the command's return and absent from its table
- WHEN the roster test runs
- THEN it SHALL fail and SHALL name that key.

#### Scenario: A table row no command returns

- GIVEN a table row naming a status the command does not return
- WHEN the roster test runs
- THEN it SHALL fail and SHALL name that row.

---

## Group 4 — `probe`'s unread facts (F3, commit 4)

### MODIFIED Requirement: `probe`'s reported facts MUST be documented and readable before a campaign

Doctrine MUST present `probe`'s reported facts as a parseable table including `coupling`, remote-execution jobs, `smokeReady`, and job `staleness`. The Decision Gates table MUST carry rows stating that `smokeReady: false` and a drifted `staleness` are reported beside a `benchmark` answer and MUST be read before a campaign is offered. The readiness ladder MUST NOT branch on `smokeReady` or `staleness`; `probe` remains read-only and a target with no remote execution MUST still reach `benchmark`.

#### Scenario: A stale, unrehearsed job is visible at the answer

- GIVEN `probe` reports `smokeReady: false` or drifted staleness alongside a `benchmark` answer
- WHEN a reader follows the doctrine for that answer
- THEN a Decision Gates row SHALL tell them to read those facts before offering a campaign.

#### Scenario: The ladder is unchanged

- GIVEN any target, including one with no remote execution
- WHEN `probe` runs
- THEN the ladder's branch conditions and `nextStep` semantics SHALL be identical to before this change.

---

## Group 5 — The named remedy (F6, commit 5)

### MODIFIED Requirement: A reported drift MUST name the command that repairs it

Where doctrine reports a drifted or unreliable remote-execution ledger, it MUST name the `remote_cli reconcile` subcommand as the remedy, in `SKILL.md`, in the Decision Gates table, and with an invocation in `references/usage.md`. A remedy MUST NOT be described only as manual work, and MUST NOT be reachable only from a Python docstring.

#### Scenario: The remedy is reachable from where the state is reported

- GIVEN a reader who has just read a drift or unreliable state in doctrine
- WHEN they look for the fix
- THEN the exact subcommand SHALL be named there and in the Decision Gates table.

---

## Group 6 — The seam (#8, commit 6)

### ADDED Requirement: Every remote-execution subcommand this flow routes to MUST be named

Doctrine MUST carry a parseable subcommand-to-reported-state table covering all remote-execution subcommands, including `poll`. `references/usage.md` MUST give invocations for `reconcile`, `poll`, and `generate-job` only, and MUST point at the `remote-execution` skill for the remaining flag documentation. Flag documentation MUST NOT be duplicated here. Doctrine MUST state that `generate-job` is the command that places the `tools/<service>/<job-name>/` directory; no scaffold step and no kit template SHALL be added for it.

#### Scenario: A subcommand the flow depends on and no table names

- GIVEN a subcommand present in the remote-execution parser and absent from the table
- WHEN the command-roster test runs
- THEN it SHALL fail and SHALL name that subcommand.

#### Scenario: A rung that waits on a command names it

- GIVEN a rung telling the reader to wait for polling
- WHEN a reader follows it
- THEN the subcommand to run SHALL be named in the table.

#### Scenario: The `tools/` directory has a named producer

- GIVEN doctrine argues the `tools/` directory must exist
- WHEN a reader asks what creates it
- THEN doctrine SHALL name `generate-job` and the path shape it writes.

### ADDED Requirement: A command roster MUST hold the parser to the table

The suite MUST derive the remote-execution subcommand names from that parser, including nested subparsers, and compare them to the subcommand-to-state table. Divergence in either direction MUST fail. A new subcommand MUST therefore force a doctrine decision.

#### Scenario: A new subcommand without a doctrine row fails

- GIVEN a subcommand added to the parser with no table row
- WHEN the roster test runs
- THEN it SHALL fail and SHALL name the undocumented subcommand.

---

## Group 7 — The shard refusal (F2, commit 7)

### ADDED Requirement: `verify` MUST be able to refuse a disagreeing shard set

`verify` MUST accept an optional shard-directory argument. When given, it MUST read those shards, compute disagreements over the fields the declaration marks as identical across shards, and feed the result and the arrived-shard list into the existing distribution merge input, so that `shardsDisagree` and `shardsArrived` are produced from disk. The forge MUST refuse on disagreement and MUST NOT average, pool, or otherwise merge shard results; doctrine MUST state explicitly that the forge refuses and the target averages. The scale reported MUST be recomputed from what actually came back.

#### Scenario: Shards disagree on a declared-identical field

- GIVEN a real shard directory whose stamps disagree on a field declared identical across shards
- WHEN `verify` runs with the shard directory
- THEN `distribution.shardsDisagree` SHALL report that disagreement from the command's own output
- AND `shardsArrived` SHALL list the shards actually read
- AND no averaged or pooled value SHALL be produced.

#### Scenario: Shards agree

- GIVEN a real shard directory whose stamps agree on every declared-identical field
- WHEN `verify` runs with the shard directory
- THEN `distribution.shardsDisagree` SHALL report no disagreement
- AND `shardsArrived` SHALL list every shard read.

#### Scenario: The flag is omitted

- GIVEN `verify` invoked without the shard-directory argument
- WHEN it runs
- THEN its output SHALL be identical to before this change.

### MODIFIED Requirement: `shardsArrived` MUST be reported symmetrically

Every distribution branch that reports `shardsDisagree` MUST also report `shardsArrived`, including the branches for absent, undeclared, and no-shard distributions. The key MUST NOT vanish for some targets.

#### Scenario: A target with no declared distribution

- GIVEN a target whose distribution is absent or undeclared
- WHEN `verify` reports distribution state
- THEN both `shardsDisagree` and `shardsArrived` SHALL be present.

---

## Cross-cutting requirements

### ADDED Requirement: Doctrine locked to code MUST be locked through a table

Any doctrine repaired by this change that is held to code MUST first be expressed as a table the test parses. A lock MUST NOT match free prose. Each lock that passes on its first run MUST be proven reachable-red by inversion: break the guarded fact, observe the failure, restore by inverse patch.

#### Scenario: A lock's reachable-red proof

- GIVEN a new lock that passes on first run
- WHEN the guarded fact is broken and the lock re-run
- THEN the lock SHALL fail
- AND restoring by inverse patch SHALL return it to green.

### ADDED Requirement: The forge stays general and `implementations/` stays untouched

No skill file, template, example, doctrine paragraph, scenario, or fixture introduced by this change SHALL name anything particular to a specific target. No file under `implementations/` SHALL be created, modified, or deleted. Throwaway targets used by tests MUST live outside the real target's path and MUST be deleted after use.

#### Scenario: A target identifier in a forge file

- GIVEN a target's module, package, or directory name appearing in any forge file
- WHEN the vocabulary guards run
- THEN they SHALL fail and SHALL name the file.

#### Scenario: The suite leaves targets untouched

- GIVEN the full suite runs with targets present
- WHEN it completes
- THEN every file under `implementations/` SHALL be byte-identical to before the run.

---

## Explicit non-goals

| Non-goal | Reason |
|---|---|
| Fixing the `p.name in (contract.get("record") or …)` substring test where equality was meant | A distinct defect found while reading this surface; it has its own blast radius and its own reachable-red proof, and folding it in would make commit 1 satisfy two unrelated claims. Reported, not fixed. |
| Making the readiness ladder branch on `smokeReady` or `staleness` | Would convert a reported fact into a gate, change what `nextStep` means, and suppress a legitimate answer for targets with no remote execution. |
| A forge-side average, pool, or merge of shard results | The doctrine promises a refusal. A refusal is generic; an average is not. |
| A kit template or scaffold step for `tools/` | `generate-job` already writes that exact shape and the admission guard accepts it; the gap is one naming sentence. |
| Duplicating remote-execution flag documentation in this skill | Two copies of a flag list is the drift the code already refuses to create. |
| Any edit under `implementations/` | Read-only by constraint; repairs that appear to need one are reported as findings. |
| The undocumented `materialize` command in the accounts skill | Different skill, carries its own credential decision. |
| The stale remote-execution prose claiming probe's remote-execution fact does not exist yet | Different skill; noted, not repaired here. |

## Acceptance

Both suites green — the skill suite and full discovery — plus the new tests, with every new lock proven reachable-red.
