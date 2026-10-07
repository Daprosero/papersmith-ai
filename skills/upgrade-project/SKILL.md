---
name: upgrade-project
description: "Trigger: a workspace created by `papersmith init` is running an older release and needs the current one — its skills, agents, slash commands, harness wiring and artifact shapes brought up to the installed distribution. Delegates every write to `papersmith upgrade`, which owns the kit copy, the projections, the orphan sweep and the artifact migrations; this skill never copies a file or edits an artifact itself. Refuses before writing when the directory is not a workspace or the CLI is unreachable, and names the one command that fixes each. Verbs: `plan` previews pending migrations and writes nothing; `apply` performs the upgrade; `status` reports the recorded version against the installed one."
---

# Upgrade Project

A workspace is not a checkout. `papersmith init` copies a release's skills,
renders its slash commands and agents for every harness, and records which
release the workspace received in `.papersmith/version`. Nothing about that is
live: when the installed distribution moves ahead, the workspace keeps the
release it was born with until someone upgrades it.

This skill is the in-workspace surface for that upgrade. It exists because the
work was only reachable from a terminal, which meant that an agent working
inside a workspace could see that the workspace was stale and could not do
anything about it.

## What this skill does not do

It performs no upgrade of its own. Every byte written is written by
`papersmith upgrade`, and that is deliberate: the upgrade is not a file copy.
It is a kit copy, a symlink repair, a re-derivation of every projection, an
orphan sweep over previously-baselined dynamic paths, and an ordered run of
artifact migrations — with the version marker written last, and only when the
artifacts actually reached that version.

A reimplementation here would be a second answer to all of that, and two
answers that can disagree are worse than one that can be wrong. So this skill
decides *whether* to call the CLI and *with which arguments*, and reports what
it said. Nothing else.

It also never decides to upgrade on its own. A stale workspace is a fact to
report; moving it is the user's call.

## Preflight, before anything is written

Two conditions are checked first, because both fail better before a write than
during one.

**Is this a workspace?** `.papersmith/manifest.json` must exist. The CLI checks
this too and refuses with exit 1, but checking here lets the refusal name the
directory the user is actually in.

```
test -f .papersmith/manifest.json
```

Absent, refuse and say so plainly: this directory was not created by
`papersmith init`, and `papersmith init .` is what creates one. Do not offer to
run `init` as a recovery — initializing a directory somebody believed was
already a workspace is how a misunderstanding becomes a tree of files.

**Is the CLI reachable?** The workspace vendors no copy of the `papersmith`
package, so the upgrade can only come from the installed distribution.

```
papersmith --version
```

If that fails, try `python -m papersmith.cli --version`, which works whenever
the distribution is importable even if no console script landed on `PATH`.

Note the module path: it is `papersmith.cli`, not `papersmith`. The package
ships no `__main__.py`, so `python -m papersmith` fails with "'papersmith' is a
package and cannot be directly executed" — a message that looks like a broken
install and is not one. The entry point is `papersmith.cli:main`.

If neither answers, refuse with the installation command rather than a guess:

```
pipx install git+https://github.com/Daprosero/papersmith-ai.git
```

A workspace cannot upgrade itself from inside; saying that clearly is more
useful than attempting a fallback that cannot exist.

## The verbs

### `plan` — what would a migration do

```
papersmith upgrade . --plan-migrations
```

Reports the migrations that would run and exits having written nothing.

Be precise about what this previews, because the flag is deliberately not
called `--dry-run`: it covers **migrations only**. The kit copy, the
projections and the orphan sweep are not previewed by it and have no preview at
all. Telling a user "this is a dry run" would be false.

### `apply` — perform the upgrade

```
papersmith upgrade .
```

Copies the current kit, repairs the per-harness `skills` links, rewrites
`.papersmith/config.json`, re-renders every projection, sweeps orphans, runs
the pending migrations, and writes `.papersmith/version` last.

Flags worth knowing, with what each actually changes:

- `--tools <a,b,c>` — replace the workspace's `active_tools`. Omitted, the
  declared set is kept. This is how a workspace gains or drops a harness.
- `--force` — write kit files whose hashes already match. Normally a matching
  hash is skipped; this is for a workspace whose files were edited in place.
- `--no-migrate` — sync files, skip artifact migrations. The version marker
  then stays where it was, which is correct rather than unfortunate: the
  artifacts did not reach the new version, so the workspace must not claim they
  did.
- `--allow-downgrade` — install an older kit over a newer workspace. Deliberately
  separate from `--force`. Never add it to recover from a refusal without
  saying what it does first; a refusal here is usually a sign that the wrong
  distribution is installed.

### `status` — how far behind is this workspace

```
papersmith status
```

Reports the recorded version against the installed one. Prefer this over
reading `.papersmith/version` directly: the marker is a claim about artifacts,
and `status` is where that claim is interpreted.

## What is never overwritten

The upgrade preserves the user's own work by pattern, not by hope. The
protected set covers the directories that hold authored research output and
the files that carry a workspace's own configuration and identity, including
its environment files.

Read the set from `PRESERVE_PATTERNS` in `src/papersmith/core/manifest.py`
rather than from a list restated here. A roster copied into prose is a roster
that drifts the first time the real one changes, and the question a user asks
-- "will this overwrite my work?" -- deserves the current answer, not the
answer that was current when this file was written.

State that when asked whether an upgrade is safe, and state its limit honestly:
there is **no backup and no dry run for files**. A file outside those patterns
that was edited by hand will be replaced by the release's own copy. If a user
has such edits, the answer is to commit them first — a working tree under
version control is the backup the CLI does not provide.

## Reading the result

The report names the workspace, the version, the count of changed files, and
then four things that are warnings rather than failures:

- **unsynchronized** — a kit file could not be written. The upgrade continued.
- **stranded** — an orphan could not be deleted. It is still there.
- **link warnings** — a harness `skills` symlink was blocked.
- **"recorded version stays at X"** — the marker did not advance, because the
  artifacts did not reach the new version. With `--no-migrate` this is
  expected; without it, read the migration lines above it, because something
  failed.

Exit codes: `0` success; `1` a user error (not a workspace, corrupt manifest or
ledger, refused downgrade, unknown tool name); `2` a source error (the installed
distribution carries no kit); `4` a migration failed.

Report a non-zero exit as a failure with its message. An upgrade that printed a
migration failure and exited 4 did not succeed, and a summary that calls it done
is the one outcome this skill must never produce.
