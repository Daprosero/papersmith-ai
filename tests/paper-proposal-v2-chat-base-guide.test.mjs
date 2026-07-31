import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
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
	'@earendil-works/pi-ai/compat': path.join(root, '.claude/skills/paper-proposal/engine/_pi-compat/pi-ai-compat.ts'),
	'@earendil-works/pi-ai': path.join(aiRoot, 'index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/proposal-workspace.ts'));
const aiCompat = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/_pi-compat/pi-ai-compat.ts'));

const MARKER = '<!-- proposal-workspace:artifact:v1 -->\n';

function payload(context) {
	return JSON.parse(context.messages.at(-1).content.find((part) => part.type === 'text').text);
}

async function writeManagedProposal(projectRoot, filename, body) {
	await writeFile(path.join(projectRoot, 'proposals', filename), MARKER + body);
}

async function writeGuideFile(projectRoot, filename, content) {
	const directory = path.join(projectRoot, 'guidance', 'paper-guide', 'normalized');
	await mkdir(directory, { recursive: true });
	await writeFile(path.join(directory, filename), content);
}

async function fixture() {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-chat-base-guide-'));
	await mkdir(path.join(projectRoot, 'proposals'));
	const guard = workspace.createDocumentOperationGuard(projectRoot);
	const providerId = `paper-proposal-base-guide-${Date.now()}-${Math.random()}`;
	const faux = aiCompat.registerFauxProvider({ api: providerId, provider: providerId, models: [{ id: `${providerId}-model`, input: ['text'], contextWindow: 32000, maxTokens: 4096 }] });
	let tutorCalls = 0;
	const tutorInputs = [];
	faux.setResponses(Array.from({ length: 8 }, () => (context) => {
		const input = payload(context);
		tutorCalls += 1;
		tutorInputs.push(input);
		return aiCompat.fauxAssistantMessage(JSON.stringify({ decision: 'ACCEPT', summary: 'El estado matemático del documento es consistente.', mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: [] }));
	}));
	const tools = [];
	workspace.createPaperProposalExtension({ projectRoot, operationGuard: guard })({ registerTool: (candidate) => tools.push(candidate), on: () => {} });
	const tool = tools.find((candidate) => candidate.name === 'paper_proposal_execute');
	const sessionIdentity = `chat-base-guide-session-${Math.random().toString(36).slice(2)}`;
	const ctx = { model: faux.getModel(), sessionManager: { getSessionId: () => sessionIdentity }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'fake', headers: {}, env: {} }) } };
	return {
		projectRoot, tutorCalls: () => tutorCalls, tutorInputs: () => tutorInputs,
		execute: async (params) => (await tool.execute('chat-base-guide', params, undefined, undefined, ctx)).details,
		async dispose() { faux.unregister?.(); await rm(projectRoot, { recursive: true, force: true }); },
	};
}

test('a new deliberation with an existing unambiguous managed proposal and no override requires base confirmation before the tutor runs', async () => {
	const run = await fixture();
	try {
		await writeManagedProposal(run.projectRoot, 'research-concept-r01.md', '# Base\n\nLa definición de bolsas es informal.\n');
		const result = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Delibera sobre la definición de bolsas.' });
		assert.equal(result.status, 'base_confirmation_required', JSON.stringify(result));
		assert.equal(result.proposedBase, 'research-concept-r01.md');
		assert.equal(result.nextAction, 'confirm_or_override_base');
		assert.equal(run.tutorCalls(), 0, 'no tutor call is spent before the base is confirmed');
	} finally { await run.dispose(); }
});

test('confirming the proposed base with confirmBase:true proceeds using that revision as document context (spec I4 scenario: confirm proposed base)', async () => {
	const run = await fixture();
	try {
		await writeManagedProposal(run.projectRoot, 'research-concept-r01.md', '# Base\n\nLa definición de bolsas es informal.\n');
		const proposal = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Delibera sobre la definición de bolsas.' });
		assert.equal(proposal.status, 'base_confirmation_required');
		const confirmed = await run.execute({ operation: 'CHAT_DELIBERATION', confirmBase: true, instruction: 'Delibera sobre la definición de bolsas.' });
		assert.equal(confirmed.status, 'deliberated', JSON.stringify(confirmed));
		assert.ok(confirmed.conversationId);
		const document = run.tutorInputs().at(-1).context.fragments.find((fragment) => fragment.entryId === 'chat-document:research-concept-r01.md');
		assert.ok(document, 'the confirmed base reaches the tutor as document context');
		assert.match(document.text, /bolsas es informal/i);
	} finally { await run.dispose(); }
});

test('multiple active revisions surface a MULTIPLE_ACTIVE_REVISIONS warning listing every candidate; a caller-supplied sourceFilename override selects the base (spec I4 scenario: multiplicity warned, override accepted)', async () => {
	const run = await fixture();
	try {
		await writeManagedProposal(run.projectRoot, 'research-concept-r01.md', '# Concept A\n\nLa definición de bolsas A es informal.\n');
		await writeManagedProposal(run.projectRoot, 'research-concept-idea-b-r01.md', '# Concept B\n\nLa definición de bolsas B es informal.\n');
		const proposal = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Delibera sobre la definición de bolsas.' });
		assert.equal(proposal.status, 'base_confirmation_required', JSON.stringify(proposal));
		assert.deepEqual(proposal.warnings, ['MULTIPLE_ACTIVE_REVISIONS']);
		assert.deepEqual(proposal.candidates.sort(), ['research-concept-idea-b-r01.md', 'research-concept-r01.md']);
		assert.equal(run.tutorCalls(), 0);
		const overridden = await run.execute({ operation: 'CHAT_DELIBERATION', sourceFilename: 'research-concept-idea-b-r01.md', instruction: 'Delibera sobre la definición de bolsas B.' });
		assert.equal(overridden.status, 'deliberated', JSON.stringify(overridden));
		const document = run.tutorInputs().at(-1).context.fragments.find((fragment) => fragment.entryId === 'chat-document:research-concept-idea-b-r01.md');
		assert.ok(document, 'the caller-overridden candidate reaches the tutor as document context');
	} finally { await run.dispose(); }
});

test('an already-open conversation never re-asks for base confirmation on its second turn', async () => {
	const run = await fixture();
	try {
		await writeManagedProposal(run.projectRoot, 'research-concept-r01.md', '# Base\n\nLa definición de bolsas es informal.\n');
		const confirmed = await run.execute({ operation: 'CHAT_DELIBERATION', confirmBase: true, instruction: 'Delibera sobre la definición de bolsas.' });
		assert.equal(confirmed.status, 'deliberated', JSON.stringify(confirmed));
		const second = await run.execute({ operation: 'CHAT_DELIBERATION', conversationId: confirmed.conversationId, instruction: 'Sigamos discutiendo la misma definición.' });
		assert.equal(second.status, 'deliberated', JSON.stringify(second));
		assert.equal(second.context.turnCount, 2);
	} finally { await run.dispose(); }
});

test('a project with no managed proposal at all proceeds without any base-confirmation gate (nothing to confirm)', async () => {
	const run = await fixture();
	try {
		const result = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Delibera sin propuesta gestionada.' });
		assert.equal(result.status, 'deliberated', JSON.stringify(result));
	} finally { await run.dispose(); }
});

test('the paper-guide is loaded once at deliberation open and never reloaded on a later turn (task 3.5/3.6, spec I2)', async () => {
	const run = await fixture();
	try {
		await writeGuideFile(run.projectRoot, 'method-guide.md', 'Distinctive paper-guide reference content ZQX-7.');
		const first = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Delibera sin propuesta gestionada.' });
		assert.equal(first.status, 'deliberated', JSON.stringify(first));
		const firstGuideFragment = run.tutorInputs().at(-1).context.fragments.find((fragment) => fragment.entryId.startsWith('paper-guide:'));
		assert.ok(firstGuideFragment, 'the guide is present as initial context on the first turn');
		assert.match(firstGuideFragment.text, /ZQX-7/);

		const second = await run.execute({ operation: 'CHAT_DELIBERATION', conversationId: first.conversationId, instruction: 'Continuemos la deliberación.' });
		assert.equal(second.status, 'deliberated', JSON.stringify(second));
		const secondGuideFragment = run.tutorInputs().at(-1).context.fragments.find((fragment) => fragment.entryId.startsWith('paper-guide:'));
		assert.equal(secondGuideFragment, undefined, 'the guide is never reloaded on a later turn of the same conversation');
	} finally { await run.dispose(); }
});

test('a project with no paper-guide directory proceeds without a guide fragment and without throwing', async () => {
	const run = await fixture();
	try {
		const result = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Delibera sin guía disponible.' });
		assert.equal(result.status, 'deliberated', JSON.stringify(result));
		const guideFragment = run.tutorInputs().at(-1).context.fragments.find((fragment) => fragment.entryId.startsWith('paper-guide:'));
		assert.equal(guideFragment, undefined);
	} finally { await run.dispose(); }
});
