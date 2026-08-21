# Archive Report: the-pin-the-runner-can-actually-fetch

**Change**: `the-pin-the-runner-can-actually-fetch`
**Phase**: ARCHIVE (terminal record of the cycle)
**Closed at**: 2026-08-21
**Repository**: `/Users/diego/Proyectos/papersmith-ai`
**Evidence revision**: `c4ee27f917c5442616e2eaddfee4ff90ec3bdff6`, branch `main`, working tree clean, `ahead 8`, nothing pushed
**Verification verdict carried in**: `pass_with_warnings` — 0 blockers, 0 CRITICAL, validator-admitted
**Artifact store**: `engram` — **the Engram MCP backend was disconnected for the entire cycle**. Every artifact of this change is a file in a session scratchpad, not an Engram observation. There are no observation IDs to record. See OPEN RISK A.
**Execution mode**: `interactive` · **Delivery strategy**: `ask-on-risk` · **Review budget**: 1200 lines (session)

---

## 1. Gate — re-measured by this phase, not inherited

Nothing in this section is copied from `verify-report` or `apply-progress`. Each figure
was produced by this phase, at `c4ee27f`, with the repository in the state the
orchestrator will push.

| Gate | Command | Result |
|---|---|---|
| Focused suite | `python3 -m unittest tests.test_remote_execution` | **Ran 335 tests — OK**, exit 0 |
| Full discovery | `python3 -m unittest discover -s tests` | **Ran 872 tests — OK**, exit 0 |
| Duplicate class names (this file) | `rg '^class ' tests/test_remote_execution.py \| sort \| uniq -d` | **empty** — no class defined twice (44 classes total) |
| Duplicate class names (all of `tests/`) | `rg --no-filename '^class ' tests/ \| sort \| uniq -d` | **empty** |
| Working tree | `git status --porcelain` | **empty** — clean |
| Branch state | `git status -sb` | `## main...origin/main [ahead 8]` |

Both suite counts match the figures the orchestrator and the verifier measured
independently (335 / 872). The duplicate-class check is not ceremony here: earlier in
this session a redefined class name silently disabled seven tests in this exact file
behind a green suite, so a green suite alone is not evidence and was not accepted as
evidence at any point in this cycle.

### `implementations/` was untouched, proven rather than asserted

`implementations/*` is gitignored, so `git status --porcelain implementations/` is empty
**by construction** and proves nothing. A full content manifest was therefore taken
before and after this phase's test runs, using `manifest.py` (per-file `sha256`, mode and
size for 51,580 entries):

```text
entries: 51580   (before)
entries: 51580   (after)
adaaf1a8c262398e7c48719b1814597257994033c88d5464e728e1260cbc5028  impl.before
adaaf1a8c262398e7c48719b1814597257994033c88d5464e728e1260cbc5028  impl.after
diff impl.before impl.after → (no output)
```

Identical digests, identical entry counts, empty diff. `implementations/` — including
`implementations/Domain_Adaptation`, which constraint C2 forbids editing — is
byte-identical across this phase.

---

## 2. What shipped — eight commits, each with the seam it closed

All eight are local commits on `main`. No branches, no PRs (delivery was settled as
direct commits under `ask-on-risk`).

| # | SHA | Date | Churn | The seam it closed |
|---|---|---|---|---|
| 1 | `a60e5d0` | 2026-08-20 | +73 | **`generate-job` never loaded the adapter its own `--service` named.** The same defect `d0e28fe` had already closed for the four `--backend` commands, surviving under a second spelling of the flag. Reproduced live as `error: "no metadata assembler registered under 'kaggle'"`. |
| 2 | `26d8e57` | 2026-08-21 | +679/−53 | **The reachability probe asked the one repository that already held the answer**, so it could never fail for a pinned commit. `git fetch --dry-run` ran with `cwd=target`; git answered from the local object store and never contacted upload-pack. The guard passed for every pin anyone would write, including one committed a second ago and never pushed. |
| 3 | `b7cb43f` | 2026-08-21 | +214/−3 | **A pin that is a branch name is a pin the runner resolves differently every day.** `--commit main` passed every guard and `readiness` compared `"main"` to itself forever. `COMMIT_PATTERN` (lowercase 40- or 64-hex) now refuses it by shape. |
| 4 | `9224be9` | 2026-08-21 | +656/−49 | **The shared `verify_pin_preconditions` seam, plus condition (1)**: clean tree over the declared clone paths via `status --porcelain` — never `git diff`, which cannot see an untracked `run_search.py`, the exact case the condition exists to catch. |
| 5 | `3ef8dc8` | 2026-08-21 | +506/−5 | **Condition (2), plus the doctrine table.** The staleness verdict only ever *reported*, at the one place that should *refuse*. `_staleness_for` already computed the diff; nothing ever acted on it at a decision point. |
| 6 | `82ceda7` | 2026-08-21 | +562/−34 | **`submit` spent the quota first and reported the staleness afterwards.** The verdict landed in the return payload after `LEDGER.append()` — after the submission had already happened. The gate now sits before the digest walk, the plan, the adapter and the ledger. |
| 7 | `726dd76` | 2026-08-21 | +377/−8 | **`--commit` can be omitted once HEAD is provably the code that was validated** — safe only because conditions (1) and (2) now hold, which is why this landed last of the planned six. |
| 8 | `c4ee27f` | 2026-08-21 | +88/−3 | **The skill said it needed nothing while its one backend needed a command line.** `requirements.txt` gained `kaggle>=1.7`, `## Environment` names the CLI the adapter shells out to, and `KaggleAdapter._run`'s `OSError` refusal now says what to install. See OPEN WARNING 1 — no artifact planned this commit. |

---

## 3. The root — one class, four shapes

Every one of these eight commits closes the same class of defect this session closed
fourteen times over in `proposal-implementation`: **a capability, a dependency or a check
whose two halves nobody joined.** Here it arrived in four shapes:

1. **A loader wired to one spelling of a flag.** The adapter side-load existed and worked
   — for `--backend`. `generate-job` spells it `--service`, and the join was never made
   (`a60e5d0`).
2. **A probe pointed at the one place that could not answer honestly.** The question
   "can the remote serve this commit?" was asked of a repository that already held the
   commit (`26d8e57`).
3. **A verdict computed where it could only report.** `_staleness_for` produced exactly
   the right answer, at `read()`, where refusing is not an option — and no decision point
   ever consulted it (`3ef8dc8`, `82ceda7`).
4. **A dependency the doctrine said did not exist.** The skill declared it needed nothing
   while its only backend needed a command-line tool on `PATH` (`c4ee27f`).

The pattern is not "a bug per file". In every case both halves were present and correct
in isolation; what was missing was the line that joins them.

---

## 4. The structural answer

One public function is the whole answer, and it is deliberately the only thing either
decision point calls:

```python
PIN_CONDITIONS = ("clean-worktree", "pin-is-head", "pin-published")   # order is the contract

def verify_pin_preconditions(*, target, commit, clone_paths,
                             repo_url, repo_ref, decision) -> None: ...
```

Verified on disk at `c4ee27f`, not taken from the design:

| Claim | Evidence |
|---|---|
| Exactly **two production call sites** | `jobfolder.py:772` (`generate_job`, before `resolve_clone_paths()`) and `remote_cli.py:364` (inside `_gate_job_folder_pin`). Definition at `jobfolder.py:1332`. Every other occurrence in `scripts/` is prose in a docstring (`:20`, `:501`, `:743`, `:1280`, `:1313`, `remote_cli.py:326`). |
| **No second implementation of condition (1)** | `status --porcelain` appears **once** in executable code — `jobfolder.py:1183`. The three other hits (`:30`, `:1141`, `:1151`) are docstrings explaining why `git diff` is the wrong instrument. |
| **No second implementation of condition (3)** | `fetch --dry-run` appears **once** — `jobfolder.py:1104`, with `--depth 1`, in a discarded scratch repository. |
| **Order is a constant, not a convention** | `PIN_CONDITIONS` is defined once (`jobfolder.py:1132`) and iterated once (`:1372`). |

Two callers, one implementation, one message shape, one order — by construction rather
than by convention. `decision` (`"generation"` / `"submission"`) is the single word that
differs between the call sites.

---

## 5. The verification's strongest evidence, preserved

Per `verify-report` (verdict `pass_with_warnings`, `evidence_revision`
`sha256:5ac7159e…`, written at `c4ee27f`). These four items are recorded here because
they are the kind of evidence that is expensive to re-create and easy to lose:

**Counts re-derived independently, per commit, by AST.** The test file was parsed at each
of the nine commit blobs, counting `test_*` methods and checking for redefined classes:

```text
6460587 → 253   a60e5d0 → 254   26d8e57 → 264   b7cb43f → 275   9224be9 → 292
3ef8dc8 → 309   82ceda7 → 321   726dd76 → 333   c4ee27f → 335
```

Every delta matched the number of tests the apply record claimed to add, and **zero
duplicate class names at every commit**. This is what makes the count a measurement
rather than a hope: the suite is judged by the number going *up*, never by it staying
green.

**Seven of twenty-six inversions reproduced, and one found the record had *under*counted.**
Moving `_gate_job_folder_pin()` from before `source_digest()` to after `LEDGER.append()`
reddened **7** locks where the apply record predicted 6 — the seventh being the corrected
legacy test. The one numeric disagreement between the two phases was in the
implementation's favour.

**Probe authority proven by planting, not by reading.** `SSH_AUTH_SOCK`,
`GIT_CONFIG_GLOBAL`, `HOME` and `GIT_ASKPASS` were planted in the parent process; the
child's environment was observed to be exactly `{PATH, GIT_TERMINAL_PROMPT=0}`, with
`stdin=DEVNULL`. Separately, after a *passing* probe the target's object count was 24→24,
`git show-ref` was byte-identical, and `.git/FETCH_HEAD` was absent before and after.

**Both apply-record corrections independently confirmed.** (a) A full-depth
`fetch --dry-run` exits **0** from inside the repository that holds the pin, while the
same fetch with `--depth 1` exits **128** (`upload-pack: not our ref`) — so `--depth 1`
alone defeats the local-object-store shortcut, and the scratch repository's remaining
teeth are about *where objects land*, not about the answer. (b) The `_run_git` doubles can
never hold a `cwd` claim, because they replace the function wholesale — there is no git
process left to have a cwd. Task 3.6's recorded outcome ("they do not fail, and no repair
could make them") is correct.

---

## 6. The methodological result

This is the session's recurring lesson, and it arrived twice more inside this change:

1. **A green suite is not proof.** A duplicate class name once hid seven dead tests in
   this exact file while the runner still printed `OK`. Every commit in this change was
   therefore judged by the test count rising by the number of tests added, verified per
   commit by AST at nine separate blobs.
2. **A passing test is not proof either.** `AdapterEnvironmentTests`' first draft went
   *falsely green*: its fixture binary was named `...-not-an-installed-binary-...`, so an
   assertion looking for `"install"` in the refusal message was satisfied by the
   fixture's own name. The test asserted nothing about the code.

Both shapes are now guarded **inside the tests themselves**, not in a convention someone
has to remember. `tests/test_remote_execution.py:8424` names the absent binary
`zzz-no-such-service-binary-zzz`, and `:8430` asserts `assertNotIn("install", absent)`
*before* asserting `assertIn("install", message.lower())` — so the assertion is now
unsatisfiable by the fixture's name. The per-commit count discipline is the guard for the
first shape.

---

## 7. Warnings — recorded as OPEN, not closed

The verdict was `pass_with_warnings` with no blocking risk, so unlike the earlier changes
in this session there was no stale failure to discharge at archive time. These warnings
were not fixed; they are carried forward as-is.

**W1 — An eighth commit no artifact planned.** `c4ee27f` satisfies **no spec requirement**
and completes **no task**. Its content is correct and both its locks are proven
reachable-red, but it entered the change from outside the spec; the spec's own non-goals
table would have been the place to admit or exclude it. Recorded as **in-scope-by-adoption**,
not as spec-derived.

**W2 — Review budget exceeded. This happened; it was not authorized.** Measured churn
`6460587..c4ee27f` is **3,219 insertions + 219 deletions = 3,438 authored lines**, against
a tasks forecast of ~895 and a cached session budget of 1,200. Production and doc churn is
831 lines; tests are 2,388 added / 160 deleted. **No `size:exception` was ever accepted**,
and no chained-PR split was executed. Delivery was settled as direct commits on `main`, so
the 400-line per-PR guard had no PR to bind — but the guard was *exceeded*, not
*satisfied*, and any future reviewer of these eight commits inherits all 3,438 lines at
once. The apply record acknowledged the overrun for slice 3 only (732 vs ~230) and never
restated it for the change as a whole.

**W3 — A refusal path the spec does not name.** A malformed `run-config.json` now refuses
at `submit`. This is the right call — reusing `_job_folder_staleness` was measured to
return `None` for *both* the malformed and the legacy shape, so unreadability would have
bought an exemption from all three conditions. But it is a behaviour change for a state
that previously submitted, carried by commit `82ceda7`'s body rather than by the spec.

**W4 — Spec counts in the verify launch prompt did not match the artifact.** The prompt
declared 12 requirements / 33 scenarios; the spec artifact on disk contains **11
requirements / 30 scenarios**. Verification was performed against the artifact on disk and
used 11/30 as authoritative. If a newer spec revision exists somewhere, the verification
was built against the wrong one. **Unresolved** — no higher-ranked source settles which
count was intended.

**W5 — 19 of 26 claimed inversions were not independently re-run.** Seven were reproduced
(the four the task named load-bearing, plus the doctrine lock and two others). The other
19 rest on the apply record alone. Every attempted reproduction succeeded, and the single
numeric disagreement was in the implementation's favour — but "proven here" and "recorded
there" are different claims and are not merged.

**W6 — `PIN_CONDITIONS` shipped in two steps.** `9224be9` landed a 2-tuple and `3ef8dc8`
inserted `"pin-is-head"` in the middle. The delivered state is the design's 3-tuple in the
design's order; recorded because a bisect landing between those two commits meets a
2-tuple.

**W7 — `validate_commit_shape()` was hoisted ahead of every condition**, beyond the spec's
"run-config validation" wording. It strictly adds a check (both callers exist), and it
avoids a wasted network round trip for a pin that would be refused anyway. Judged sound;
recorded because it widened where a refusal can originate.

**W8 — Task 6.4's second half had no target.** `.claude/skills/remote-execution/references/usage.md`
does not exist — the skill has no `references/` directory. `SKILL.md` was updated instead
and now documents `--commit` as optional.

---

## 8. Recorded, not fixed — carried forward as follow-ups

**Ours, deliberately out of scope:**

- **`resolve_clone_paths` still walks the working tree.** Addressed *by condition (1)*
  rather than by changing that function: once the tree is clean over the clone paths and
  the pin is HEAD, the tree the walk sees and the tree the runner clones are the same
  bytes. The function was left alone deliberately, exactly as the spec's non-goals state.
- **Nothing cross-checks a job's declared `service` against `submit --backend`.** A real
  gap with a disjoint blast radius; its own change.
- **A meta-test forbidding duplicate test-class names.** A real incident here, cheap and
  separable; not this change.

**Target-side and forbidden by constraint C2 — reported, never fixed:**

- The live target `implementations/Domain_Adaptation` declares
  `"identicalAcrossShards": ["epochs"]` only, so `evidence.codeDigest` must be *present*
  but need not *agree*: **two shards can run different code and `merge()` pools them
  silently.** This belongs to the target's own declaration, and `implementations/` is
  read-only by constraint. The manifest in section 1 proves it was not touched.

### Contradiction recorded rather than resolved silently

The archive launch prompt lists **"dead `return destination` at `jobfolder.py:989`"** under
*Recorded, not fixed*. Direct repository evidence at `c4ee27f` contradicts this: `rg -n
'return destination' jobfolder.py` returns exactly two hits, `:204` (the live return of
`resolve_destination`) and `:863` (the live return of `generate_job`). The dead statement
is **gone**. Task 6.3 is checked in the tasks artifact, and `verify-report` records it as
implemented with an AST proof that `read()` has exactly one top-level return. Both
statements are recorded here: the launch prompt's claim (2026-08-21, archive launch) and
the repository evidence plus tasks artifact plus verify-report (all agreeing it was
removed). **Final state: removed.** The prompt's line is read as a stale carry-forward
from the pre-change "Recorded, not fixed" list in `apply-progress`.

---

## 9. Delivery state at close — archiving delivered nothing

Say this plainly, because it is the fact a future reader most needs:

- **Eight commits sit local on `main`. Nothing was pushed at archive time.** `git status -sb`
  reads `## main...origin/main [ahead 8]`.
- **This archive phase pushed nothing, committed nothing, branched nothing, and opened no
  PR.** It ran two test suites, two content manifests and a set of read-only greps.
- The orchestrator pushes these eight commits immediately after this phase returns. The
  **target repository** (`implementations/Domain_Adaptation`) is pushed **separately** and
  by a different actor — and until it is, `generate-job` against that target will still
  refuse under condition (3), correctly: its HEAD `d903d148…` is unpushed and the declared
  remote cannot serve it. That refusal is the change working, not a defect.

**Native review authority**: `reviewGate` is structurally absent for this candidate — no
review was started, so archive proceeds under ordinary repository policy. No receipt was
manufactured and none was required.

---

## 10. Gates and traceability

### Task Completion Gate — PASSED

The tasks artifact contains **43 implementation tasks plus 3 carried open questions, all
`- [x]`**. Zero `- [ ]` items. No stale-checkbox reconciliation was performed or needed.
Open questions Q1 (malformed `run-config.json` refuses at submit — yes), Q2 (seam swap
acceptable — yes), Q3 (probe measurement reported before the two-tier decision — yes,
2.1–2.9 s / 12.35 MiB, fallback **not adopted**) are all answered in the apply record.

### Native Review Receipt Gate — PASSED (`reviewGate` structurally absent)

### Strict archive policy — PASSED

0 CRITICAL findings. 0 blockers. Full artifact set present (explore, proposal, spec,
design, tasks, apply-progress, verify-report). No partial-archive override was requested
or used.

### Mechanical Copy Contract — NOT APPLICABLE, and why

Artifact store is `engram`. Per the archive skill, engram mode **skips filesystem spec
sync and skips the archive folder move** — there is no `openspec/changes/the-pin-the-runner-can-actually-fetch/`
directory to move (confirmed: `fd --no-ignore --hidden 'the-pin-the-runner'` finds nothing
in the repository). **No `cp -R`, `mv` or `git mv` was executed by this phase**, so there
is no source/destination pair to `diff -r`. No file content was routed through model
Read/Write at any point.

The one byte-identity claim this phase *does* make — that `implementations/` is untouched
— is backed by a real before/after content diff, reproduced verbatim in section 1:
identical `sha256` over 51,580 manifest entries and empty `diff` output.

### Artifact index

Engram was disconnected for the whole cycle, so **there are no observation IDs**. The
artifacts are files:

| Artifact | Path |
|---|---|
| explore | `<scratchpad>/the-pin-the-runner-can-actually-fetch-explore.md` |
| proposal | `<scratchpad>/the-pin-the-runner-can-actually-fetch-proposal.md` |
| spec | `<scratchpad>/the-pin-the-runner-can-actually-fetch-spec.md` (11 requirements, 30 scenarios) |
| design | `<scratchpad>/the-pin-the-runner-can-actually-fetch-design.md` |
| tasks | `<scratchpad>/the-pin-the-runner-can-actually-fetch-tasks.md` (43/43 complete) |
| apply-progress | `<scratchpad>/the-pin-the-runner-can-actually-fetch-apply-progress.md` |
| verify-report | `<scratchpad>/the-pin-the-runner-can-actually-fetch-verify-report.md` |
| **archive-report** | `<scratchpad>/the-pin-the-runner-can-actually-fetch-archive-report.md` (this file) |

`<scratchpad>` = `/private/tmp/claude-501/-Users-diego-Proyectos-papersmith-ai/bbf0d055-1eda-4f88-a67c-39777642bdcc/scratchpad`

---

## OPEN RISK A — this audit trail lives only in a session temp directory

Every artifact of this change, including this report, is a file under a session-scoped
scratchpad that does not survive the session. Engram was disconnected for the entire
cycle, so nothing was persisted to the memory backend either.

This is not hypothetical. The **immediately preceding change in this session hit exactly
this**, and was repaired by a separate follow-up commit — `c8a04a0`, *"docs(openspec): the
audit trail of the-flow-names-what-it-needs lived only in a session temp directory"* —
which mirrored that change's eight artifacts into `openspec/changes/the-flow-names-what-it-needs/`.

**This phase did not perform the equivalent mirror**, because the launch prompt named a
single scratchpad output path and forbade committing. The decision belongs to the
orchestrator. The mechanical repair, if wanted, is a `cp` of the eight files above into
`openspec/changes/the-pin-the-runner-can-actually-fetch/` followed by its own commit —
never a Read/Write reproduction of their content.

---

## Verdict

**ARCHIVED — closed with warnings, none blocking.**

All 11 spec requirements and 30 scenarios are satisfied by code on disk and proven by
tests that pass at runtime, re-measured by this phase at 335 / 872 with zero duplicate
class names. All 43 tasks are complete. The three conditions live behind one shared
function with exactly two production call sites, fire in `PIN_CONDITIONS` order, each
carries git's own message forward, and `submit` gates strictly before it spends. Eight
warnings and four follow-ups are recorded above as open. The eight commits are local and
unpushed; this phase delivered nothing.
