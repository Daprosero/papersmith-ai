// Lever 1: amortize the engine's cold-start (jiti compiling ~63 TS files, ~0.72s)
// by resolving a CREATE_SUCCESSOR locus INSIDE the same persistent `--serve`
// process instead of spawning a separate jiti node per locus (the old SKILL.md
// recipe). This file proves `RESOLVE_TARGET`:
//   1. resolves an unambiguous locus to the exact entryId the CREATE_SUCCESSOR
//      path itself would resolve, and reports blocked+question for an
//      ambiguous one -- reusing `resolveSuccessorTarget` + `ambiguityGate`
//      unchanged;
//   2. never diverges from CREATE_SUCCESSOR's own resolution: a RESOLVE_TARGET
//      entryId fed into CREATE_SUCCESSOR + resolvedDecisions in the SAME
//      `--serve` session applies successfully (no WRONG_TARGET_ENTRY_ID);
//   3. needs no ANTHROPIC_API_KEY, makes no mutation, and no model call.
//
// No proposal `.md` file is ever created in the repository -- the CLI targets
// a mkdtemp() temp project root via PAPER_PROPOSAL_PROJECT_ROOT, exactly like
// the existing ambient-model keyless CLI coverage.
import assert from 'node:assert/strict';
import { execFile, spawn } from 'node:child_process';
import { mkdir, mkdtemp } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import { pathToFileURL } from 'node:url';

const execFileAsync = promisify(execFile);

const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, '.claude/skills/paper-proposal/engine');
const cliPath = path.join(engineDir, 'cli.mjs');

const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspaceModule = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));

const SOURCE = [
	'# 1 Intro',
	'',
	'Keep prefix exactly.',
	'',
	'# 2 Kappa Prime',
	'',
	'Body Kappa Prime.',
	'',
	'# 3 Kappa Second',
	'',
	'Body Kappa Second.',
	'',
	'# 4 Zeta',
	'',
	'Keep suffix exactly.',
	'',
].join('\n');

async function seedProjectRoot(content) {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-serve-resolve-'));
	await mkdir(path.join(projectRoot, 'proposals'), { recursive: true });
	await workspaceModule.createProposalWorkspaceTool(projectRoot).execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content });
	return projectRoot;
}

function keylessEnv(projectRoot, sessionId) {
	const env = { ...process.env, PAPER_PROPOSAL_PROJECT_ROOT: projectRoot, PAPER_PROPOSAL_SESSION_ID: sessionId };
	delete env.ANTHROPIC_API_KEY;
	return env;
}

function createServeSession(projectRoot, sessionId) {
	const child = spawn(process.execPath, [cliPath, '--serve'], { cwd: engineDir, env: keylessEnv(projectRoot, sessionId), stdio: ['pipe', 'pipe', 'pipe'] });
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
	return { child, lines, getStderr: () => stderr };
}

async function waitForLine(lines, index, timeoutMs = 10_000) {
	const start = Date.now();
	while (lines.length <= index) {
		if (Date.now() - start > timeoutMs) throw new Error(`timed out waiting for CLI --serve response line ${index}`);
		await new Promise((resolve) => setTimeout(resolve, 25));
	}
	return lines[index];
}

test('RESOLVE_TARGET one-shot (no ANTHROPIC_API_KEY) resolves an unambiguous locus to a concrete entryId', async () => {
	const projectRoot = await seedProjectRoot(SOURCE);
	const request = { operation: 'RESOLVE_TARGET', sourceFilename: 'research-concept-r01.md', query: 'sección Zeta' };
	const { stdout, stderr } = await execFileAsync(process.execPath, [cliPath, JSON.stringify(request)], {
		cwd: engineDir,
		env: keylessEnv(projectRoot, 'resolve-oneshot'),
	});
	const result = JSON.parse(stdout);
	assert.equal(result.blocked, false, `${JSON.stringify(result)}\nstderr: ${stderr}`);
	assert.ok(result.entryId, 'a resolved, unambiguous locus must return a concrete entryId');
	assert.equal(result.question, null);
});

test('RESOLVE_TARGET reports blocked + question for an ambiguous locus, exactly like ambiguityGate', async () => {
	const projectRoot = await seedProjectRoot(SOURCE);
	const request = { operation: 'RESOLVE_TARGET', sourceFilename: 'research-concept-r01.md', query: 'sección Kappa' };
	const { stdout, stderr } = await execFileAsync(process.execPath, [cliPath, JSON.stringify(request)], {
		cwd: engineDir,
		env: keylessEnv(projectRoot, 'resolve-oneshot-ambiguous'),
	});
	const result = JSON.parse(stdout);
	assert.equal(result.blocked, true, `${JSON.stringify(result)}\nstderr: ${stderr}`);
	assert.ok(result.question, 'an ambiguous locus must carry a disambiguating question');
	assert.equal(result.entryId, null);
});

test('RESOLVE_TARGET supports a `queries` array, resolving each independently in one call', async () => {
	const projectRoot = await seedProjectRoot(SOURCE);
	const request = {
		operation: 'RESOLVE_TARGET',
		sourceFilename: 'research-concept-r01.md',
		queries: [{ query: 'sección Zeta' }, { query: 'sección Kappa' }],
	};
	const { stdout, stderr } = await execFileAsync(process.execPath, [cliPath, JSON.stringify(request)], {
		cwd: engineDir,
		env: keylessEnv(projectRoot, 'resolve-oneshot-batch'),
	});
	const result = JSON.parse(stdout);
	assert.equal(result.results.length, 2, `${JSON.stringify(result)}\nstderr: ${stderr}`);
	assert.equal(result.results[0].blocked, false);
	assert.ok(result.results[0].entryId);
	assert.equal(result.results[1].blocked, true);
	assert.ok(result.results[1].question);
});

test('RESOLVE_TARGET then CREATE_SUCCESSOR + resolvedDecisions in the SAME --serve session applies successfully (no divergence)', async () => {
	const projectRoot = await seedProjectRoot(SOURCE);
	const session = createServeSession(projectRoot, 'resolve-then-create-successor');
	try {
		session.child.stdin.write(`${JSON.stringify({ operation: 'RESOLVE_TARGET', sourceFilename: 'research-concept-r01.md', query: 'sección Zeta' })}\n`);
		const resolved = await waitForLine(session.lines, 0);
		assert.equal(resolved.blocked, false, `${JSON.stringify(resolved)}\n${session.getStderr()}`);
		assert.ok(resolved.entryId);

		const replacement = '# 4 Zeta Revised\n\nNew zeta body via RESOLVE_TARGET-derived entryId.\n\n';
		const previewRequest = {
			operation: 'CREATE_SUCCESSOR',
			sourceFilename: 'research-concept-r01.md',
			instruction: 'Reescribe la sección Zeta.',
			selectedEntryId: 'sección Zeta',
			resolvedDecisions: [{ kind: 'replace', targetEntryId: resolved.entryId, replacementText: replacement }],
		};
		session.child.stdin.write(`${JSON.stringify(previewRequest)}\n`);
		const preview = await waitForLine(session.lines, 1);
		assert.equal(preview.status, 'awaiting_acceptance', `${JSON.stringify(preview)}\n${session.getStderr()}`);
		assert.ok(preview.acceptanceToken);

		const acceptRequest = { ...previewRequest, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken };
		session.child.stdin.write(`${JSON.stringify(acceptRequest)}\n`);
		const published = await waitForLine(session.lines, 2);
		assert.equal(published.status, 'published', `${JSON.stringify(published)}\n${session.getStderr()}`);
	} finally {
		session.child.stdin.end();
		session.child.kill();
	}
});

test('RESOLVE_TARGET makes no mutation: no proposals/ file is created or changed by a resolve-only call', async () => {
	const projectRoot = await seedProjectRoot(SOURCE);
	const before = await (await import('node:fs/promises')).readdir(path.join(projectRoot, 'proposals'));
	const request = { operation: 'RESOLVE_TARGET', sourceFilename: 'research-concept-r01.md', query: 'sección Zeta' };
	await execFileAsync(process.execPath, [cliPath, JSON.stringify(request)], {
		cwd: engineDir,
		env: keylessEnv(projectRoot, 'resolve-no-mutation'),
	});
	const after = await (await import('node:fs/promises')).readdir(path.join(projectRoot, 'proposals'));
	assert.deepEqual([...before].sort(), [...after].sort(), 'RESOLVE_TARGET must never add/remove a proposals/ document');
});
