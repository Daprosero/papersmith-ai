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

let sequence = 0;
async function run(request) {
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
