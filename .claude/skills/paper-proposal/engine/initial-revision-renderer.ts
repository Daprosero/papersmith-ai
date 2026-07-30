import type { CanonicalProposalMetadata, CreateR01PayloadV1, MaterializationClaimProvenance } from './scientific-domain.js';

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
}
