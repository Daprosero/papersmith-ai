# `pip install papersmith-ai`: the package becomes publishable

Installing meant a git URL. That works, and it has one property worth losing:
it has no version resolution, so `pip install --upgrade` cannot bring a user to
a newer release — it re-clones whatever `main` happens to be. An index gives
them `pipx upgrade papersmith-ai` and gives us a version history users can
order.

## What was already true

Nothing about the package needed fixing to be publishable. Verified by building
and installing rather than by reading:

- The wheel and sdist already carried the generated `_kit` (251 and 308 files).
- A `pip install` of that wheel into a clean venv produced a working CLI, and
  `papersmith init` created a complete workspace: 12 commands, 13 skills, all
  four harnesses wired.
- `papersmith-ai` is free on PyPI. `papersmith` alone is taken, so the suffixed
  name is the only option, not a preference.

So this cycle adds metadata, a workflow, and the test that keeps both honest.
It changes no behaviour.

## The failure this is shaped around

A published version cannot be replaced, only yanked, and its number is spent
forever. The loud failure — the upload breaks — is not the dangerous one. The
dangerous one is an upload that succeeds and ships something that does not work.

Here there is exactly one way that happens. `src/papersmith/_kit/` is generated
by `scripts/build-kit.py` and gitignored, while `pyproject.toml` declares it as
package data. A fresh runner checks out a tree without it and builds a wheel
whose declared `_kit/**/*` matches nothing. That wheel is structurally valid,
passes every other test, uploads without complaint, and then exits 2 with a
kitless install on the user's first command.

Both the workflow and the test exist for that single scenario. The workflow
builds the kit before packaging; the test asks the built archive whether the kit
is in it, because a manifest that promises the kit and a tree where it is absent
read identically in `pyproject.toml`.

## Decisions

**Trusted Publishing, not an API token.** PyPI verifies a short-lived OIDC token
naming this repository, this workflow and the `pypi` environment. No durable
credential lives in the repository, so there is none to leak or rotate. It costs
nothing: Actions is free and unlimited on public repositories, and PyPI's core
publishing features are free, with Community Organizations free as well.

**Triggered by a release, with a dry run.** Publishing on push would spend a
version number per commit. `workflow_dispatch` defaults to `dry_run: true`, so
the entire path — suites, kit, build, artifact inspection, install probe — can
be rehearsed without touching the index.

**The last check installs the wheel and creates a workspace with it.**
Everything above it can pass on an artifact that still cannot do its job.

**`dependencies = []` stays empty**, and the reason is now a comment in
`pyproject.toml`. `papersmith init` provisions the real environment, so the
installed CLI is a 2 MB tool that cannot conflict with anything a user already
has. A dependency added there is one every `pipx install` pays for before the
user even has a workspace.

**The `Daprosero` URLs were deliberately left alone.** The transfer to LIAUNAL
is blocked on repository admin rights, and pointing the published metadata at a
repository that may not exist would be worse than pointing it at one that
redirects. All ten references move in one commit once the transfer lands.

## Tasks

- [x] **T1 — The publishing contract exists.** `tests/test_pypi_publishing.py`:
  metadata, the kit inside both built archives, the per-file size limit, and the
  workflow's two invisible properties. RED first: 9 failures, with the 5 kit
  assertions passing because that part was already correct.
- [x] **T2 — The metadata is complete.** Authors, SPDX licence, README as the
  long description, project URLs, keywords and classifiers.
- [x] **T3 — The workflow publishes safely.** `.github/workflows/publish.yml`.

## Evidence

Branch `feat/pypi-publishing`.

- RED: 9 failed / 5 passed.
- GREEN: 15/15, and 56 passed across `test_pypi_publishing`,
  `test_version_sources`, `test_forge_gate` and
  `test_no_personal_context_dependency`.
- The built wheel's `METADATA` was read directly to confirm the fields reach the
  artifact: `Author-email`, `License-Expression: Apache-2.0`, four
  `Project-URL`s, eleven classifiers, `Description-Content-Type: text/markdown`.
- The workflow parses as YAML with the expected shape: two jobs, `release` and
  `workflow_dispatch` triggers, `id-token: write` on the publish job only, and
  the `pypi` environment.

### A defect the test caught in this work

The first metadata attempt declared both `license = "Apache-2.0"` and the
`License :: OSI Approved :: Apache Software License` classifier. **PEP 639**
superseded the classifier with the SPDX expression, and setuptools refuses a
build carrying both:

```
InvalidConfigError: License classifiers have been superseded by license
expressions (see https://peps.python.org/pep-0639/). Please remove: ...
```

The build-the-archive assertions went from passing to erroring, which is how it
surfaced. The classifier was removed and `test_states_the_licence_once` now
guards the combination, because declaring the licence twice is not redundancy
here — it is a build that fails.

## What is still manual, and must stay so

**Configuring the Trusted Publisher on PyPI.** Done once, on pypi.org, naming
owner, repository, `publish.yml` and the `pypi` environment. Nothing in a
repository can do this, which is the security property.

**Creating the `pypi` environment** in the repository's settings. Worth adding a
required reviewer, so a release cannot publish without a human.

**The first publication.** The irreversible step stays a human action:
`gh release create vX.Y.Z`, or a dry run first.

## Not done

- **No TestPyPI rehearsal.** The `dry_run` path verifies everything except the
  upload itself. A TestPyPI run would need a separate Trusted Publisher and
  would verify the one step that cannot be rehearsed safely anywhere else; it
  was judged out of scope rather than unnecessary.
- **The ten `Daprosero` URLs**, pending the transfer.
- **`docs/releasing.md` does not mention PyPI yet.** It describes four artifacts
  that must agree — version, changelog, tag, GitHub release — and there is now a
  fifth. The document should say so before the first publication.

## Next step

The user resolves the transfer (repository admin is required and this session
does not have it), then configures the Trusted Publisher and cuts the first
release. Nothing is published.
