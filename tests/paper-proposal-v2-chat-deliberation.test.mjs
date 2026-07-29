import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
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
	'@earendil-works/pi-ai/compat': path.join(aiRoot, 'compat.js'),
	'@earendil-works/pi-ai': path.join(aiRoot, 'index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(path.join(root, '.pi/extensions/proposal-workspace.ts'));
const v2 = await jiti.import(path.join(root, '.pi/extensions/paper-proposal-v2/exports.ts'));
const aiCompat = await jiti.import(path.join(aiRoot, 'compat.js'));

function payload(context) {
	return JSON.parse(context.messages.at(-1).content.find((part) => part.type === 'text').text);
}

async function fixture() {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-chat-'));
	await mkdir(path.join(projectRoot, 'proposals'));
	const guardCalls = [];
	const guard = workspace.createDocumentOperationGuard(projectRoot);
	const originalExecute = guard.execute.bind(guard);
	guard.execute = async (input, signal) => { guardCalls.push(input); return originalExecute(input, signal); };
	const providerId = `paper-proposal-v2-chat-${Date.now()}-${Math.random()}`;
	const faux = aiCompat.registerFauxProvider({ api: providerId, provider: providerId, models: [{ id: `${providerId}-model`, input: ['text'], contextWindow: 32000, maxTokens: 4096 }] });
	let tutorCalls = 0;
	const tutorInputs = [];
	faux.setResponses(Array.from({ length: 8 }, () => (context) => {
		const input = payload(context);
		if (input.intent) {
			assert.match(input.instruction, /Las bolsas deben denotarse como conjuntos finitos/i);
			return aiCompat.fauxAssistantMessage(JSON.stringify({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: 'La definición de bolsas de entrenamiento las denota como conjuntos finitos.' }], unresolvedQuestions: [] }));
		}
		tutorCalls += 1;
		tutorInputs.push(input);
		if (input.context.fragments.some((fragment) => fragment.entryId === 'chat-turn-1')) assert.match(JSON.stringify(input.context.fragments), /Las bolsas deben denotarse como conjuntos finitos/i);
		return aiCompat.fauxAssistantMessage(JSON.stringify({ decision: 'ACCEPT', summary: 'El estado matemático del documento indica que las bolsas deben denotarse como conjuntos finitos.', mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: [] }));
	}));
	let tool;
	const register = () => {
		const tools = [];
		const handlers = new Map();
		workspace.createPaperProposalV2Extension({ projectRoot, operationGuard: guard })({ registerTool: (candidate) => tools.push(candidate), on: (event, handler) => handlers.set(event, handler) });
		tool = tools.find((candidate) => candidate.name === 'paper_proposal_v2_execute');
		return handlers;
	};
	let handlers = register();
	const sessionIdentity = `chat-test-session-${Math.random().toString(36).slice(2)}`;
	const ctx = { model: faux.getModel(), sessionManager: { getSessionId: () => sessionIdentity }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'fake', headers: {}, env: {} }) } }; 
	return {
		projectRoot, guardCalls, tutorCalls: () => tutorCalls, tutorInputs: () => tutorInputs,
		execute: async (params) => (await tool.execute('chat-deliberation', params, undefined, undefined, ctx)).details,
		async reload() {
			await handlers.get('session_shutdown')?.({ reason: 'reload' }, ctx);
			handlers = register();
			await handlers.get('session_start')?.({ reason: 'reload' }, ctx);
		},
		async seed() {
			const bootstrap = workspace.createProposalWorkspaceTool(projectRoot);
			await bootstrap.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# Propuesta\n\n## Método\n\nLa definición de bolsas de entrenamiento es informal.\n\nLa definición de bolsas de validación es informal.\n' });
		},
		async dispose() { faux.unregister?.(); await rm(projectRoot, { recursive: true, force: true }); },
	};
}

test('CHAT_DELIBERATION is multi-turn, bounded, non-mutating, and available without scientific persistence or a managed proposal', async () => {
	const run = await fixture();
	const previous = process.env.PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		delete process.env.PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED;
		const first = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: '¿Qué hipótesis conviene usar para la definición de bolsas?' });
		assert.equal(first.status, 'deliberated', JSON.stringify(first));
		assert.ok(first.conversationId);
		assert.match(first.conclusion, /conjuntos finitos/i);
		assert.equal(first.receiptId, null);
		assert.equal(first.mutations, 0);
		const second = await run.execute({ operation: 'CHAT_DELIBERATION', conversationId: first.conversationId, instruction: '¿Cómo afecta esa hipótesis a la sección 3.1?' });
		assert.equal(second.status, 'deliberated', JSON.stringify(second));
		assert.equal(second.conversationId, first.conversationId);
		assert.equal(second.context.turnCount, 2);
		assert.equal(run.tutorCalls(), 2);
		assert.deepEqual(await readdir(run.projectRoot), ['proposals']);
		assert.deepEqual(run.guardCalls, []);
	} finally {
		if (previous === undefined) delete process.env.PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED;
		else process.env.PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED = previous;
		await run.dispose();
	}
});

test('explicit CHAT_DELIBERATION overrides document-like scientific terminology without selecting or mutating', async () => {
	const run = await fixture();
	try {
		const result = await run.execute({
			operation: 'CHAT_DELIBERATION',
			instruction: 'Deliberemos la formulación conceptual de las pseudoetiquetas, el alineamiento y las predicciones falsables sin modificar el documento.',
		});
		assert.equal(result.status, 'deliberated', JSON.stringify(result));
		assert.equal(result.routeStage, 'CHAT_DELIBERATION');
		assert.equal(result.mutations, 0);
		assert.equal(result.receiptId, null);
		assert.equal('selector' in result, false);
		assert.deepEqual(result.authority, { scope: 'CHAT_DELIBERATION', taskDelegation: 'FORBIDDEN', documentAuthority: 'FORBIDDEN', durableState: 'FORBIDDEN', stateIdentifier: 'conversationId', explicitHandoffRequired: false });
		assert.deepEqual(run.guardCalls, []);
	} finally { await run.dispose(); }
});

test('chat remains principal-only for candidate-equation analysis regardless of scientific persistence or active maintenance state', async () => {
	const previous = process.env.PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		for (const persistence of [undefined, 'true']) {
			const run = await fixture();
			try {
				if (persistence === undefined) delete process.env.PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED;
				else process.env.PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED = persistence;
				const maintenance = await run.execute({ operation: 'MAINTENANCE', maintenanceTaskId: 'maintenance-task-1', instruction: 'Inspect extension infrastructure.' });
				assert.equal(maintenance.status, 'delegation_permitted');
				assert.equal(maintenance.authority.taskDelegation, 'PERMITTED');
				const chat = await run.execute({ operation: 'CHAT_DELIBERATION', activeThreadId: 'maintenance-task-1', maintenanceTaskId: 'maintenance-task-1', instruction: 'Analiza la ecuación candidata y sus supuestos, pero no modifiques el documento.' });
				assert.equal(chat.status, 'deliberated', JSON.stringify(chat));
				assert.match(chat.conversationId, /^chat-/);
				assert.equal(chat.routeStage, 'CHAT_DELIBERATION');
				assert.equal(chat.authority.taskDelegation, 'FORBIDDEN');
				assert.equal(chat.authority.durableState, 'FORBIDDEN');
				assert.equal('activeThreadId' in chat, false);
				assert.equal('maintenanceTaskId' in chat, false);
				const reservedMaintenance = await run.execute({ operation: 'MAINTENANCE', maintenanceTaskId: chat.conversationId, instruction: 'Inspect extension infrastructure.' });
				assert.equal(reservedMaintenance.status, 'blocked');
				assert.equal(reservedMaintenance.blockers[0].code, 'MAINTENANCE_TASK_ID_INVALID');
				const reservedScientific = await run.execute({ operation: 'SCIENTIFIC_WORKFLOW', activeThreadId: chat.conversationId, instruction: 'Construct a scientific idea.' });
				assert.equal(reservedScientific.status, 'blocked');
				assert.equal(reservedScientific.blockers[0].code, 'SCIENTIFIC_THREAD_ID_RESERVED_FOR_CHAT');
				assert.deepEqual(run.guardCalls, []);
				assert.deepEqual(await readdir(run.projectRoot), ['proposals']);
			} finally { await run.dispose(); }
		}
	} finally {
		if (previous === undefined) delete process.env.PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED;
		else process.env.PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED = previous;
	}
});

test('CHAT_DELIBERATION loads either canonical managed-document spelling as immutable tutor context without mutation', async () => {
	const run = await fixture();
	try {
		await run.seed();
		const target = path.join(run.projectRoot, 'proposals/research-concept-r01.md');
		const before = await readFile(target);
		const basename = await run.execute({ operation: 'CHAT_DELIBERATION', sourceFilename: 'research-concept-r01.md', instruction: 'Resume el estado matemático de las bolsas de entrenamiento.' });
		const prefixed = await run.execute({ operation: 'CHAT_DELIBERATION', sourceFilename: 'proposals/research-concept-r01.md', instruction: 'Resume nuevamente el estado matemático de las bolsas de validación.' });
		assert.equal(basename.status, 'deliberated', JSON.stringify(basename));
		assert.equal(prefixed.status, 'deliberated', JSON.stringify(prefixed));
		assert.match(basename.conclusion, /estado matemático.*conjuntos finitos/i);
		assert.deepEqual(basename.authority, { scope: 'CHAT_DELIBERATION', taskDelegation: 'FORBIDDEN', documentAuthority: 'FORBIDDEN', durableState: 'FORBIDDEN', stateIdentifier: 'conversationId', explicitHandoffRequired: false });
		assert.equal(basename.mutations, 0);
		assert.equal(prefixed.mutations, 0);
		const contexts = run.tutorInputs().slice(-2);
		assert.equal(contexts.length, 2);
		for (const input of contexts) {
			const document = input.context.fragments.find((fragment) => fragment.entryId === 'chat-document:research-concept-r01.md');
			assert.ok(document, 'managed document reaches the tutor as context');
			assert.match(document.text, /bolsas de entrenamiento es informal/i);
			assert.equal(input.context.documentSha256.length, 64);
		}
		assert.deepEqual(await readFile(target), before, 'chat context leaves managed document bytes untouched');
		assert.deepEqual(await readdir(run.projectRoot), ['proposals'], 'chat loading creates no derived state, receipt, or manifest');
		assert.deepEqual(run.guardCalls, []);
	} finally { await run.dispose(); }
});

test('a fresh CHAT_DELIBERATION after extension reload still loads prefixed managed-document context read-only', async () => {
	const run = await fixture();
	try {
		await run.seed();
		const target = path.join(run.projectRoot, 'proposals/research-concept-r01.md');
		const before = await readFile(target);
		await run.reload();
		const result = await run.execute({ operation: 'CHAT_DELIBERATION', sourceFilename: 'proposals/research-concept-r01.md', instruction: 'Tras recargar, resume el estado matemático de las bolsas.' });
		assert.equal(result.status, 'deliberated', JSON.stringify(result));
		assert.deepEqual(result.authority, { scope: 'CHAT_DELIBERATION', taskDelegation: 'FORBIDDEN', documentAuthority: 'FORBIDDEN', durableState: 'FORBIDDEN', stateIdentifier: 'conversationId', explicitHandoffRequired: false });
		assert.equal(result.mutations, 0);
		const document = run.tutorInputs().at(-1).context.fragments.find((fragment) => fragment.entryId === 'chat-document:research-concept-r01.md');
		assert.ok(document, 'reloaded extension passes the managed document to the tutor');
		assert.match(document.text, /bolsas de entrenamiento es informal/i);
		assert.deepEqual(await readFile(target), before, 'reload chat leaves managed document bytes untouched');
		assert.deepEqual(await readdir(run.projectRoot), ['proposals']);
		assert.deepEqual(run.guardCalls, []);
	} finally { await run.dispose(); }
});

test('CHAT_DELIBERATION blocks invalid or unavailable document context before invoking the tutor', async () => {
	const run = await fixture();
	try {
		await run.seed();
		const invalid = [
			'/tmp/research-concept-r01.md',
			'../research-concept-r01.md',
			'proposals/../research-concept-r01.md',
			'proposals/nested/research-concept-r01.md',
			'research\\concept-r01.md',
			'notes.md',
		];
		const callsBefore = run.tutorCalls();
		for (const sourceFilename of invalid) {
			const result = await run.execute({ operation: 'CHAT_DELIBERATION', sourceFilename, instruction: 'No uses un documento inválido.' });
			assert.equal(result.status, 'blocked', JSON.stringify(result));
			assert.equal(result.message, 'CHAT_DOCUMENT_FILENAME_INVALID');
			assert.equal(result.mutations, 0);
		}
		const missing = await run.execute({ operation: 'CHAT_DELIBERATION', sourceFilename: 'proposals/research-concept-r99.md', instruction: 'No uses un documento inexistente.' });
		assert.equal(missing.status, 'blocked', JSON.stringify(missing));
		assert.equal(missing.message, 'CHAT_DOCUMENT_NOT_FOUND');
		assert.equal(run.tutorCalls(), callsBefore, 'blocked document context never falls back to incomplete tutor chat');
		assert.deepEqual(run.guardCalls, []);
	} finally { await run.dispose(); }
});

test('explicit document operations retain exact selection, guard use, ambiguity blocking, and reuse the prior chat conclusion', async () => {
	const run = await fixture();
	try {
		const chat = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Delibera sobre la definición de bolsas.' });
		await run.seed();
		const before = await readFile(path.join(run.projectRoot, 'proposals/research-concept-r01.md'));
		const ambiguous = await run.execute({ sourceFilename: 'research-concept-r01.md', conversationId: chat.conversationId, instruction: 'aplica esa conclusión a la definición de bolsas' });
		assert.equal(ambiguous.status, 'ambiguous', JSON.stringify(ambiguous));
		assert.deepEqual(await readFile(path.join(run.projectRoot, 'proposals/research-concept-r01.md')), before);
		assert.deepEqual(run.guardCalls, []);
		const state = await v2.loadDocumentState(run.projectRoot, 'research-concept-r01.md');
		const target = state.structuralIndex.entries.find((entry) => entry.type === 'paragraph' && state.documentBytes.subarray(entry.startByte, entry.endByte).toString().includes('entrenamiento'));
		assert.ok(target, 'exact training-bag target');
		assert.equal(v2.resolveTargets(state, target.entryId).length, 1, 'selected entry resolves exactly');
		const exact = await run.execute({ sourceFilename: 'research-concept-r01.md', conversationId: chat.conversationId, selectedEntryId: target.entryId, instruction: 'aplica esa conclusión a la definición de bolsas de entrenamiento' });
		assert.equal(exact.status, 'published', JSON.stringify(exact));
		assert.equal(exact.mutations, 1);
		assert.deepEqual(exact.authority, { scope: 'DOCUMENT_EDIT', taskDelegation: 'LOCAL_ONLY', documentAuthority: 'GUARDED', durableState: 'NOT_APPLICABLE', stateIdentifier: null, explicitHandoffRequired: true });
		assert.deepEqual(run.guardCalls.map((call) => call.action), ['begin_document_operation', 'preflight_plan', 'authorize_mutation', 'complete_operation']);
		const successor = await readFile(path.join(run.projectRoot, 'proposals/research-concept-r02.md'), 'utf8');
		assert.match(successor, /conjuntos finitos/i);
	} finally { await run.dispose(); }
});
