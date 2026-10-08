# Releasing

The version a user installs, the changelog entry, the tag and the GitHub release
are four statements about one build. This file is how they are kept saying the
same thing, and what to run to prove it afterwards.

## What has to agree

| Artifact | Where it lives | Enforced by |
| --- | --- | --- |
| The version | `src/papersmith/__init__.py`, `package.json`, `package-lock.json` | `tests/test_version_sources.py` |
| The changelog entry | `CHANGELOG.md`, a `## X.Y.Z` section | `test_the_changelog_documents_the_current_version` |
| The annotated tag | `vX.Y.Z`, on the merge commit of the release branch | nothing automatic |
| The GitHub release | body is that changelog section, tag verified | nothing automatic |
| The pinned example | `README.md`, the `git+…@vX.Y.Z` URL | nothing automatic |

Only the first two are enforced. The rule behind them is the one that matters:
**once a tag exists, any change under `src/`, `skills/` or `scripts/` forces a
version move**, because two builds a user cannot tell apart are two builds
`upgrade` cannot order either. Documentation, `odd/`, `README.md` and
`CHANGELOG.md` are not shipped roots — editing them forces nothing, and needing a
release for a typo is the failure this rule was shaped to avoid.

## The steps

Merge the work first, with a merge commit:

```bash
git switch main
git merge --no-ff <feature-branch> -m "merge: bring <feature-branch> into main (<summary>)"
```

Then bump on a release branch, because the release is a reviewable change of its
own:

```bash
git switch -c chore/release-X.Y.Z main
```

Three edits belong to that commit: the version literals, the `## X.Y.Z` section
at the top of `CHANGELOG.md` (the release body is copied from it), and the pinned
example in the manual's install section, which should name the newest tag. Merge
it with `--no-ff`; its merge commit is what the tag will point at.

Tag the merge commit, in the shape the earlier tags use:

```bash
git tag -a vX.Y.Z -m "papersmith-ai X.Y.Z

<one line about the release>: see CHANGELOG.md." <merge-commit>
git push origin main vX.Y.Z
```

Then publish the release, with the body read from the changelog section rather
than retyped:

```bash
python3 - <<'PY'
import pathlib, re
text = pathlib.Path("CHANGELOG.md").read_text(encoding="utf-8")
body = re.search(r"^## X\.Y\.Z\n(.*?)(?=^## )", text, re.S | re.M).group(1)
pathlib.Path("/tmp/release.md").write_text(body.strip() + "\n", encoding="utf-8")
PY
gh release create vX.Y.Z --verify-tag --title "papersmith-ai X.Y.Z" --notes-file /tmp/release.md
```

`--verify-tag` is the guard worth keeping: it refuses to invent a tag at the
wrong ref, which is the one way a release ends up pointing somewhere nobody
chose.

## The audit

Run this after publishing. It states the invariant directly — for every tag, the
tree that tag points at must declare that version and carry its changelog
section:

```bash
for t in $(git tag -l --sort=v:refname); do
  c=$(git rev-list -n1 "$t")
  printf "%-8s %-8s %-8s %s\n" "$t" "$(git rev-parse --short $c)" \
    "$(git show "$t:src/papersmith/__init__.py" | sed -n 's/^__version__ = "\(.*\)"/\1/p')" \
    "$(git show "$t:CHANGELOG.md" | grep -c "^## ${t#v}$")"
done
```

Every row must read `vX.Y.Z  <commit>  X.Y.Z  1`. Then install what a user would
install, in a throwaway environment, because a tag that does not resolve to a
working install is not a release:

```bash
python3 -m venv /tmp/verify && /tmp/verify/bin/pip install \
  "papersmith-ai @ git+https://github.com/LIAUNAL/papersmith-ai@vX.Y.Z"
/tmp/verify/bin/papersmith --version
```

One trap when reading the remote: `git ls-remote --tags origin vX.Y.Z` prints the
**tag object's** hash, not the commit. Peel it with `vX.Y.Z^{}` when you want to
confirm the tag lands on `main`.

## When the release changes an artifact, not just a file

The rule above — a change under `src/`, `skills/` or `scripts/` forces a
version move — is about files a user receives. A release can also change the
shape of something the user's workspace already produced, and `upgrade`
synchronizing files does nothing for that. `src/papersmith/core/migrations.py`
is where that case is handled, and its registry is the only place a release
declares it.

Ask one question first: does the workspace have to reach this shape *because of
this release*, or does it have to match the installed release whatever its
history?

**Because of this release** — a version-gated migration. Set `applies_from` to
the version you are about to ship, never to one already tagged. A gate at or
below the current version would never be selected for a workspace already on it
and would fire for every older one without the release that introduced it ever
existing; `test_the_shipped_registry_declares_no_gate_at_or_below_this_release`
refuses it. The migration runs once per workspace and is recorded in
`.papersmith/migrations.json`, so write it to be correct exactly once.

**Whatever its history** — a convergence migration, with `applies_from` left
`None`. It is evaluated on every upgrade, so `plan` must be a read-only probe
that asks the filesystem and returns no actions when the workspace already
satisfies it. Nothing records it, because the next release can change what
there is to converge to.

Two rules bind both kinds:

- **Neither `plan` nor `apply` may raise for a state a workspace can be in.** A
  missing script, an unreadable artifact, a read-only parent: each is a failure
  *returned* by `apply`. A migration that raises aborts a run that has already
  synchronized files and leaves the operator no report of what did happen.
- **A failure holds `.papersmith/version` back.** That is the contract the
  whole mechanism exists for, so a migration that half-finishes must report the
  failure rather than swallow it. The next run retries.

A migration that regenerates a derived artifact should decide staleness from
content hashes, the way `atlas-render-refresh` does, rather than from
modification times. `upgrade` rewrites file mtimes for reasons that have
nothing to do with any artifact.

## What has no automation, and the history behind it

Nothing creates a tag or a release. There is no CI job for either, so the four
statements above agree because the process says so, not because a machine checks
them — which is why the audit above is a step and not a suggestion.

GitHub releases began with `0.8.0`; the tags before it are tags only. Two
versions shipped with a changelog entry and no tag at all, `0.6.0` and `0.7.1`,
and both were tagged afterwards, once a credential could publish them.

**Publishing a retroactive tag needs the `workflow` scope.** A new ref at an old
commit makes that commit's whole tree reachable at a ref, and an old
`.github/workflows/` blob inside it is enough for GitHub to refuse the push —
`refusing to allow a Personal Access Token to create or update workflow …
without workflow scope`. The same policy answers `404` on `POST /git/refs`,
which reads like a missing object and is not one: the object is there, and
`GET /git/tags/<sha>` returns it. A token without that scope cannot publish such
a tag by any route — annotated, lightweight, or built object by object, all
tested. Tag the merge commit at release time and this never comes up.
