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

/**
 * Receipt for `InitialRevisionCreationService`'s explicit, slugged v1 creation (spec I1) --
 * distinct from `InitialPublicationReceipt`, which is reserved for the scientific workflow's
 * fixed-filename `CREATE_R01` contract (`research-concept-r01.md` only). `targetFilename` here is
 * the actual slugged filename (`research-concept-<slug>-r01.md`). `kind` is intentionally omitted
 * (never `'INITIAL_PUBLICATION'`) so `derived-state-store.ts`'s `validatePublicationReceipt`
 * accepts it via its `kind===undefined` branch -- the same acceptance path an ordinary successor
 * `RevisionReceipt` uses.
 */
export type ManagedInitialRevisionReceipt = {
	operation: 'CREATE_INITIAL_REVISION';
	targetRevision: 'r01';
	targetFilename: string;
	documentShaAfter: string;
	derivedStateStatus: 'COMMITTED';
	createdAt: string;
};

export type PublicationReceipt = RevisionReceipt | InitialPublicationReceipt;
export function createRevisionReceipt(receipt: PublicationReceipt) { return Object.freeze(receipt); }
