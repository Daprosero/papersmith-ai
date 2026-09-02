import { ENGINE_MODULE_ROOT } from './_engine-module-root.mjs';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const piRoot = ENGINE_MODULE_ROOT;
const aiRoot = path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(aiRoot, 'index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(path.join(root, '.claude/skills/_core/deliberation/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.join(root, '.claude/skills/_core/deliberation/engine/exports.ts'));

// Ambient-model paradigm (design `sdd/proposal-deliberation-ambient-model`, SLICE 2): the
// production real-API transport (faux-provider harness over `ctx.model`) was removed
// along with `production-tutor-adapter.ts`/`production-planner-adapter.ts`. This test
// now injects plain scripted `TutorAdapter`/`SemanticEditPlanner` doubles directly
// through the SAME seam `createProposalDeliberationExtension`'s `tutor`/`semanticPlanner`
// options and `orchestrator.ts`/`chat-deliberation.ts` already accept.
async function fixture() {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'proposal-deliberation-chat-'));
	await mkdir(path.join(projectRoot, 'proposals'));
	const guardCalls = [];
	const guard = workspace.createDocumentOperationGuard(projectRoot);
	const originalExecute = guard.execute.bind(guard);
	guard.execute = async (input, signal) => { guardCalls.push(input); return originalExecute(input, signal); };
	let tutorCalls = 0;
	const tutorInputs = [];
	const tutor = {
		assess: async (input) => {
			tutorCalls += 1;
			tutorInputs.push(input);
			if (input.context.fragments.some((fragment) => fragment.entryId === 'chat-turn-1')) assert.match(JSON.stringify(input.context.fragments), /Las bolsas deben denotarse como conjuntos finitos/i);
			return { decision: 'ACCEPT', summary: 'El estado matemático del documento indica que las bolsas deben denotarse como conjuntos finitos.', mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: [] };
		},
	};
	const semanticPlanner = {
		plan: async (input) => {
			// ADAPTED (Phase 2, D1): this planner call used to always carry the tutor's OWN prior
			// conclusion into `instruction` (via the now-retired bare-conversationId leak). The lock
			// fix means a fresh direct-document request is decoupled from any chat conversationId, so
			// only the looser "bolsas" match (true for both the retired and the current phrasing) is
			// asserted here.
			assert.match(input.instruction, /bolsas/i);
			return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: 'La definición de bolsas de entrenamiento las denota como conjuntos finitos.' }], unresolvedQuestions: [] };
		},
	};
	let tool;
	const register = () => {
		const tools = [];
		const handlers = new Map();
		workspace.createProposalDeliberationExtension({ projectRoot, operationGuard: guard, tutor, semanticPlanner })({ registerTool: (candidate) => tools.push(candidate), on: (event, handler) => handlers.set(event, handler) });
		tool = tools.find((candidate) => candidate.name === 'proposal_deliberation_execute');
		return handlers;
	};
	let handlers = register();
	const sessionIdentity = `chat-test-session-${Math.random().toString(36).slice(2)}`;
	const ctx = { sessionManager: { getSessionId: () => sessionIdentity } };
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
		async dispose() { await rm(projectRoot, { recursive: true, force: true }); },
	};
}

test('CHAT_DELIBERATION is multi-turn, bounded, non-mutating, and available without a managed proposal', async () => {
	const run = await fixture();
	try {
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

// ADAPTED (proposal-deliberation-tutor-repair, Phase 2, D1/D2/D4/D5): this test used to prove that a bare
// edit-verb follow-up reusing an OPEN chat conversationId leaked straight into a mutating
// DIRECT_DOCUMENT route and reused the tutor's prior conclusion automatically. That leak was
// exactly BUG-D1 (session-lock leak) from the logic-review audit; the design's mode-first lock
// requires this scenario to now STAY in chat until an explicit CLOSE. This test is rewritten to:
//   1) prove the lock (an edit-verb follow-up on the SAME open conversationId stays CHAT_DELIBERATION
//      and never touches the document guard);
//   2) prove explicit CLOSE_DELIBERATION exits and discards state (D2/D4);
//   3) prove reusing the SAME conversationId to continue chatting after close is reported
//      terminated, not resumed (D5);
//   4) prove the underlying document-edit mechanics (ambiguity blocking, exact selection, guard
//      sequence, guarded publish to r02) are unchanged in substance -- exercised here as an
//      ordinary fresh direct-document request with no conversationId, since the old "carry the
//      open conversation's conclusion into a bare keyword edit" path is retired by the lock itself
//      (the explicit CREATE_SUCCESSOR operation remains the honored escape hatch for continuing an
//      open deliberation into a real edit, per the design's explicit-operation carve-out).
test('an edit-verb follow-up inside an open deliberation stays locked in chat; explicit CLOSE exits and discards state; a fresh direct-document request still retains exact selection, guard use, and ambiguity blocking', async () => {
	const run = await fixture();
	try {
		const chat = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Delibera sobre la definición de bolsas.' });
		assert.equal(chat.status, 'deliberated', JSON.stringify(chat));

		// D1: a bare edit-verb follow-up on the SAME open conversationId never leaks to DIRECT_DOCUMENT.
		const stillChat = await run.execute({ conversationId: chat.conversationId, instruction: 'aplica esa conclusión a la definición de bolsas' });
		assert.equal(stillChat.routeStage, 'CHAT_DELIBERATION', JSON.stringify(stillChat));
		assert.equal(stillChat.status, 'deliberated', JSON.stringify(stillChat));
		assert.deepEqual(run.guardCalls, [], 'the locked follow-up never touches the document guard');

		// D2/D4: explicit CLOSE exits and discards in-session state.
		const closed = await run.execute({ operation: 'CLOSE_DELIBERATION', conversationId: chat.conversationId });
		assert.equal(closed.status, 'closed', JSON.stringify(closed));

		// D5: reusing the SAME conversationId to keep chatting reports the conversation terminated, not resumed.
		const reused = await run.execute({ operation: 'CHAT_DELIBERATION', conversationId: chat.conversationId, instruction: 'Sigamos con la deliberación.' });
		assert.equal(reused.status, 'blocked', JSON.stringify(reused));
		assert.equal(reused.message, 'CONVERSATION_TERMINATED');

		// A fresh direct-document request (no conversationId) still retains exact selection, guard use, and ambiguity blocking.
		await run.seed();
		const before = await readFile(path.join(run.projectRoot, 'proposals/research-concept-r01.md'));
		const ambiguous = await run.execute({ sourceFilename: 'research-concept-r01.md', instruction: 'aplica esa conclusión a la definición de bolsas' });
		assert.equal(ambiguous.status, 'ambiguous', JSON.stringify(ambiguous));
		assert.deepEqual(await readFile(path.join(run.projectRoot, 'proposals/research-concept-r01.md')), before);
		assert.deepEqual(run.guardCalls, []);
		const state = await v2.loadDocumentState(run.projectRoot, 'research-concept-r01.md');
		const target = state.structuralIndex.entries.find((entry) => entry.type === 'paragraph' && state.documentBytes.subarray(entry.startByte, entry.endByte).toString().includes('entrenamiento'));
		assert.ok(target, 'exact training-bag target');
		assert.equal(v2.resolveTargets(state, target.entryId).length, 1, 'selected entry resolves exactly');
		const exact = await run.execute({ sourceFilename: 'research-concept-r01.md', selectedEntryId: target.entryId, instruction: 'aplica esa conclusión a la definición de bolsas de entrenamiento' });
		assert.equal(exact.status, 'published', JSON.stringify(exact));
		assert.equal(exact.mutations, 1);
		assert.deepEqual(exact.authority, { scope: 'DOCUMENT_EDIT', taskDelegation: 'LOCAL_ONLY', documentAuthority: 'GUARDED', durableState: 'NOT_APPLICABLE', stateIdentifier: null, explicitHandoffRequired: true });
		assert.deepEqual(run.guardCalls.map((call) => call.action), ['begin_document_operation', 'preflight_plan', 'authorize_mutation', 'complete_operation']);
		const successor = await readFile(path.join(run.projectRoot, 'proposals/research-concept-r02.md'), 'utf8');
		assert.match(successor, /conjuntos finitos/i);
	} finally { await run.dispose(); }
});
