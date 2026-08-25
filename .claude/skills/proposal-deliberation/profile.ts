import type { DeliberationDomainProfile } from "../_core/deliberation/engine/domain-profile.js";

/**
 * What the shared deliberation engine needs to know about THIS domain.
 *
 * The engine under `_core/` is domain-neutral and refuses to start without one of
 * these. Everything here was once spelled inside the engine itself, which is why
 * a sibling skill could not reuse it without inheriting a research project it has
 * nothing to do with.
 */
export const profile: DeliberationDomainProfile = {
	deriveBase: "matematica_propuesta_CREDA.md",
	baseLabel: "fixed CREDA base",
	baseLabelLong: "fixed CREDA proposal base",
	exampleSlug: "subject-bag-creda-integrated-r06",
	names: ["CREDA"],
	// These documents number with `\tag{N}` and cite as `(Ec. N)`; they do not
	// use `\label`/`\eqref`, so this is the only citation form that resolves.
	proseReferencePattern: "\\((?:Ec|Eq)\\.\\s*([0-9]+[a-z]?)\\)",
	proseReferenceText: (value) => `(Ec. ${value})`,
	vocabulary: {
		conceptualTerms: ["regularización", "motivación matemática", "múltiples dominios", "semi-supervisado"],
		expertPattern: "matem|ecuaci|regularización|semi-supervisado|teórico",
		displayNounPattern: "ecuaci[oó]n",
		displayNounStripPattern: "\\becuaci[oó]n(?:es)?\\b",
		subjectPattern: "one[- ]?hot|codificaci[oó]n|etiqueta|clase",
		subjectTerms: ["one-hot", "one hot"],
		subjectLocusDescription: "ecuación relacionada con one-hot",
		subjectEvidenceLabel: "nearby one-hot/coding definition",
	},
};
