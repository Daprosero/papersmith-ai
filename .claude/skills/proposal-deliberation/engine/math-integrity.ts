import { sha256 } from './types.js';

/**
 * Mathematical integrity: what the document must never lose in silence, and the
 * canonical form every byte it stores must keep.
 *
 * The engine's other validators check *internal consistency* — that labels are
 * unique, that `\eqref` targets exist, that symbols do not conflict. None of
 * them check *preservation*: a locus rewrite that drops an equation outright
 * passes every one of them, because what remains is still perfectly consistent.
 * Byte coverage only guards the bytes OUTSIDE the resolved locus, which is
 * exactly where the loss is not.
 *
 * So this module answers two different questions:
 *
 *   1. `mathDelta`  — which mathematical atoms existed before and are now gone?
 *                     Reported on preview, and refused on accept unless the
 *                     caller acknowledges each one by id.
 *   2. `canonicalFormViolations` — does the candidate still spell its
 *                     mathematics the one way the `.md` renders correctly?
 *                     Never intentional, so this blocks outright.
 */

export type MathAtomKind = 'display' | 'inline' | 'tag' | 'macro' | 'ref';
export type MathAtom = { id: string; kind: MathAtomKind; text: string };
export type MathDelta = { lost: MathAtom[]; added: MathAtom[] };
export type CanonicalViolation = { rule: string; line: number; detail: string };

const short = (value: string) => sha256(value).slice(0, 8);
const collapse = (value: string) => value.replace(/\s+/gu, ' ').trim();

/**
 * Unicode ranges that mean "this should have been a LaTeX command". Deliberately
 * narrow: Spanish prose accents, dashes and quotes are untouched, so a violation
 * here is always a real substitution (`ε` for `\varepsilon`), never punctuation.
 */
const GLYPH_RANGES: readonly (readonly [number, number])[] = [
	[0x0370, 0x03ff], // Greek and Coptic
	[0x2070, 0x209f], // super/subscripts
	[0x2100, 0x214f], // letterlike (ℒ ℝ ℕ ℤ ℚ ℂ ℋ)
	[0x2190, 0x21ff], // arrows
	[0x2200, 0x22ff], // mathematical operators
	[0x27c0, 0x27ef], // misc mathematical symbols A
	[0x2980, 0x29ff], // misc mathematical symbols B
	[0x1d400, 0x1d7ff], // mathematical alphanumeric symbols
];
const isMathGlyph = (codePoint: number) => GLYPH_RANGES.some(([lo, hi]) => codePoint >= lo && codePoint <= hi);

/**
 * Marks the bytes that live inside `$…$` or `$$…$$`.
 *
 * The glyph rule applies to notation, and notation is always delimited: prose
 * may legitimately be any Unicode it likes (a title, a Greek word, an arrow in
 * a sentence), and flagging that would block edits that spell nothing wrong.
 * A real substitution — `ε` where `\varepsilon` belongs — lands inside the
 * delimiters, which is exactly what this mask keeps in scope.
 */
function mathRegionMask(source: string): Uint8Array {
	const mask = new Uint8Array(source.length);
	for (const match of source.matchAll(/\$\$[\s\S]*?\$\$/gu)) mask.fill(1, match.index, match.index + match[0].length);
	for (const match of source.matchAll(/(?<!\$)\$[^$\n]+\$(?!\$)/gu)) if (!mask[match.index]) mask.fill(1, match.index, match.index + match[0].length);
	return mask;
}

/**
 * Every mathematical atom the source declares, keyed by a stable id.
 *
 * Presence-based, never counted: an atom is only "lost" when it disappears
 * entirely. Rewording a paragraph that happens to repeat `$\sigma$` one time
 * fewer is not a loss of notation, and blocking on it would make the gate
 * useless noise.
 */
export function mathAtoms(source: string): Map<string, MathAtom> {
	const atoms = new Map<string, MathAtom>();
	const add = (kind: MathAtomKind, key: string, text: string) => {
		const id = `${kind}:${key}`;
		if (!atoms.has(id)) atoms.set(id, { id, kind, text });
	};
	for (const [, body] of source.matchAll(/\$\$([\s\S]*?)\$\$/gu)) add('display', short(collapse(body)), collapse(body));
	const prose = source.replace(/\$\$[\s\S]*?\$\$/gu, '');
	for (const [, body] of prose.matchAll(/(?<!\$)\$([^$\n]+)\$(?!\$)/gu)) add('inline', short(collapse(body)), collapse(body));
	for (const [, value] of source.matchAll(/\\tag\{([^}]+)\}/gu)) add('tag', value, `\\tag{${value}}`);
	for (const [macro] of source.matchAll(/\\[A-Za-z]+/gu)) add('macro', macro, macro);
	for (const [, value] of source.matchAll(/\((?:Ec|Eq)\.\s*([0-9]+[a-z]?)\)/gu)) add('ref', value, `(Ec. ${value})`);
	return atoms;
}

/**
 * Atoms present before and absent after (and the reverse).
 *
 * Compares whole documents rather than the resolved locus, which is equivalent
 * and far more robust: everything outside the locus is byte-identical by
 * `unchangedByteCoverage`, so any atom missing from the whole document went
 * missing inside the locus.
 */
export function mathDelta(before: string, after: string): MathDelta {
	const a = mathAtoms(before), b = mathAtoms(after);
	return {
		lost: [...a.values()].filter(atom => !b.has(atom.id)),
		added: [...b.values()].filter(atom => !a.has(atom.id)),
	};
}

/** The canonical form: how this document spells mathematics so the `.md` renders. */
export function canonicalFormViolations(source: string): CanonicalViolation[] {
	const out: CanonicalViolation[] = [];
	const lines = source.split('\n');
	if ((source.match(/^\$\$\r?$/gmu)?.length ?? 0) % 2 !== 0)
		out.push({ rule: 'display-delimiters-unbalanced', line: 0, detail: 'the count of lines that are exactly `$$` is odd' });
	lines.forEach((line, index) => {
		const at = index + 1;
		if (/\$\$.+\$\$/u.test(line))
			out.push({ rule: 'display-math-inline', line: at, detail: 'display math must open and close on its own `$$` lines, never inside a prose line' });
		// `\\[1em]` is a LaTeX line break with spacing, not a `\[…\]` delimiter:
		// require that the backslash is not itself escaped by a preceding one.
		const delimiter = /(?<!\\)\\[()[\]]/u.exec(line);
		if (delimiter)
			out.push({ rule: 'latex-delimiter', line: at, detail: `use $…$ and $$…$$, never ${delimiter[0]}` });
		if (!/\$\$/u.test(line) && (line.match(/\$/gu)?.length ?? 0) % 2 !== 0)
			out.push({ rule: 'inline-math-unbalanced', line: at, detail: 'an inline `$` opens without closing on the same line' });
	});
	const mask = mathRegionMask(source);
	const flagged = new Set<number>();
	let index = 0, line = 1;
	for (const character of source) {
		if (character === '\n') { line += 1; index += 1; continue; }
		if (mask[index] && isMathGlyph(character.codePointAt(0)!) && !flagged.has(line)) {
			flagged.add(line);
			out.push({ rule: 'unicode-math-glyph', line, detail: `${JSON.stringify(character)} must be written as a LaTeX command` });
		}
		index += character.length;
	}
	return out.sort((left, right) => left.line - right.line);
}
