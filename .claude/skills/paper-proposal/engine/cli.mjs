#!/usr/bin/env node
// Native Claude Code host for the paper-proposal engine.
//
// Ambient-model paradigm (design `sdd/paper-proposal-ambient-model`): this host
// is keyless. It builds the extension, registers `paper_proposal_execute`, and
// invokes it with a runtime context — the ambient model calling this CLI IS the
// tutor/reviewer/planner (deliberating in-conversation and supplying already-
// resolved `resolvedDecisions` on CREATE_SUCCESSOR); the engine never performs a
// separate model/network call itself. The engine logic, operations, guards,
// receipts, and audits are unchanged.
//
// Usage:
//   node cli.mjs '<json-request>'      # one-shot; prints the JSON result
//   echo '<json-request>' | node cli.mjs
//   node cli.mjs --serve               # NDJSON stdin -> NDJSON stdout, one
//                                       # request per line; keeps in-memory
//                                       # chat/draft session state across turns
//
// Performance note (design `sdd/paper-proposal-serve-resolve`, "Lever 1"): this
// host's own jiti cold start (compiling the engine's ~63 TS files) dominates a
// deliberation's wall-clock cost -- roughly 0.72s per spawned node process. A
// full CREATE_SUCCESSOR round used to pay that cost THREE times: once for a
// separate `node --input-type=module -e` jiti recipe to resolve the target
// entry ID (see SKILL.md), once for the preview call, once for the accept
// call. `{ operation: "RESOLVE_TARGET" }` (below) moves that resolution INSIDE
// this same process/request loop -- one `--serve` session now pays the cold
// start ONCE for resolve + preview + accept + any further versions.
//
// `RESOLVE_TARGET` is a read-only, additive operation handled directly in this
// host, bypassing `paper_proposal_execute`/`PaperProposalOrchestrator` entirely
// (no routing, schema, or operation-semantics change to the engine). It calls
// the EXACT SAME `loadDocumentState` + `resolveSuccessorTarget` +
// `ambiguityGate` functions `orchestrator.ts` calls internally for
// `CREATE_SUCCESSOR`, via the same jiti module cache, so a resolved entryId is
// guaranteed to match what `CREATE_SUCCESSOR` itself would resolve for the
// identical (sourceFilename, query) -- no divergence. It performs no
// mutation, no publish, and no model call, and needs no ANTHROPIC_API_KEY.
//
//   { "operation": "RESOLVE_TARGET", "sourceFilename": "<file>.md", "query": "<locus description>" }
//   -> { "status": "resolved", "operation": "RESOLVE_TARGET", "entryId": "...", "blocked": false, "question": null }
//
//   { "operation": "RESOLVE_TARGET", "sourceFilename": "<file>.md", "queries": [{ "query": "..." }, ...] }
//   -> { "status": "resolved", "operation": "RESOLVE_TARGET", "results": [{ "query": "...", "entryId": "...", "blocked": false, "question": null }, ...] }
//
// Environment:
//   PAPER_PROPOSAL_PROJECT_ROOT  managed project root (default: process.cwd())
//   PAPER_PROPOSAL_SESSION_ID    stable session identity (default: cli session)

import { createInterface } from 'node:readline';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createJiti } from 'jiti';

const engineDir = path.dirname(new URL(import.meta.url).pathname);
const jiti = createJiti(import.meta.url);

const host = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));

const projectRoot = process.env.PAPER_PROPOSAL_PROJECT_ROOT ?? process.cwd();
const sessionId = process.env.PAPER_PROPOSAL_SESSION_ID ?? 'paper-proposal-cli-session';

/** Runtime context: the exact ExtensionContext surface the engine reads. No model
 * identity or model-auth registry is wired -- the keyless CREATE_SUCCESSOR +
 * `resolvedDecisions` path never needs one. */
const ctx = {
	sessionManager: { getSessionId: () => sessionId },
	hasUI: false,
	ui: { confirm: async () => false },
};

// Build the extension once so in-memory session state (chat conversations,
// draft registry) survives across requests within a single process — matching
// how pi loaded the extension once per long-running session.
const registered = [];
host.createPaperProposalExtension({ projectRoot })({
	registerTool: (tool) => registered.push(tool),
	on: () => {},
});
const tool = registered.find((candidate) => candidate.name === 'paper_proposal_execute');
if (!tool) {
	process.stderr.write('paper_proposal_execute tool was not registered\n');
	process.exit(1);
}

// Same jiti instance/module cache the `host` import above already populated --
// `orchestrator.ts` (reached transitively through `proposal-workspace.ts`)
// already imports these exact three modules, so re-importing them here by
// path returns the SAME cached, already-compiled module instances (no extra
// compile cost, and literally the same function objects `CREATE_SUCCESSOR`
// resolves through internally).
const documentStateModule = await jiti.import(path.join(engineDir, 'document-state.ts'));
const targetResolverModule = await jiti.import(path.join(engineDir, 'target-resolver.ts'));
const ambiguityGateModule = await jiti.import(path.join(engineDir, 'ambiguity-gate.ts'));

// Deliberately NOT memoizing `loadDocumentState` results across calls within a
// `--serve` session (would-be item 2 of the amortization design): the real
// CREATE_SUCCESSOR path calls `materializeCompositeTarget(state, target)`,
// which MUTATES the resolved `DocumentState`'s `structuralIndex` (`entries`/
// `byId`) IN PLACE to register the composite entry it just resolved. If a
// cached `DocumentState` object were shared/returned across independent
// RESOLVE_TARGET/preview/accept calls in the same process, one call's
// materialized composite entries would leak into and contaminate a later,
// unrelated call's resolution against the "same" (root, filename,
// documentSha256) key -- a genuine staleness/correctness hazard, not merely a
// performance question. Skipping the cache keeps every call's `DocumentState`
// independent and correct; the persistent-process reuse above (no per-call
// jiti cold start) is the amortization win.
async function resolveOneTarget(sourceFilename, query) {
	if (typeof sourceFilename !== 'string' || !sourceFilename) {
		return { entryId: null, blocked: true, question: 'RESOLVE_TARGET_SOURCE_FILENAME_REQUIRED' };
	}
	if (typeof query !== 'string' || !query.trim()) {
		return { entryId: null, blocked: true, question: 'RESOLVE_TARGET_QUERY_REQUIRED' };
	}
	let state;
	try {
		state = await documentStateModule.loadDocumentState(projectRoot, sourceFilename);
	} catch (error) {
		return { entryId: null, blocked: true, question: error?.message ?? String(error) };
	}
	const resolution = targetResolverModule.resolveSuccessorTarget(state, query);
	const gate = ambiguityGateModule.ambiguityGate(resolution.candidates);
	return { entryId: gate.candidate?.entryId ?? null, blocked: gate.blocked, question: gate.question ?? null };
}

async function runResolveTarget(request) {
	if (Array.isArray(request.queries)) {
		const results = [];
		for (const item of request.queries) {
			const resolved = await resolveOneTarget(item?.sourceFilename ?? request.sourceFilename, item?.query);
			results.push({ query: item?.query, ...resolved });
		}
		return { status: 'resolved', operation: 'RESOLVE_TARGET', results };
	}
	const resolved = await resolveOneTarget(request.sourceFilename, request.query);
	return { status: 'resolved', operation: 'RESOLVE_TARGET', ...resolved };
}

let sequence = 0;
async function run(request) {
	if (request?.operation === 'RESOLVE_TARGET') return runResolveTarget(request);
	const result = await tool.execute(`cli-${++sequence}`, request, undefined, undefined, ctx);
	return result.details ?? result;
}

function parseRequest(text) {
	const trimmed = text.trim();
	if (!trimmed) throw new Error('empty request');
	return JSON.parse(trimmed);
}

async function readStdin() {
	const chunks = [];
	for await (const chunk of process.stdin) chunks.push(chunk);
	return Buffer.concat(chunks).toString('utf8');
}

const args = process.argv.slice(2);

if (args.includes('--serve')) {
	const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
	for await (const line of rl) {
		if (!line.trim()) continue;
		try {
			const result = await run(parseRequest(line));
			process.stdout.write(`${JSON.stringify(result)}\n`);
		} catch (error) {
			process.stdout.write(`${JSON.stringify({ status: 'error', message: error?.message ?? String(error) })}\n`);
		}
	}
} else {
	const inline = args.find((arg) => !arg.startsWith('--'));
	const raw = inline ?? (await readStdin());
	try {
		const result = await run(parseRequest(raw));
		process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
	} catch (error) {
		process.stdout.write(`${JSON.stringify({ status: 'error', message: error?.message ?? String(error) }, null, 2)}\n`);
		process.exit(1);
	}
}

void pathToFileURL;
