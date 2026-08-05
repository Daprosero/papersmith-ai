// Design `sdd/proposal-deliberation-base-reconciliation`: a deterministic, read-only
// `STATUS` operation on the ambient-model proposal-deliberation CLI host. It gives
// the ambient agent the ground truth of `proposals/` (which files are
// managed, which is the latest, which are ambiguous/tied, which files are
// unmanaged) instead of the agent eyeballing the directory before running the
// SKILL.md base-resolution decision tree.
//
// STATUS reuses the SAME `parseManagedRevisionFilename` / canonical
// `resolveLatestManagedRevision` recognition and tie-break rule the real
// engine operations (CREATE_SUCCESSOR's orchestrator, withdrawal) use --
// there is deliberately no separate/divergent regex or tie-break here.
//
// STATUS needs no ANTHROPIC_API_KEY, makes no model call, and never mutates
// `proposals/` -- every seeded fixture lives in a mkdtemp() temp project
// root, never in the repository's own `proposals/` directory.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdir, mkdtemp, readdir, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, '.claude/skills/proposal-deliberation/engine');
const cliPath = path.join(engineDir, 'cli.mjs');

const MARKER = '<!-- proposal-workspace:artifact:v1 -->\n';

function managedBody(label) {
	return `${MARKER}# ${label}\n\nBody for ${label}.\n`;
}

async function seedProposals(files) {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-status-'));
	const proposalsDir = path.join(projectRoot, 'proposals');
	await mkdir(proposalsDir, { recursive: true });
	for (const [filename, content] of Object.entries(files)) {
		await writeFile(path.join(proposalsDir, filename), content, 'utf8');
	}
	return projectRoot;
}

function keylessEnv(projectRoot) {
	const env = { ...process.env, PROPOSAL_DELIBERATION_PROJECT_ROOT: projectRoot };
	delete env.ANTHROPIC_API_KEY;
	return env;
}

async function callStatus(projectRoot, sourceFilename) {
	const request = sourceFilename === undefined ? { operation: 'STATUS' } : { operation: 'STATUS', sourceFilename };
	const { stdout, stderr } = await execFileAsync(process.execPath, [cliPath, JSON.stringify(request)], {
		cwd: engineDir,
		env: keylessEnv(projectRoot),
	});
	try {
		return JSON.parse(stdout);
	} catch (error) {
		throw new Error(`STATUS did not return JSON: ${error.message}\nstdout: ${stdout}\nstderr: ${stderr}`);
	}
}

test('STATUS on an empty proposals/ (only .gitkeep) reports no managed revisions and no latest', async () => {
	const projectRoot = await seedProposals({ '.gitkeep': '' });
	const result = await callStatus(projectRoot);
	assert.equal(result.status, 'ok');
	assert.equal(result.operation, 'STATUS');
	assert.deepEqual(result.managedRevisions, []);
	assert.equal(result.latest, null);
	assert.equal(result.multipleActive, false);
	assert.deepEqual(result.candidates, []);
	assert.deepEqual(result.nonManagedFiles, []);
});

test('STATUS lists every managed revision with lineage/revisionNumber/isLatest, sorted by revisionNumber then filename', async () => {
	const projectRoot = await seedProposals({
		'research-concept-r01.md': managedBody('r01'),
		'research-concept-r03.md': managedBody('r03'),
		'research-concept-r02.md': managedBody('r02'),
	});
	const result = await callStatus(projectRoot);
	assert.deepEqual(result.managedRevisions, [
		{ filename: 'research-concept-r01.md', lineage: 'ROOT', revisionNumber: 1, isLatest: false },
		{ filename: 'research-concept-r02.md', lineage: 'ROOT', revisionNumber: 2, isLatest: false },
		{ filename: 'research-concept-r03.md', lineage: 'ROOT', revisionNumber: 3, isLatest: true },
	]);
	assert.equal(result.latest, 'research-concept-r03.md');
	assert.equal(result.multipleActive, false);
});

test('STATUS recognizes lineage from a slugged managed filename', async () => {
	const projectRoot = await seedProposals({
		'research-concept-my-idea-r01.md': managedBody('lineage r01'),
	});
	const result = await callStatus(projectRoot);
	assert.deepEqual(result.managedRevisions, [
		{ filename: 'research-concept-my-idea-r01.md', lineage: 'my-idea', revisionNumber: 1, isLatest: true },
	]);
	assert.equal(result.latest, 'research-concept-my-idea-r01.md');
});

test('STATUS excludes .gitkeep, .DS_Store, and dotfiles from nonManagedFiles, but lists real unmanaged files', async () => {
	const projectRoot = await seedProposals({
		'.gitkeep': '',
		'.DS_Store': 'binary-ish',
		'.hidden-note.md': 'hidden',
		'draft-notes.md': '# Draft\n\nSome unmanaged notes.\n',
		'outline.txt': 'plain outline',
	});
	const result = await callStatus(projectRoot);
	assert.deepEqual(result.nonManagedFiles, ['draft-notes.md', 'outline.txt']);
	assert.deepEqual(result.managedRevisions, []);
});

test('STATUS classifies a managed-shaped filename missing the MARKER bytes as nonManagedFiles, not managedRevisions', async () => {
	const projectRoot = await seedProposals({
		'research-concept-r01.md': '# No marker here\n\nThis looks managed by name only.\n',
	});
	const result = await callStatus(projectRoot);
	assert.deepEqual(result.managedRevisions, []);
	assert.deepEqual(result.nonManagedFiles, ['research-concept-r01.md']);
	assert.equal(result.latest, null);
});

test('STATUS reports multipleActive + tied candidates when two lineages tie at the same highest revisionNumber', async () => {
	const projectRoot = await seedProposals({
		'research-concept-r03.md': managedBody('root r03'),
		'research-concept-alt-r03.md': managedBody('alt r03'),
		'research-concept-r02.md': managedBody('root r02'),
	});
	const result = await callStatus(projectRoot);
	assert.equal(result.multipleActive, true);
	assert.deepEqual(result.candidates, ['research-concept-alt-r03.md', 'research-concept-r03.md']);
	assert.ok(result.candidates.includes(result.latest));
});

test('STATUS sourceClassification LATEST for the current latest managed revision', async () => {
	const projectRoot = await seedProposals({
		'research-concept-r01.md': managedBody('r01'),
		'research-concept-r02.md': managedBody('r02'),
	});
	const result = await callStatus(projectRoot, 'research-concept-r02.md');
	assert.equal(result.sourceClassification, 'LATEST');
	assert.equal(result.newerRevisionNumbers, undefined);
});

test('STATUS sourceClassification OLDER_MANAGED reports the newer revisionNumbers that exist in the same lineage', async () => {
	const projectRoot = await seedProposals({
		'research-concept-r01.md': managedBody('r01'),
		'research-concept-r02.md': managedBody('r02'),
		'research-concept-r03.md': managedBody('r03'),
	});
	const result = await callStatus(projectRoot, 'research-concept-r01.md');
	assert.equal(result.sourceClassification, 'OLDER_MANAGED');
	assert.deepEqual(result.newerRevisionNumbers, [2, 3]);
});

test('STATUS sourceClassification UNMANAGED for a real file that does not match the managed marker+pattern', async () => {
	const projectRoot = await seedProposals({
		'draft-notes.md': '# Draft\n\nUnmanaged base candidate.\n',
	});
	const result = await callStatus(projectRoot, 'draft-notes.md');
	assert.equal(result.sourceClassification, 'UNMANAGED');
});

test('STATUS sourceClassification NOT_FOUND for a filename absent from proposals/', async () => {
	const projectRoot = await seedProposals({
		'research-concept-r01.md': managedBody('r01'),
	});
	const result = await callStatus(projectRoot, 'research-concept-r99.md');
	assert.equal(result.sourceClassification, 'NOT_FOUND');
});

test('STATUS sourceClassification NOT_FOUND for a path-traversal-shaped sourceFilename (never a real basename match)', async () => {
	const projectRoot = await seedProposals({
		'research-concept-r01.md': managedBody('r01'),
	});
	const result = await callStatus(projectRoot, '../outside.md');
	assert.equal(result.sourceClassification, 'NOT_FOUND');
});

test('STATUS needs no ANTHROPIC_API_KEY', async () => {
	const projectRoot = await seedProposals({ 'research-concept-r01.md': managedBody('r01') });
	const env = keylessEnv(projectRoot);
	assert.equal(env.ANTHROPIC_API_KEY, undefined);
	const { stdout } = await execFileAsync(process.execPath, [cliPath, JSON.stringify({ operation: 'STATUS' })], { cwd: engineDir, env });
	const result = JSON.parse(stdout);
	assert.equal(result.status, 'ok');
});

test('STATUS never mutates proposals/', async () => {
	const projectRoot = await seedProposals({
		'research-concept-r01.md': managedBody('r01'),
		'draft-notes.md': '# Draft\n\nUnmanaged.\n',
	});
	const before = (await readdir(path.join(projectRoot, 'proposals'))).sort();
	await callStatus(projectRoot, 'research-concept-r01.md');
	const after = (await readdir(path.join(projectRoot, 'proposals'))).sort();
	assert.deepEqual(before, after, 'STATUS must never add/remove/modify a proposals/ file');
});
