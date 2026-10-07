# `/upgrade-project`: the upgrade becomes reachable from inside a workspace

`papersmith upgrade` has existed since 0.12.0 and was only reachable from a
terminal. An agent working inside a workspace could see that the workspace was
running an older release and could do nothing about it. This adds the
in-workspace surface, and nothing else.

## What the repository decided for us

The design space here was smaller than it looked, and the repository settled
three of the four open questions on its own.

**A slash command cannot be hand-written.** `.claude/commands/*.md` are derived
artifacts in the checkout as well as in a workspace: `collect_commands`
(`src/papersmith/generators.py:327-363`) lists `skills/*` and projects one
command per skill. A hand-made command file with no skill behind it is an
orphan — deleted by the upgrade's own orphan sweep if it was ever baselined
(`.claude/commands/` is a `DYNAMIC_PREFIX`, `core/upgrade.py:26-29`). So the
only correct shape is a twelfth `skills/upgrade-project/SKILL.md`, from which
all three projections follow: `.claude/commands/`, `.opencode/commands/` and
`.pi/prompts/`. Antigravity gets no command file by design.

**The command must shell out.** A workspace vendors no copy of the `papersmith`
package, so the upgrade can only come from the installed distribution.

**The projection ships in the same commit**, because
`scripts/sync-repo-harness.py --check` is a drift gate; a skill without its
projected files would fail CI.

The fourth question — which flags to expose — was ours. All five are
documented, with `--allow-downgrade` explicitly marked as something never to
add silently to recover from a refusal.

## The skill delegates and never reimplements

Every byte is written by `papersmith upgrade`. The skill decides *whether* to
call it and *with which arguments*, and reports what it said. The upgrade is
not a file copy — it is a kit copy, a symlink repair, a re-derivation of every
projection, an orphan sweep and an ordered migration run, with the version
marker written last and only when the artifacts reached that version. A second
implementation of that in a skill would be a second answer that can disagree
with the first.

## Tasks

- [x] **T1 — The fixtures declare the twelfth command.** Three pinned rosters
  (`tests/test_papersmith_generators.py`, `tests/test_workspace_commands_e2e.py`,
  `tests/test_workspace_skills_e2e.py`) plus the three `== 11` literals. RED
  first: 8 failures naming the absent skill.
- [x] **T2 — The skill exists and is honest.** `skills/upgrade-project/SKILL.md`
  with the `Trigger:` description contract, the two preflight checks, the three
  verbs, the flag semantics, and the exit-code reading.
- [x] **T3 — The command is projected to every harness.** `build-kit.py` then
  `sync-repo-harness.py`, with `--check` clean.
- [x] **T4 — Verified against a real workspace**, not only in tests.

## Evidence

Branch `feat/upgrade-project-command`.

- RED: 8 failures across the generator and skill-tree suites, every one naming
  `upgrade-project` as absent.
- GREEN: 129 passed in the four command/skill suites; `test_agents.py` passes
  untouched, so `NORTHLESS_SKILLS` needed no entry (it only covers skills bound
  to an agent).
- Projection: `harness projection: clean (95 files)`.
- `npm run test:node`: 681/681.

### Verified on a real workspace

A workspace was created with `papersmith init /tmp/ws-upgrade-test --no-env`,
and:

- the command landed in all three harness directories and the skill in
  `skills/`;
- `--plan-migrations` reported pending migrations and `Nothing was written.`;
- the version marker was hand-set back to `0.11.0`, and `upgrade` carried it to
  `0.13.0` with 6 changed files;
- a second `upgrade` changed 0 files, confirming idempotency;
- an empty directory was refused with `not a papersmith workspace` and exit 1;
- an already-current workspace exited 0.

### Two defects found in our own work

- **`python -m papersmith` does not work.** The skill offered it as a fallback;
  the package ships no `__main__.py`, so it fails with "'papersmith' is a
  package and cannot be directly executed". The entry point is
  `papersmith.cli:main`, so the fallback is `python -m papersmith.cli`. Caught
  by running it rather than by reading the entry-point declaration.
- **A copied roster broke a prose rule.** The skill enumerated
  `PRESERVE_PATTERNS` inline, which put a target-specific word into a forge
  document and failed
  `test_the_whole_forge_borrows_no_repository_s_vocabulary`. Fixed by pointing
  at `PRESERVE_PATTERNS` in `core/manifest.py` instead of restating it — which
  is the better answer anyway, and the same argument that replaced the `== 11`
  literals with `len(COMMAND_NAMES)`.

## Known pre-existing failures, unrelated to this work

Three, all environmental and all reproduced on clean `main` in a temporary
worktree: `test_case_of_the_public_prefix_is_exact` (APFS is case-insensitive),
and two `test_papersmith_init.py` cases defeated by the macOS
`/var/folders` → `/private/var` symlink.

Also note: the full pytest run is unreliable on this machine while Google Drive
syncs the 2.2 GB `.micromamba` environment under `~/Documents`. One parallel run
reported 389 spurious errors in `test_skill_audit.py`; the file passes 386/386
with 1294 subtests in isolation.

## Not done

- **The MCP `papersmith.workspace_upgrade` tool was left untouched**, as the
  0.12.0 cycle also chose. It exposes a deliberate subset of flags, and
  widening it is a separate reviewable decision.
- **No test drives the slash command end to end as an agent would**, because
  nothing in the suite does that for any of the twelve. The command's behaviour
  is verified through the CLI it delegates to.

## Next step

None: the cycle is closed. The user decides push and merge.
