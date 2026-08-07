import type { CanonicalProposalMetadata, CreateR01PayloadV1, MaterializationClaimProvenance } from './revision-domain.js';

/** Read-only paper-guide reference fragment, mirroring `ChatGuideFragment`'s shape without importing chat-only types. */
export type InitialRevisionGuideFragment = { path: string; content: string };
export type ComposedInitialRevision = { markdown: string; slug: string; canonicalMetadata: CanonicalProposalMetadata };

function splitIdeaSentences(idea: string): string[] {
	return idea.split(/(?<=[.!?])\s+/).map((sentence) => sentence.trim()).filter(Boolean);
}

/** Derives title/sectionHeading directly from the caller's idea text -- never a hardcoded generic label (spec I5). */
function deriveCanonicalMetadataFromIdea(idea: string): CanonicalProposalMetadata {
	const sentences = splitIdeaSentences(idea);
	const title = (sentences[0] ?? idea).slice(0, 200).trim() || 'Untitled Research Concept';
	const sectionHeading = (sentences[1] ?? sentences[0] ?? idea).slice(0, 200).trim() || 'Concept Overview';
	return { schemaVersion: 1, title, sectionHeading };
}

/** Derives a lowercase-hyphen filename slug from the idea-derived title -- never the fixed `r01` slug. */
function deriveSlugFromTitle(title: string): string {
	const normalized = title
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-+|-+$/g, '')
		.slice(0, 60)
		.replace(/-+$/g, '');
	return normalized || 'concept';
}

function validMetadata(metadata: CanonicalProposalMetadata) {
	return metadata.schemaVersion === 1
		&& typeof metadata.title === 'string' && metadata.title.trim().length > 0 && metadata.title.length <= 200
		&& typeof metadata.sectionHeading === 'string' && metadata.sectionHeading.trim().length > 0 && metadata.sectionHeading.length <= 200;
}

function validClaims(claims: readonly MaterializationClaimProvenance[]) {
	return claims.length > 0
		&& claims.every((claim, index) => typeof claim.claimId === 'string' && claim.claimId.length > 0
			&& typeof claim.summary === 'string' && claim.summary.trim().length > 0
			&& (index === 0 || claims[index - 1]!.decisionId < claim.decisionId));
}

/** Renders only immutable accepted decisions and caller-frozen canonical metadata. */
export class InitialRevisionRenderer {
	render(input: { acceptedDecisions: readonly MaterializationClaimProvenance[]; canonicalMetadata: CanonicalProposalMetadata }): CreateR01PayloadV1 {
		if (!validMetadata(input.canonicalMetadata) || !validClaims(input.acceptedDecisions)) throw new Error('MATERIALIZATION_INITIAL_RENDER_INPUT_INVALID');
		const markdown = [
			`# ${input.canonicalMetadata.title.trim()}`,
			'',
			`## ${input.canonicalMetadata.sectionHeading.trim()}`,
			'',
			...input.acceptedDecisions.flatMap((claim) => [`### ${claim.decisionId}`, '', claim.summary.trim(), '']),
		].join('\n');
		return {
			kind: 'CREATE_R01',
			payloadVersion: 1,
			markdown,
			target: { filename: 'research-concept-r01.md', revision: 'r01' },
			canonicalMetadata: structuredClone(input.canonicalMetadata),
		};
	}

	/**
	 * Composes v1 content from the caller's idea plus paper-guide fragments (spec I2, I5). Unlike
	 * `render()` (which only ever renders immutable accepted scientific decisions for the gated
	 * scientific-workflow route), this never requires accepted decisions and never emits a fixed
	 * generic skeleton: title/sectionHeading and the filename slug are both derived from the idea
	 * text itself, and the guide fragments (when present) are included verbatim as reference context.
	 */
	renderFromIdea(input: { idea: string; guideFragments?: readonly InitialRevisionGuideFragment[] }): ComposedInitialRevision {
		const idea = input.idea.trim();
		if (!idea) throw new Error('INITIAL_REVISION_IDEA_REQUIRED');
		const canonicalMetadata = deriveCanonicalMetadataFromIdea(idea);
		const slug = deriveSlugFromTitle(canonicalMetadata.title);
		const sections = [`# ${canonicalMetadata.title}`, '', `## ${canonicalMetadata.sectionHeading}`, '', idea, ''];
		const guideFragments = input.guideFragments ?? [];
		if (guideFragments.length > 0) {
			sections.push('## Paper Guide Reference', '');
			for (const fragment of guideFragments) sections.push(`### ${fragment.path}`, '', fragment.content.trim(), '');
		}
		const markdown = `${sections.join('\n').replace(/\n+$/, '')}\n`;
		return { markdown, slug, canonicalMetadata };
	}
}
