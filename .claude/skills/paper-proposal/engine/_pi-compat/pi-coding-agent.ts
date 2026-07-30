// pi-free compatibility shim for `@earendil-works/pi-coding-agent`.
//
// Reproduces exactly the surface the paper-proposal engine consumes:
//   - types: ExtensionAPI, ExtensionContext, SessionShutdownEvent, ModelDescriptor
//   - runtime: withFileMutationQueue (per-path async mutation serialization)
//
// The host (cli.ts) supplies a concrete ExtensionContext backed by the Claude
// transport; the engine logic is untouched.

/** Model identity the engine forwards to the transport layer. */
export type ModelDescriptor = { provider: string; id: string };

export type ApiKeyAndHeaders =
	| { ok: true; apiKey: string; headers?: Record<string, string>; env?: Record<string, string | undefined>; error?: undefined }
	| { ok: false; apiKey?: undefined; headers?: undefined; env?: undefined; error: string };

export interface ModelRegistry {
	getApiKeyAndHeaders(model: ModelDescriptor): Promise<ApiKeyAndHeaders>;
}

export interface SessionManager {
	getSessionId(): string;
}

export interface UI {
	confirm(title: string, message: string): Promise<boolean>;
}

/** Runtime context handed to the tool's execute(): the members the engine reads. */
export interface ExtensionContext {
	model?: ModelDescriptor;
	modelRegistry: ModelRegistry;
	sessionManager: SessionManager;
	hasUI?: boolean;
	ui: UI;
}

export type SessionShutdownEvent = { reason: string };
export type SessionStartEvent = Record<string, unknown>;

type ExtensionEventHandler = (event: any, ctx: ExtensionContext) => unknown | Promise<unknown>;

/** The registration surface an extension factory uses. */
export interface ExtensionAPI {
	registerTool(tool: unknown): void;
	on(event: string, handler: ExtensionEventHandler): void;
}

// --- withFileMutationQueue -------------------------------------------------
// Serializes mutations per canonical target path so overlapping operations on
// the same file never interleave. Distinct paths run concurrently. This matches
// the pi runtime's file mutation queue semantics the engine relies on.

const queues = new Map<string, Promise<unknown>>();

export function withFileMutationQueue<T>(target: string, work: () => T | Promise<T>): Promise<T> {
	const previous = queues.get(target) ?? Promise.resolve();
	const run = previous.then(() => work());
	// Keep the chain alive even if `work` rejects, without swallowing the error
	// seen by the caller.
	const settled = run.then(
		() => undefined,
		() => undefined,
	);
	queues.set(target, settled);
	void settled.then(() => {
		if (queues.get(target) === settled) queues.delete(target);
	});
	return run;
}
