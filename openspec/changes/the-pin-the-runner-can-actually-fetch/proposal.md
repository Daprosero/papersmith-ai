# Proposal: the-pin-the-runner-can-actually-fetch

## Intent

`generate-job` writes a job folder pinned to a commit, and a remote kernel later clones
that pin. Two guards stand between the two, and neither works.

`generate-job` cannot reach any service at all (**D1**: the adapter its `--service`
names is never side-loaded; reproduced live as `error: "no metadata assembler
registered under 'kaggle'"`). And the guard that exists to prove the pin is fetchable
(**D2**) runs `git fetch --dry-run` with `cwd=target` — a repository that by definition
already holds the commit being pinned — so git answers from the local object store and
never contacts upload-pack. The guard passes for every pin anyone would ever write,
including one committed a second ago and never pushed.

The spine of this change is the user's rule. **At generation time, three conditions, in
order:**

| # | Condition | Today |
|---|---|---|
| 1 | The working tree is clean over the declared clone paths; otherwise refuse and name the files | **Nothing checks this**, while `resolve_clone_paths` (`jobfolder.py:349-351`) validates imports by walking that same tree — generation validates code the runner will never run |
| 2 | The pin is HEAD, or nothing changed between pin and HEAD under those paths | `_staleness_for` (`:923-925`) already computes exactly this diff, and only ever *reports* `fresh`/`drift`. It never refuses. Blind to uncommitted work by construction, which is why (1) is separate and not a refinement |
| 3 | The pin is published on the declared remote | The guard exists and can never fire (D2) |

**With (1) and (2) holding, `--commit` becomes optional and defaults to HEAD** — safe
precisely because HEAD is then provably the code that was validated. An explicit
`--commit` still means exactly what it says.

The order is also cheapest-first: (1) and (2) are local and instant, so the one network
call in (3) is only paid once the local story is coherent.

**Why this supersedes resolving the pin from the remote** (exploration's option C):
`ls-remote` can pin a commit *older* than the caller's code. Verified live — `origin/main`
is `225310f`, while the `run_search` entrypoint the user needs exists only in unpushed
`d903d148`. C pins `225310f`, every local guard passes because generation validates
against the working tree, and the kernel dies on a missing entrypoint after quota is
spent: the same failure class, reintroduced by helpfulness. Defaulting to HEAD pins
exactly the caller's code and then *checks* it is published.

## Scope

### In scope

| Finding | Files |
|---|---|
| **D1** adapter side-load | `remote_cli.py:1517` (+1 line); new subprocess test |
| **D2** probe runs in a scratch repo | `jobfolder.py:823-874` (`_verify_commit_reachable`), `:20-36` + `:824-865` docstrings, `tests:4003-4033` + `:4097` + `:4099`, `SKILL.md` (guard currently documented nowhere) |
| **C1** clean-tree precondition | new `jobfolder` helper, called from `generate_job` before `resolve_clone_paths` |
| **C2** pin-vs-HEAD precondition | `generate_job` calls the existing `_staleness_for`; no second diff |
| **C3** `--commit` optional, defaults to HEAD | `remote_cli.py:1313` (drop `required=True`), `jobfolder.generate_job` signature, CLI stdout JSON |
| **C4** commit shape validation | `validate_run_config` (`jobfolder.py:441-463`) |
| **C5** git env + refusal message | `jobfolder.py:764` `GIT_ENV_ALLOWLIST`, refusal text |
| Cleanup | dead `return destination` at `jobfolder.py:989` |

### Out of scope — recorded with reasons

- **`resolve_clone_paths` walking the working tree while the runner runs the pin.** This
  is *addressed* by condition (1), not by changing that function: once the tree is clean
  over the clone paths and the pin is HEAD, the tree the walk sees and the tree the runner
  clones are the same bytes. The function is left alone deliberately.
- **`repo.ref` validation.** `repo.ref` is write-only today (set at `:546`, zero readers).
  Proving "the pin is on the declared ref" needs either the ref's whole history (unbounded
  — the cost `--depth 1` exists to avoid) or `ls-remote`'s tip alone (false the moment
  anyone else pushes). A guard that can only be *sometimes* right is worse than an honest
  absence — the same reasoning D2 is about. **Decision: keep `repo.ref`, give it exactly one
  job — the remedy sentence in (3)'s refusal ("push it to `<ref>` on `<url>`") — and record
  that validating it is not attempted.**
- Nothing cross-checks a job's `service` against `submit --backend` (`remote_cli.py:429-541`).
- **Target-side, not ours:** `implementations/Domain_Adaptation` declares
  `"identicalAcrossShards": ["epochs"]` only, so `evidence.codeDigest` must be *present* but
  need not *agree* — two shards can run different code and `merge()` pools them silently.
  Reported; it belongs to the target's own declaration, and the target is never edited.
- A meta-test guarding against duplicate test-class names (a real incident here: a second
  `CommitReachabilityTests` silently disabled seven tests while the suite still said OK).
  Cheap and worth its own change; not this one.

## Approach, per finding

### D1 — side-load the adapter `--service` names
`_load_backend_module(args.service)` before the `generate_job` call. All five
`ADAPTER.resolve*` sites were enumerated: submit/poll/fetch/reconcile each carry a loader
on the preceding line (`:1378, :1429, :1456, :1493`); `generate-job` is the only subcommand
spelling the flag `--service` rather than `--backend`, and is the one that has none.
**Rejected:** renaming `--service` to `--backend`. It is the on-disk directory name in
`<target>/tools/<service>/`; renaming it is a breaking change to a folder layout for a
cosmetic win.

### D2 — ask the question from a repository that cannot already answer it
Probe from a `tempfile.TemporaryDirectory()` scratch repo (`git init -q`, then the fetch),
with **`git init` inside the same `try`** as the fetch. Proven with a two-repo experiment:
the identical fetch for `d903d148…` succeeds from inside the target and fails from an empty
scratch repo with `upload-pack: not our ref`.
**Rejected:** `ls-remote`. It matches ref *names*; a bare 40-hex pin returns empty with exit
0 either way. The existing docstrings say this and stay true.

### C5 — `GIT_ENV_ALLOWLIST`: decided against widening for credentials
Evidence: `runner_bootstrap.py:70` sets its own `GIT_ENV_ALLOWLIST = ("PATH",)`, and
`:166-170` clones with that env and **no credential step anywhere**. The runner's fetch is
therefore unauthenticated by construction except for whatever the URL itself carries. A
probe with `HOME`/`SSH_AUTH_SOCK` would answer a question the runner never asks — passing
for remotes the runner can never clone, which is exactly D2's defect class re-created.

**Decision: widen only for asker-side transport plumbing, never for authorization.**
Proxy vars (`HTTP(S)_PROXY`, `ALL_PROXY`, `NO_PROXY`, both cases) and trust-store vars
(`SSL_CERT_FILE`, `SSL_CERT_DIR`, `GIT_SSL_CAINFO`) let the question *travel*; they do not
change *who* is asking. Additionally **set** `GIT_TERMINAL_PROMPT=0` so a credential-requiring
remote fails fast instead of blocking against the 120s timeout — the kernel has no tty either.
Enrich the refusal instead of adding a guard: when the probe fails and `repo_url` is
SSH-shaped (`git@…:` / `ssh://`), append one sentence naming why. This costs no new refusal
path, because a PATH-only probe already fails for SSH.
Supporting evidence: user `~/.gitconfig` has **no credential helper, no `insteadOf`, no
proxy**; both `origin` remotes are public `https://github.com/Daprosero/…`.
**Rejected:** widening to `HOME`+`SSH_AUTH_SOCK`. It would also drag in the global
`filter.lfs.required = true` and make generation pass for jobs that cannot run.

### C5b — `--depth 1`: adopt
Two arguments, neither depending on the unmeasured byte count. **Fidelity:**
`runner_bootstrap.py:169` is `fetch --depth 1 origin <commit>`; a full-depth probe asks a
different question than the operation it claims to emulate. **Bounded cost:** `--dry-run`
suppresses ref updates, not the object transfer, so a full-depth scratch probe downloads
reachable history on *every* generation, unbounded. Final argv:
`["fetch", "--dry-run", "--depth", "1", <url>, <commit>]`. `--dry-run` is kept even though
the scratch dir is discarded, so `tests:4097` stays a meaningful assertion.
**Residual transfer size is still unmeasured — this phase had no Bash.** Measuring it is a
task, not a blocker: the decision does not turn on the number.

### C1 / C2 — the two local preconditions
- (1) `git status --porcelain -- <clone_paths…>` via the existing `_run_git`. Non-empty
  refuses and names the files. Untracked (`??`) counts — an untracked file under a clone
  path is code the walk may read and the runner will never get. Ignored files do not.
  Not a repo / no history refuses too: generation cannot *prove* cleanliness.
- (2) **Call `_staleness_for(target, commit, clone_paths)` and refuse unless `fresh`.** No
  second diff implementation, so the generation guard and the read-time report can never
  drift. The deliberate asymmetry to write down: the same verdict *refuses* at generation
  (a decision point) and merely *reports* at `read()` (an observation). `unknown` refuses at
  generation, matching `_verify_commit_reachable`'s existing "cannot determine == refuse".
- **Every new refusal must carry git's own message forward**, as `:873` already does. This is
  load-bearing, not style: it is what keeps `tests:4200`
  (`test_reachability_refusal_precedes_clone_path_resolution`, which mocks `_run_git` to
  raise `"not our ref"` and asserts on that substring) green through a new earlier guard.

### C3 — `--commit` optional, defaulting to HEAD
Default resolved inside `jobfolder.generate_job` (`commit: str | None = None` →
`git rev-parse HEAD`), not in the CLI, so the Python API and the CLI share one
implementation. Drop `required=True` at `remote_cli.py:1313`.
**Decision: do not record `commitSource` in `run-config.json`.** Under conditions (1)-(3) a
defaulted pin and an explicit pin naming the same commit are indistinguishable *by
construction*; the field would record how the caller typed it, not a fact about the job —
the same "an echo of the argument" mistake the forge already rejected once for
`latestRevision`. Report `commit` and `commitSource` in the CLI's **stdout JSON**, where it
is operator feedback rather than provenance.

### C4 — commit shape
`validate_run_config` refuses a `commit` that is not lowercase 40- or 64-hex. `--commit main`
currently passes every guard, the runner checks out whatever `main` points at that day, and
`readiness` (`remote_cli.py:1071`) compares `"main"` to itself and reports ready forever.
With a default now in play this is a precondition, not an adjacent nicety.
**Migration hazard: none.** No `run-config.json` exists anywhere on disk (globbed under
`implementations/`, including ignored paths), so no existing job folder can be invalidated.

## Commit decomposition

| # | Commit | Depends on | Lines (est.) |
|---|---|---|---|
| 1 | **D1** adapter side-load + subprocess test | — | ~60 |
| 2 | **C4** commit shape validation | — | ~50 |
| 3 | **D2 + C5 + C5b** scratch-repo probe, env allowlist, `--depth 1`, docstrings, `SKILL.md` | — | ~200 |
| 4 | **C1 + C2** the two local preconditions | 3 (message-carry idiom) | ~180 |
| 5 | **C3** `--commit` optional + dead-return cleanup | 4 (**hard**) | ~110 |

**Independence:** 1, 2, 3 touch disjoint code and can land in any order. **Ordering
constraints:** 5 must follow 4 — a pin defaulting to HEAD is only safe once (1) and (2)
refuse, and landing 5 first would ship exactly the silent-wrong-pin behaviour this change
exists to remove. 4 should follow 3 so the "carry git's own message" idiom is already
established where `tests:4200` depends on it.

**Slice 1 is self-contained and unblocks the user today.** It is the recommended first PR
regardless of what happens to the rest.

## Test strategy

RED before GREEN, every unit. The local idiom holds: a lock that passes on its first run
must be proven reachable-red **by inversion** (invert the production line, watch it fail,
restore by inverse patch — never `git checkout --`).

**Before adding any class, grep the name first.** Verified free today: `ServiceResolutionTests`,
`CleanWorkingTreeTests`, `PinIsHeadTests`, `CommitShapeTests`, `CommitDefaultTests`. Occupied:
`CommitReachabilityTests` (`:4002`). 29 test classes exist in the file; the suite is 790 green.

**D1's test must be a subprocess** — `KAGGLE` is preloaded at module scope in the suite, so an
in-process assertion passes against the bug.

**The seven existing guard tests.** Exactly one encodes the defect: `assertEqual(recorded["cwd"], target)`
at **`:4099`**. `:4097`'s argv assertion changes too, for `--depth 1` — justified, not routed
around: the test's own class docstring claims the probe emulates the runner's clone, and
`--depth 1` is what makes that claim true. The other five assertions stay.

**Two mock-fidelity repairs, flagged in advance so they are not mistaken for routing around a red.**
`:4189` and `:4166` mock `_run_git` as `Mock(returncode=0)`; once generation asks git two more
questions, `.stdout` returns an auto-Mock and `.splitlines()` yields a truthy Mock, so the new
guards would refuse. Adding `stdout=""` adds no permissiveness — it makes the double answer the
new question the way real git answers it for a clean tree. Preferred where the diff allows:
replace those mocks with a **real git fixture repo**, as the D2 end-to-end test already does.

**The WIP patch's two spurious reds are not locks.** It placed `git init` outside the `try`, so
the mock's raise escaped unwrapped without the repo URL and `assertIn(url, …)` failed at `:4134`
and `:4181`. Moving `git init` inside the same `try` makes both green: `:4136` already requires
that an *unanswerable* question refuse with a message naming commit and URL, and a scratch
`git init` that fails is exactly an unanswerable question.

**Commands:** `python3 -m unittest tests.test_remote_execution`, then
`python3 -m unittest discover -s tests` (790 baseline). Never pytest; `-k` misses new classes.
Throwaway boxes under `implementations/_<name>`, deleted after.
**`implementations/Domain_Adaptation` is never edited.** `fd`/`rg` need `--no-ignore` to see
`implementations/` at all.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Condition (1) is too strict for real practice — operators routinely generate with a dirty tree | **Med** | Open question Q1 below. An `--accept-dirty` recording escape hatch mirrors the existing `--accept-unresolved` precedent if the answer is yes |
| A corporate proxy or custom CA still breaks the probe despite C5's plumbing widening | Low | Refusal is local, free, and re-runnable; the message names the proxy possibility |
| `--dry-run` + `--depth 1` interaction unverified against a real remote | Low | Verify in apply against `https://github.com/Daprosero/Domain_Adaptation`; falls back to dropping `--dry-run` (scratch dir is discarded anyway) |
| Probe transfer size unmeasured | Low | Measure in design/apply; the `--depth 1` decision does not turn on the number |
| The three conditions plus mock repairs make slice 4 exceed a 400-line PR | Med | Slice 4 splits cleanly into C1 and C2 as two commits if it does |
| `run-config.json` gaining no `commitSource` is later regretted | Low | Additive optional field, no schema bump needed, reversible |

**Review budget forecast (against 1200):** ~600 authored lines (additions + deletions),
across 5 slices of ~50-200 each. Under the session budget as one review; **over the 400-line
per-PR guard**, so chained PRs are recommended, ordered 1 → 2 → 3 → 4 → 5. The exploration's
250-450 forecast predates the user's rule, which adds C1/C2/C3.

## Rollback

Each slice is one commit against `main` and reverts independently, with the single ordering
exception that slice 5 must be reverted before slice 4. Slice 3 restores the old probe by
reverting one function; no on-disk artifact is produced by any slice (no `run-config.json`
exists anywhere), so there is no data to migrate back.

## Success criteria

- [ ] `generate-job --service kaggle` reaches the metadata assembler (D1 closed, asserted by subprocess).
- [ ] Generation refuses a commit that exists locally and is absent from the declared remote (D2 closed, asserted end to end).
- [ ] Generation refuses, naming files, when the tree is dirty over the declared clone paths.
- [ ] Generation refuses when the pin and HEAD differ under those paths.
- [ ] `generate-job` without `--commit` pins HEAD and reports `commitSource` on stdout.
- [ ] `--commit main` is refused.
- [ ] `discover -s tests` is green, at 790 + the new tests, with every new lock proven reachable-red.
- [ ] `SKILL.md` documents the three conditions (it documents the reachability guard nowhere today).

## Proposal question round

This phase could not ask interactively. Four questions that would sharpen the proposal;
the assumption each currently rests on is stated so it can be corrected rather than
discovered later.

1. **Dirty-tree escape hatch.** Condition (1) refuses on a dirty tree. Should there be an
   `--accept-dirty` that *records* the dirt in `run-config.json`, mirroring the existing
   `--accept-unresolved` precedent, or is dirty always fatal?
   *Assumed: always fatal.*
2. **Private or SSH remotes.** C5 decides the probe stays unauthenticated because the runner
   is. Does any real workflow point `--repo-url` at a remote needing credentials? If yes, that
   job cannot run in a kernel today either, and we should say so out loud rather than only
   refuse it.
   *Assumed: public HTTPS only, forever.*
3. **Generating from another clone.** Condition (2) refuses `unknown` — no git history, or a pin
   absent from the local checkout. Does anyone legitimately generate a job for a pin they do not
   have locally?
   *Assumed: no; refusing is right.*
4. **`repo.ref`'s future.** The proposal keeps it and gives it only a remedy-message job.
   Would you rather remove it from `run-config.json` entirely, given nothing reads it?
   *Assumed: keep — removing it is a schema change for no gain.*

Answering, skipping, correcting the framing, or asking for a second round are all fine.
