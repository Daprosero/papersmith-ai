import { randomUUID } from 'node:crypto';
import { MAX_CHAT_CONCLUSION_BYTES, MAX_CHAT_CONVERSATIONS, MAX_CHAT_TURNS, type PiSessionDraftRegistry } from './chat-draft-registry.js';
import { modelCall } from './runtime-metrics.js';
import type { DraftMaterializationPayload } from './draft-materialization.js';
import type { LocalContext } from './types.js';
import type { TutorAdapter, TutorAssessment } from './tutor-adapter.js';
import { validateTutorAssessment } from './tutor-adapter.js';

const MAX_CONTEXT_BYTES = 8_000;
export const MAX_CHAT_DOCUMENT_CONTEXT_BYTES = 6_000;
const CHAT_CONVERSATION_ID = /^chat-[a-z0-9][a-z0-9-]{0,250}$/;

type ChatTurn = { conclusion: string; assessment: TutorAssessment };
export type ChatDocumentContext = Readonly<{
	access: 'READ_ONLY';
	filename: string;
	revision: string;
	lineage: string;
	documentSha256: string;
	content: string;
	bytesRead: number;
	truncated: boolean;
}>;
type Conversation = { turns: ChatTurn[]; document?: ChatDocumentContext }; 

export type ChatDeliberationResult = {
	status: 'deliberated' | 'blocked';
	conversationId: string;
	conclusion?: string;
	assessment?: TutorAssessment;
	alternatives: string[];
	risks: TutorAssessment['riskLevel'][];
	unresolvedQuestions: string[];
	context: { turnCount: number; reusedConclusion: boolean };
	modelCalls: number;
	mutations: 0;
	receiptId: null;
	manifestStatus: 'NOT_PUBLISHED';
	auditStatus: 'NOT_RUN';
	selfAuditStatus: 'NOT_RUN';
	recoveryStatus: 'not_required';
	nextAction: null | 'clarify_request';
	reason?: string;
};

function boundedConclusion(value: string): string {
	return Buffer.from(value.trim()).subarray(0, MAX_CHAT_CONCLUSION_BYTES).toString('utf8').trim();
}

function createMaterializationPayload(conversationId: string, turns: readonly ChatTurn[]): DraftMaterializationPayload {
	return Object.freeze({ source: 'CHAT_DELIBERATION', conversationId, content: turns.map(turn => turn.conclusion).join('\n\n') });
}

/** Session-local tutor chat. It intentionally never reads or writes project state. */
export class ChatDeliberationService {
	private readonly conversations = new Map<string, Conversation>();

	constructor(private readonly tutor: TutorAdapter | undefined, private readonly draftRegistry: PiSessionDraftRegistry, private readonly newConversationId: () => string = randomUUID) {}

	latestConclusion(conversationId?: string): string | undefined {
		if (!conversationId) return undefined;
		return this.conversations.get(conversationId)?.turns.at(-1)?.conclusion;
	}

	currentManagedDocument(conversationId?: string): ChatDocumentContext | undefined {
		if (!conversationId) return undefined;
		return this.conversations.get(conversationId)?.document;
	}

	async deliberate(input: { instruction: string; sessionIdentity: string; conversationId?: string; document?: ChatDocumentContext }): Promise<ChatDeliberationResult> {
		const conversationId = input.conversationId ?? `chat-${this.newConversationId()}`;
		const conversation = this.conversations.get(conversationId) ?? { turns: [] };
		if (!CHAT_CONVERSATION_ID.test(conversationId)) return this.blocked(conversationId, conversation, 'CHAT_CONVERSATION_ID_INVALID');
		if (!this.tutor) return this.blocked(conversationId, conversation, 'TUTOR_REQUIRED');
		const priorTurns = conversation.turns.slice(-MAX_CHAT_TURNS + 1);
		const context = this.context(conversationId, priorTurns, input.instruction, input.document);
		try {
			const assessment = validateTutorAssessment(await modelCall('tutor', () => this.tutor!.assess({ instruction: input.instruction, context })), context.fragments.map((fragment) => fragment.entryId));
			const conclusion = boundedConclusion(assessment.summary);
			if (!conclusion) return this.blocked(conversationId, conversation, 'TUTOR_CONCLUSION_INVALID');
			const updatedConversation = { turns: [...priorTurns, { conclusion, assessment }], document: input.document ?? conversation.document };
			this.draftRegistry.put(input.sessionIdentity, conversationId, createMaterializationPayload(conversationId, updatedConversation.turns));
			this.remember(conversationId, updatedConversation);
			return {
				status: 'deliberated', conversationId, conclusion, assessment,
				alternatives: assessment.proposedAlternative ? [assessment.proposedAlternative] : [], risks: [assessment.riskLevel], unresolvedQuestions: assessment.unresolvedQuestions,
				context: { turnCount: updatedConversation.turns.length, reusedConclusion: priorTurns.length > 0 }, modelCalls: 1, mutations: 0, receiptId: null,
				manifestStatus: 'NOT_PUBLISHED', auditStatus: 'NOT_RUN', selfAuditStatus: 'NOT_RUN', recoveryStatus: 'not_required', nextAction: assessment.unresolvedQuestions.length ? 'clarify_request' : null,
			};
		} catch (error) {
			return this.blocked(conversationId, conversation, error instanceof Error ? error.message : String(error), 1);
		}
	}

	private context(conversationId: string, turns: ChatTurn[], instruction: string, document?: ChatDocumentContext): LocalContext {
		let bytes = 0;
		const fragments = [
			...(document ? [{ entryId: `chat-document:${document.filename}`, type: 'document' as const, text: document.content, textSha256: document.documentSha256, headingPath: ['Document', document.filename] }] : []),
			...turns.map((turn, index) => ({ entryId: `chat-turn-${index + 1}`, type: 'paragraph' as const, text: turn.conclusion, textSha256: '', headingPath: ['Conversation', conversationId] })),
		].filter((fragment) => {
			const size = Buffer.byteLength(fragment.text);
			if (bytes + size > MAX_CONTEXT_BYTES) return false;
			bytes += size;
			return true;
		});
		return { documentSha256: document?.documentSha256 ?? `chat:${conversationId}`, targetEntryId: fragments.at(-1)?.entryId ?? 'chat-turn-0', instruction, fragments, nearbySymbols: {}, directReferences: [], maxBytes: MAX_CONTEXT_BYTES };
	}

	private remember(conversationId: string, conversation: Conversation) {
		if (!this.conversations.has(conversationId) && this.conversations.size >= MAX_CHAT_CONVERSATIONS) this.conversations.delete(this.conversations.keys().next().value!);
		this.conversations.set(conversationId, conversation);
	}

	private blocked(conversationId: string, conversation: Conversation, reason: string, modelCalls = 0): ChatDeliberationResult {
		return { status: 'blocked', conversationId, alternatives: [], risks: [], unresolvedQuestions: [], context: { turnCount: conversation.turns.length, reusedConclusion: conversation.turns.length > 0 }, modelCalls, mutations: 0, receiptId: null, manifestStatus: 'NOT_PUBLISHED', auditStatus: 'NOT_RUN', selfAuditStatus: 'NOT_RUN', recoveryStatus: 'not_required', nextAction: 'clarify_request', reason };
	}
}
