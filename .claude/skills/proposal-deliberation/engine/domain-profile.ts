/**
 * The one place a deliberation domain names itself.
 *
 * The engine is domain-neutral: it manages revisions of a Markdown document,
 * indexes it, patches it byte-exactly, and transacts the result. None of that is
 * mathematics. What IS domain-specific is a thin rim -- which file a first
 * revision derives from, and what that file is called when the engine has to
 * name it in a refusal. Both used to be spelled inline in `proposal-workspace.ts`,
 * 35 times, with one research project's name baked into each, so every skill
 * derived from this engine inherited a target it has nothing to do with.
 *
 * The values below are byte-identical to what the engine hardcoded, so this file
 * changes no behavior: the messages it composes are the exact messages the
 * existing tests already assert on.
 */

export type DeliberationDomainProfile = {
	/** The single file `derive` and `derive_revision` accept as a source. */
	readonly deriveBase: string;
	/** How a refusal names that file mid-sentence: "... is missing from the X." */
	readonly baseLabel: string;
	/** The same file, named where the sentence needs the longer form. */
	readonly baseLabelLong: string;
	/** A well-formed revision slug, shown to the caller when it supplies a malformed one. */
	readonly exampleSlug: string;
	/**
	 * Every word that belongs to this domain and to no other.
	 *
	 * The lock in `tests/proposal-deliberation-domain-profile-lock.test.mjs`
	 * refuses any engine file outside this one that contains any of them, matched
	 * case-insensitively. Checking only the composed values above is not enough:
	 * `exampleSlug` carries the same proper noun in lowercase, and that residue
	 * survived a phrase-by-phrase sweep precisely because it was spelled
	 * differently everywhere it appeared.
	 */
	readonly names: readonly string[];
	/**
	 * How this domain's documents cite their own numbered displays in prose.
	 *
	 * A source string rather than a RegExp, because two call sites need it with
	 * different flags and a shared mutable RegExp carries `lastIndex` between
	 * them. Both used to spell this pattern out separately -- `reference-index.ts`
	 * and `math-integrity.ts` -- with two literals that agreed only by luck.
	 */
	readonly proseReferencePattern: string;
	/** The same citation, written back out for an atom's display text. */
	readonly proseReferenceText: (value: string) => string;
};

export const proposalDeliberationProfile: DeliberationDomainProfile = {
	deriveBase: "matematica_propuesta_CREDA.md",
	baseLabel: "fixed CREDA base",
	baseLabelLong: "fixed CREDA proposal base",
	exampleSlug: "subject-bag-creda-integrated-r06",
	names: ["CREDA"],
	// These documents number with `\tag{N}` and cite as `(Ec. N)`; they do not
	// use `\label`/`\eqref`, so this is the only citation form that resolves.
	proseReferencePattern: "\\((?:Ec|Eq)\\.\\s*([0-9]+[a-z]?)\\)",
	proseReferenceText: (value) => `(Ec. ${value})`,
};

/**
 * The profile this engine checkout serves.
 *
 * Static on purpose, and honestly so: the TypeBox schemas in
 * `proposal-workspace.ts` are built at module scope, so the profile has to
 * resolve at import time. Making it injectable per call means moving those
 * schema constructions into a factory -- a real change to a 5,687-line file, and
 * a separate one from this. Until then one checkout serves one domain, and this
 * constant is where that choice is written down instead of scattered.
 *
 * `deriveBase` is required because this host requires it. A domain whose first
 * revision is composed from several upstream sources rather than derived from a
 * single file cannot be expressed here yet; that needs the same factory change,
 * and inventing an unreachable `null` branch now would only promise otherwise.
 */
export const DOMAIN: DeliberationDomainProfile = proposalDeliberationProfile;

/** A fresh matcher for the domain's prose citations. Never shared: `matchAll` needs `g`, and a reused instance carries `lastIndex`. */
export const proseReference = (flags: string): RegExp => new RegExp(DOMAIN.proseReferencePattern, flags);
