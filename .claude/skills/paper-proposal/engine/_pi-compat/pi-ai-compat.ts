// pi-free compatibility shim for `@earendil-works/pi-ai/compat`.
//
// The paper-proposal engine performs every model call through the single
// `complete(...)` entry point, exactly as the pi runtime exposed it. This shim
// reproduces that call contract on top of the Claude Messages API so the
// engine's planner/tutor/reviewer logic is preserved without change.
//
// It also reproduces pi's faux-provider harness (`registerFauxProvider`,
// `fauxAssistantMessage`, `fauxToolCall`) so the engine's production-path tests
// run fully offline against scripted model responses — the same mechanism the
// original pi test-suite used, now self-contained.
//
// The engine only ever consumes `response.stopReason` and `response.content`
// (parts of shape `{type:'toolCall',name,arguments}` or `{type:'text',text}`).

import type { ModelDescriptor } from './pi-coding-agent.js';

/** The single message shape the engine builds for a completion. */
export type UserMessage = {
	role: 'user';
	content: Array<{ type: 'text'; text: string }>;
	timestamp: number;
};

type ToolSpec = { name: string; description: string; parameters: unknown };

type CompleteRequest = {
	systemPrompt: string;
	messages: UserMessage[];
	tools?: ToolSpec[];
};

type CompleteOptions = {
	apiKey: string;
	headers?: Record<string, string>;
	env?: Record<string, string | undefined>;
	signal?: AbortSignal;
	toolChoice?: 'required';
};

type CompletionPart =
	| { type: 'toolCall'; name: string; arguments: Record<string, unknown> }
	| { type: 'text'; text: string };

export type CompletionResponse = {
	stopReason: string;
	content: CompletionPart[];
};

// --- faux provider harness -------------------------------------------------
// Mirrors pi's contract: a test registers a provider keyed by `api`, scripts
// responses, and reads back the call count. The engine's `complete` routes to
// the registered provider whenever `model.provider` matches, bypassing Claude.

const FAUX_TOOL_CALL = Symbol.for('paper-proposal.faux.toolCall');
const FAUX_ASSISTANT = Symbol.for('paper-proposal.faux.assistant');

type FauxToolCall = { [FAUX_TOOL_CALL]: true; name: string; arguments: Record<string, unknown> };
type FauxAssistant = { [FAUX_ASSISTANT]: true; body: FauxToolCall | string };

type FauxContext = { systemPrompt: string; messages: UserMessage[]; tools?: ToolSpec[] };
type FauxResponder = (context: FauxContext) => FauxAssistant;

type FauxProvider = {
	api: string;
	provider: string;
	models: Array<{ id: string; [key: string]: unknown }>;
	responders: FauxResponder[];
	state: { callCount: number };
};

// Backed by a globalThis symbol so the registry is a true singleton even if the
// module is instantiated more than once (e.g. imported as both `.ts` and `.js`
// under a test loader) — the same pattern the engine uses for its draft
// registry. Without this, an engine copy and a test copy would hold separate
// registries and faux registrations would be invisible to the model call.
const FAUX_REGISTRY = Symbol.for('paper-proposal.faux.providerRegistry/v1');

function fauxRegistry(): Map<string, FauxProvider> {
	const scope = globalThis as typeof globalThis & Record<symbol, unknown>;
	let registry = scope[FAUX_REGISTRY] as Map<string, FauxProvider> | undefined;
	if (!registry) {
		registry = new Map<string, FauxProvider>();
		Object.defineProperty(scope, FAUX_REGISTRY, { value: registry, configurable: false, enumerable: false, writable: false });
	}
	return registry;
}

const fauxProviders = fauxRegistry();

/** Builds a scripted tool-call the engine will see as a structured output. */
export function fauxToolCall(name: string, args: Record<string, unknown>): FauxToolCall {
	return { [FAUX_TOOL_CALL]: true, name, arguments: args };
}

/** Wraps a tool-call or raw text as one assistant turn. */
export function fauxAssistantMessage(body: FauxToolCall | string): FauxAssistant {
	return { [FAUX_ASSISTANT]: true, body };
}

export function registerFauxProvider(options: {
	api?: string;
	provider?: string;
	models?: Array<{ id: string; [key: string]: unknown }>;
} = {}) {
	const api = options.api ?? options.provider ?? 'faux';
	const provider = options.provider ?? api;
	const models = options.models ?? [{ id: `${provider}-model` }];
	const record: FauxProvider = { api, provider, models, responders: [], state: { callCount: 0 } };
	fauxProviders.set(provider, record);
	return {
		state: record.state,
		setResponses(responders: FauxResponder[]) {
			record.responders = responders;
		},
		getModel(): ModelDescriptor {
			return { provider, id: models[0].id };
		},
		unregister() {
			if (fauxProviders.get(provider) === record) fauxProviders.delete(provider);
		},
	};
}

function runFaux(record: FauxProvider, request: CompleteRequest): CompletionResponse {
	const index = record.state.callCount;
	record.state.callCount += 1;
	const responder = record.responders[Math.min(index, record.responders.length - 1)];
	if (!responder) throw new Error('FAUX_PROVIDER_NO_RESPONSE');
	const assistant = responder({ systemPrompt: request.systemPrompt, messages: request.messages, tools: request.tools });
	const body = assistant?.body;
	if (body && typeof body === 'object' && (body as FauxToolCall)[FAUX_TOOL_CALL]) {
		const call = body as FauxToolCall;
		return { stopReason: 'tool_use', content: [{ type: 'toolCall', name: call.name, arguments: call.arguments }] };
	}
	return { stopReason: 'end_turn', content: [{ type: 'text', text: typeof body === 'string' ? body : '' }] };
}

const DEFAULT_MAX_TOKENS = 8192;

function resolveMaxTokens(): number {
	const raw = process.env.PAPER_PROPOSAL_MAX_TOKENS;
	if (!raw) return DEFAULT_MAX_TOKENS;
	const value = Number(raw);
	return Number.isSafeInteger(value) && value > 0 ? value : DEFAULT_MAX_TOKENS;
}

/**
 * Executes one model completion.
 *
 * Routes to a registered faux provider when `model.provider` matches (offline,
 * scripted); otherwise calls the Claude Messages API. Mirrors the pi
 * `complete(model, request, options)` surface: the engine passes its resolved
 * model descriptor, a system prompt, exactly one user message, and an optional
 * single output tool with `toolChoice: 'required'`. Aborts resolve with
 * `stopReason: 'aborted'` (never throw) so the engine maps them to its
 * MODEL_CALL_ABORTED classification, matching the original runtime.
 */
export async function complete(
	model: ModelDescriptor,
	request: CompleteRequest,
	options: CompleteOptions,
): Promise<CompletionResponse> {
	const faux = fauxProviders.get(model.provider);
	if (faux) return runFaux(faux, request);

	// Lazy import: the Claude SDK is only required for real model calls, so the
	// shim (and the whole engine) loads offline for faux-driven test fixtures.
	const { default: Anthropic } = await import('@anthropic-ai/sdk');
	const client = new Anthropic({ apiKey: options.apiKey, ...(options.headers ? { defaultHeaders: options.headers } : {}) });

	const messages = request.messages.map((message) => ({
		role: message.role,
		content: message.content.map((part) => ({ type: 'text' as const, text: part.text })),
	}));

	const tools = request.tools?.map((tool) => ({
		name: tool.name,
		description: tool.description,
		input_schema: tool.parameters as { type: 'object'; [key: string]: unknown },
	}));

	const toolChoice =
		options.toolChoice === 'required' && tools && tools.length > 0
			? ({ type: 'tool', name: tools[0].name } as const)
			: undefined;

	let response: Awaited<ReturnType<typeof client.messages.create>>;
	try {
		response = await client.messages.create(
			{
				model: model.id,
				max_tokens: resolveMaxTokens(),
				system: request.systemPrompt,
				messages,
				...(tools ? { tools } : {}),
				...(toolChoice ? { tool_choice: toolChoice } : {}),
			},
			{ signal: options.signal },
		);
	} catch (cause) {
		if (options.signal?.aborted || (cause instanceof Error && cause.name === 'AbortError')) {
			return { stopReason: 'aborted', content: [] };
		}
		throw cause;
	}

	if ('content' in response === false) return { stopReason: 'end_turn', content: [] };
	const content: CompletionPart[] = response.content.map((block) => {
		if (block.type === 'tool_use') {
			return { type: 'toolCall', name: block.name, arguments: (block.input ?? {}) as Record<string, unknown> };
		}
		if (block.type === 'text') return { type: 'text', text: block.text };
		return { type: 'text', text: '' };
	});

	return { stopReason: response.stop_reason ?? 'end_turn', content };
}
