import type { RevisionReceipt } from './types.js';

export type InitialPublicationReceipt = {
	kind: 'INITIAL_PUBLICATION';
	targetRevision: 'r01';
	targetFilename: 'research-concept-r01.md';
	documentShaAfter: string;
	derivedStateStatus: 'COMMITTED';
	materializationId: string;
	selectionKey: string;
	planDigest: string;
	candidateDigest: string;
};

export type PublicationReceipt = RevisionReceipt | InitialPublicationReceipt;
export function createRevisionReceipt(receipt: PublicationReceipt) { return Object.freeze(receipt); }
