import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const aiRoot = path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(aiRoot, 'index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/exports.ts'));

async function serviceFixture(overrides = {}) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-draft-'));
	const primaryName = `source-${Math.random().toString(36).slice(2)}.md`;
	const primaryRoute = `documents/${primaryName}`;
	const primaryBytes = Buffer.from('# Source\n\nProtected primary bytes.\n');
	await mkdir(path.join(projectRoot, 'documents'));
	await writeFile(path.join(projectRoot, primaryRoute), primaryBytes);
	const guard = workspace.createDocumentOperationGuard(projectRoot);
	const guardCalls = [];
	const originalExecute = guard.execute.bind(guard);
	guard.execute = async input => { guardCalls.push(input); return originalExecute(input); };
	const policy = { managedDocumentPath: primaryRoute, draftDirectory: 'working-drafts', allowedExtensions: ['.md', '.txt'], documentMetadata: { purpose: 'notes' }, ...overrides };
	const service = new v2.DraftMaterializationService(projectRoot, guard, policy, () => `draft-test-${Math.random().toString(36).slice(2)}`);
	return { projectRoot, primaryRoute, primaryBytes, guardCalls, service, async dispose() { await rm(projectRoot, { recursive: true, force: true }); } };
}

const request = (route, extra = {}) => ({ operation: 'INITIAL_CREATE', route, authorized: true, ...extra });
const materializationPayload = (conversationId, content) => ({ source: 'CHAT_DELIBERATION', conversationId, content });
const materialize = (service, conversationId, content, draftRequest) => service.execute({ conversationId, materializationPayload: materializationPayload(conversationId, content), request: draftRequest });

test('missing or empty materializationPayload fails closed before resolving or creating any file', async () => {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-empty-draft-'));
	let inventoryCalls = 0;
	const guard = workspace.createDocumentOperationGuard(projectRoot);
	const service = new v2.DraftMaterializationService(projectRoot, guard, {
		draftDirectory: 'generated-drafts',
		managedDocumentInventory: async () => { inventoryCalls += 1; throw new Error('PRIMARY_MUST_NOT_BE_OPENED'); },
	});
	const conversationId = 'chat-empty-payload';
	const route = `generated-drafts/${Math.random().toString(36).slice(2)}.md`;
	try {
		for (const payload of [undefined, materializationPayload(conversationId, ' \n\t')]) {
			const result = await service.execute({ conversationId, materializationPayload: payload, request: request(route) });
			assert.equal(result.status, 'blocked');
			assert.equal(result.reason, 'CHAT_CONTENT_REQUIRED');
			assert.equal(result.missingPayload, 'materializationPayload');
			assert.equal(result.primaryDocumentPath, null);
		}
		assert.equal(inventoryCalls, 0, 'missing payload is rejected before primary-document resolution');
		assert.deepEqual(await readdir(projectRoot), [], 'no target or directory is created');
	} finally { await rm(projectRoot, { recursive: true, force: true }); }
});

for (const [name, route, expectedReason] of [
	['outside-directory rejection', 'other/place.md', 'DRAFT_ROUTE_OUTSIDE_DIRECTORY'],
	['dot-dot traversal rejection', 'working-drafts/../escape.md', 'DRAFT_ROUTE_NOT_NORMALIZED'],
	['unauthorized absolute path rejection', path.join(tmpdir(), 'absolute-draft.md'), 'DRAFT_ROUTE_ABSOLUTE_OR_INVALID'],
]) {
	test(name, async () => {
		const run = await serviceFixture();
		try {
			const result = await materialize(run.service, 'chat-generic-route', 'Consolidated content.', request(route));
			assert.equal(result.status, 'blocked');
			assert.equal(result.requestedRoute, route, 'invalid user route is returned unchanged');
			assert.equal(result.reason, expectedReason);
			assert.deepEqual(run.guardCalls, []);
			assert.deepEqual(await readFile(path.join(run.projectRoot, run.primaryRoute)), run.primaryBytes);
		} finally { await run.dispose(); }
	});
}

test('accepted in-directory INITIAL_CREATE writes exact bytes and rejects a duplicate without changing the primary', async () => {
	const run = await serviceFixture();
	const route = `working-drafts/${Math.random().toString(36).slice(2)}.md`;
	const content = 'First conclusion.\n\nSecond conclusion.';
	try {
		const created = await materialize(run.service, 'chat-create-once', content, request(route));
		assert.deepEqual(created, {
			status: 'materialized', operation: 'INITIAL_CREATE', route, bytesWritten: Buffer.byteLength(content), primaryDocumentPath: run.primaryRoute,
			primaryDocumentIntact: true, terminalState: 'COMPLETED', nextAction: null, mutations: 1,
		});
		assert.equal(await readFile(path.join(run.projectRoot, route), 'utf8'), content);
		assert.deepEqual(run.guardCalls.map(call => call.action), ['begin_document_operation', 'preflight_plan', 'authorize_mutation', 'complete_operation']);
		const duplicate = await materialize(run.service, 'chat-create-again', 'Replacement attempt.', request(route));
		assert.equal(duplicate.status, 'blocked');
		assert.equal(duplicate.reason, 'DRAFT_TARGET_ALREADY_EXISTS');
		assert.equal(await readFile(path.join(run.projectRoot, route), 'utf8'), content);
		assert.deepEqual(await readFile(path.join(run.projectRoot, run.primaryRoute)), run.primaryBytes);
	} finally { await run.dispose(); }
});

test('primary target, symlink routes, and UPDATE or REPLACE from chat are denied before the guard', async () => {
	const run = await serviceFixture({ draftDirectory: 'documents' });
	try {
		const primary = await materialize(run.service, 'chat-primary', 'No.', request(run.primaryRoute));
		assert.equal(primary.status, 'blocked');
		assert.equal(primary.reason, 'DRAFT_ROUTE_IS_PRIMARY_DOCUMENT');
		await mkdir(path.join(run.projectRoot, 'outside'));
		await symlink(path.join(run.projectRoot, 'outside'), path.join(run.projectRoot, 'documents', 'linked'));
		const linked = await materialize(run.service, 'chat-linked', 'No.', request('documents/linked/draft.md'));
		assert.equal(linked.status, 'blocked');
		assert.match(linked.reason, /SYMLINK|OUTSIDE/);
		for (const operation of ['UPDATE', 'REPLACE']) {
			const conversationId = `chat-${operation.toLowerCase()}`;
			const rejected = await materialize(run.service, conversationId, 'No.', { operation, route: `documents/${operation.toLowerCase()}.md`, authorized: true });
			assert.equal(rejected.status, 'blocked');
			assert.equal(rejected.reason, 'CHAT_DRAFT_UPDATE_REPLACE_FORBIDDEN');
		}
		assert.deepEqual(run.guardCalls, []);
		assert.deepEqual(await readFile(path.join(run.projectRoot, run.primaryRoute)), run.primaryBytes);
	} finally { await run.dispose(); }
});

test('generated path uses generic metadata, is proposed without writing, and requires approval plus current-turn authorization', async () => {
	const run = await serviceFixture({ documentMetadata: { slug: 'dataset-summary', purpose: 'discussion', revision: 'r7' } });
	try {
		const proposed = await materialize(run.service, 'chat-propose', 'Bounded content.', { operation: 'INITIAL_CREATE', authorized: false, metadata: { extension: '.txt' } });
		assert.equal(proposed.status, 'draft_path_proposed');
		assert.equal(proposed.route, 'working-drafts/dataset-summary-discussion-r7.txt');
		assert.equal(proposed.terminalState, 'PENDING_APPROVAL');
		assert.deepEqual(await readdir(run.projectRoot), ['documents']);
		assert.deepEqual(run.guardCalls, []);
		const unauthorized = await materialize(run.service, 'chat-propose', 'Bounded content.', { operation: 'INITIAL_CREATE', authorized: false, approveProposedRoute: true });
		assert.equal(unauthorized.status, 'blocked');
		assert.equal(unauthorized.reason, 'INITIAL_CREATE_NOT_AUTHORIZED_CURRENT_TURN');
		const approved = await materialize(run.service, 'chat-propose', 'Bounded content.', { operation: 'INITIAL_CREATE', authorized: true, approveProposedRoute: true });
		assert.equal(approved.status, 'materialized');
		assert.equal(approved.route, proposed.route);
		assert.equal(await readFile(path.join(run.projectRoot, proposed.route), 'utf8'), 'Bounded content.');
	} finally { await run.dispose(); }
});

function registerPublicDraftExtension({ run, sessionIdentity, tutor, draftRegistry, operationGuard }) {
	const tools = [];
	const handlers = new Map();
	const pi = {
		registerTool: tool => tools.push(tool),
		on: (event, handler) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
	};
	workspace.createPaperProposalExtension({
		projectRoot: run.projectRoot,
		operationGuard: operationGuard ?? workspace.createDocumentOperationGuard(run.projectRoot),
		draftMaterialization: { managedDocumentPath: run.primaryRoute, draftDirectory: 'working-drafts', allowedExtensions: ['.md'] },
		tutor,
		...(draftRegistry ? { draftRegistry } : {}),
	})(pi);
	const tool = tools.find(candidate => candidate.name === 'paper_proposal_execute');
	const ctx = { sessionManager: { getSessionId: () => sessionIdentity } };
	return {
		execute: async params => (await tool.execute('draft-session-transition', params, undefined, undefined, ctx)).details,
		emit: async (event, value) => { for (const handler of handlers.get(event) ?? []) await handler({ type: event, ...value }, ctx); },
	};
}

// Ambient-model paradigm (design `sdd/paper-proposal-ambient-model`, SLICE 2): the
// production real-API tutor transport (faux-provider harness over `ctx.model`) was
// removed along with `production-tutor-adapter.ts`. A plain scripted `TutorAdapter`
// (`{assess}`) is injected directly through `createPaperProposalExtension`'s `tutor`
// option instead -- the same seam the deterministic/scripted-adapter suites use.
function scriptedTutor(summaries) {
	let call = 0;
	return {
		assess: async (input) => {
			const summary = summaries[Math.min(call, summaries.length - 1)];
			call += 1;
			return { decision: 'ACCEPT', summary, mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: input.context.fragments.map(fragment => fragment.entryId) };
		},
	};
}

test('public session draft survives route proposal and reload re-registration, then materializes exact bytes and is removed', async () => {
	const run = await serviceFixture();
	const sessionIdentity = `pi-session-reload-${Math.random().toString(36).slice(2)}`;
	const registry = v2.getSharedPiSessionDraftRegistry();
	const exactDraft = '# Session draft\n\nExact UTF-8 bytes: café — λ.';
	const tutor = scriptedTutor([exactDraft]);
	registry.clearSession(sessionIdentity);
	try {
		let extension = registerPublicDraftExtension({ run, sessionIdentity, tutor });
		await extension.emit('session_start', { reason: 'startup' });
		const chat = await extension.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Create a bounded chat draft.' });
		assert.equal(chat.status, 'deliberated', JSON.stringify(chat));
		assert.equal(registry.has(sessionIdentity, chat.conversationId), true);
		const received = registry.get(sessionIdentity, chat.conversationId);
		assert.ok(Object.isFrozen(received));
		assert.equal(received.content, exactDraft);

		const proposed = await extension.execute({ operation: 'CHAT_DELIBERATION', conversationId: chat.conversationId, instruction: 'Propose a route only.', draftMaterialization: { operation: 'INITIAL_CREATE', authorized: false } });
		assert.equal(proposed.status, 'draft_path_proposed', JSON.stringify(proposed));
		assert.equal(proposed.bytesWritten, 0);
		assert.equal(registry.has(sessionIdentity, chat.conversationId), true, 'route proposal does not consume the payload');
		assert.deepEqual(await readdir(run.projectRoot), ['documents']);

		await extension.emit('session_shutdown', { reason: 'reload' });
		assert.equal(registry.has(sessionIdentity, chat.conversationId), true, 'reload shutdown is not Pi session termination');
		extension = registerPublicDraftExtension({ run, sessionIdentity, tutor });
		await extension.emit('session_start', { reason: 'reload' });
		const materialized = await extension.execute({ operation: 'CHAT_DELIBERATION', conversationId: chat.conversationId, instruction: 'Authorize the exact proposed route.', draftMaterialization: request(proposed.route) });
		assert.equal(materialized.status, 'materialized', JSON.stringify(materialized));
		assert.equal(materialized.bytesWritten, Buffer.byteLength(exactDraft));
		assert.deepEqual(await readFile(path.join(run.projectRoot, proposed.route)), Buffer.from(received.content));
		assert.equal(registry.has(sessionIdentity, chat.conversationId), false, 'successful materialization consumes the payload');
	} finally {
		registry.clearSession(sessionIdentity);
		await run.dispose();
	}
});

test('draft registry isolates Pi sessions that reuse a conversation ID', () => {
	const registry = v2.createPiSessionDraftRegistry();
	const conversationId = 'chat-reused-conversation';
	const first = materializationPayload(conversationId, 'First session payload.');
	const second = materializationPayload(conversationId, 'Second session payload.');
	registry.put('pi-session-a', conversationId, first);
	registry.put('pi-session-b', conversationId, second);
	assert.equal(registry.get('pi-session-a', conversationId).content, first.content);
	assert.equal(registry.get('pi-session-b', conversationId).content, second.content);
	registry.delete('pi-session-a', conversationId);
	assert.equal(registry.has('pi-session-a', conversationId), false);
	assert.equal(registry.has('pi-session-b', conversationId), true);
});

test('draft payload survives multiple reload re-registrations', async () => {
	const run = await serviceFixture();
	const registry = v2.createPiSessionDraftRegistry();
	const sessionIdentity = 'pi-session-multiple-reloads';
	const exactDraft = 'Payload retained across repeated extension instances.';
	const tutor = scriptedTutor([exactDraft]);
	try {
		let extension = registerPublicDraftExtension({ run, sessionIdentity, tutor, draftRegistry: registry });
		await extension.emit('session_start', { reason: 'startup' });
		const chat = await extension.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Create a reload-safe payload.' });
		for (let index = 0; index < 3; index += 1) {
			await extension.emit('session_shutdown', { reason: 'reload' });
			assert.equal(registry.has(sessionIdentity, chat.conversationId), true);
			extension = registerPublicDraftExtension({ run, sessionIdentity, tutor, draftRegistry: registry });
			await extension.emit('session_start', { reason: 'reload' });
		}
		const route = `working-drafts/${Math.random().toString(36).slice(2)}.md`;
		const created = await extension.execute({ operation: 'CHAT_DELIBERATION', conversationId: chat.conversationId, instruction: 'Materialize after repeated reloads.', draftMaterialization: request(route) });
		assert.equal(created.status, 'materialized', JSON.stringify(created));
		assert.equal(await readFile(path.join(run.projectRoot, route), 'utf8'), exactDraft);
		assert.equal(registry.has(sessionIdentity, chat.conversationId), false);
	} finally {
		await run.dispose();
	}
});

test('failed materialization preserves the session draft payload', async () => {
	const run = await serviceFixture();
	const registry = v2.createPiSessionDraftRegistry();
	const sessionIdentity = 'pi-session-failed-materialization';
	const exactDraft = 'Retain this payload after a denied materialization.';
	const tutor = scriptedTutor([exactDraft]);
	const backingGuard = workspace.createDocumentOperationGuard(run.projectRoot);
	const denyingGuard = {
		...backingGuard,
		execute: async input => input.action === 'preflight_plan'
			? { decision: 'denied', reason: { code: 'TEST_PREFLIGHT_DENIED' } }
			: backingGuard.execute(input),
	};
	try {
		const extension = registerPublicDraftExtension({ run, sessionIdentity, tutor, draftRegistry: registry, operationGuard: denyingGuard });
		await extension.emit('session_start', { reason: 'startup' });
		const chat = await extension.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Create content that must survive a failed write attempt.' });
		const route = `working-drafts/${Math.random().toString(36).slice(2)}.md`;
		const failed = await extension.execute({ operation: 'CHAT_DELIBERATION', conversationId: chat.conversationId, instruction: 'Attempt materialization.', draftMaterialization: request(route) });
		assert.equal(failed.status, 'blocked');
		assert.equal(failed.reason, 'DRAFT_GUARD_PREFLIGHT_TEST_PREFLIGHT_DENIED');
		assert.equal(registry.get(sessionIdentity, chat.conversationId).content, exactDraft);
	} finally {
		await run.dispose();
	}
});

test('Pi session end clears every transient draft for that session', async () => {
	const run = await serviceFixture();
	const registry = v2.createPiSessionDraftRegistry();
	const sessionIdentity = 'pi-session-cleanup';
	const tutor = scriptedTutor(['Transient payload.']);
	try {
		const extension = registerPublicDraftExtension({ run, sessionIdentity, tutor, draftRegistry: registry });
		await extension.emit('session_start', { reason: 'startup' });
		const chat = await extension.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Create transient content.' });
		assert.equal(registry.has(sessionIdentity, chat.conversationId), true);
		await extension.emit('session_shutdown', { reason: 'quit' });
		assert.equal(registry.sessionSize(sessionIdentity), 0);
	} finally {
		await run.dispose();
	}
});

test('public materialization without any produced draft returns CHAT_CONTENT_REQUIRED before guards or filesystem', async () => {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-no-chat-draft-'));
	let inventoryCalls = 0;
	const guardCalls = [];
	const guard = workspace.createDocumentOperationGuard(projectRoot);
	const originalExecute = guard.execute.bind(guard);
	guard.execute = async input => { guardCalls.push(input); return originalExecute(input); };
	const sessionIdentity = 'pi-session-no-draft';
	const tools = [];
	workspace.createPaperProposalExtension({
		projectRoot,
		operationGuard: guard,
		draftRegistry: v2.createPiSessionDraftRegistry(),
		draftMaterialization: { draftDirectory: 'working-drafts', managedDocumentInventory: async () => { inventoryCalls += 1; throw new Error('MUST_NOT_RESOLVE_PRIMARY'); } },
	})({ registerTool: tool => tools.push(tool), on: () => {} });
	const tool = tools.find(candidate => candidate.name === 'paper_proposal_execute');
	const ctx = { sessionManager: { getSessionId: () => sessionIdentity } };
	try {
		const result = (await tool.execute('no-chat-draft', { operation: 'CHAT_DELIBERATION', conversationId: 'chat-never-produced', instruction: 'Materialize absent content.', draftMaterialization: request('working-drafts/absent.md') }, undefined, undefined, ctx)).details;
		assert.equal(result.status, 'blocked');
		assert.equal(result.reason, 'CHAT_CONTENT_REQUIRED');
		assert.equal(result.missingPayload, 'materializationPayload');
		assert.equal(inventoryCalls, 0);
		assert.deepEqual(guardCalls, []);
		assert.deepEqual(await readdir(projectRoot), []);
	} finally { await rm(projectRoot, { recursive: true, force: true }); }
});

test('public CHAT_DELIBERATION hands off consolidated bytes exactly once to guarded DOCUMENT_EDIT materialization', async () => {
	const run = await serviceFixture();
	let tutorCalls = 0;
	const draftFragments = ['# Generic draft\n\nExact UTF-8 bytes: café — λ.', '## Consolidated conclusion\n\nFinal paragraph.'];
	const consolidatedDraft = draftFragments.join('\n\n');
	const tutor = {
		assess: async (input) => {
			const summary = draftFragments[Math.min(tutorCalls, draftFragments.length - 1)];
			tutorCalls += 1;
			return { decision: 'ACCEPT', summary, mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: input.context.fragments.map(fragment => fragment.entryId) };
		},
	};
	try {
		const tools = [];
		workspace.createPaperProposalExtension({ projectRoot: run.projectRoot, operationGuard: workspace.createDocumentOperationGuard(run.projectRoot), draftMaterialization: { managedDocumentPath: run.primaryRoute, draftDirectory: 'working-drafts', allowedExtensions: ['.md'] }, tutor })({ registerTool: tool => tools.push(tool), on: () => {} });
		const tool = tools.find(candidate => candidate.name === 'paper_proposal_execute');
		const sessionIdentity = `draft-test-session-${Math.random().toString(36).slice(2)}`;
		const ctx = { sessionManager: { getSessionId: () => sessionIdentity } };
		const execute = async params => (await tool.execute('draft-transition', params, undefined, undefined, ctx)).details;
		const chat = await execute({ operation: 'CHAT_DELIBERATION', instruction: 'Discuss a generic bounded topic.' });
		assert.equal(chat.status, 'deliberated');
		const followUp = await execute({ operation: 'CHAT_DELIBERATION', conversationId: chat.conversationId, instruction: 'Consolidate the final conclusion.' });
		assert.equal(followUp.status, 'deliberated');
		assert.equal(followUp.conversationId, chat.conversationId);
		const draftRoutesBefore = v2.getRuntimeMetrics().routeMetrics.routeSelections.DRAFT_MATERIALIZATION;
		const route = `working-drafts/${Math.random().toString(36).slice(2)}.md`;
		const materialized = await execute({ operation: 'CHAT_DELIBERATION', conversationId: followUp.conversationId, instruction: 'Save the consolidated discussion as a draft.', draftMaterialization: request(route) });
		assert.equal(materialized.status, 'materialized', JSON.stringify(materialized));
		assert.equal(materialized.routeStage, 'DOCUMENT_EDIT');
		assert.equal(materialized.transition, 'CHAT_DELIBERATION_TO_DOCUMENT_EDIT');
		assert.equal(materialized.operation, 'INITIAL_CREATE');
		assert.equal(materialized.bytesWritten, Buffer.byteLength(consolidatedDraft));
		assert.equal(materialized.primaryDocumentIntact, true);
		assert.equal(materialized.terminalState, 'COMPLETED');
		assert.equal(materialized.authority.scope, 'DOCUMENT_EDIT');
		assert.equal(v2.getRuntimeMetrics().routeMetrics.routeSelections.DRAFT_MATERIALIZATION, draftRoutesBefore + 1);
		assert.equal(tutorCalls, 2, 'materialization does not reopen scientific reasoning');
		assert.deepEqual(await readFile(path.join(run.projectRoot, route)), Buffer.from(consolidatedDraft), 'final document bytes equal the consolidated chat draft');
		const replayRoute = `working-drafts/${Math.random().toString(36).slice(2)}.md`;
		const replay = await execute({ operation: 'CHAT_DELIBERATION', conversationId: followUp.conversationId, instruction: 'Save the same draft again.', draftMaterialization: request(replayRoute) });
		assert.equal(replay.status, 'blocked');
		assert.equal(replay.reason, 'CHAT_CONTENT_REQUIRED');
		assert.equal(replay.missingPayload, 'materializationPayload');
		assert.equal(tutorCalls, 2, 'successful materialization discards the chat snapshot instead of resuming deliberation');
		assert.deepEqual((await readdir(path.join(run.projectRoot, 'working-drafts'))).sort(), [path.basename(route)]);
		assert.deepEqual(await readFile(path.join(run.projectRoot, run.primaryRoute)), run.primaryBytes);
		// D5 (Phase 2): a successful materialization terminates the conversation's OWN deliberation
		// state, not merely its draft-registry entry -- reusing the conversationId to keep chatting
		// reports it terminated instead of silently resuming.
		const continued = await execute({ operation: 'CHAT_DELIBERATION', conversationId: followUp.conversationId, instruction: 'Keep discussing after materialization.' });
		assert.equal(continued.status, 'blocked', JSON.stringify(continued));
		assert.equal(continued.message, 'CONVERSATION_TERMINATED');
		assert.equal(tutorCalls, 2, 'the terminated conversation never reopens tutor reasoning');
	} finally {
		await run.dispose();
	}
});
