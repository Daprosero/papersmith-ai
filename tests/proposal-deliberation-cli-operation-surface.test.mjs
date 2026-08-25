// The CLI's accepted-operation surface, exercised through the real host.
//
// Four operations the host accepts had no coverage at this boundary at all:
// MAINTENANCE, CLOSE_DELIBERATION, WITHDRAW_REVISION and RESTORE_WITHDRAWN_REVISION,
// and CHAT_DELIBERATION appeared only incidentally, as a side condition of another
// suite's promise. Everything below drives `cli.mjs` as a subprocess, the same way a
// caller does.
//
// The first test is the one that pays for the file: it pins the accepted set itself.
// A subsystem removal previously left a stale operation name in that set, so the name
// passed validation and fell through to document routing — the exact fail-open the
// validation exists to prevent. No test noticed; a manual smoke run did.
//
// Keyless: no API key, no model call, no network. Every fixture is an mkdtemp() root,
// never the repository's own proposals/.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdir, mkdtemp, readdir, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, '.claude/skills/_core/deliberation/engine');
const cliPath = path.join(engineDir, 'cli.mjs');
const MARKER = '<!-- proposal-workspace:artifact:v1 -->\n';

/** Every operation name the host accepts. Adding or removing one is a public change and must edit this list. */
const ACCEPTED_OPERATIONS = [
	'STATUS',
	'RESOLVE_TARGET',
	'WITHDRAW_REVISION',
	'RESTORE_WITHDRAWN_REVISION',
	'CREATE_SUCCESSOR',
	'CREATE_INITIAL_REVISION',
	'CHAT_DELIBERATION',
	'CLOSE_DELIBERATION',
	'MAINTENANCE',
];

async function seed(files = { 'research-concept-r01.md': `${MARKER}# Propuesta\n\n## Método\n\nUn cuerpo estable.\n` }) {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-cli-surface-'));
	await mkdir(path.join(projectRoot, 'proposals'), { recursive: true });
	for (const [name, content] of Object.entries(files)) await writeFile(path.join(projectRoot, 'proposals', name), content, 'utf8');
	return projectRoot;
}

async function call(projectRoot, request) {
	const env = { ...process.env, PROPOSAL_DELIBERATION_PROJECT_ROOT: projectRoot };
	delete env.ANTHROPIC_API_KEY;
	const { stdout, stderr } = await execFileAsync(process.execPath, [cliPath, JSON.stringify(request)], { cwd: engineDir, env })
		.catch((error) => ({ stdout: error.stdout ?? '', stderr: error.stderr ?? String(error) }));
	try {
		return JSON.parse(stdout);
	} catch (error) {
		throw new Error(`CLI did not return JSON: ${error.message}\nstdout: ${stdout}\nstderr: ${stderr}`);
	}
}

/** The proposals directory, so a test can prove an operation wrote nothing. */
async function proposalsOf(projectRoot) {
	return (await readdir(path.join(projectRoot, 'proposals'))).sort();
}

test('the accepted-operation set is exactly the published one, and an unknown name is refused rather than routed', async () => {
	const projectRoot = await seed();

	for (const operation of ACCEPTED_OPERATIONS) {
		const result = await call(projectRoot, { operation, instruction: 'prueba' });
		assert.notEqual(
			result.message?.startsWith?.('UNKNOWN_OPERATION'),
			true,
			`${operation} is published as accepted but the host refuses it: ${JSON.stringify(result)}`,
		);
	}

	for (const operation of ['SCIENTIFIC_WORKFLOW', 'FROBNICATE', 'DELETE_EVERYTHING', 'create_successor']) {
		const result = await call(projectRoot, { operation, instruction: 'prueba' });
		assert.equal(result.status, 'error', `${operation} must not be accepted: ${JSON.stringify(result)}`);
		assert.match(result.message, /^UNKNOWN_OPERATION/, `${operation} must be refused by name, never routed as something else`);
	}

	assert.deepEqual(await proposalsOf(projectRoot), ['research-concept-r01.md'], 'probing the surface must not write anything');
});

test('MAINTENANCE permits delegation, claims no document authority, and mutates nothing', async () => {
	const projectRoot = await seed();
	const result = await call(projectRoot, { operation: 'MAINTENANCE', instruction: 'Actualiza las dependencias del repositorio.' });

	assert.equal(result.status, 'delegation_permitted', JSON.stringify(result));
	assert.equal(result.routeStage, 'MAINTENANCE');
	assert.equal(result.mutations, 0);
	assert.equal(result.authority.documentAuthority, 'FORBIDDEN', 'maintenance must never carry authority over the proposal');
	assert.equal(result.authority.taskDelegation, 'PERMITTED');
	assert.equal(result.authority.explicitHandoffRequired, true);
	assert.deepEqual(await proposalsOf(projectRoot), ['research-concept-r01.md']);
});

test('CLOSE_DELIBERATION on a conversation that was never opened answers not_open instead of failing', async () => {
	const projectRoot = await seed();
	const result = await call(projectRoot, { operation: 'CLOSE_DELIBERATION', instruction: 'Cerramos la deliberación.' });

	assert.equal(result.status, 'not_open', JSON.stringify(result));
	assert.equal(result.routeStage, 'CHAT_DELIBERATION');
	assert.equal(result.authority.documentAuthority, 'FORBIDDEN');
	assert.deepEqual(await proposalsOf(projectRoot), ['research-concept-r01.md']);
});

test('CHAT_DELIBERATION asks which base it is talking about before deliberating, and writes nothing', async () => {
	const projectRoot = await seed();
	const result = await call(projectRoot, { operation: 'CHAT_DELIBERATION', instruction: '¿Qué hipótesis conviene para la definición?' });

	assert.equal(result.status, 'base_confirmation_required', JSON.stringify(result));
	assert.equal(result.routeStage, 'CHAT_DELIBERATION');
	assert.equal(result.mutations, 0);
	assert.equal(result.receiptId, null);
	assert.equal(result.authority.durableState, 'FORBIDDEN', 'chat must not claim durable state: deliberation is session-local');
	assert.deepEqual(await proposalsOf(projectRoot), ['research-concept-r01.md']);
});

test('WITHDRAW_REVISION refuses to withdraw the only revision, naming the reason and touching nothing', async () => {
	const projectRoot = await seed();
	const result = await call(projectRoot, { operation: 'WITHDRAW_REVISION', instruction: 'Retira la revisión.', sourceFilename: 'research-concept-r01.md' });

	assert.equal(result.status, 'blocked', JSON.stringify(result));
	assert.deepEqual(result.warnings, ['BASE_REVISION_WITHDRAWAL_BLOCKED']);
	assert.equal(result.withdrawnFilename, null);
	assert.equal(result.operationId, null);
	assert.equal(result.modelCalls, 0, 'a refusal must not have cost a model call');
	assert.deepEqual(await proposalsOf(projectRoot), ['research-concept-r01.md'], 'a blocked withdrawal must leave the lineage untouched');
});

test('RESTORE_WITHDRAWN_REVISION with nothing withdrawn refuses instead of inventing a restore', async () => {
	const projectRoot = await seed();
	const result = await call(projectRoot, { operation: 'RESTORE_WITHDRAWN_REVISION', instruction: 'Restaura la revisión retirada.' });

	assert.notEqual(result.status, 'ok', JSON.stringify(result));
	assert.equal(result.restoredLatestFilename ?? null, null, 'nothing was withdrawn, so nothing may be reported as restored');
	assert.deepEqual(await proposalsOf(projectRoot), ['research-concept-r01.md']);
});

test('every accepted operation answers with one JSON object on stdout, even when it refuses', async () => {
	const projectRoot = await seed();
	for (const operation of ACCEPTED_OPERATIONS) {
		const result = await call(projectRoot, { operation, instruction: 'prueba' });
		assert.equal(typeof result, 'object', `${operation} must answer with a JSON object`);
		assert.notEqual(result, null, `${operation} must not answer null`);
		assert.ok('operation' in result || 'status' in result, `${operation} answered a shapeless object: ${JSON.stringify(result)}`);
	}
});
