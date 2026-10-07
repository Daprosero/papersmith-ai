# Changelog

Notable changes to papersmith-ai, newest first.

This file starts at 0.2.0. `0.1.0` was set in the commit that created the
package and never moved again across more than a thousand commits, so there
is no honest way to reconstruct a release history for it — its record is the
git log, and pretending otherwise would put a fabricated summary where a
reader expects a kept one.

Versions follow [semantic versioning](https://semver.org): while the first
number is `0`, breaking changes can still arrive without a major bump.

## 0.13.0

### Changed

- **The Paper Command Center speaks the architecture diagram's visual
  language, in two themes.** A reader moving from
  `docs/diagrams/papersmith-pi-flow.html` to `papersmith ui` crossed a visual
  seam that carried no information: different type, different elevation,
  different palette, for the same stages and the same gates. Light stays
  `:root`, dark arrives as `[data-theme='dark']`, and the choice persists ---
  the system preference decides the first visit, an explicit choice wins after
  that, and `light` is the floor when storage cannot be read at all.
  Archify publishes no stylesheet, so the signature is transcribed rather than
  imported: elevation as glow instead of drop shadow, radius by opposition
  (pills at 999px against structure at 1px), and tracking by opposition (tight
  on headings, wide on uppercase micro-labels). Archify's infrastructure-role
  hues are deliberately not adopted --- its frontend/backend/database taxonomy
  says nothing about a paper pipeline, so stage, gate and section keep their
  meaning and only their hues move. On the canvas a node's role is now a full
  stroke over a translucent fill of the same hue, the way the diagram states
  it, instead of an accent bar on one edge.

### Added

- **The style contract understands two themes, and still refuses literal
  colour.** `ui/src/styles.test.ts` was generalized from a single `:root` to a
  theme map: it reads both blocks, excises both from the text its
  literal-colour rule inspects, resolves dark tokens through a light fallback
  the way the cascade does, and runs every WCAG AA contrast assertion once per
  theme. The contract was extended, never weakened; both themes pass on every
  surface, badge fill, node, edge label and terminal.
- **Browser checks for behaviour and layout.** 255 jsdom tests could not see a
  clipped label or an overlapping control, because jsdom computes no layout.
  Playwright now runs `ui`-local as `npm run test:e2e` against the real FastAPI
  server serving the committed bundle --- not `vite preview`, which resolves
  assets differently and skips the `Host` validation that has broken the
  dashboard before. It waits on `body[data-ready]`, the signal `App.tsx`
  already published. Functional: tab activation and singularity, deep links
  surviving a reload, node selection opening an addressable detail panel, and
  the theme switch actually repainting --- asserted through computed
  `backgroundColor`, because an attribute that changes while the paint does not
  is the failure worth catching. Layout: text clipped by its own box,
  horizontal spill past the viewport, pairwise control overlap, a 24px minimum
  hit target, and the element panel's geometry on both sides of the 900px
  breakpoint.
  It earned its place on the first run: the new uppercase tabs spilled past an
  820px viewport. Bisecting against the pre-restyle stylesheet proved it was a
  regression introduced by this work rather than a pre-existing defect, and the
  tab strip now wraps. Horizontal scroll was rejected for hiding the last tabs
  behind a gesture nobody announces.
  It is deliberately not in `npm run test:all`, which does not run the vitest
  suite either; wiring a browser suite into a gate that skips the unit suite
  would be backwards.

## 0.12.0

### Added

- **`upgrade` migrates workspace artifacts, not only framework files.** The
  recorded `.papersmith/version` is now a claim about a workspace's artifacts
  rather than about which skills tree it holds, and a release that changes an
  artifact's shape can carry an older workspace to it. Migrations run in one
  place — after the kit is copied, because a migration may need the scripts and
  assets of the release that just arrived, and before the version marker is
  written. The mechanism is `src/papersmith/core/migrations.py`.
- **Two classes of migration, and only one of them is recorded.** A
  version-bound migration runs once, when the workspace sits below its gate and
  the installed kit at or above it, and lands in `.papersmith/migrations.json`
  so it cannot run twice. A convergence migration has no gate: it asks the
  filesystem through a read-only probe and is evaluated on every run, because
  the next release can change what it converges toward.
- **`sota-pool/` is a declared directory instead of a survivor.** It holds
  `candidates.json` and `atlas.json` from the scouting agents plus the derived
  `atlas.html`, and it survived upgrades only because `upgrade` deletes nothing
  it did not baseline first. This release ships two convergence migrations:
  `sota-pool-scaffold` creates the pool's `.gitkeep` in older workspaces, and
  `atlas-render-refresh` re-renders `sota-pool/atlas.html` when its atlas, its
  renderer or the vendored viewer bundle it inlines has changed — decided by
  hashes stored in `sota-pool/.atlas-render.json` and never by modification
  times, because `upgrade` rewrites files for reasons that have nothing to do
  with the page.
- **`status` reports pending migrations**, and `upgrade` gained
  `--plan-migrations`, which reports the pending set and writes nothing. It is
  deliberately not named `--dry-run`: that name would imply the kit copy, the
  harness projections and the orphan sweep were previewed as well, and they are
  not.

### Changed

- **The version marker advances only when that version's migrations are done.**
  A failed migration leaves `.papersmith/version` where it was, exits non-zero,
  and the next run retries. `--no-migrate` does not advance it either — doing so
  would record a release the workspace never reached and let `status`'s
  `version_match` report that as agreement. The manifest is the opposite case
  and is always written: it describes files, and the files did move.
- **A version that cannot be ordered refuses rather than guesses.** With the
  marker missing or unreadable, a version-bound migration is reported
  `undetermined` and never applied: migrating artifacts under a relation nobody
  established is the silence the downgrade guard already removed on the file
  side. Convergence migrations are unaffected, because they ask the disk.
- **The downgrade guard and the migration gate share one ordering
  implementation** (`migrations.version_order`), replacing `upgrade`'s own
  `_version_order`.

### Fixed

- **Four `test_papersmith_upgrade` fixtures derive a version newer than the
  kit's instead of pinning `0.9.0`.** A fresh workspace records the
  *distribution* version, so once the package moved past `0.9.0` those fixtures
  turned their own setup upgrade into a downgrade that the guard correctly
  refused: the guard doing its job while the tests asserted the opposite. They
  had been failing the CI gate since `0.10.0`.

## 0.11.0

### Changed

- **The proposal tramo reports its two artifacts separately.** It was lit only
  by `proposals/*.md`, so a published revision and a published revision with
  its graph read the same to the board. It now counts the revisions and the sky
  graphs (`proposals/*.graph.html`), names both in its detail, and reports
  their ratio as its progress -- a revision without its graph is exactly the
  half-done state worth showing.
- **The Pi flow diagram names both artifacts** on `proposals/` and draws a
  dashed `atlas.json` edge from `sota-grapher` to `deliberation-publish`. A
  sixth node in that carril did not survive the diagram's own gates. With a cell
  narrow enough to leave the figure readable, validation reports
  `layout/constraint`: `/experimental-implementation` is ~185px of label in a
  176px cell, and connections shortened with it fall under their 24px floor.
  With cells and gaps wide enough for both, the six-column viewBox reaches
  1370px, where `composition/desktop-readability` projects 8px source text at
  5.43px against its 6px floor. The graph therefore travels as the second
  artifact of the tramo's existing node, which is how the extractor counts it.

### Added

- **The proposal's sky graph is a step of the flow.** Stage 3's graph -- the
  SOTA constellation with the proposal inside it -- was documented, tested and
  run by nobody: the architecture diagram had no node for it, the *Pipeline*
  tab could not see it, and no agent produced it. Three surfaces now carry it.
  `deliberation-publish` now requires the overlay — reporting it as `owed`
  rather than inventing a relation to have something to draw — runs the skill's
  three commands in order (merge, check, render), and reports the rendered path,
  `proposals/<revision>.graph.html`, with the checker's verdict and whether the
  published revision names it. The deliberation's own skill now pins *when* the
  overlay is authored -- before the change is accepted, because the successor's
  text is what names the picture -- and the publish stretch has no `Write`, so
  an overlay it cannot find is reported rather than manufactured.

## 0.10.0

### Changed

- **The dashboard's flow is the architecture diagram's flow.** The Paper Command
  Center's *Pipeline* tab drew six stages invented inside the extractor --
  `ingestion`, `deliberation`, `experiments`, `drafting`, `auditing`,
  `publishing` -- while `docs/diagrams/papersmith-pi-flow.html` drew the same
  project as twelve numbered tramos plus a transversal audit lane, and nothing
  compared the two. The board now draws those twelve tramos in the diagram's
  order, with the diagram's main chain as the edges, and each tramo lights up
  from its own artifact on disk: `sota-pool/`, `guidance/`, `proposals/`,
  `implementations/`, `.experimental-deliberation/`, `experiments/`, the
  accounts store, the inbox, `paper/Figures/`, `sections/`. A tramo with no
  artifact reports what is missing instead of an invented progress. The chain
  travels in the payload (`pipeline_chain`, `gate_links`), so the drawing cannot
  disagree with the stage list it is drawn from -- which is how it disagreed
  before.

### Added

- **The writing flow, section by section.** A new *Writing* tab draws the
  paper's ten sections in rendering order, each with its live status, its word
  count and its blocks, as a flow of its own.
- **`npm run build:ui` and `npm run dev:ui`.** Rebuilding or serving the
  dashboard meant knowing to run `npm install` and `vite build` inside `ui/`,
  and the repository offered no script for either half.

## 0.9.0

### Added

- **`papersmith init` reports its own progress.** A bar with an estimate of the
  time left, plus the streamed log of the two child processes it runs —
  `npm install` and the workspace's environment provisioning — which until now
  ran with their output captured: minutes of silence, and on a cold cache up to
  the whole provisioning timeout. The estimate starts from declared priors and
  is recalibrated with the pace the run measures, so a step that overruns its
  share moves the number instead of contradicting it. `--progress` forces a
  plain log for CI, `--no-progress` silences the bar, and a pipe stays silent by
  default — which is what keeps the MCP server's child invocation readable.

## 0.8.0

### Changed

- **The Pi entrypoint is the file Pi reads.** The `pi` runtime's generated
  entrypoint moves from `PI.md` at the workspace root to
  `.pi/APPEND_SYSTEM.md`. Pi never read `PI.md`: its project context candidates
  are `AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md` and
  `CLAUDE.MD`, while a trusted project `.pi/APPEND_SYSTEM.md` is appended to the
  system prompt and takes precedence over the operator's own agent-level append
  instead of combining with it. `upgrade` retires a baselined `PI.md` — nothing
  else could, since a static entrypoint is deliberately outside the orphan rule
  — and `audit` names a leftover one, in any workspace, as surplus. A `PI.md`
  this tool never wrote is the operator's file and is never removed.
- **The SOTA atlas is a 3D sky.** `/plausibility`'s `sota-pool/atlas.html`
  now draws the constellation with three.js instead of an inline SVG plane:
  family neighborhoods at their own heights, one tilted orbital plane per
  system, arcs between systems, orbit/zoom/fly-to controls. It is still one
  self-contained file that opens offline and renders byte-identically from the
  same atlas: `render_atlas.py` (stdlib-only) precomputes the scene and inlines
  the vendored viewer `skills/plausibility/assets/atlas3d.bundle.js`, rebuilt
  with `npm run build:atlas-viewer` (pinned `three` and `esbuild`
  devDependencies). The planet popup now builds its text with `textContent`.

### Fixed

- **Skill descriptions fit the ceiling the harness enforces.** Pi caps a
  skill's `description` at 1024 UTF-16 code units
  (`MAX_DESCRIPTION_LENGTH`), and `paper-writing` sat at 1680 while
  `remote-execution` sat at 1814; Pi warned and loaded both anyway, so nothing
  ever failed. They now measure 1015 and 923, and
  `tests/test_skill_descriptions.py` holds the budget — in UTF-16 code units,
  because that is the unit JS `length` counts and therefore the unit the
  ceiling is written in. No claim was dropped on the way: `remote-execution`'s
  provenance date for the pinned `kagglesdk` (`since 2025-07-11`) moved into
  the body beside the pin, where it had never been written down.
- **Pi agents no longer list unsourced `mcp`/`mcpScript` tools.** The
  `.pi/agents` projection skips `WebSearch`/`WebFetch` with a note instead of
  mapping them to names Pi does not document. The Antigravity
  `commandExecutionPolicy` values are documented as having undocumented
  semantics; its output is unchanged.
- **Workspace `.gitignore` covers the skills links.** A new workspace now
  ignores `.claude/skills`, `.opencode/skills`, `.pi/skills` and
  `.agents/skills` (the generated symlinks to `skills/`), so `git add .` no
  longer commits them.

### Added

Interactive Paper Command Center: a light theme, a clickable diagram and a
session history.

- **The proposal travels with its own sky.** Stage 3 ships a 3D graph beside the
  published revision — the SOTA constellation with the proposal inside it, drawn
  by the same vendored viewer. `merge_proposal_sky.py` merges the pool
  (`sota-pool/atlas.json`) with the proposal's overlay
  (`proposals/<revision>.sky.json`) into one atlas, and the existing
  `render_atlas.py` draws it, so the proposal's main idea, the topics it takes
  from the SOTA papers, its one novelty claim, the issue it could resolve and
  its three to five contribution concepts are nodes with real edges into the
  papers they touch — the relationship is drawn rather than asserted. The atlas
  gains one optional slot, `contribution` (orbit 1, zero to five planets), which
  a paper leaves empty; the three-to-five range belongs to the merger, because
  it is the overlay's contract and not the constellation's, and the pool's own
  checker stays the single authority on families, orbits and evidence.
  `render_atlas.py` also gains `--title`, so one viewer can name another
  domain's sky instead of borrowing a title that would be false for it.
- **Read-only paper preview routes in the command center.**
  `GET /api/paper/preview` returns sections (extractor order and ids) with
  plain-text block bodies from `paper/main.tex`, citation keys, `written`,
  truncation/duplicate flags, PDF/figure info (with an `mtime` in ms used as
  a `?v=` cache-buster) and `sections_dir` (`ok`/`absent`/`unsafe`, `truncated`
  past 100 non-canonical sections); `GET /api/paper/file?name=`
  serves only `main.pdf` and `figures/<id>.pdf|png` (real directory
  `paper/Figures/`; id is one `[A-Za-z0-9._-]` segment, no leading dot, at most
  100 characters). Reads are size-capped before reading (`main.tex` 2 MiB,
  sections 256 KiB, 200 KiB of text per response, 25 MiB per file with 413),
  resolved and contained in the workspace, regular files only. Responses carry
  `nosniff`, `X-Frame-Options: SAMEORIGIN` and `no-store`; there is no CSP
  sandbox and no `Range` support. The `Host` allow-list (421) covers them only on
  loopback binds; non-loopback binds do no `Host` filtering.
- **Preview tab.** `#preview` shows the written block text (escaped plain text,
  citation keys as chips, placeholders for unwritten blocks, truncation and
  `main.tex` status notices) beside the compiled `paper/main.pdf` in an
  `<iframe>` (with a stale badge) and a list of `paper/Figures` files. It is
  fetched when the tab opens and refetched when the workspace revision changes,
  with an inline error and Retry. The visual checker covers the tab.
- **Atlas tab.** `#atlas` shows a native summary of `sota-pool/atlas.json`
  (systems, planets, families, link and relation counts, a capped evidence list,
  a validation chip) beside `atlas.html` in an
  `<iframe sandbox="allow-scripts">` without `allow-same-origin`. Every text is
  escaped; absent, too-large, unsafe, unreadable, invalid, missing-HTML,
  missing-JSON and STALE states are explained. The atlas is not watched, so it is
  fetched when the tab opens and on a Refresh button, with an inline error and
  Retry. The visual checker covers the tab and waits for the frame fetch.
- **Decisions tab.** `#decisions` renders `/api/decisions` as a read-only
  timeline: dated events newest first, then an "Undated" group for edit receipts; each
  row shows a UTC timestamp, a source chip, the kind, the summary and the `ref`
  as plain text, an "unverified" label for lifecycle records read without hash
  checks, and muted notes. Per-source status chips (ok, absent, unreadable,
  too_large, counts, detail, truncated), a client-side source filter and a
  "Showing N of total" notice. Fetched when the tab opens and on Refresh, with an
  inline error and Retry; all text is escaped. No Sections link (not cleanly
  derivable). The visual checker covers the tab.
- **Read-only decisions timeline route in the command center.**
  `GET /api/decisions` merges, on request, normalized events
  `{ts, source, kind, summary, ref}` from the declarations region of
  `paper/main.tex` (only the current state is stored, so earlier values are not
  recoverable), the `.proposal-deliberation/` and `.experimental-deliberation/`
  receipts and lifecycle transitions, and the remote-execution ledgers at
  `implementations/<repo>/<Name>/.remote-execution/ledger.jsonl` (exactly two
  levels, no recursion; `kaggle-inbox/` is never read). Edit receipts have no
  timestamp, so their events carry `ts: null` and sort after dated events (file
  mtime is never used); the initial-revision receipt carries `createdAt`, which is
  its `ts` ("Created initial revision r01"); deliberation events are plain-JSON reads without the
  lifecycle hash checks and carry `verified: false` (to be shown as
  "unverified"). Newest first with a stable tie-break; each source reports
  `status` (`ok`, `absent`, `unreadable`, `too_large`) so one broken source never
  fails the response. Caps: 500 events per source, 1000 total (`truncated`),
  `main.tex` 2 MiB, 256 KiB per receipt or transition, 500 files per sidecar
  directory, 20 ledgers of 2 MiB and 2000 lines each (the newest 2000 lines are kept; `detail`
  counts the oldest ones ignored). Optional `source=` (422 on
  an unknown name) and `limit=` (1 to 1000). Nothing is written. The `Host`
  allow-list (421) covers it only on loopback binds.
- **Read-only SOTA atlas routes in the command center.** `GET /api/atlas`
  reports the state of `sota-pool/atlas.json` and `atlas.html` (ok, absent,
  too_large, unsafe, unreadable, invalid), staleness (json newer than html),
  the workspace checker's verdict (`ok`, `failed` with up to 50 errors,
  `unavailable`) and a summary (systems, families, links, relations, evidence).
  Each file entry carries an `mtime` (ms) the UI uses as `?v=` on the iframe;
  `GET /api/atlas/view` serves `atlas.html` (404 absent/unsafe, 413 over 2 MiB)
  under `Content-Security-Policy: sandbox allow-scripts; default-src 'none';
  script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:`,
  `nosniff`, `no-store`, `X-Frame-Options: SAMEORIGIN` and
  `Referrer-Policy: no-referrer`. Reads are size-capped (2 MiB), resolved and
  contained in the workspace, regular files only; nothing is written or
  regenerated. Validation loads the workspace's own
  `skills/plausibility/scripts/check_atlas.py` from that one fixed path and runs
  it inside the server process (workspace Python execution: only serve trusted
  workspaces); a missing or failing script yields `unavailable`. The `Host`
  allow-list (421) covers both routes only on loopback binds.
- **Light theme.** The dashboard uses one light theme built on colour tokens;
  Vitest guards reject colour literals outside `:root` and check WCAG AA
  contrast for the token pairs. The state and health payloads now load
  independently, so a slow health measurement no longer keeps the page on
  "Loading".
- **Clickable pipeline diagram with deep links.** Every stage, gate, section
  and edge can be selected with the mouse or the keyboard and opens a detail
  panel (fields, connections, history). The selection lives in the URL hash
  (`#pipeline?el=<id>`), so links open the element directly.
- **In-memory history.** A History tab and `GET /api/history` (cursor paging
  with `boot_id`, `after_seq`, `has_more`, `reset` and `gap`) record section,
  gate, stage, health and smoke changes since the server started, and
  `history_append` streams new entries over SSE. Nothing is written to disk.
- **Host allow-list.** On loopback binds the server answers 421 to a `Host`
  header it does not recognise; `papersmith ui --allowed-host HOST:PORT`
  (repeatable) adds one, for example `--allowed-host localhost:5173` when
  running `npm run dev`. Stage history entries now say what changed.
- **Visual checker and UI tests.** `scripts/command-center-visual-check.mjs`
  screenshots every tab in Chromium (`--full-page`, `--click-check`,
  `--drag-check`); the Node CI job now also runs `npm ci --prefix ui` and the
  Vitest suite (`npm test --prefix ui`).

Harness parity: skills, commands, agents and guards in each harness, wired by
`init` and `upgrade`, with an honest report of what is not.

- **Per-harness wiring summary.** `init` and `upgrade` print one line per active
  harness (`skills`, `commands`, `agents`, `plugins` as `wired`, `unsupported`,
  `failed` or `blocked`) and add a `wiring` key to their results. The support
  matrix lives in `generators.HARNESS_CAPABILITIES`, derived from the constants
  `render_files` writes through; exit codes and existing keys are unchanged.
  The health inspector's structural fallback also checks agents and the
  plugin/extension. The README table of what each harness wires is tested
  against that matrix.
- **README support matrix and Antigravity note.** The README now carries the
  sourced per-harness support matrix (with source URLs and the 2026-10-02 date)
  and states why Antigravity gets no command files (workflows are deprecated in
  favour of skills); its commands cell reads "unsupported — vía skills". Nothing
  generated changes.
- **Link-failure warnings.** Skill-link failures (an `OSError`, or a real
  directory at a link path) are reported by `init` and `upgrade` instead of
  being skipped silently.
- **OpenCode agents.** `init` and `upgrade` project each `.claude/agents/*.md`
  definition into `.opencode/agents/<name>.md` with `mode: subagent` and a
  least-privilege `permission` block mapped from the Claude `tools:` list
  (unknown tools are never granted and are reported). `upgrade` removes agents
  whose source disappeared.
- **Antigravity agents.** `init` and `upgrade` generate `.agents/agents/<name>.md`
  from the `.claude/agents/` sources (explicit `tools` allow-list mapped to
  Antigravity tool names, `commandExecutionPolicy` `off` unless the agent has a
  shell tool). Stale ones are removed on upgrade. Sourced from
  https://antigravity.google/docs/subagents and /docs/hooks.
- **Pi prompt templates.** `init` and `upgrade` project one prompt template per
  skill under `.pi/prompts/<name>.md` (the same body as the Claude Code and
  OpenCode commands, with `$ARGUMENTS`), and `upgrade` removes the ones whose
  skill disappeared.
- **Pi off-path push guard.** `init` and `upgrade` generate
  `.pi/extensions/refuse-offpath-push.js` for workspaces that declare `pi`: a
  `tool_call` extension that shells out to the same Python guard as the OpenCode
  plugin (a tripwire, not a gate) and fails open when the guard, python, or the
  event is unusable. `docs/guard-hooks.md` documents an opt-in Claude Code hook
  snippet (never written to `.claude/settings.json`) and records that an
  Antigravity guard is unsupported until its hook input schema is verified.
- **Antigravity `.agents/skills` link.** `init`, `upgrade` and
  `scripts/setup-harnesses.sh` link `.agents/skills` to `skills/`, so skills can
  be invoked as `/name`. Antigravity still gets no command files.
- **Docs.** `docs/harness-support-matrix.md` (sourced per-harness support) and
  `docs/guard-hooks.md`; the README now states per harness what is wired,
  unsupported or opt-in.

### Changed

- **The health check is per enabled tool.** It requires each harness link and
  commands directory only for the tools the workspace enables, instead of
  reporting drift for every known harness.
- **Antigravity uses only documented locations.** Skills at `.agents/skills`,
  agents at `.agents/agents/` and the rules entrypoint at `.agents/AGENTS.md`.
  `.antigravity/rules.md` and `.antigravity/skills` are no longer generated.
  Pre-1.0 breaking change: existing workspaces are not migrated; re-run
  `papersmith init` in a fresh workspace.
- `upgrade` also removes stale `.pi/agents` files whose source disappeared.
- Pi agents need the third-party `pi-subagents` package; Pi core has no
  sub-agents.
- Unverified before release: that real Antigravity lists `.agents/skills/<name>`
  as `/name`, and whether Pi shows a trust prompt for project `.pi/prompts`. If
  the Antigravity premise fails, ship the Pi part alone.

## 0.7.1

### Fixed

- **The clean-context gate fails when the gate itself fails.** `scripts/clean_context_gate.py`
  only compared the empty-HOME run with the decoy-HOME run, so a suite that
  failed the same way under both exited 0. The empty home is the machine with
  no personal context, so its own failure now fails the step. Its temporary
  homes are also removed on SIGTERM (a cancelled CI job) and when a read-only
  file is left under HOME, and a leftover is reported instead of ignored.

### Changed

- **CI runs the suite once per job, not twice.** The plain `pytest` step is
  gone: the gate already runs the declared suite under an empty HOME, and
  with the fix above it fails on that run's own failure. About eleven minutes
  less per Python job.
- **The README installs the latest `main`**, never a pinned tag, and its
  counts (CLI commands, skills, agents, MCP tools), flag tables, badges and CI
  description now match the code.

## 0.7.0

### Added

- **Pi receives the agent roster.** The nineteen agent definitions existed
  only under `.claude/agents/`, while Pi discovers agents at
  `<cwd>/.pi/agents/*.md` -- so in that harness a delegated stretch had no agent
  to land on, and a flow could stall asking the operator about routing that did
  not exist. The kit renderer now projects each definition onto Pi's shape:
  front matter travels verbatim except `tools:`, mapped onto Pi's tool names
  (`WebSearch`/`WebFetch` onto the MCP gateway the agent bodies already
  prefer), and the body's `.claude/skills/` references become the
  harness-neutral `skills/` link every workspace already carries. It is a
  rendered path, so `init`, `upgrade`, `status` and the drift check pick it up
  from the one path authority -- and nothing is forked: the projection derives
  from `.claude/agents/` on every run. A malformed definition, an absent or
  unsafe name, or an unreadable file is skipped with a warning, never raised
  on.
- **A fresh workspace ships the `paper_writing` connector roles.** Without
  them, `paper_cli.py resolve` refused `RESOLVER_ROLE_EMPTY` before any
  literature work could start -- and that front door is what the scout and the
  screener both depend on. The seeded block mirrors this repository's own:
  OpenAlex/Crossref/arXiv for resolution, and full-text only for the two
  connectors whose own resolved metadata names a fetchable PDF. `contact` is
  seeded empty on purpose; it is the operator's courtesy address for OpenAlex's
  polite pool, never a shared credential.

### Fixed

- **`init` no longer aborts a workspace's provisioning on the editable
  install.** The provisioner ran `pip install -e <root>` unconditionally and
  with `check=True`, and a workspace is not a Python project -- no
  `pyproject.toml`, no `setup.py`, only `requirements.txt`. Pip refused with
  "does not appear to be a Python project", the step aborted before
  `marker-pdf`, and the workspace reported `OCR Engine Missing` while its conda
  environment was otherwise fine: `fastapi` imported and `papersmith ui` ran.
  The editable install now runs only where there is a Python project to
  install, which is the framework checkout, and says so when it skips.
- **`resolve` accepts the identifier a user actually pastes.**
  `arXiv:1512.03385` was sent to the arXiv API with its prefix, and that feed
  answers entry-less -- measured: 706 bytes with no `<entry>`, against 2814 for
  the bare id -- so the command died on a traceback instead of returning
  metadata. One case-insensitive `arXiv:` prefix and surrounding whitespace are
  stripped before the query, and a feed that names no work now refuses as
  `IDENTIFIER_UNRESOLVED`, the code the contract already documented.
- **Both offline smoke wrappers are hermetic again.** They called `init` with
  `--no-npm` and no `--no-env`, so the wrapper provisioned a real
  multi-gigabyte environment: the wiring smoke built one inside its own 180s
  test timeout and failed there, while its header promises "no npm, no
  network". Neither line had changed since it was written -- `init` gained the
  provisioning step two days later -- and the guard written to catch exactly
  this swept `tests/` only, so it stayed green over both callers. The wrappers
  pass `--no-env` now, and the guard sweeps `scripts/` and `.github/` too.

### Internal

- `.gitignore` covers the `.venv` symlink CI creates. The directory form
  (`.venv/`) does not match a symlink, so `git status` reported the workflow's
  own artifact as untracked.

## 0.6.0

### Added

- **`papersmith ui`: the Paper Command Center.** A local dashboard and
  health/wiring control plane for an initialized workspace, reachable through
  one command. It serves the workspace's own state -- paper metadata, the ten
  section contracts, the four quality gates, the pipeline stages, and the
  evidence ledgers -- over `/api/state`, reports harness, skill, agent and
  environment wiring over `/api/health/wiring`, and streams changes over SSE
  within about a second of a section edit. The backend ships in the kit
  (`skills/_core/command_center/`), so a workspace can run
  `python -m skills._core.command_center.server` standalone with no Node/npm
  dependency in the paper directory; the React/Vite dashboard is committed as a
  built bundle beside it, and `--export-static` writes a copy anywhere. The
  server is read-only: it observes a paper and never edits one.

### Changed

- **`init` reports a wired harness `skills` link like every other kit file,
  and `upgrade` repairs one.** Each harness (`claude`, `opencode`, `pi`,
  `antigravity`) reaches the kit through a relative `skills` symlink. A
  filesystem that could not create one used to read as a silent success; it now
  surfaces as a gap. The link never overwrites real, non-symlinked content at the
  same path, and `upgrade` re-links a stale one. A hermetic smoke script,
  `scripts/cli-paper-wiring-smoke.sh`, asserts the four links, agent and
  slash-command parity across the harnesses, and live repair.
- **`init` provisions the workspace environment, and `papersmith ui` resolves
  the interpreter that provisioning creates.** `init` runs the workspace's own
  `scripts/setup_env.py install` (fail-soft, skipped with `--no-env`), so the
  dashboard works straight after `init` instead of exiting on a raw
  `ModuleNotFoundError`. `ui` looks for `.micromamba/envs/papersmith` first, then
  a `.venv`, and refuses with the one command that provisions the environment
  when neither can import the backend.

### Fixed

- **`scripts/setup_env.py` installs the command center's dependencies.**
  `fastapi`, `uvicorn`, `watchfiles` and `pydantic` were declared in the kit's
  `requirements.txt` but never installed, so the environment the gate names could
  not load the server's tests. They are installed from the same list now.

## 0.5.1

### Added

- **`settle --attach --replace`: re-pointing a proof is not retracting a
  claim.** A checklist line's `` `test_<id>` `` witness could be attached
  once and never moved -- `--attach` refused `SETTLE_ALREADY_WITNESSED` on a
  line that already carried one, and the only path that reached a re-point
  was `--reverse` followed by a fresh placement, which de-ticks and
  un-witnesses a line that was already measured and closed. `--replace`
  closes that gap as a modifier on `--attach`'s own write, not a sixth mode:
  the mark is never touched (mark-blind between a ticked and an open line),
  and every other byte of the holder file is identical before and after the
  call. Three new refusals guard it, all `INVOCATION_DEFECT`:
  `SETTLE_REPLACE_CONFLICT` (`--replace` without `--attach`),
  `SETTLE_NOTHING_TO_REPLACE` (the located line carries no witness at all --
  plain `--attach` is the create path), and `SETTLE_WITNESS_UNCHANGED` (the
  incoming token equals the one already there). Performs no read of
  `tests/`: gating on whether a witness names a real test stays exactly
  where it already was, at `verify`/`close`. The previous token is recorded
  as `replacedWitness` in both the `settle` ledger event and the command's
  response, beside an always-present `replace` boolean that mirrors the
  other four mode flags on every `settle` call.

### Changed

- The one sealed `settle` case's declared golden delta did not materialize:
  that case already refuses `SETTLE_NOT_DISCUSSED` before reaching the
  success path where `replace`/`replacedWitness` would appear, a
  pre-existing condition unrelated to this change. `tests/seal/digests.json`
  is therefore unchanged -- recaptured and confirmed byte-identical, not
  regenerated.

## 0.5.0

### Added

- **`figure-review`, the tenth skill: the eye that looks at the rendered
  diagram.** `render` compiled a figure to PDF and `figure audit` judged it
  against the prose, and nothing ever looked at the picture. Overlapping boxes,
  text running off the canvas and bad connections were all reported
  `unmeasured` -- honestly, but unmeasured, and the socket for the skill that
  would measure them had been written and left empty.

  The skill rasterizes the already-compiled `Figures/<id>.pdf` through the
  first of `pdftoppm`, `pdftocairo`, `gs`, `sips` that resolves, decodes the
  PNG with a stdlib `zlib` reader, and computes what a raster can actually
  support. It calls `latexmk` never, so it spends nothing against `render`'s
  repair budget, and it imports nothing into `paper-writing` -- the join is
  `--visual-report <path>`, a report already on disk read as plain data. A
  test now holds that import edge absent rather than leaving it true by
  accident.

  What it reports is graded by what can be known, and the grading is the
  point:

  - **A verdict** for `out-of-bounds` and `overlap` -- computed, numeric,
    with intersecting boxes in pixel and point coordinates, and reported as
    unnamed regions. The raster found the collision; the source names the
    nodes, and nothing here joins them.
  - **A number with no verdict** for `canvas-occupancy`. "Too much whitespace"
    is a judgement about composition, so the fraction is reported and nothing
    fails on it.
  - **An announced silence** for legibility, style, connection correctness and
    which component an overlap belongs to, each with a named reason.
  - **An assisted reading** for what the agent itself sees. It is labelled,
    never appears in a verdict field, and may never upgrade an `unmeasured`
    dimension to `pass`.

  `out-of-bounds` is itself `unmeasured` when the source declares no border: a
  standalone TikZ canvas is fitted to its own ink, so without one there is no
  way to tell ink that ran off from a canvas that was drawn to fit.

- **`figure audit`'s report carries a `visual` key**, always present, never
  null, supplied by the caller and unable to change the semantic verdict. A
  visual `fail` beside a semantic `pass` leaves the top-level verdict at
  `pass`, and a test holds that in both places it could regress.

### Fixed

- **`figure-auditor`'s precondition is a command instead of a belief.** It read
  "when that skill is available in this session" with nothing measuring it; it
  now runs the skill's front door and quotes the exit.
- **`legibility`'s reason for being unmeasured was false.** It named a missing
  image tool. Glyph metrics come from the PDF's text layer, not an image, so
  the tool was never the obstacle -- legibility is a threshold judgement, and
  the reason code now says so. Deferring behind an honest reason is a note;
  deferring behind a false one is the defect this release exists to remove.

### Internal

- Five sequential work units, each mutation-proved: every lock was broken on
  purpose with the mutation a weaker lock would have survived, and watched to
  go red. One lock did survive its mutation and was rewritten -- it had been
  comparing literals rather than calling the function it claimed to guard.
- A file this repository tracked inside the target's own repository, under a
  path its own `.gitignore` declares it does not carry, is tracked no longer.

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
