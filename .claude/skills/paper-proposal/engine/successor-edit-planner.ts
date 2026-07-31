import type { CreateSuccessorPayloadV1, MaterializationClaimProvenance, RevisionEvidence } from './scientific-domain.js';
import { sha256, type DocumentState, type EditAction, type EditPlan, type StructuralEntry } from './types.js';
import { materializeCompositeTarget, resolveSuccessorTarget } from './target-resolver.js';

function sameRevision(state: DocumentState, expected: RevisionEvidence) {
	return state.filename === expected.filename && state.revision === expected.revision && state.documentSha256 === expected.documentSha256;
}

function anchorFor(state: DocumentState, excludeEntryIds: ReadonlySet<string> = new Set()): StructuralEntry | undefined {
	return [...state.structuralIndex.entries]
		.filter((entry) => entry.endByte > entry.startByte && !excludeEntryIds.has(entry.entryId))
		.sort((left, right) => right.endByte - left.endByte || right.startByte - left.startByte || left.entryId.localeCompare(right.entryId))[0];
}

/**
 * Structural (real, byte-preserving) claims: those whose accepted decision
 * carries a `proposedEdit` resolved by EXPLICIT `targetEntryId` against the
 * CURRENT base -- a document-index lookup, never fuzzy summary matching.
 * Overlapping/duplicate targets are never silently applied: both members of a
 * colliding pair degrade to the summary-annotation fallback instead of
 * forcing an offset.
 */
function resolveStructuralClaims(base: DocumentState, acceptedDecisions: readonly MaterializationClaimProvenance[]): { structural: { claim: MaterializationClaimProvenance; entry: StructuralEntry }[]; fallback: MaterializationClaimProvenance[] } {
	const candidates = acceptedDecisions
		.map((claim) => ({ claim, entry: claim.proposedEdit?.kind === 'replace' ? base.structuralIndex.byId[claim.proposedEdit.targetEntryId] : undefined }))
		.filter((item): item is { claim: MaterializationClaimProvenance; entry: StructuralEntry } => !!item.entry && item.entry.type !== 'document');
	const overlapping = new Set<string>();
	for (const left of candidates) for (const right of candidates) {
		if (left.claim.decisionId === right.claim.decisionId) continue;
		if (left.entry.startByte < right.entry.endByte && right.entry.startByte < left.entry.endByte) { overlapping.add(left.claim.decisionId); overlapping.add(right.claim.decisionId); }
	}
	const structural = candidates.filter((item) => !overlapping.has(item.claim.decisionId));
	const structuralIds = new Set(structural.map((item) => item.claim.decisionId));
	return { structural, fallback: acceptedDecisions.filter((claim) => !structuralIds.has(claim.decisionId)) };
}

/**
 * Resolves a single accepted decision's summary to its addressable heading/section
 * locus via `resolveSuccessorTarget` (the same resolver used elsewhere for
 * successor targets). Only attempted for exactly one accepted decision with
 * exactly one unambiguous candidate; anything else (zero, multiple decisions, or
 * an ambiguous/unresolved locus) intentionally returns `undefined` so the caller
 * falls back to the document-tail anchor unchanged.
 */
function resolveLocusAnchor(state: DocumentState, acceptedDecisions: readonly MaterializationClaimProvenance[]): StructuralEntry | undefined {
	if (acceptedDecisions.length !== 1) return undefined;
	const resolution = resolveSuccessorTarget(state, acceptedDecisions[0]!.summary);
	if (resolution.candidates.length !== 1) return undefined;
	return materializeCompositeTarget(state, resolution.candidates[0]!);
}

function validClaims(claims: readonly MaterializationClaimProvenance[]) {
	return claims.length > 0 && claims.every((claim, index) => typeof claim.summary === 'string' && claim.summary.trim().length > 0
		&& (index === 0 || claims[index - 1]!.decisionId < claim.decisionId));
}

function tailBlockContent(decisions: readonly MaterializationClaimProvenance[]): string {
	return [
		'',
		'',
		'## Accepted scientific decisions',
		'',
		...decisions.flatMap((claim) => [`### ${claim.decisionId}`, '', claim.summary.trim(), '']),
	].join('\n');
}

function instructionHashFor(acceptedDecisions: readonly MaterializationClaimProvenance[]): string {
	return sha256(JSON.stringify({ operation: 'CREATE_SUCCESSOR', decisionIds: acceptedDecisions.map((claim) => claim.decisionId) }));
}

/** Produces canonical V2 edit plans from a supplied frozen base and accepted decisions only. */
export class SuccessorEditPlanner {
	plan(input: { base: DocumentState; expectedRevision: RevisionEvidence; acceptedDecisions: readonly MaterializationClaimProvenance[] }): CreateSuccessorPayloadV1 {
		if (!sameRevision(input.base, input.expectedRevision) || !validClaims(input.acceptedDecisions)) throw new Error('MATERIALIZATION_SUCCESSOR_INPUT_INVALID');
		const { structural, fallback } = resolveStructuralClaims(input.base, input.acceptedDecisions);

		if (structural.length === 0) {
			// Unchanged pre-existing behavior: exactly the prior single-locus scoped
			// note, or the document-tail summary block -- no claim in this batch
			// carries a usable, resolvable structural edit.
			const locusAnchor = resolveLocusAnchor(input.base, input.acceptedDecisions);
			const anchor = locusAnchor ?? anchorFor(input.base);
			if (!anchor) throw new Error('MATERIALIZATION_SUCCESSOR_ANCHOR_MISSING');
			const content = locusAnchor
				? `\n\n> Accepted revision: ${input.acceptedDecisions[0]!.summary.trim()}\n`
				: tailBlockContent(input.acceptedDecisions);
			return this.buildPayload(input, [anchor.entryId], [{ kind: 'insert', anchorEntryId: anchor.entryId, position: 'after', content }], anchor);
		}

		// At least one decision carries a real, resolvable structural edit: apply
		// every resolvable structural replace directly at its own locus -- ALL
		// spliced into the SAME successor version, never a separate one per
		// decision -- and fold every remaining (no-proposedEdit, or
		// drifted/overlapping) decision into ONE shared document-tail summary
		// block, so no decision is ever silently lost.
		const replaceActions: EditAction[] = structural.map(({ claim, entry }) => ({ kind: 'replace', targetEntryId: entry.entryId, replacementText: (claim.proposedEdit as Extract<EditAction, { kind: 'replace' }>).replacementText }));
		const resolvedTargets = structural.map(({ entry }) => entry.entryId);
		const primaryAnchor = structural[0]!.entry;
		if (fallback.length === 0) return this.buildPayload(input, resolvedTargets, replaceActions, primaryAnchor);

		const tailAnchor = anchorFor(input.base, new Set(resolvedTargets)) ?? primaryAnchor;
		const actions: EditAction[] = [...replaceActions, { kind: 'insert', anchorEntryId: tailAnchor.entryId, position: 'after', content: tailBlockContent(fallback) }];
		return this.buildPayload(input, [...resolvedTargets, tailAnchor.entryId], actions, primaryAnchor);
	}

	private buildPayload(input: { base: DocumentState; expectedRevision: RevisionEvidence; acceptedDecisions: readonly MaterializationClaimProvenance[] }, resolvedTargets: string[], actions: EditAction[], anchor: StructuralEntry): CreateSuccessorPayloadV1 {
		const plan: EditPlan = {
			planVersion: '2' as const,
			documentSha256: input.base.documentSha256,
			intent: 'INSERT' as const,
			instructionHash: instructionHashFor(input.acceptedDecisions),
			resolvedTargets,
			semanticChange: false,
			destructiveIntent: false,
			cleanupLevel: 'NONE' as const,
			constraints: ['frozen-scientific-materialization'],
			actions,
			expectedEffects: ['apply accepted scientific decisions'],
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
