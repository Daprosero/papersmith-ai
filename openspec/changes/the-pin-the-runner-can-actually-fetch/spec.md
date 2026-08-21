# Spec Delta: the-pin-the-runner-can-actually-fetch

Change: `the-pin-the-runner-can-actually-fetch` · Domain: `remote-execution` (`scripts/jobfolder.py`, `scripts/remote_cli.py`, `SKILL.md`, `tests/test_remote_execution.py`) · Store: engram (MCP down — mirrored to scratchpad).

No prior spec exists for this capability in the store, so every MODIFIED block below is stated in full and is self-contained. Groups map one-to-one onto the proposal's remaining commits and are independently satisfiable in that order.

Terminology: **the three conditions** are (1) clean tree over the declared clone paths, (2) the pin is HEAD or nothing changed between them under those paths, (3) the pin is published on the declared remote. A **decision point** is any command that writes a job folder or spends remote quota — `generate-job` and `submit`. **Doctrine** is `SKILL.md`. A **refusal** raises and produces no artifact and no submission.

D1 (`generate-job` never side-loading its `--service` adapter) landed at `a60e5d0` and is not specified here.

---

## Group 1 — Commit shape (C4, commit 2)

### ADDED Requirement: A pin MUST be a commit, not a name

Run-config validation MUST refuse a `commit` that is not a lowercase 40- or 64-character hex string. The refusal MUST name the offending value and state that a branch or tag name is not a pin. This requirement MUST land before any default pin exists, because a name-shaped pin makes every downstream check compare a value to itself.

#### Scenario: A branch name is refused

- GIVEN `--commit main`
- WHEN `generate-job` runs
- THEN generation SHALL refuse and the message SHALL name `main`
- AND no job folder SHALL be written.

#### Scenario: A full hex pin is accepted

- GIVEN a lowercase 40-hex commit that satisfies the three conditions
- WHEN `generate-job` runs
- THEN validation SHALL accept the pin
- AND behaviour SHALL be otherwise unchanged.

#### Scenario: Uppercase or truncated hex is refused

- GIVEN a `commit` of `D903D14` or any abbreviated hex
- WHEN validation runs
- THEN it SHALL refuse and SHALL name the value.

---

## Group 2 — The probe asks a question the asker cannot already answer (D2 + C5 + C5b, commit 3)

### MODIFIED Requirement: Reachability MUST be proven from a repository that does not hold the pin

The reachability probe MUST run in a scratch repository created for the probe alone and discarded after it, never in the target. A repository that already holds the pin answers from its local object store and never contacts the remote's upload-pack, so a probe run there passes for every pin anyone would write, including one committed a second ago and never pushed. The probe MUST emulate the runner's own fetch, which is shallow; a full-depth probe both asks a different question and transfers unbounded history on every generation, because `--dry-run` suppresses ref updates and not object transfer. Failure to create the scratch repository is an unanswerable question and MUST refuse on the same path as a refused fetch. The probe MUST NOT write refs, `FETCH_HEAD`, or any object into the target.

#### Scenario: A pin that exists locally and was never pushed

- GIVEN a commit present in the target and absent from the declared remote
- WHEN `generate-job` runs
- THEN generation SHALL refuse, naming the commit and the remote URL
- AND no job folder SHALL be written.

#### Scenario: A published pin passes

- GIVEN a commit the declared remote can serve
- WHEN the probe runs
- THEN it SHALL succeed
- AND the target's refs, `FETCH_HEAD`, and object store SHALL be unchanged.

#### Scenario: The question cannot be asked at all

- GIVEN the scratch repository cannot be created, or the remote is unreachable, or the probe times out
- WHEN the probe runs
- THEN generation SHALL refuse
- AND the message SHALL name the commit and the remote URL.

### ADDED Requirement: The probe MUST carry no more authority than the runner

The environment reaching the probe's git process MAY be widened only for asker-side transport — proxy and trust-store configuration — and MUST NOT be widened for authorization: no credential helper, no agent socket, no user git configuration. The runner clones unauthenticated by construction, so a probe that authenticates would pass for remotes the runner can never clone, which is this change's own defect one layer up. The probe MUST NOT block on an interactive credential prompt; a credential-requiring remote MUST fail fast rather than hold the timeout open. When the probe fails and the declared remote URL is SSH-shaped, the refusal MUST additionally state that the probe is unauthenticated and that such a remote cannot be cloned by a runner either. This SHALL be an enriched message on the existing refusal path, not a new guard.

#### Scenario: An SSH remote

- GIVEN a declared remote URL of `git@host:owner/repo.git`
- WHEN `generate-job` runs
- THEN generation SHALL refuse through the reachability path
- AND the message SHALL name the unauthenticated probe as the reason
- AND no separate SSH-specific guard SHALL exist.

#### Scenario: Authorization never leaks in

- GIVEN a user environment carrying credential, agent, or global-config variables
- WHEN the probe runs
- THEN none of them SHALL reach the git process.

---

## Group 3 — Condition (1): the tree the runner never sees (C1, commit 4)

### ADDED Requirement: Generation MUST refuse a dirty tree over the declared clone paths

Before clone paths are resolved, generation MUST verify that the working tree is clean over the declared clone paths, and MUST refuse otherwise, naming each offending path. Untracked files under a clone path count as dirt: import validation walks the working tree, so an untracked file is code the walk may read and the runner will never receive. Ignored files do not count. A target that is not a repository, or has no history, MUST refuse too — cleanliness that cannot be proven is not cleanliness. The refusal MUST name the commands the operator can run and MUST NOT stage, commit, stash, or otherwise mutate the repository. There SHALL be no flag that accepts a dirty tree.

#### Scenario: A modified file under a clone path

- GIVEN an uncommitted modification to a file under a declared clone path
- WHEN `generate-job` runs
- THEN generation SHALL refuse, naming that exact path
- AND no job folder SHALL be written
- AND the repository SHALL be byte-identical afterwards.

#### Scenario: An untracked file under a clone path

- GIVEN a new, untracked, non-ignored file under a declared clone path
- WHEN `generate-job` runs
- THEN generation SHALL refuse and SHALL name that path.

#### Scenario: Dirt outside the clone paths is irrelevant

- GIVEN uncommitted changes only outside every declared clone path
- WHEN `generate-job` runs
- THEN this condition SHALL pass.

#### Scenario: Cleanliness cannot be proven

- GIVEN a target that is not a git repository or has no commits
- WHEN `generate-job` runs
- THEN generation SHALL refuse and SHALL carry git's own message.

---

## Group 4 — Condition (2): the pin and HEAD (C2, commit 4)

### MODIFIED Requirement: The same staleness verdict MUST refuse at a decision point and report at a read

Generation MUST require that the pin is HEAD, or that nothing changed between the pin and HEAD under the declared clone paths, and MUST refuse otherwise. It MUST obtain that verdict from the one existing staleness computation rather than a second diff, so the generation guard and the read-time report can never drift. `drift` and `unknown` both refuse at generation; `unknown` is never rendered as `fresh`. The asymmetry is deliberate and MUST be documented: the same verdict refuses at a decision point and only reports at `read()`, which is an observation.

#### Scenario: The pin is behind HEAD under the clone paths

- GIVEN a pin whose diff against HEAD under the declared clone paths is non-empty
- WHEN `generate-job` runs
- THEN generation SHALL refuse, naming the changed paths and both commits
- AND no job folder SHALL be written.

#### Scenario: The pin is behind HEAD only outside the clone paths

- GIVEN a pin older than HEAD whose diff under the declared clone paths is empty
- WHEN `generate-job` runs
- THEN this condition SHALL pass.

#### Scenario: The pin is not in local history

- GIVEN a pin absent from the target's history
- WHEN `generate-job` runs
- THEN the verdict SHALL be `unknown` and generation SHALL refuse.

#### Scenario: Reading is still only reporting

- GIVEN an already-generated job folder whose pin has drifted
- WHEN `read()` runs
- THEN it SHALL report `drift` and SHALL NOT refuse.

---

## Group 5 — Condition-dependent default (C3, commit 5)

### MODIFIED Requirement: `--commit` MAY be omitted and then MUST default to HEAD

`--commit` MUST become optional; when omitted, the pin MUST default to the target's HEAD. The default MUST be resolved in one place shared by the CLI and the Python API. An explicit `--commit` MUST continue to mean exactly what it says and MUST NOT be substituted, discovered, or overridden from any remote. The default MUST NOT exist independently of conditions (1) and (2): HEAD is a safe pin only because those two conditions prove HEAD is the code that was validated, so this requirement MUST land after them and MUST NOT be satisfiable while they are absent. The pin and its source MUST be reported on the command's stdout as operator feedback, and the source MUST NOT be recorded in the job folder, where it would describe how the caller typed the argument rather than a fact about the job.

#### Scenario: Omitted with a clean tree

- GIVEN a clean tree over the declared clone paths and a published HEAD
- WHEN `generate-job` runs without `--commit`
- THEN the job folder SHALL pin HEAD
- AND stdout SHALL report the pinned commit and that its source was the default.

#### Scenario: Omitted with a dirty tree

- GIVEN a dirty tree over the declared clone paths
- WHEN `generate-job` runs without `--commit`
- THEN generation SHALL refuse under condition (1)
- AND no pin SHALL be defaulted into a job folder.

#### Scenario: Explicit still means explicit

- GIVEN an explicit `--commit` naming a commit other than HEAD
- WHEN `generate-job` runs
- THEN that commit SHALL be evaluated against the three conditions unchanged
- AND no remote-derived commit SHALL ever be substituted for it.

---

## Group 6 — `submit` MUST gate, not report

### MODIFIED Requirement: A submission MUST be refused before quota is spent, not reported after it

`submit` currently computes a staleness verdict and places it in its return value after the ledger event has already been appended, so the submission has already happened. `submit` MUST instead evaluate the same three conditions against the job folder's declared pin, clone paths, and remote before the adapter is asked to submit and before any ledger event is appended, and MUST refuse when any condition fails. Every refusal MUST name the failing condition with the same message shape generation uses, and MUST NOT commit, push, or otherwise mutate the repository. The staleness value MUST remain in the return payload for callers that read it. An entrypoint with no job folder has no pin, no declared clone paths, and no declared remote, and MUST submit exactly as it does today.

#### Scenario: A dirty tree at submit time

- GIVEN a job folder whose declared clone paths are dirty in the working tree
- WHEN `submit` runs
- THEN it SHALL refuse, naming the dirty paths
- AND no adapter submission SHALL be attempted
- AND no ledger event SHALL be appended.

#### Scenario: The pin drifted since generation

- GIVEN a job folder whose pin now differs from HEAD under its clone paths
- WHEN `submit` runs
- THEN it SHALL refuse before the adapter is called.

#### Scenario: The pin was rewritten or unpushed since generation

- GIVEN a job folder whose pin the declared remote can no longer serve
- WHEN `submit` runs
- THEN it SHALL refuse, naming the commit, the remote, and the missing push.

#### Scenario: A legacy entrypoint is unaffected

- GIVEN an entrypoint with no `run-config.json` beside it
- WHEN `submit` runs
- THEN behaviour SHALL be identical to before this change.

---

## Group 7 — Doctrine

### ADDED Requirement: The three conditions MUST be documented and locked through a table

Doctrine MUST document the three conditions, their order, that both `generate-job` and `submit` enforce them, and the refusal shape. It currently documents the reachability guard nowhere, which is why the defect had no doctrine to contradict it. The documentation MUST be expressed as a parseable table the suite holds to code, per the established local idiom; a lock MUST NOT match free prose. Doctrine MUST also state that the tool never commits or pushes on the operator's behalf, and that there is no dirty-tree escape hatch.

#### Scenario: A condition present in code and absent from the table

- GIVEN a condition enforced at a decision point with no table row
- WHEN the doctrine lock runs
- THEN it SHALL fail and SHALL name the undocumented condition.

#### Scenario: An operator looks up why generation refused

- GIVEN a refusal naming one of the three conditions
- WHEN the operator searches doctrine for it
- THEN the condition, its order, and its remedy SHALL be found there.

---

## Cross-cutting requirements

### ADDED Requirement: Every refusal MUST carry git's own message and name the exact remedy

Every new refusal MUST carry the underlying git message forward, as the existing reachability refusal already does. This is load-bearing rather than stylistic: an existing test asserts on a substring of git's message reaching the caller, and inserting an earlier guard that swallows it would break that assertion. Each refusal MUST also name the exact commands the operator can run — which files are dirty, and the push that is missing, addressed to the declared remote URL and ref. The tool MUST NOT stage, commit, push, stash, or fetch on the operator's behalf, because a commit message is a human artifact and an automatic commit poisons the history later used to say which code produced which number.

#### Scenario: An unanswerable question refuses with git's words

- GIVEN a git invocation inside any of the three conditions that fails
- WHEN the refusal is raised
- THEN the message SHALL contain git's own text and the declared remote URL.

#### Scenario: Nothing is written on the operator's behalf

- GIVEN any refusal from any of the three conditions at either decision point
- WHEN it is raised
- THEN the working tree, index, refs, and remotes SHALL be unchanged.

### MODIFIED Requirement: The existing guard tests MUST be corrected, not routed around

Of the seven existing reachability guard tests, exactly one encodes the defect — the assertion that the probe runs in the target — and it MUST change. The assertion on the probe's exact argv MUST change too, for the shallow depth, which is what makes that suite's own claim that the probe emulates the runner's clone true. Two tests double git with a return object whose output attribute is auto-generated; once generation asks git two further questions, that auto-generated output is truthy and the new guards refuse. Making the double answer as real git answers for a clean tree is a fidelity repair that adds no permissiveness, and MUST be recorded as such so it is never mistaken for routing around a red. Where the diff allows, a real git fixture repository is preferred over a mock. The remaining assertions MUST stay true untouched.

#### Scenario: The defect assertion is gone

- GIVEN the corrected guard suite
- WHEN it runs
- THEN no test SHALL assert that the probe runs in the repository that already holds the pin.

#### Scenario: A new class does not silently shadow an existing one

- GIVEN a new test class added by this change
- WHEN the suite runs
- THEN the total test count SHALL increase by the number of tests added
- AND no existing class name SHALL be redefined.

### ADDED Requirement: Every new lock MUST be proven reachable-red

Each lock that passes on its first run MUST be proven reachable-red by inversion: break the guarded fact, observe the failure, restore by inverse patch. Greenness alone is not evidence a lock runs.

#### Scenario: A lock's reachable-red proof

- GIVEN a new lock that passes on first run
- WHEN the production line it guards is inverted
- THEN the lock SHALL fail
- AND restoring by inverse patch SHALL return it to green.

---

## Explicit non-goals

| Non-goal | Reason |
|---|---|
| Changing `resolve_clone_paths` to walk the pinned tree instead of the working tree | Addressed by condition (1) instead: once the tree is clean over the clone paths and the pin is HEAD, the tree the walk sees and the tree the runner clones are the same bytes. The function is left alone deliberately. |
| Validating that the pin is contained in `repo.ref` | Proving it needs either the ref's whole history — unbounded, the cost the shallow probe exists to avoid — or the remote's tip alone, which is false the moment anyone else pushes. A guard that can only be sometimes right is the same mistake this change is about. `repo.ref` is kept and given exactly one job: the remedy sentence in condition (3)'s refusal. |
| Resolving the pin from the remote when `--commit` is omitted | Verified live: the remote tip is older than the entrypoint the operator needs, which exists only in an unpushed commit. Remote resolution would pin code older than the caller's, pass every local check because generation validates against the working tree, and die in the kernel after quota is spent — the same failure class, reintroduced by helpfulness. |
| A flag that accepts a dirty tree | Rejected by name. |
| Cross-checking a job's declared service against `submit --backend` | A real gap, disjoint blast radius, its own change. |
| A meta-test forbidding duplicate test-class names | A real incident here — a redefined class silently disabled seven tests while the suite still said OK — but cheap and separable. |
| The target's shard declaration marking only one field identical across shards, so two shards may run different code and still pool | Target-side. `implementations/` is read-only by constraint and is never edited. Reported, not fixed. |

## Acceptance

Full discovery green at 791 plus the new tests, with every new lock proven reachable-red, and the count verified to have gone up rather than merely stayed green.

One in-scope item carries no behavioural delta and therefore no requirement: the unreachable `return` at the end of the job-folder destination resolver is removed alongside the last commit. It is stated here so it is not read as scope creep at apply time.
