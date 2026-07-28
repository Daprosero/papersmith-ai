import { sha256, type ContextFragment } from './types.js';
import type {
	EvidenceReference,
	RevisionEvidence,
	ScientificActKind,
	ScientificContextLimits,
	ScientificDocumentFragment,
	ScientificEvent,
	ScientificRoleContext,
	ScientificThread,
	ScientificThreadId,
	ThreadRelation,
	ThreadSummary,
} from './scientific-domain.js';

const DEFAULT_LIMITS: ScientificContextLimits = Object.freeze({
	maxRelatedThreads: 4,
	maxEvidence: 12,
	maxDocumentFragments: 4,
	maxBytes: 16_000,
});
const FORBIDDEN_PRIVATE_CONTENT = /(?:chain.?of.?thought|hidden.?prompt|raw.?trace|private.?reasoning|raw.?role|role.?transcript|\bprompt\b|\btrace\b|\bthought\b)/i;
const SHA256 = /^[0-9a-f]{64}$/;

type ScientificContextSnapshot = {
	threads: ScientificThread[];
	relations: ThreadRelation[];
	events: ScientificEvent[];
};

export interface ScientificContextStatePort {
	read(): Promise<ScientificContextSnapshot>;
}

export interface VerifiedDocumentFragmentPort {
	load(input: {
		revision: RevisionEvidence;
		entryIds: string[];
		maxFragments: number;
		maxBytes: number;
	}): Promise<{ revision: RevisionEvidence; fragments: ContextFragment[] }>;
}

export type ScientificContextBuilderInput = {
	activeThread: ScientificThread;
	requestedDirectRelationIds: ScientificThreadId[];
	act: ScientificActKind;
	verifiedRevision?: RevisionEvidence;
	actEvidence?: EvidenceReference[];
	documentEntryIds?: string[];
};

export type ScientificContextBuilderOptions = {
	documentFragments?: VerifiedDocumentFragmentPort;
	limits?: Partial<ScientificContextLimits>;
};

export class ScientificContextBuilderError extends Error {
	constructor(readonly code: string) {
		super(code);
	}
}

const fail = (code: string): never => { throw new ScientificContextBuilderError(code); };
const bytes = (value: unknown) => Buffer.byteLength(JSON.stringify(value), 'utf8');
const sameRevision = (left: RevisionEvidence, right: RevisionEvidence) => left.filename === right.filename && left.revision === right.revision && left.documentSha256 === right.documentSha256;
const summary = (thread: ScientificThread): ThreadSummary => ({ threadId: thread.threadId, status: thread.status, title: thread.title, summary: thread.summary });
const keyForEvidence = (evidence: EvidenceReference) => `${evidence.kind}\u0000${evidence.id}\u0000${evidence.sha256 ?? ''}`;

function narrowerLimits(overrides: Partial<ScientificContextLimits> = {}): ScientificContextLimits {
	const limits = { ...DEFAULT_LIMITS };
	for (const key of Object.keys(DEFAULT_LIMITS) as Array<keyof ScientificContextLimits>) {
		const value = overrides[key];
		if (value === undefined) continue;
		if (!Number.isSafeInteger(value) || value < 0 || value > DEFAULT_LIMITS[key]) fail('SCIENTIFIC_CONTEXT_LIMIT_INVALID');
		limits[key] = value;
	}
	if (limits.maxBytes === 0) fail('SCIENTIFIC_CONTEXT_LIMIT_INVALID');
	return limits;
}

function assertPublicText(value: string, code: string) {
	if (typeof value !== 'string' || FORBIDDEN_PRIVATE_CONTENT.test(value)) fail(code);
}

function assertPublicEvidence(evidence: EvidenceReference) {
	if (!evidence || typeof evidence.kind !== 'string' || typeof evidence.id !== 'string' || evidence.kind.length === 0 || evidence.kind.length > 64 || evidence.id.length === 0 || evidence.id.length > 256 || FORBIDDEN_PRIVATE_CONTENT.test(evidence.kind) || FORBIDDEN_PRIVATE_CONTENT.test(evidence.id)) fail('SCIENTIFIC_CONTEXT_EVIDENCE_PRIVATE_OR_INVALID');
	if (evidence.sha256 !== undefined && (typeof evidence.sha256 !== 'string' || !SHA256.test(evidence.sha256))) fail('SCIENTIFIC_CONTEXT_EVIDENCE_PRIVATE_OR_INVALID');
}

function assertThreadMatches(authoritative: ScientificThread, requested: ScientificThread) {
	if (authoritative.threadId !== requested.threadId || authoritative.version !== requested.version || authoritative.status !== requested.status || authoritative.title !== requested.title || authoritative.summary !== requested.summary || authoritative.createdEventId !== requested.createdEventId || authoritative.headEventId !== requested.headEventId) fail('SCIENTIFIC_CONTEXT_ACTIVE_THREAD_MISMATCH');
}

function directNeighbors(activeThreadId: ScientificThreadId, relations: ThreadRelation[]) {
	return new Set(relations.flatMap((relation) => {
		if (relation.fromThreadId === activeThreadId) return [relation.toThreadId];
		if (relation.toThreadId === activeThreadId) return [relation.fromThreadId];
		return [];
	}));
}

function relevantEvidence(
	requested: EvidenceReference[],
	threadIds: Set<ScientificThreadId>,
	events: ScientificEvent[],
): EvidenceReference[] {
	const available = new Set<string>();
	for (const event of events) {
		if (!event.threadId || !threadIds.has(event.threadId)) continue;
		for (const evidence of event.evidence) available.add(keyForEvidence(evidence));
	}
	const selected: EvidenceReference[] = [];
	const seen = new Set<string>();
	for (const evidence of requested) {
		assertPublicEvidence(evidence);
		const key = keyForEvidence(evidence);
		if (!available.has(key)) fail('SCIENTIFIC_CONTEXT_EVIDENCE_NOT_RELEVANT');
		if (!seen.has(key)) {
			seen.add(key);
			selected.push({ ...evidence });
		}
	}
	return selected;
}

function documentEvidenceIds(evidence: EvidenceReference[]) {
	return new Set(evidence.filter((item) => item.kind === 'document-fragment').map((item) => item.id));
}

function normalizeRequestedIds(ids: string[] | undefined, code: string) {
	const result: string[] = [];
	for (const id of ids ?? []) {
		if (typeof id !== 'string' || id.length === 0 || id.length > 256) fail(code);
		if (!result.includes(id)) result.push(id);
	}
	return result;
}

export class ScientificContextBuilder {
	private readonly limits: ScientificContextLimits;
	private readonly documents?: VerifiedDocumentFragmentPort;

	constructor(private readonly state: ScientificContextStatePort, options: ScientificContextBuilderOptions = {}) {
		this.limits = narrowerLimits(options.limits);
		this.documents = options.documentFragments;
	}

	async build(input: ScientificContextBuilderInput): Promise<ScientificRoleContext> {
		const snapshot = await this.state.read();
		const authoritativeActive = snapshot.threads.find((thread) => thread.threadId === input.activeThread.threadId);
		if (!authoritativeActive) fail('SCIENTIFIC_CONTEXT_ACTIVE_THREAD_NOT_FOUND');
		assertThreadMatches(authoritativeActive, input.activeThread);
		assertPublicText(authoritativeActive.title, 'SCIENTIFIC_CONTEXT_PRIVATE_CONTENT');
		assertPublicText(authoritativeActive.summary, 'SCIENTIFIC_CONTEXT_PRIVATE_CONTENT');

		const requestedRelatedIds = normalizeRequestedIds(input.requestedDirectRelationIds, 'SCIENTIFIC_CONTEXT_RELATION_INVALID');
		const neighbors = directNeighbors(authoritativeActive.threadId, snapshot.relations);
		const threads = new Map(snapshot.threads.map((thread) => [thread.threadId, thread]));
		for (const relatedThreadId of requestedRelatedIds) {
			if (relatedThreadId === authoritativeActive.threadId || !threads.has(relatedThreadId) || !neighbors.has(relatedThreadId)) fail('SCIENTIFIC_CONTEXT_RELATION_NOT_DIRECT');
		}
		const relatedThreads = requestedRelatedIds
			.slice(0, this.limits.maxRelatedThreads)
			.map((relatedThreadId) => threads.get(relatedThreadId)!)
			.map((thread) => {
				assertPublicText(thread.title, 'SCIENTIFIC_CONTEXT_PRIVATE_CONTENT');
				assertPublicText(thread.summary, 'SCIENTIFIC_CONTEXT_PRIVATE_CONTENT');
				return thread;
			});
		const contextThreadIds = new Set([authoritativeActive.threadId, ...relatedThreads.map((thread) => thread.threadId)]);
		const relevant = relevantEvidence(input.actEvidence ?? [], contextThreadIds, snapshot.events);
		const relevantDocumentEntryIds = documentEvidenceIds(relevant);
		const documentEntryIds = normalizeRequestedIds(input.documentEntryIds, 'SCIENTIFIC_CONTEXT_DOCUMENT_SELECTION_INVALID')
			.filter((entryId) => relevantDocumentEntryIds.has(entryId));
		const evidence = relevant.slice(0, this.limits.maxEvidence);

		let byteCount = bytes({ act: input.act, activeThread: summary(authoritativeActive), relatedThreads: relatedThreads.map(summary), privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } });
		if (byteCount > this.limits.maxBytes) fail('SCIENTIFIC_CONTEXT_LIMIT_TOO_SMALL');
		const boundedEvidence: EvidenceReference[] = [];
		for (const item of evidence) {
			const size = bytes(item);
			if (byteCount + size > this.limits.maxBytes) break;
			byteCount += size;
			boundedEvidence.push(item);
		}

		const documentFragments = await this.boundedDocumentFragments(input, documentEntryIds, byteCount);
		for (const fragment of documentFragments) byteCount += bytes(fragment);
		return {
			schemaVersion: 1,
			act: input.act,
			activeThread: summary(authoritativeActive),
			relatedThreads: relatedThreads.map(summary),
			evidence: boundedEvidence,
			documentFragments,
			limits: { ...this.limits },
			byteCount,
			privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 },
		};
	}

	private async boundedDocumentFragments(input: ScientificContextBuilderInput, entryIds: string[], currentBytes: number): Promise<ScientificDocumentFragment[]> {
		if (entryIds.length === 0) return [];
		if (!input.verifiedRevision || !this.documents) fail('SCIENTIFIC_CONTEXT_DOCUMENT_NOT_VERIFIED');
		const selectedIds = entryIds.slice(0, this.limits.maxDocumentFragments);
		const availableBytes = this.limits.maxBytes - currentBytes;
		if (availableBytes <= 0 || selectedIds.length === 0) return [];
		const loaded = await this.documents.load({
			revision: input.verifiedRevision,
			entryIds: selectedIds,
			maxFragments: this.limits.maxDocumentFragments,
			maxBytes: availableBytes,
		});
		if (!sameRevision(loaded.revision, input.verifiedRevision)) fail('SCIENTIFIC_CONTEXT_DOCUMENT_REVISION_MISMATCH');
		const loadedByEntryId = new Map<string, ContextFragment>();
		for (const fragment of loaded.fragments) {
			if (!selectedIds.includes(fragment.entryId)) continue;
			if (loadedByEntryId.has(fragment.entryId) || typeof fragment.text !== 'string' || !fragment.text || sha256(fragment.text) !== fragment.textSha256 || !Array.isArray(fragment.headingPath) || fragment.headingPath.some((heading) => typeof heading !== 'string') || FORBIDDEN_PRIVATE_CONTENT.test(fragment.text)) fail('SCIENTIFIC_CONTEXT_DOCUMENT_INVALID');
			loadedByEntryId.set(fragment.entryId, fragment);
		}
		const fragments: ScientificDocumentFragment[] = [];
		let consumed = 0;
		for (const entryId of selectedIds) {
			const fragment = loadedByEntryId.get(entryId);
			if (!fragment) continue;
			const publicFragment: ScientificDocumentFragment = { ...fragment, headingPath: [...fragment.headingPath], revision: { ...loaded.revision } };
			const size = bytes(publicFragment);
			if (consumed + size > this.limits.maxBytes - currentBytes) break;
			consumed += size;
			fragments.push(publicFragment);
		}
		return fragments;
	}
}
