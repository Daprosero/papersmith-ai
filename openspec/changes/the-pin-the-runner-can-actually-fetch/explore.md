# Exploration: the-pin-the-runner-can-actually-fetch (2026-08-20)

## Confirmed defects

**F1 — `generate-job` never side-loads the adapter its `--service` names.**
Consumer `jobfolder.py:709` `ADAPTER.resolve_metadata(service)`; the dispatch at
`remote_cli.py:1517-1519` calls no loader. Registration at `adapters/kaggle.py:751`
never runs. Complete enumeration of all five `ADAPTER.resolve*` sites: submit
(:1379), poll (:1430), fetch (:1457), reconcile (:1494) all have a loader at the
preceding line; `jobfolder.py:709` has none and structurally cannot. `generate-job`
is the ONLY subcommand spelling the flag `--service`. One-line fix; the test must
be a subprocess because KAGGLE is preloaded at module scope in the suite.

**F2 — the reachability probe asks what the local repo can answer.**
`jobfolder.py:867` runs `fetch --dry-run` with `cwd=target`. The runner it claims
to emulate (`assets/runner_bootstrap.py:166-170`) fetches from an EMPTY dir. Git
resolves a want it already holds locally and never contacts upload-pack, so the
guard passes for every pinned commit — pinning means the target has it.

## Forced into scope by F2

**F3 — `GIT_ENV_ALLOWLIST = ("PATH",)`** (`jobfolder.py:764`) has never faced a real
network call, because F2 meant the probe never dialled out. Fix F2 and it does, with
no HOME, no SSH_AUTH_SOCK, no credential helper. Survives for THIS target (public
HTTPS, verified; no global credential helper). Breaks generation outright for SSH or
private-HTTPS remotes — fail-closed becomes fail-always.

**F4 — `--dry-run` suppresses ref updates, not the object transfer.** A scratch-repo
probe downloads history each time. `--depth 1` both bounds it and makes the probe
byte-identical to `runner_bootstrap.py:169`. Residual size unmeasured.

**F6 — `commit` has no shape validation** (`validate_run_config`, `jobfolder.py:441-463`).
`--commit main` passes every guard, the runner checks out whatever main points at that
day, and `readiness` compares "main" to itself and reports ready forever.

## The lever

**F5 — `repo.ref` is write-only.** Written at `jobfolder.py:546`, read by NOTHING in
the skill. Nothing validates the pin is on the declared ref. And it is exactly the
input needed to ask what is newest on the remote — `ls-remote <url> <ref>` answers
with no object transfer.

## Also

**F7** — `resolve_clone_paths` walks the WORKING TREE (`:349-351`) while the runner runs
the pin. Fixing F2 makes the pin routinely trail the tree, widening the gap.
**F8** — nothing cross-checks a job's `service` against `submit --backend`. Out of scope.
**F9** — dead `return destination` at `jobfolder.py:989`.

## The seven guard tests — only ONE encodes the defect

`tests/test_remote_execution.py:4002 CommitReachabilityTests`. The `cwd == target`
assertion at **:4099** is the bug written down as a requirement; the other six stay
true. **The WIP patch's other two reds were its own bug**: it put `git init` OUTSIDE
the `try`, so the mock's raise escaped unwrapped without the repo URL, failing
`assertIn(url, ...)` at :4134 and :4181. Move it inside and both go green.

Prose to correct: `jobfolder.py:20-36`, `:824-865`, `tests:4003-4033`. And `SKILL.md`
documents this guard NOWHERE (zero hits for reachab/dry-run/ls-remote), which is why
the defect had no doctrine to contradict it.

## The design fork

Downstream consumers of the pin: `run-config.json` (:545), the runner's clone
(`runner_bootstrap.py:169` — the only one that must work), `bootstrap.json` provenance,
`_staleness_for` (:912, :924), `smoke record` (`remote_cli.py:988`), and `readiness`'s
whole binding (`remote_cli.py:1071`).

- **A. keep `--commit` required, fix the probe only.** Smallest. Leaves the retype loop
  and leaves `repo.ref` decoration.
- **B. always resolve from the remote.** **Falsified by the live case**: `origin/main` is
  `225310f` (verified live); `run_search` exists only in unpushed `d903d148`. B pins
  `225310f`, generation validates against the working tree (F7) so every local guard
  passes, and the kernel dies on a missing entrypoint after quota is spent. Same failure
  class, reintroduced by helpfulness. Also destroys the pin as a scientific claim.
- **C. `--commit` optional; explicit means exactly what it says; omitted resolves from
  `ls-remote <url> <ref>` and reports its source.** RECOMMENDED, with F6 as precondition.

Why C: the forge already decided this shape once. `revision_discovery` was written
because a field named `latestRevision` "was an echo of the argument" — and it discovers
scoped by what the caller declared, reports the source of its authority, surfaces
ambiguity rather than deciding it, and is "reported, never refused". Ported honestly
that says: discover scoped by `--repo-ref`, report `commitSource`, never substitute for
a stated value.

**Falsifier for C:** find one invocation anywhere where `--commit` is supplied by
`git rev-parse` rather than typed by a human. Searched `usage.md:601-604`,
`SKILL.md:208-245`, `proposal-implementation/SKILL.md:384,1109` — only hand-typed
placeholders. Search was over docs, not over practice.

## Could not check
No Bash in that phase: test counts (248/790) unverified there, no git experiment re-run,
no measurement of F4's transfer size.

## Forecast
250-450 changed lines. F1 is a one-line fix with a self-contained test and is worth
slicing out as its own unit.
