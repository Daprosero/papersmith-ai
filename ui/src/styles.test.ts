/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { composite, contrastRatio, parseColor, type Rgba } from './test/color';

const css = readFileSync(join(process.cwd(), 'src', 'styles.css'), 'utf8');

/**
 * The dashboard ships two themes: light on `:root` and dark on
 * `[data-theme='dark']`. Both are allowed to hold literal colours — they are
 * where colour is *defined*. Everywhere else must go through `var()`, so the
 * selectors are listed here once and excised from the text the literal-colour
 * rule inspects.
 */
const THEME_SELECTORS = [':root', "[data-theme='dark']"] as const;
type ThemeName = 'light' | 'dark';

const THEME_OF: Record<(typeof THEME_SELECTORS)[number], ThemeName> = {
  ':root': 'light',
  "[data-theme='dark']": 'dark',
};

/** The body of the first block declared with `selector`, or null when absent. */
function blockBody(source: string, selector: string): { body: string; start: number; end: number } | null {
  const start = source.indexOf(selector);
  if (start === -1) return null;
  const open = source.indexOf('{', start);
  if (open === -1) return null;
  const close = source.indexOf('}', open);
  if (close === -1) return null;
  return { body: source.slice(open + 1, close), start, end: close + 1 };
}

const stripped = css.replace(/\/\*[\s\S]*?\*\//g, '');

/** Theme blocks keyed by theme, plus everything that is not a theme block. */
function splitThemes(source: string): { themes: Map<ThemeName, string>; rest: string } {
  const themes = new Map<ThemeName, string>();
  const spans: Array<{ start: number; end: number }> = [];
  for (const selector of THEME_SELECTORS) {
    const found = blockBody(source, selector);
    if (!found) continue;
    themes.set(THEME_OF[selector], found.body);
    spans.push({ start: found.start, end: found.end });
  }
  let rest = source;
  for (const span of spans.sort((a, b) => b.start - a.start)) {
    rest = rest.slice(0, span.start) + rest.slice(span.end);
  }
  return { themes, rest };
}

const { themes, rest } = splitThemes(stripped);

function tokensOf(body: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const match of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    map.set(match[1], match[2].trim());
  }
  return map;
}

/**
 * A theme's tokens, falling back to light for anything the dark block does not
 * override — which mirrors how the cascade actually resolves them.
 */
function themeTokens(theme: ThemeName): Map<string, string> {
  const light = tokensOf(themes.get('light') ?? '');
  if (theme === 'light') return light;
  const merged = new Map(light);
  for (const [name, value] of tokensOf(themes.get('dark') ?? '')) merged.set(name, value);
  return merged;
}

function reader(theme: ThemeName) {
  const map = themeTokens(theme);
  const token = (name: string): string => {
    const value = map.get(name);
    if (value === undefined) throw new Error(`missing token ${name} in the ${theme} theme`);
    return value;
  };
  /** Resolve a token to an opaque colour, compositing translucent values over `backdrop`. */
  const resolve = (name: string, backdrop = '--bg-panel'): Rgba => {
    const color = parseColor(token(name));
    return color.a < 1 ? composite(color, resolve(backdrop)) : color;
  };
  return { has: (name: string) => map.has(name), token, resolve };
}

const THEMES: ThemeName[] = ['light', 'dark'];

const NAMED_COLORS = new Set(
  (
    'aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown burlywood ' +
    'cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod ' +
    'darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon ' +
    'darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue dimgray ' +
    'dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray green ' +
    'greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush lawngreen lemonchiffon ' +
    'lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon ' +
    'lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen ' +
    'magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue ' +
    'mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy ' +
    'oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred ' +
    'papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon ' +
    'sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue ' +
    'tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen'
  ).split(' '),
);

/** Every declaration value outside `:root`, with var(...) references and strings removed. */
function declarationValues(source: string): string[] {
  const values: string[] = [];
  for (const match of source.matchAll(/(?:^|[;{\s])([a-z-]+)\s*:\s*([^;{}]+)(?=[;}])/g)) {
    values.push(match[2].replace(/var\([^)]*\)/g, '').replace(/(["']).*?\1/g, ''));
  }
  return values;
}

describe('themed stylesheet', () => {
  it('declares every colour only inside a theme block', () => {
    const offenders: string[] = [];
    for (const value of declarationValues(rest)) {
      if (/#[0-9a-f]{3,8}\b/i.test(value)) offenders.push(value.trim());
      if (/\b(?:rgb|rgba|hsl|hsla)\(/i.test(value)) offenders.push(value.trim());
      for (const word of value.match(/[a-z]+/gi) ?? []) {
        if (NAMED_COLORS.has(word.toLowerCase())) offenders.push(value.trim());
      }
    }
    expect(offenders).toEqual([]);
  });

  it('ships both themes', () => {
    expect(themes.has('light')).toBe(true);
    expect(themes.has('dark')).toBe(true);
  });

  it.each(THEMES)('the %s theme defines the extra theme tokens', (theme) => {
    const { has } = reader(theme);
    for (const name of [
      '--graph-bg',
      '--node-bg',
      '--edge',
      '--edge-label-bg',
      '--overlay',
      '--shadow',
      '--terminal-bg',
      '--terminal-text',
      '--ok-border',
      '--warn-border',
      '--bad-border',
      '--accent-border',
      '--sealed-border',
    ]) {
      expect(has(name), `${name} in ${theme}`).toBe(true);
    }
  });

  it.each(THEMES)('the %s theme carries the Archify signature tokens', (theme) => {
    const { has } = reader(theme);
    for (const name of ['--glow', '--glow-strong', '--ring', '--knockout', '--radius-pill', '--radius-edge']) {
      expect(has(name), `${name} in ${theme}`).toBe(true);
    }
  });

  it('overrides every colour surface in the dark theme', () => {
    const dark = tokensOf(themes.get('dark') ?? '');
    for (const name of ['--bg', '--bg-panel', '--bg-elevated', '--bg-input', '--border', '--text', '--graph-bg', '--node-bg']) {
      expect(dark.has(name), `${name} must be redefined for dark`).toBe(true);
    }
  });
});

describe.each(THEMES)('contrast (WCAG AA) — %s theme', (theme) => {
  const { resolve } = reader(theme);
  const ratio = (fg: string, bg: string, backdrop?: string) =>
    contrastRatio(resolve(fg, backdrop), resolve(bg, backdrop));

  it.each(['--bg', '--bg-panel', '--bg-elevated', '--bg-input'])('text on %s reaches 4.5:1', (bg) => {
    expect(ratio('--text', bg)).toBeGreaterThanOrEqual(4.5);
  });

  it('muted text on the panel reaches 4.5:1', () => {
    expect(ratio('--text-muted', '--bg-panel')).toBeGreaterThanOrEqual(4.5);
  });

  it('dim text on the panel reaches 3:1', () => {
    expect(ratio('--text-dim', '--bg-panel')).toBeGreaterThanOrEqual(3);
  });

  it.each([
    ['--ok', '--ok-soft'],
    ['--warn', '--warn-soft'],
    ['--bad', '--bad-soft'],
    ['--sealed', '--sealed-soft'],
    ['--accent', '--accent-soft'],
  ])('badge text %s on its composited %s fill reaches 4.5:1', (fg, soft) => {
    expect(ratio(fg, soft)).toBeGreaterThanOrEqual(4.5);
  });

  it('the strong border against the panel reaches 3:1', () => {
    expect(ratio('--border-strong', '--bg-panel')).toBeGreaterThanOrEqual(3);
  });

  it('node text on the node background reaches 4.5:1', () => {
    expect(ratio('--text', '--node-bg')).toBeGreaterThanOrEqual(4.5);
    expect(ratio('--text-muted', '--node-bg')).toBeGreaterThanOrEqual(4.5);
  });

  it('edge label text on the label background reaches 4.5:1', () => {
    expect(ratio('--text-muted', '--edge-label-bg', '--graph-bg')).toBeGreaterThanOrEqual(4.5);
  });

  it('terminal text on the terminal background reaches 4.5:1', () => {
    expect(ratio('--terminal-text', '--terminal-bg')).toBeGreaterThanOrEqual(4.5);
  });
});

describe('mutating cue', () => {
  const rule = /\.dag-node\.is-mutating\s*\{([^}]*)\}/.exec(stripped);
  const focus = /\.react-flow__node:focus-visible \.dag-node\s*\{([^}]*)\}/.exec(stripped);

  it('draws a dashed token-based outline so it reads on the light theme', () => {
    expect(rule).not.toBeNull();
    expect(rule?.[1]).toMatch(/outline:\s*\d+px dashed var\(--accent\)/);
  });

  it('differs from the solid keyboard focus outline', () => {
    expect(focus).not.toBeNull();
    expect(focus?.[1]).toMatch(/outline:\s*2px solid var\(--accent\)/);
    expect(focus?.[1]).toMatch(/outline-offset:\s*2px/);
    const outline = (body: string) => /outline:\s*([^;]+);/.exec(body)?.[1];
    const offset = (body: string) => /outline-offset:\s*([^;]+);/.exec(body)?.[1];
    expect(outline(rule?.[1] ?? '')).not.toBe(outline(focus?.[1] ?? ''));
    expect(offset(rule?.[1] ?? '')).not.toBe(offset(focus?.[1] ?? ''));
  });
});

describe('element panel on narrow viewports', () => {
  const sheet = /@media \(max-width: 899px\)\s*\{\s*\.element-panel\s*\{([^}]*)\}/.exec(stripped);

  it('becomes a full-width bottom sheet capped at 60vh and scrollable under 900px', () => {
    expect(sheet).not.toBeNull();
    const body = sheet?.[1] ?? '';
    expect(body).toMatch(/top:\s*auto/);
    expect(body).toMatch(/left:\s*0/);
    expect(body).toMatch(/width:\s*auto/);
    expect(body).toMatch(/max-height:\s*60vh/);
    expect(body).toMatch(/overflow-y:\s*auto/);
  });

  it('swaps the drawer left border for a top border using tokens only', () => {
    const body = sheet?.[1] ?? '';
    expect(body).toMatch(/border-top:\s*1px solid var\(--border-strong\)/);
    expect(body).toMatch(/border-left:\s*none/);
  });
});
