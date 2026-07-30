#!/usr/bin/env node
// Native Claude Code host for the paper-proposal engine.
//
// Reproduces exactly what the pi runtime did around `paper_proposal_execute`:
// it builds the same extension, registers the same tool, and invokes it with a
// runtime context — only the host is Claude Code instead of pi, and the model
// backend is the Claude Messages API (see engine/_pi-compat/pi-ai-compat.ts).
// The engine logic, operations, guards, receipts, and audits are unchanged.
//
// Usage:
//   node cli.mjs '<json-request>'      # one-shot; prints the JSON result
//   echo '<json-request>' | node cli.mjs
//   node cli.mjs --serve               # NDJSON stdin -> NDJSON stdout, one
//                                       # request per line; keeps in-memory
//                                       # chat/draft session state across turns
//
// Environment:
//   ANTHROPIC_API_KEY            required for any model-backed operation
//   PAPER_PROPOSAL_MODEL         Claude model id (default: claude-sonnet-5)
//   PAPER_PROPOSAL_PROJECT_ROOT  managed project root (default: process.cwd())
//   PAPER_PROPOSAL_SESSION_ID    stable session identity (default: cli session)
//   PAPER_PROPOSAL_MAX_TOKENS    max output tokens per model call (default 8192)

import { createInterface } from 'node:readline';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createJiti } from 'jiti';

const engineDir = path.dirname(new URL(import.meta.url).pathname);
const jiti = createJiti(import.meta.url);

const host = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));

const projectRoot = process.env.PAPER_PROPOSAL_PROJECT_ROOT ?? process.cwd();
const sessionId = process.env.PAPER_PROPOSAL_SESSION_ID ?? 'paper-proposal-cli-session';

/** Runtime context: the exact ExtensionContext surface the engine reads. */
const ctx = {
	model: { provider: 'anthropic', id: process.env.PAPER_PROPOSAL_MODEL ?? 'claude-sonnet-5' },
	modelRegistry: {
		getApiKeyAndHeaders: async () => {
			const apiKey = process.env.ANTHROPIC_API_KEY;
			return apiKey
				? { ok: true, apiKey, headers: {}, env: {} }
				: { ok: false, error: 'MODEL_AUTH_REQUIRED:anthropic (set ANTHROPIC_API_KEY)' };
		},
	},
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
