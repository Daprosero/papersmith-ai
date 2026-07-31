---
name: paper-proposal
description: "Trigger: session-local scientific chat/deliberation, or edits and lifecycle operations on existing managed mathematical proposals. Runs the bounded paper-proposal engine."
---

# Paper Proposal

Use this skill for Paper Proposal work: non-mutating scientific deliberation, explicit first-version creation, edits to an existing managed mathematical proposal, and managed-revision lifecycle operations. All execution goes through the engine host CLI. Edits require an existing managed proposal; explicit `CREATE_INITIAL_REVISION` is the only way to create one, and only when none exists yet. `CHAT_DELIBERATION` requires no managed proposal. A chat may also be materialized as a new standalone draft through the explicit create-only route below.

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

1. When no managed proposal exists yet, send `{"operation":"CREATE_INITIAL_REVISION","instruction":"<the idea>"}` to create v1. Only use this when starting from nothing; it is rejected outright if a managed proposal already exists.
2. For a non-mutating scientific conversation, send `{"operation":"CHAT_DELIBERATION","instruction":"..."}` and reuse the returned `conversationId` for follow-ups. The conversation stays locked in chat — including on edit-verb follow-ups — until you explicitly send `{"operation":"CLOSE_DELIBERATION","conversationId":"..."}`.
3. To save that chat as a standalone draft instead of closing it into an edit, send `draftMaterialization` with `operation: INITIAL_CREATE`, explicit current-turn authorization, and either an exact route or approval of the previously proposed route.
4. For an edit to the managed document, state the requested mutation in natural language and identify its target by meaning or exact quoted text; do not provide offsets, hashes, revision names, or patch fields.
5. Send one request and follow any clarification it returns, including a base-confirmation prompt on a new deliberation. Confirm a receipt and manifest only for a completed managed edit or lifecycle operation.

See [user-facing examples and help](references/usage.md) for request patterns.

## Runtime authority boundary

- Ordinary `CHAT_DELIBERATION` is mode-first: it wins over lifecycle, document, and scientific-workflow wording. It uses only a `chat-…` `conversationId`; it does not open `document_operation_guard`, mutate `proposal_workspace`, create durable scientific/document state, or mint/continue task authority.
- A returned `conversationId` remains locked in chat until the user sends an explicit `CLOSE_DELIBERATION`, explicitly materializes the chat as a new draft, or requests an explicit `MAINTENANCE` handoff. An edit-verb follow-up inside an open deliberation does NOT leak into a mutating route on its own; it is handled in-chat and still requires `CLOSE_DELIBERATION` before a document edit can proceed. Passing scientific or maintenance identifiers with chat does not join their state.
- Deliberation state (turns, tutor/reviewer conclusions, accumulated approved-change tally) is in-session only. `CLOSE_DELIBERATION` discards it; reusing the same `conversationId` afterward is rejected as terminated, not resumed.
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

## Base selection for a new deliberation

On a new `CHAT_DELIBERATION` (no `sourceFilename` and no prior `confirmBase`), the engine resolves the latest managed revision through one unified resolver shared by every call site, then asks for interactive confirmation before proceeding:

- If exactly one active managed revision resolves, the engine proposes it and asks the caller to confirm (`confirmBase: true`) or override it (`sourceFilename: "<exact-filename>"`).
- If more than one active managed revision resolves, the engine surfaces the `MULTIPLE_ACTIVE_REVISIONS` warning with the full candidate list — never silently picking or suppressing it — and requires an exact `sourceFilename` to proceed.

No revision name or path is ever hardcoded by the skill; always resolve or confirm the base through this prompt rather than guessing a filename.

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
| `CREATE_SUCCESSOR` | Creates a managed successor revision for a bounded edit. The edit locus is inferred from the resolved target (heading/phrase/paragraph), not a mandatory numbered range; `editIntent` defaults silently to `MODIFY` when omitted and may be overridden to `CONCEPTUAL_REVISION`. Untouched content is byte-preserved; only the approved add/change/delete is applied. Multiple independently resolved sections can be approved and applied in one version, but multi-section application is currently `MODIFY`-only — `CONCEPTUAL_REVISION` with more than one target is rejected. |
| `DELIBERATE` / `CHAT_DELIBERATION` | Evaluates alternatives, assumptions, and tradeoffs without a document target or mutation. Use `CHAT_DELIBERATION` explicitly for a multi-turn conversation. By default the tutor assesses every turn; a turn proposing a concrete change additionally runs a bounded tutor→reviewer→repair loop (at most 2 repair cycles). |
| `CLOSE_DELIBERATION` | Explicitly ends an open `CHAT_DELIBERATION` conversation. Required to exit chat — an edit-verb follow-up alone does not exit it. Discards in-session deliberation state; the `conversationId` cannot be resumed afterward. |
| `CREATE_INITIAL_REVISION` | Creates the first managed proposal (v1) from the supplied idea (`instruction`) and the paper-guide, only when no managed proposal exists yet. Never runs automatically and never overwrites or duplicates an existing managed proposal. Title, heading, and filename slug are derived from the idea, not a fixed generic skeleton. |
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

In `CHAT_DELIBERATION`, the tutor assesses every turn (one call). When the tutor's decision proposes a concrete change, the engine additionally runs the reviewer and, if the reviewer requests changes, a bounded repair loop (at most 2 repair cycles) by default — this is not gated behind a separate flag. A discussion-only turn with no concrete change runs the tutor alone. Each completed turn also carries a non-blocking `growthAdvisory` that suggests materializing the accumulated approved changes once they exceed roughly 4 independent sections or 40% of the document; it never blocks the turn.

On a new deliberation, the engine loads the paper-guide directory once as read-only reference context for that conversation; it is not reloaded on every turn.

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

- The engine edits existing managed proposals; `CREATE_INITIAL_REVISION` is the only way to create one, and only when none exists yet — it is never triggered automatically. `CHAT_DELIBERATION` is session-local and is not promised to survive across separate one-shot invocations (use `--serve` for a multi-turn session); its state is discarded on `CLOSE_DELIBERATION`. Explicit draft materialization creates only a separate standalone draft and never changes the managed primary document.
- Multi-section `CREATE_SUCCESSOR` (more than one approved locus in one version) is currently `MODIFY`-only; a multi-section `CONCEPTUAL_REVISION` is not yet supported.
- Use only the engine host CLI for proposal execution.
- Do not expose or ask users to supply internal patch, index, hash, offset, or publication mechanics.
- Do not modify engine infrastructure, shims, tests, or this skill during normal proposal work.
