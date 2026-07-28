import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, {
	alias: {
		'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
		'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
		'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
		typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
	},
});

const domainPath = path.join(root, '.pi/extensions/paper-proposal-v2/scientific-domain.ts');
const domain = await jiti.import(domainPath);

const sharedContracts = [
	'SCIENTIFIC_WORKFLOW_OPERATION',
];

test('scientific domain exposes the canonical runtime contract discriminant', () => {
	for (const name of sharedContracts) assert.ok(name in domain, `${name} must be exported`);
	assert.equal(domain.SCIENTIFIC_WORKFLOW_OPERATION, 'SCIENTIFIC_WORKFLOW');
});

test('scientific domain keeps version and privacy metadata literals canonical', async () => {
	const source = await readFile(domainPath, 'utf8');
	assert.match(source, /version:\s*1/);
	assert.match(source, /schemaVersion:\s*1/);
	assert.match(source, /contentClass:\s*'PUBLIC_SUMMARY_ONLY'/);
	assert.match(source, /redactionVersion:\s*1/);
	assert.match(source, /ACCEPTED_UNMATERIALIZED/);
	assert.match(source, /MATERIALIZATION_COMMITTED/);
});

test('scientific implementation files have one shared contract owner', async () => {
	const directory = path.join(root, '.pi/extensions/paper-proposal-v2');
	const scientificFiles = (await readdir(directory)).filter((name) => name.startsWith('scientific-') && name !== 'scientific-domain.ts');
	for (const filename of scientificFiles) {
		const source = await readFile(path.join(directory, filename), 'utf8');
		assert.match(source, /scientific-domain\.js/, `${filename} must import the canonical domain`);
		assert.doesNotMatch(source, /(?:export\s+)?type\s+(?:ScientificThread|ScientificDecision|ScientificEvent|ThreadRelation|ThreadSynthesis|ScientificAct|ProjectEntryState)\s*=/, `${filename} must not redeclare a shared contract`);
	}
});

test('V2 barrel loads the canonical scientific domain module', async () => {
	const v2 = await jiti.import(path.join(root, '.pi/extensions/paper-proposal-v2/exports.ts'));
	assert.equal(v2.SCIENTIFIC_WORKFLOW_OPERATION, 'SCIENTIFIC_WORKFLOW');
});
