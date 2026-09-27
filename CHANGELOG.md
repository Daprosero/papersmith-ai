# Changelog

Notable changes to papersmith-ai, newest first.

This file starts at 0.2.0. `0.1.0` was set in the commit that created the
package and never moved again across more than a thousand commits, so there
is no honest way to reconstruct a release history for it — its record is the
git log, and pretending otherwise would put a fabricated summary where a
reader expects a kept one.

Versions follow [semantic versioning](https://semver.org): while the first
number is `0`, breaking changes can still arrive without a major bump.

## 0.5.0

### Added

- **Pi relays the off-path push tripwire, and refuses by returning instead of
  throwing.** `.pi/extensions/refuse-offpath-push.ts` is generated for every Pi
  workspace and loaded by Pi from the project `.pi/` directory. It shells out to
  `remote-execution`'s own `refuse_offpath_push.py` with the payload OpenCode
  already sends, so the predicate keeps exactly one authority and a second
  service is covered by that service's own `PUSH_SURFACE`, never by editing the
  relay.

  It could not be a copy of the OpenCode plugin. Pi treats a failed `tool_call`
  handler as a fail-safe block, so the OpenCode relay's `throw` to refuse would
  instead block every `bash` command in the session. This relay refuses by
  returning `{ block: true, reason }`, and its whole handler body is wrapped so
  that any unexpected failure -- including while degrading -- warns once and
  then allows. A tripwire that silently fails open is bad; one that fails closed
  onto unrelated commands is worse.

  The default export is load-bearing: Pi loads extensions with
  `jiti.import(path, { default: true })` and rejects a module that is not a
  function, which takes every `pi` command down with it rather than just the
  extension's own tools. The gate loads the real generated artifact the same
  way, so that contract is proven instead of assumed.

### Internal

- **`.pi/` was ignored wholesale, so a Pi extension could not be versioned.** It
  now follows the split `.opencode/` already drew: `.pi/skills` (the harness
  link) and `.pi/gentle-ai/` (the generated persona) stay ignored, while
  `.pi/extensions/` is a source artifact projected by
  `scripts/sync-repo-harness.py` like every other harness surface.

## 0.4.0

### Added

- **A step now reports the product the repository was told to ignore.** A
  `__steps__` step declares what it writes, `step` already compares those
  declared roots against what the run actually wrote, and nothing asked whether
  those written files were ones `.gitignore` excludes. So a step could declare a
  product, produce it, and have git skip it silently: the declaration read
  satisfied, the run read clean, and the artifact never entered history. Nobody
  finds out until someone looks for a file that was never committed.

  `wrote` now carries `ignored` -- always present, `[]` when clean -- the subset
  of the run's own written paths the repository's ignore rules exclude, plus an
  `ignoredNote` when it is non-empty. Both readings reach the terminal ledger
  event, so the finding is durable rather than printed once.

  It reports and never refuses, for the reason `undeclaredProduces` already
  gives: it grades an act already taken. The step has run and the files are on
  disk; refusing now undoes nothing and hides the finding behind an error.

  The check runs over the paths actually written, never over the bare declared
  roots. A declared root checked against a content-only rule (`Results/*`)
  answers "not ignored" truthfully and uselessly, because every file under it
  is. That distinction is what the test fixture proves: its rule is anchored to
  the product folder, because an unanchored rule matches the product-relative
  path at the repository root just as well and would pass with the path join
  deleted.

### Internal

- This repository's own `.gitignore` already stated the insight behind the above
  by hand, in the one file whose whole job is declaring what does not ship: *"una
  regla escrita nombrando lo que existia ese dia no alcanza a lo que nace
  despues"*. It was applied to two subtrees one at a time and derived nowhere.

## 0.3.1

### Fixed

- **The `pin-published` refusal no longer prescribes a push nobody measured.**
  It appended the same remedy -- push it and re-pin -- to every failure it
  caught, so a remote answering `not our ref`, a DNS failure, a proxy refusal
  and a scratch `git init` that could not write all arrived at one sentence
  telling the operator to push. Nothing in the skill had ever asked how much
  that push would carry. The refusal now takes one of two shapes, chosen only
  by whether the weight could be read and never by how large it is: measured
  states the count and keeps the remedy; unmeasurable states what is known and
  prescribes nothing. That second shape is not new to this codebase -- the
  `GitTimeoutError` branch one block above has always named no remedy, because
  a question that could not be finished being asked is not the remote saying
  no. That branch is untouched here; it was the model, not the patient.

  The reader is local and transfers nothing. It matches a configured remote to
  `--repo-url` by exact string comparison, resolves the cached
  `refs/remotes/<name>/<branch>`, and counts commits. Two remotes sharing one
  URL resolve to unmeasurable rather than picking one: they are independent
  caches fetched at different moments, so a choice between them is an answer
  the operator cannot audit. The measurement is therefore often unavailable,
  and that is the intended trade -- a weight anchored on the wrong remote is a
  number that looks measured and is not.

  The clause states an exact distance from the cache and claims nothing about
  the remote now. An earlier draft called that number a floor. It is a ceiling
  on the real push: a remote that moved forward since the last fetch needs
  fewer objects, not more. Both framings over-claim, and over-claiming from a
  true measurement is the defect this change exists to close.

## 0.3.0

### Fixed

- **A campaign submitted with `--unit` now distributes the work.** Both
  per-submission facts already reached the worker — the packer splits the unit
  list across workers and writes each worker's own slice, `--smoke` sets the
  mode the same way, and the adapter merges both into the job folder's
  `run-config.json`. Nothing read them. Every worker received its slice in a
  file nobody opened and ran the identical whole job, so a distributed
  campaign distributed the ledger and not the work. `submission_environment()`
  is now the one place either name is decided, applied by both the notebook
  and callable branches and kept separate from `kernel_environment()`, which
  the callable branch has no clone or `PYTHONPATH` to compose for. An absent
  mode or absent units leave the environment as it was rather than
  substituting an empty string for a value nobody declared; a DECLARED empty
  list still sets the variable, because only a present key can say that zero
  units was the answer.
- **`lfs` names the large files that are real content.** It reported the
  pointers by path and the materialized side by tally, so a reader needing one
  specific checkpoint could not tell whether it had arrived — while the
  skill's own table promises to report which files are which.

### Internal

- The D2 grounding tripwire counts recorded runs before judging, instead of
  failing permanently. Below ten it announces the silence; at or above it, it
  applies the falsifier and either names what fired or asks for the discharge.
  A permanently red test is not a signal, and this repository has already paid
  for that lesson once.
- `init`'s tests derive the recorded version from the kit instead of restating
  `0.1.0`, a literal that passed for a thousand commits and broke on the first
  real bump.

## 0.2.0

The first release where the version means anything: `0.1.0` had been frozen
since the package skeleton, so nothing downstream could tell two builds
apart.

### Fixed

- **The provisioned environment can now run the suites.** `setup_env.py`
  built an environment missing `nbformat`, `nbclient`, an editable install of
  this project, and `ipykernel`. Running the configured gate under it failed
  31 tests. `nbclient` pulls in `jupyter_client`, which knows how to talk to
  a kernel, and never `ipykernel`, which runs the cells — so that last gap
  surfaced as a child process exiting non-zero rather than as a missing
  module.
- **`npm run setup` runs.** It invoked bare `python`, which does not exist on
  a machine that has only `python3`, while the script it calls documented
  `python3` in its own usage. Same for `setup:env`, `clean:env` and two
  README instructions.
- **The test gate names the environment this project provisions.** It named
  bare `pytest`, resolved by the caller's `PATH` — measured resolving to a
  Python 3.9 install that cannot import this project at all.
- **`upgrade` refuses to move a workspace backwards.** It read the kit's
  version and wrote it in three places while comparing only for equality, so
  installing an older kit rolled a workspace back in silence and reported the
  older version as the new truth. A deliberate rollback now needs
  `--allow-downgrade`, which is its own flag: `--force` already means "write
  even when the bytes match" and must not double as permission to change
  version.
- **Ingesting a paper no longer deletes its appendix.** `strip_references`
  cut from the references heading to the end of the document. Measured on a
  116-document corpus: five papers place supplementary material after their
  references, and the cut removed 52% to 74% of each file — a generalization
  bound, a derivation, dataset details, an algorithm's specification. Every
  references section is now cut, and only up to the next heading, which also
  makes the operation idempotent.
- **A failed remote run reports why.** The Colab executor records its reason
  in `status.json`, bounded on purpose; `poll` reported the exit code alone
  and dropped it. Separately, the "session not found" test matched that
  phrase anywhere in a helper's output, including the run's own recorded
  error — so a run whose error contained those words was reported as a
  vanished session, which means *evidence missing* rather than *this failed*.

### Added

- **Each `write` run records its grounding counts** to
  `paper/.paper-writing/grounding-runs.jsonl`, one line per completed run.
  A ruling that shipped without a numeric threshold named ten recorded runs
  as its falsifier, and nothing recorded them.
- **A `--allow-downgrade` flag** on `papersmith upgrade`.

### Changed

- **`upgrade` now refuses where it used to proceed.** Installing an older kit
  over a newer workspace was accepted silently; it now raises unless
  `--allow-downgrade` is given. For anyone driving `upgrade` from a script
  this is a breaking change, and under strict conventional commits its commit
  deserved a `!` it did not carry. Recording it here because a reader looking
  for what broke looks in this file, not in a commit subject.

  Worth naming the reason it was missed: across the 817 commits between
  `0.1.0` and this release, not one carried `!` or `BREAKING CHANGE`. The
  marker has never been used in this repository, so a version derived from
  commit types cannot answer whether a major bump is owed -- the input for
  that question was never written down.
- **Pin conditions are named by id, never by position.** Two conditions had
  been inserted into the middle of the list; the doctrine table renumbered
  itself and 55 prose references across four files did not, leaving two
  different functions documented under the same ordinal.

### Internal

Guards added for defects that were previously invisible: the two version
sources are held to each other, the gate's interpreter is probed against
every import the suites and their assets actually require plus a notebook
kernel, scratch fixtures are held to resolving their paths (a macOS symlink
had four tests failing over correct code), and the end-to-end suite's line
budget now counts code rather than taxing the explanations beside it.
