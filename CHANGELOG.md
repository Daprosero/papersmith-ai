# Changelog

Notable changes to papersmith-ai, newest first.

This file starts at 0.2.0. `0.1.0` was set in the commit that created the
package and never moved again across more than a thousand commits, so there
is no honest way to reconstruct a release history for it — its record is the
git log, and pretending otherwise would put a fabricated summary where a
reader expects a kept one.

Versions follow [semantic versioning](https://semver.org): while the first
number is `0`, breaking changes can still arrive without a major bump.

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
