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

- [ ] **T1 — The style contract learns about themes.** Generalize
  `styles.test.ts` from one `:root` to a theme map: `:root` (light) plus
  `[data-theme='dark']`. The literal-colour rule excludes both theme blocks and
  nothing else; every contrast assertion runs per theme via `it.each`. Expect
  RED: the dark theme does not exist, so token lookup throws.
- [ ] **T2 — Both themes exist as tokens.** Move light surfaces toward Archify's
  register and add the dark theme block. Add the tokens the new signature needs
  (glow elevation, knockout ring, micro-label tracking). GREEN on T1 for both
  themes, with no literal colour outside the theme blocks.
- [ ] **T3 — The reader can switch themes.** A control in the topbar, honouring
  `prefers-color-scheme` on first load and persisting the explicit choice.
  Covered by a vitest unit test.
- [ ] **T4 — The chrome carries the signature.** Shell, topbar, tabs, panels,
  badges, buttons and terminal adopt Archify's type scale, tracking, radius
  opposition and glow elevation.
- [ ] **T5 — The canvas carries the signature.** Stage, gate and section nodes,
  edges and labels adopt the Archify register while keeping their semantic
  roles and the existing mutating/focus cues distinct.
- [ ] **T6 — Playwright verifies behaviour and layout.** Install and configure
  it `ui`-local against the FastAPI server. Functional: tab navigation, node
  selection opens the detail panel, theme switch persists across reload.
  Layout: no text overflow or clipping, no overlapping controls, buttons meet a
  minimum hit target, the element panel becomes a bottom sheet under 900px.
- [ ] **T7 — The shipped bundle matches the source.** Build the UI and re-sync
  `skills/_core/command_center/static/`, then confirm the served dashboard shows
  the restyle.

## Honest limits

Playwright asserts geometry and observable behaviour: that controls respond,
that text does not overflow its box, that nothing overlaps at a given viewport.
It cannot judge whether the result looks good. That judgement stays with the
user, and no test in this cycle claims otherwise.

## Evidence

(filled in per task as it closes)

## Next step

T1.
