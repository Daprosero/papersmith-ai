---
name: paper-proposal
description: "Trigger: session-local scientific chat/deliberation, or edits and lifecycle operations on existing managed mathematical proposals. Runs the bounded paper-proposal engine."
---

# Paper Proposal

Use this skill for Paper Proposal work: non-mutating scientific deliberation, edits to an existing managed mathematical proposal, and managed-revision lifecycle operations. All execution goes through the engine host CLI. The engine does not create an initial managed proposal; edits require an existing managed proposal, while `CHAT_DELIBERATION` does not. A chat may be materialized only as a new standalone draft through the explicit create-only route below.

## How to execute

Every operation is one call to the engine host, which builds the same bounded engine, resolves the target, plans, and publishes under guard:

```
node .claude/skills/paper-proposal/engine/cli.mjs '<json-request>'
```

- The request is a single JSON object (see operations below). The result is a JSON receipt/manifest printed to stdout.
- Environment: `ANTHROPIC_API_KEY` is required for any model-backed operation. Optional: `PAPER_PROPOSAL_MODEL` (default `claude-sonnet-5`), `PAPER_PROPOSAL_PROJECT_ROOT` (default cwd), `PAPER_PROPOSAL_SESSION_ID`.
- For a multi-turn chat that must keep session-local state across turns, use `node .claude/skills/paper-proposal/engine/cli.mjs --serve` and send one JSON request per line; in-memory chat and draft state persist for the life of that process.

Never construct patches, offsets, hashes, manifests, receipts, or internal revision mechanics. Supply only user-facing semantic selectors and content.

## Quick path

1. For a non-mutating scientific conversation, send `{"operation":"CHAT_DELIBERATION","instruction":"..."}` and reuse the returned `conversationId` for follow-ups.
2. To save that chat as a standalone draft, send `draftMaterialization` with `operation: INITIAL_CREATE`, explicit current-turn authorization, and either an exact route or approval of the previously proposed route.
3. For an edit to the managed document, state the requested mutation in natural language and identify its target by meaning or exact quoted text; do not provide offsets, hashes, revision names, or patch fields.
4. Send one request and follow any clarification it returns. Confirm a receipt and manifest only for a completed managed edit or lifecycle operation.

See [user-facing examples and help](references/usage.md) for request patterns.

## Runtime authority boundary

- Ordinary `CHAT_DELIBERATION` is mode-first: it wins over lifecycle, document, and scientific-workflow wording. It uses only a `chat-…` `conversationId`; it does not open `document_operation_guard`, mutate `proposal_workspace`, create durable scientific/document state, or mint/continue task authority.
- A returned `conversationId` remains a chat continuation until the user explicitly requests a managed document edit, explicitly materializes the chat as a new draft, or requests an explicit `MAINTENANCE` handoff. Passing scientific or maintenance identifiers with chat does not join their state.
- Draft materialization is a one-way `CHAT_DELIBERATION` to `DOCUMENT_EDIT` transition. It accepts only `INITIAL_CREATE`, preserves the dynamically resolved managed primary document, writes only inside the configured draft directory, and terminates without resuming deliberation.
- Without an exact route, the engine proposes a metadata-derived route and writes nothing. The caller must approve that exact proposal and explicitly authorize `INITIAL_CREATE` in the current turn. Invalid supplied routes are rejected unchanged; the engine never silently normalizes, relocates, replaces, or overwrites them.
- Direct document edits are principal-local and guarded. The engine has no generic worker/task API, so it never delegates an edit through its public surface. Any external handoff must be explicit, narrowly scoped, and justified outside the engine.
- `MAINTENANCE` is an explicit controller handoff only: it may permit external maintenance delegation, but it creates no document authority or durable task state.

## Selection

| Selection | Use it when | Example |
| --- | --- | --- |
| Semantic | The target is best identified by its role or meaning, such as a heading, equation label, symbol definition, paragraph purpose, or concept. | "In the assumptions section, tighten the definition of stationarity." |
| Literal | The exact text is known and should be matched as written. | "Replace the sentence 'The estimator is always unbiased.' with …" |

A request may combine semantic and literal selection. If the target is missing or more than one target is plausible, the engine returns a short clarification instead of choosing silently or publishing a change. Answer that clarification with enough context to select one target, then send the request again.

### Exact-block semantic MODIFY gate

For a semantic `MODIFY` phrased as "replace this block with this block":

- Send exactly `sourceFilename` and the complete original user `instruction`.
- Preserve both supplied blocks byte-for-byte inside `instruction`.
- Omit `selectedEntryId`, `literalContent`, every literal-mode field, and external `targetDescription`, `semanticChange`, or `fidelityConstraints`; the internal IntentResolver derives those semantics.
- Supply `selectedEntryId` only after real structural document resolution returns that entry ID. Never invent it from a description or quoted block.

## Supported operations

| Operation | Observable behavior |
| --- | --- |
| `MODIFY` | Rewrites selected content while keeping the change within the requested scope. |
| `INSERT` | Adds literal or semantically described content at a resolved location. |
| `MOVE` | Relocates selected content and removes it from its original location. |
| `COPY` | Reuses selected content at another location while preserving the source. |
| `DELETE` | Removes selected content or an explicitly selected section. |
| `CLEANUP` | Performs requested structural cleanup; semantic cleanup requires explicit authorization. |
| `CONCEPTUAL_REVISION` | Reworks a bounded concept and its necessary local consequences rather than applying a purely literal edit. |
| `CREATE_SUCCESSOR` | Creates a managed successor revision for a bounded edit; requires `editIntent` (`MODIFY` or `CONCEPTUAL_REVISION`) and a numbered `sectionRange`. |
| `DELIBERATE` / `CHAT_DELIBERATION` | Evaluates alternatives, assumptions, and tradeoffs without a document target or mutation. Use `CHAT_DELIBERATION` explicitly for a multi-turn conversation. |
| Draft `INITIAL_CREATE` | Materializes consolidated session-local chat content at one explicitly authorized, validated route under the configured draft directory. `UPDATE` and `REPLACE` are denied. |
| `WITHDRAW_REVISION` | Safely withdraws one eligible managed revision while preserving an audited recovery copy. |
| `RESTORE_WITHDRAWN_REVISION` | Restores one previously withdrawn managed revision from its audited recovery copy. |

Literal operations can use exact supplied text. Semantic edit operations resolve document concepts and may require planning or bounded assessment before execution. Chat deliberation never resolves a document target, opens a document-operation guard, creates a receipt, or writes durable scientific state. `MOVE` and `COPY` must name both source and destination clearly. `DELETE` must distinguish content inside a section from deletion of the whole section.

### Managed revision withdrawal and restore

Lifecycle actions are NOT content deletion:

- Set `operation` to `WITHDRAW_REVISION` and provide the exact managed `sourceFilename`. Do not provide `withdrawalOperationId`; the engine generates it and returns it with the audited backup location.
- Set `operation` to `RESTORE_WITHDRAWN_REVISION` and provide either the exact withdrawn `sourceFilename` or its returned `withdrawalOperationId`. A filename restores directly when it identifies one withdrawn record; the engine asks for the operation ID only when multiple records match.
- Direct natural-language requests such as "withdraw managed revision research-concept-r02.md" or "restore withdrawn revision research-concept-r02.md" remain supported without `operation`.
- Do not translate an uncertain phrase such as "delete r02" into `DELETE`. Clarify whether the user means managed-revision withdrawal or deletion of content. A request such as "delete this section" remains a content `DELETE`.

Withdrawal and restore bypass semantic target resolution, planning, patches, models, tutor, and reviewer. Treat the returned `operationId`, filenames, backup location, consistency audit, and `SelfAudit` as the completion evidence.

## Planning, tutoring, and review

The engine may exercise three bounded responsibilities internally:

- **Planner:** converts a resolved request into a scoped action and identifies required clarification.
- **Tutor:** evaluates supplied mathematical context, notation, assumptions, and conceptual consequences. It advises; it does not publish.
- **Reviewer:** assesses coherence, scope, unsupported claims, references, and notation. It advises; it does not publish.

These are model-backed and run inside the engine when the resolved operation calls for them. The result reports the effective calls actually made (`plannerCalls`, `tutorCalls`, `reviewerCalls`, `modelCalls`). Treat those returned effective values as authoritative.

## Completion and recovery

A successful change returns observable completion evidence. Preserve it:

- **Receipt:** identifies the completed operation and its outcome.
- **Manifest:** summarizes the affected managed artifacts and publication result.
- **Recovery state:** reports whether recovery or another user action is required after an interrupted or incomplete operation.
- **Restart guidance:** follow only the restart or resume action reported by the engine; do not invent a revision or replay a successful request blindly.
- **Consistency audit:** use the reported audit result to confirm managed state is consistent before continuing.
- **`SelfAudit`:** treat a failed or incomplete SelfAudit as unresolved, even if an edit appears locally visible.

If execution is ambiguous, blocked, interrupted, or inconsistent, do not claim completion. Resolve the returned clarification or recovery instruction and send the request again only when directed by that observable state.

## Limits

- The engine edits existing managed proposals; initial managed-proposal creation is unsupported. `CHAT_DELIBERATION` is session-local and is not promised to survive across separate one-shot invocations (use `--serve` for a multi-turn session). Explicit draft materialization creates only a separate standalone draft and never changes the managed primary document.
- Use only the engine host CLI for proposal execution.
- Do not expose or ask users to supply internal patch, index, hash, offset, or publication mechanics.
- Do not modify engine infrastructure, shims, tests, or this skill during normal proposal work.
