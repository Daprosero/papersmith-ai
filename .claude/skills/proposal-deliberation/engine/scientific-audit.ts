import { lstat, readdir, readFile, realpath } from 'node:fs/promises';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { ScientificStateStore, ScientificStateStoreError, type ScientificState } from './scientific-state-store.js';
import type { ScientificAuditStatus } from './scientific-domain.js';

const MANAGED = /^research-concept-(?:[a-z0-9]+(?:-[a-z0-9]+)*-)?r\d{2,}\.md$/;

export type ScientificAuditCheck = {
	id: string;
	status: ScientificAuditStatus;
	category: 'scientific-persistence';
	evidence: Record<string, unknown>;
	details: string;
};

export type ScientificAuditResult = {
	status: ScientificAuditStatus;
	checks: ScientificAuditCheck[];
	failures: string[];
	warnings: string[];
	summary: { passed: number; warned: number; failed: number; notRun: number };
};

const sha256 = (value: string | Buffer) => createHash('sha256').update(value).digest('hex');
const errorCode = (error: unknown) => error instanceof ScientificStateStoreError ? error.code : error instanceof Error ? error.message : String(error);

async function activeRevisionHashes(root: string): Promise<Map<string, string>> {
	const proposals = join(root, 'proposals');
	let names: string[];
	try { names = await readdir(proposals); } catch { return new Map(); }
	const revisions = new Map<string, string>();
	for (const name of names.filter((entry) => MANAGED.test(entry))) {
		const path = join(proposals, name);
		const info = await lstat(path).catch(() => undefined);
		if (!info?.isFile() || info.isSymbolicLink()) throw new ScientificStateStoreError('SCIENTIFIC_REVISION_EVIDENCE_UNSAFE');
		revisions.set(name, sha256(await readFile(path)));
	}
	return revisions;
}

function validateRevisionBindings(state: ScientificState, revisions: Map<string, string>): string[] {
	const failures: string[] = [];
	for (const thread of state.snapshot.threads) {
		if (!thread.revisionEvidence) continue;
		const observed = revisions.get(thread.revisionEvidence.filename);
		if (!observed || observed !== thread.revisionEvidence.documentSha256) failures.push(`SCIENTIFIC_REVISION_EVIDENCE_STALE:${thread.threadId}`);
	}
	return failures;
}

export async function runScientificConsistencyAudit(input: { projectRoot: string; store?: ScientificStateStore }): Promise<ScientificAuditResult> {
	const failures: string[] = [];
	const warnings: string[] = [];
	let state: ScientificState | undefined;
	let root: string;
	try {
		root = await realpath(input.projectRoot);
		state = await (input.store ?? new ScientificStateStore(root)).read();
	} catch (error) {
		failures.push(errorCode(error));
		root = input.projectRoot;
	}

	if (failures.length > 0) {
		return {
			status: 'FAIL',
			checks: [{ id: 'scientific-authoritative-state', status: 'FAIL', category: 'scientific-persistence', evidence: { failures }, details: failures.join(', ') }],
			failures,
			warnings,
			summary: { passed: 0, warned: 0, failed: 1, notRun: 0 },
		};
	}
	if (!state) {
		return {
			status: 'NOT_RUN',
			checks: [{ id: 'scientific-authoritative-state', status: 'NOT_RUN', category: 'scientific-persistence', evidence: { state: 'absent' }, details: 'No authoritative scientific state is present.' }],
			failures,
			warnings,
			summary: { passed: 0, warned: 0, failed: 0, notRun: 1 },
		};
	}

	try {
		failures.push(...validateRevisionBindings(state, await activeRevisionHashes(root)));
	} catch (error) {
		failures.push(errorCode(error));
	}
	const status = failures.length > 0 ? 'FAIL' : warnings.length > 0 ? 'WARN' : 'PASS';
	return {
		status,
		checks: [{
			id: 'scientific-authoritative-state',
			status,
			category: 'scientific-persistence',
			evidence: { eventCount: state.events.length, threadCount: state.snapshot.threads.length, relationCount: state.snapshot.relations.length, decisionCount: state.snapshot.decisions.length, activeThreadId: state.snapshot.activeThreadId },
			details: failures.concat(warnings).join(', '),
		}],
		failures,
		warnings,
		summary: { passed: status === 'PASS' ? 1 : 0, warned: status === 'WARN' ? 1 : 0, failed: status === 'FAIL' ? 1 : 0, notRun: 0 },
	};
}
