// The module root the engine's tests load jiti and typebox from.
//
// These tests were written against the Pi runtime, which shipped both packages
// inside its own global installation, so every file hardcoded that
// installation's path (`/opt/homebrew/lib/node_modules/@earendil-works/
// pi-coding-agent`). On any machine without Pi that path does not exist and the
// file fails at import, before a single assertion runs.
//
// The engine itself stopped depending on Pi some time ago: `proposal-workspace.ts`
// and `chat-draft-registry.ts` import the shims under `engine/_pi-compat/`
// directly, and `engine/cli.mjs` -- the production entry point -- resolves jiti
// from this repository's own `node_modules`. Only the test harness was left
// behind.
//
// So pointing the tests at this repository is not swapping one runtime for
// another; it is dropping a dependency the engine had already dropped. This
// repository declares `jiti` and `typebox` in its own `package.json`, and both
// land at exactly the paths each test already builds from its root:
//   <root>/node_modules/jiti/lib/jiti.mjs
//   <root>/node_modules/typebox/build/index.mjs
//
// The `@earendil-works/*` alias entries each test still derives from this root
// now point at files that do not exist. That is intentional and harmless: no
// engine module imports those specifiers any more, so jiti never resolves them.
// Deleting them would touch every test body for no behavioural gain; leaving
// them keeps this change to one line per file.
//
// One place, because a root restated in 44 files is a root that eventually
// disagrees with itself.
import { fileURLToPath } from 'node:url';

export const ENGINE_MODULE_ROOT = fileURLToPath(new URL('..', import.meta.url));
