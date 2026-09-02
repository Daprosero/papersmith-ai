import { ENGINE_MODULE_ROOT } from './_engine-module-root.mjs';
// Keyless CLI invocation coverage (design `sdd/proposal-deliberation-ambient-model`, SLICE 1
// item 3): CREATE_SUCCESSOR + resolvedDecisions must be invokable through the real
// `node cli.mjs '<json>'` entry point WITHOUT ANTHROPIC_API_KEY, because the
// ambient-supplied-planner never calls `ProductionModelRuntime.structured()`
// (the only place `ctx.modelRegistry.getApiKeyAndHeaders` is ever consulted).
//
// No proposal `.md` file is ever created in the repository -- the CLI targets a
// mkdtemp() temp project root via PROPOSAL_DELIBERATION_PROJECT_ROOT.
import assert from 'node:assert/strict';
import { execFile, spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import { pathToFileURL } from 'node:url';

const execFileAsync = promisify(execFile);

const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, '.claude/skills/_core/deliberation/engine');
const cliPath = path.join(engineDir, 'cli.mjs');

const piRoot = ENGINE_MODULE_ROOT;
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspaceModule = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));
const v2 = await jiti.import(path.join(engineDir, 'exports.ts'));

async function seedProjectRoot(content) {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-ambient-cli-'));
	await mkdir(path.join(projectRoot, 'proposals'), { recursive: true });
	await workspaceModule.createProposalWorkspaceTool(projectRoot).execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content });
	return projectRoot;
}

async function resolveLocusEntryId(projectRoot, filename, query) {
	const state = await v2.loadDocumentState(projectRoot, filename);
	const resolution = v2.resolveSuccessorTarget(state, query);
	const gate = v2.ambiguityGate(resolution.candidates);
	assert.ok(gate.candidate, `resolution must not be ambiguous for query: ${query}`);
	return gate.candidate.entryId;
}

function keylessEnv(projectRoot, sessionId) {
	const env = { ...process.env, PROPOSAL_DELIBERATION_PROJECT_ROOT: projectRoot, PROPOSAL_DELIBERATION_SESSION_ID: sessionId };
	delete env.ANTHROPIC_API_KEY;
	return env;
}

test('CLI keyless invocation: one-shot `node cli.mjs \'<json>\'` previews a CREATE_SUCCESSOR + resolvedDecisions request with NO ANTHROPIC_API_KEY set', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Tail\n\nKeep suffix exactly.\n';
	const projectRoot = await seedProjectRoot(source);
	const alphaEntryId = await resolveLocusEntryId(projectRoot, 'research-concept-r01.md', 'sección Alpha');
	const replacement = '# 2 Alpha Revised\n\nNew alpha body via the ambient CLI path.\n\n';
	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Modifica la sección Alpha.',
		selectedEntryId: 'sección Alpha',
		resolvedDecisions: [{ kind: 'replace', targetEntryId: alphaEntryId, replacementText: replacement }],
	};

	// The exact one-shot invocation form from cli.mjs's own usage comment:
	//   node cli.mjs '<json-request>'
	const { stdout, stderr } = await execFileAsync(process.execPath, [cliPath, JSON.stringify(request)], {
		cwd: engineDir,
		env: keylessEnv(projectRoot, 'ambient-cli-oneshot'),
	});
	const result = JSON.parse(stdout);
	assert.equal(result.status, 'awaiting_acceptance', `${JSON.stringify(result)}\nstderr: ${stderr}`);
	assert.equal(result.reason, undefined, 'no MODEL_AUTH_REQUIRED/model error -- the ambient path never calls the model runtime');
	assert.ok(result.acceptanceToken);
	assert.equal(result.patchCount, 1);
});

test('CLI keyless invocation: preview + accept in the SAME `--serve` session publishes a real successor, byte-preserving, with no ANTHROPIC_API_KEY set', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Tail\n\nKeep suffix exactly.\n';
	const projectRoot = await seedProjectRoot(source);
	const alphaEntryId = await resolveLocusEntryId(projectRoot, 'research-concept-r01.md', 'sección Alpha');
	const replacement = '# 2 Alpha Revised\n\nNew alpha body via the ambient CLI path.\n\n';
	const previewRequest = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Modifica la sección Alpha.',
		selectedEntryId: 'sección Alpha',
		resolvedDecisions: [{ kind: 'replace', targetEntryId: alphaEntryId, replacementText: replacement }],
	};

	// Two-phase consent gate (unchanged): the acceptanceToken is only known from
	// the FIRST response, so this drives one long-lived `--serve` process with a
	// manual NDJSON line protocol -- the exact multi-turn contract cli.mjs's own
	// usage comment documents for keeping in-memory session state across turns.
	const child = spawn(process.execPath, [cliPath, '--serve'], { cwd: engineDir, env: keylessEnv(projectRoot, 'ambient-cli-same-session'), stdio: ['pipe', 'pipe', 'pipe'] });
	const lines = [];
	let buffer = '';
	child.stdout.on('data', (chunk) => {
		buffer += chunk.toString('utf8');
		let index;
		while ((index = buffer.indexOf('\n')) !== -1) {
			const line = buffer.slice(0, index).trim();
			buffer = buffer.slice(index + 1);
			if (line) lines.push(JSON.parse(line));
		}
	});
	let stderr = '';
	child.stderr.on('data', (chunk) => { stderr += chunk.toString('utf8'); });

	try {
		child.stdin.write(`${JSON.stringify(previewRequest)}\n`);
		const preview = await waitForLine(lines, 0);
		assert.equal(preview.status, 'awaiting_acceptance', `${JSON.stringify(preview)}\n${stderr}`);

		const acceptRequest = { ...previewRequest, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken };
		child.stdin.write(`${JSON.stringify(acceptRequest)}\n`);
		const published = await waitForLine(lines, 1);
		assert.equal(published.status, 'published', `${JSON.stringify(published)}\n${stderr}`);

		const body = await readFile(path.join(projectRoot, 'proposals/research-concept-r02.md'), 'utf8');
		assert.ok(body.includes('New alpha body via the ambient CLI path.'));
		assert.ok(body.includes('Keep prefix exactly.'), 'untouched prefix preserved byte-for-byte');
		assert.ok(body.includes('Keep suffix exactly.'), 'untouched suffix preserved byte-for-byte');
		assert.equal(body.includes('Old alpha body.'), false);
	} finally {
		child.stdin.end();
		child.kill();
	}
});

async function waitForLine(lines, index, timeoutMs = 10_000) {
	const start = Date.now();
	while (lines.length <= index) {
		if (Date.now() - start > timeoutMs) throw new Error(`timed out waiting for CLI --serve response line ${index}`);
		await new Promise((resolve) => setTimeout(resolve, 25));
	}
	return lines[index];
}
