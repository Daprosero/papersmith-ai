import { isAbsolute } from "node:path";

/**
 * The contract a deliberation domain fills in, and the resolver that finds it.
 *
 * This engine is shared. It manages revisions of a Markdown document, indexes it,
 * patches it byte-exactly and transacts the result -- none of which is specific to
 * what the document argues about. What IS specific lives in a profile the HOST
 * chooses, never here: the engine that names a domain is an engine only one skill
 * can use.
 *
 * There is deliberately no default. A default would have to name one domain, which
 * is the exact coupling this file exists to remove, and a silent fallback is worse
 * than a refusal: the caller would get a working engine quietly answering for the
 * wrong document. Each skill ships a launcher that sets the variable.
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
	/**
	 * What this domain's instructions are ABOUT.
	 *
	 * The engine's intent matching is Spanish, and that part is shared: every
	 * deliberation domain says "mueve", "copia", "agrega". What is not shared is
	 * the subject -- one document argues about regularisation and one-hot
	 * encoding, another about baselines and ablations -- and that subject was
	 * spelled directly into intent resolution, locus scoring and the tutor gate.
	 */
	readonly vocabulary: {
		/** Subject words that make an instruction this domain's own conceptual work. */
		readonly conceptualTerms: readonly string[];
		/** Requires the domain expert before a conceptual plan is built. */
		readonly expertPattern: string;
		/** How a locus query names one of this domain's numbered displays. */
		readonly displayNounPattern: string;
		/** The same noun with its inflections, stripped out of a successor query. */
		readonly displayNounStripPattern: string;
		/** What this document is about, used to bias locus scoring. */
		readonly subjectPattern: string;
		/** Terms naming that subject directly in an instruction. */
		readonly subjectTerms: readonly string[];
		/** The locus description used when an instruction names the subject. */
		readonly subjectLocusDescription: string;
		/** How scoring reports that a neighbouring entry defines the subject. */
		readonly subjectEvidenceLabel: string;
	};
};

const configured = process.env.DELIBERATION_DOMAIN_PROFILE;
if (!configured)
	throw new Error(
		"DELIBERATION_DOMAIN_PROFILE_REQUIRED: this engine serves no domain of its own. " +
		"Set DELIBERATION_DOMAIN_PROFILE to a module exporting `profile`, or launch " +
		"through a skill's own cli.mjs, which sets it.",
	);

const REQUIRED = ["deriveBase", "baseLabel", "baseLabelLong", "exampleSlug", "names", "proseReferencePattern", "proseReferenceText", "vocabulary"] as const;

// Absolute, and refused otherwise. A relative path resolves against the working
// directory, and the engine does not control that: a CLI child process launched
// with its cwd inside the engine turned `.claude/skills/.../profile.ts` into
// `<engine>/.claude/skills/.../profile.ts` and died on a path nobody wrote. The
// launchers that set this variable all know an absolute path already.
if (!isAbsolute(configured))
	throw new Error(
		`DELIBERATION_DOMAIN_PROFILE_NOT_ABSOLUTE: ${configured} is relative, and the ` +
		"working directory a host or child process runs in is not the engine's to assume.",
	);

const loaded = (await import(configured)) as { profile?: DeliberationDomainProfile };
if (!loaded.profile) throw new Error(`DELIBERATION_DOMAIN_PROFILE_INVALID: ${configured} exports no \`profile\`.`);
const missing = REQUIRED.filter((key) => loaded.profile![key] === undefined);
if (missing.length) throw new Error(`DELIBERATION_DOMAIN_PROFILE_INCOMPLETE: ${configured} is missing ${missing.join(", ")}.`);

/** The profile this process serves. Chosen by the host, never by the engine. */
export const DOMAIN: DeliberationDomainProfile = loaded.profile;

/** A fresh matcher for the domain's prose citations. Never shared: `matchAll` needs `g`, and a reused instance carries `lastIndex`. */
export const proseReference = (flags: string): RegExp => new RegExp(DOMAIN.proseReferencePattern, flags);
