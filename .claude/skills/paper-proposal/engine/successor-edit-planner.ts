import type { CreateSuccessorPayloadV1, MaterializationClaimProvenance, RevisionEvidence } from './scientific-domain.js';
import { sha256, type DocumentState, type StructuralEntry } from './types.js';

function sameRevision(state: DocumentState, expected: RevisionEvidence) {
	return state.filename === expected.filename && state.revision === expected.revision && state.documentSha256 === expected.documentSha256;
}

function anchorFor(state: DocumentState): StructuralEntry | undefined {
	return [...state.structuralIndex.entries]
		.filter((entry) => entry.endByte > entry.startByte)
		.sort((left, right) => right.endByte - left.endByte || right.startByte - left.startByte || left.entryId.localeCompare(right.entryId))[0];
}

function validClaims(claims: readonly MaterializationClaimProvenance[]) {
	return claims.length > 0 && claims.every((claim, index) => typeof claim.summary === 'string' && claim.summary.trim().length > 0
		&& (index === 0 || claims[index - 1]!.decisionId < claim.decisionId));
}

/** Produces canonical V2 edit plans from a supplied frozen base and accepted decisions only. */
export class SuccessorEditPlanner {
	plan(input: { base: DocumentState; expectedRevision: RevisionEvidence; acceptedDecisions: readonly MaterializationClaimProvenance[] }): CreateSuccessorPayloadV1 {
		if (!sameRevision(input.base, input.expectedRevision) || !validClaims(input.acceptedDecisions)) throw new Error('MATERIALIZATION_SUCCESSOR_INPUT_INVALID');
		const anchor = anchorFor(input.base);
		if (!anchor) throw new Error('MATERIALIZATION_SUCCESSOR_ANCHOR_MISSING');
		const content = [
			'',
			'',
			'## Accepted scientific decisions',
			'',
			...input.acceptedDecisions.flatMap((claim) => [`### ${claim.decisionId}`, '', claim.summary.trim(), '']),
		].join('\n');
		const plan = {
			planVersion: '2' as const,
			documentSha256: input.base.documentSha256,
			intent: 'INSERT' as const,
			instructionHash: sha256(JSON.stringify({ operation: 'CREATE_SUCCESSOR', decisionIds: input.acceptedDecisions.map((claim) => claim.decisionId) })),
			resolvedTargets: [anchor.entryId],
			semanticChange: false,
			destructiveIntent: false,
			cleanupLevel: 'NONE' as const,
			constraints: ['frozen-scientific-materialization'],
			actions: [{ kind: 'insert' as const, anchorEntryId: anchor.entryId, position: 'after' as const, content }],
			expectedEffects: ['append frozen accepted scientific decisions'],
			unresolvedQuestions: [],
		};
		return {
			kind: 'CREATE_SUCCESSOR',
			payloadVersion: 1,
			expectedBase: structuredClone(input.expectedRevision),
			patches: [{
				order: 1,
				plan,
				preconditions: {
					expectedRevision: structuredClone(input.expectedRevision),
					baseDocumentSha256: input.base.documentSha256,
					anchorEntryId: anchor.entryId,
					anchorTextSha256: anchor.textSha256,
				},
			}],
		};
	}
}
