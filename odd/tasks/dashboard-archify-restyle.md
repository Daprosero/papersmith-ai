# The dashboard speaks Archify's visual language, in two themes

The Paper Command Center looks like a utility and the architecture diagram next
to it looks like a product. Both describe the same pipeline. A reader moving
from `docs/diagrams/papersmith-pi-flow.html` to `papersmith ui` crosses a visual
seam that carries no information — different type, different elevation, different
palette, for the same stages and the same gates.

This cycle closes that seam, and adds the browser-level verification the UI never
had.

## What was decided, and by whom

The user chose both answers explicitly on 2026-10-07:

1. **Two themes with a switch.** Light stays `:root`; dark arrives as
   `[data-theme='dark']`. Not a dark-first inversion, and not light-only
   borrowing.
2. **The whole dashboard.** Shell, topbar, tabs, panels, badges, buttons,
   section matrix, terminal and the DAG canvas — one token system, no seams
   between tabs.

Two decisions are mine, stated so they can be overruled:

3. **Playwright stays `ui`-local.** `npm run test:all` does not run the vitest
   suite today (`package.json:9-12`); wiring a browser suite into a gate that
   skips the unit suite would be backwards. Playwright runs against the built
   bundle served by the real FastAPI server, not `vite preview` — verifying the
   server we ship beats verifying a stand-in. `document.body.dataset.ready`
   (`ui/src/App.tsx:76-88`) is the wait signal; it already exists.
4. **No shared token file with the diagram.** `docs/diagrams/papersmith-pi-flow.html`
   is a frozen artifact pinned to Archify 3.0.1. Visual coherence here is
   achieved by transcription and checked by eye, not enforced by a build-time
   token contract. Inventing that contract is a separate decision nobody
   authorized.

## What "Archify style" means concretely

Archify publishes no stylesheet. Its tokens live inline in
`~/.claude/skills/archify/assets/template.html`, so this is transcription, not
adoption. The transferable signature, with its source lines:

- **Elevation is glow, not drop shadow** — `0 0 20px rgba(...,.12)`, focus rings
  as `0 0 0 4px color-mix(in srgb, <hue> 16%, transparent)`, and
  `inset 0 0 0 2px var(--bg)` as a knockout ring (`template.html:643,679,689`).
- **Typography by opposition** — tight negative tracking on headings
  (`-0.015em`), wide positive tracking on uppercase micro-labels (`+0.12em`,
  `+0.14em`) (`template.html:655-703`).
- **Radius by opposition** — pills at `999px` against structural elements at
  `1px`/`0` (`template.html:544,642,674,687`).
- **Slate surfaces** — dark `#020617` / `#0f172a`, light `#f4f5f7` / `#fff`,
  borders `#1e293b` / `#e5e7eb` (`template.html:145-290`).

Deliberately **not** transcribed:

- **Archify's role hues.** Its taxonomy is frontend/backend/database/cloud/
  security/messagebus/external. This dashboard's is stage/gate/section with
  `ok`/`warn`/`bad`/`sealed`. There is no mapping, so the existing semantic
  roles keep their meaning and only their hues move toward Archify's register.
- **JetBrains Mono.** Archify self-hosts it across six `@font-face` blocks. This
  bundle is explicitly offline-capable (`styles.css:1-3`); vendoring font bytes
  is a size and licensing decision outside this cycle. The system mono stack
  keeps Archify's *tracking*, not its typeface.

## Constraints that bind this work

- **`styles.test.ts` is the safety net, not an obstacle.** It forbids literal
  colours outside `:root` and asserts WCAG AA contrast with alpha compositing.
  It must be extended to understand two themes, never weakened. A dark theme
  containing hex values would fail its first rule as written
  (`styles.test.ts:11-16` treats everything outside the first `:root` as `rest`).
- **The DAG's content is not ours.** `odd/tasks/dashboard-flows.md:50-57`
  decided the flow's shape comes from `state_extractor.py`, not the frontend.
  Restyling must not reintroduce catalogue literals in the UI.
- **The stage set is locked** by `tests/test_command_center_state.py`.
- **The bundle is tracked.** `ui/dist` does not exist; the served build lives in
  `skills/_core/command_center/static/`. Nothing is visible until
  `npm --prefix ui run build` runs and that copy is re-synced.

## Review workload warning

This touches a 1690-line stylesheet, every control in the UI, and adds a test
runner. It must not land as one pull request. Each task below is one work-unit
commit, and the slices are grouped for chained review: T1-T2 (contract and
tokens), T3-T5 (visual language), T6-T7 (verification and bundle).

## Tasks

- [x] **T1 — The style contract learns about themes.** Generalize
  `styles.test.ts` from one `:root` to a theme map: `:root` (light) plus
  `[data-theme='dark']`. The literal-colour rule excludes both theme blocks and
  nothing else; every contrast assertion runs per theme via `it.each`. Expect
  RED: the dark theme does not exist, so token lookup throws.
- [x] **T2 — Both themes exist as tokens.** Move light surfaces toward Archify's
  register and add the dark theme block. Add the tokens the new signature needs
  (glow elevation, knockout ring, micro-label tracking). GREEN on T1 for both
  themes, with no literal colour outside the theme blocks.
- [x] **T3 — The reader can switch themes.** A control in the topbar, honouring
  `prefers-color-scheme` on first load and persisting the explicit choice.
  Covered by a vitest unit test.
- [x] **T4 — The chrome carries the signature.** Shell, topbar, tabs, panels,
  badges, buttons and terminal adopt Archify's type scale, tracking, radius
  opposition and glow elevation.
- [x] **T5 — The canvas carries the signature.** Stage, gate and section nodes,
  edges and labels adopt the Archify register while keeping their semantic
  roles and the existing mutating/focus cues distinct.
- [x] **T6 — Playwright verifies behaviour and layout.** Install and configure
  it `ui`-local against the FastAPI server. Functional: tab navigation, node
  selection opens the detail panel, theme switch persists across reload.
  Layout: no text overflow or clipping, no overlapping controls, buttons meet a
  minimum hit target, the element panel becomes a bottom sheet under 900px.
- [x] **T7 — The shipped bundle matches the source.** Build the UI and re-sync
  `skills/_core/command_center/static/`, then confirm the served dashboard shows
  the restyle.

## Honest limits

Playwright asserts geometry and observable behaviour: that controls respond,
that text does not overflow its box, that nothing overlaps at a given viewport.
It cannot judge whether the result looks good. That judgement stays with the
user, and no test in this cycle claims otherwise.

## Evidence

Branch `feat/dashboard-archify-restyle`, six work-unit commits:

| Commit | Task | Outcome |
| --- | --- | --- |
| `b95001c` | T1+T2 | Theme contract generalized, both token blocks. RED first: 4 failed / 37 passed, then 41/41. |
| `4a2f99b` | T3 | `useTheme` 7/7 (RED first on the missing module), `ThemeToggle` 5/5. |
| `216d71b` | T4 | Chrome signature. 255/255. |
| `c3f4d43` | T5 | Canvas signature. 255/255. |
| `1191d60` | T6 | Playwright 29/29 across 1440px and 820px, plus the tab-wrap fix. |
| `ba0ba22` | T7 | Bundle rebuilt into `skills/_core/command_center/static/`. |

T1 and T2 share a commit deliberately: a RED test is observed, never committed.

Final state: **255/255 vitest** across 23 files, **29/29 Playwright** across two
viewports, `tsc` clean, both themes passing every WCAG AA assertion.

### The regression Playwright caught

The uppercase micro-label tabs from T4 spilled past an 820px viewport. This was
bisected rather than guessed: rebuilding with the pre-T4 stylesheet passed the
same assertion, which proves T4 introduced it and that it was not a pre-existing
defect. Fixed by wrapping the tab strip. Horizontal scroll was the alternative
and was rejected for hiding the last tabs behind an unannounced gesture.

This is the whole argument for the task: 255 jsdom tests could not see it,
because jsdom computes no layout.

### Discovered during the work

- **There is no re-sync step.** `vite.config.ts` points `outDir` straight at
  `skills/_core/command_center/static` with `emptyOutDir`, so the build replaces
  the served bundle directly. The task description assumed a manual copy.
- **The minifier drops the quotes**, emitting `[data-theme=dark]`. Equivalent
  selector; the Playwright repaint assertion verifies it rather than trusting it.

## Not done, and why

- **No CI wiring.** `.github/workflows/test.yml` is untouched. `npm run test:all`
  still excludes both the vitest and the Playwright suites, so UI verification
  remains a local command. Closing that gap means deciding whether CI installs a
  browser and a Python venv, which is a separate decision with a real cost.
- **No visual-regression snapshots.** Playwright asserts geometry and behaviour,
  not appearance.
- **JetBrains Mono not vendored**, per the decision above: the system mono stack
  carries Archify's tracking, not its typeface.

## Next step

The user reviews the dashboard in both themes and decides whether this lands as
one pull request or as the three chained slices described above. Nothing is
pushed.
