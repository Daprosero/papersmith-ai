---
name: paper-proposal
description: Edit and deliberate on existing managed mathematical proposals with Paper Proposal V2.
---
# Paper Proposal V2

Use this skill for observable V2 work on an existing managed proposal. All execution goes through the single tool `paper_proposal_v2_execute`. It does not create an initial proposal.

## Quick path

1. State the requested change in natural language.
2. Identify the target by meaning or by exact quoted text; do not provide offsets, hashes, revision names, or patch fields.
3. Call `paper_proposal_v2_execute` once and follow any clarification it returns.
4. Confirm the returned result, receipt, and manifest before treating the operation as complete.

See [user-facing examples and help](references/usage.md) for request patterns.

## Selection

| Selection | Use it when | Example |
| --- | --- | --- |
| Semantic | The target is best identified by its role or meaning, such as a heading, equation label, symbol definition, paragraph purpose, or concept. | “In the assumptions section, tighten the definition of stationarity.” |
| Literal | The exact text is known and should be matched as written. | “Replace the sentence ‘The estimator is always unbiased.’ with …” |

A request may combine semantic and literal selection. If the target is missing or more than one target is plausible, V2 returns a short clarification instead of choosing silently or publishing a change. Answer that clarification with enough context to select one target, then call `paper_proposal_v2_execute` again.

### Exact-block semantic MODIFY gate

For a semantic `MODIFY` phrased as “replace this block with this block”:

- Call `paper_proposal_v2_execute` with exactly `sourceFilename` and the complete original user `instruction`.
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
| `DELIBERATE` | Evaluates alternatives, assumptions, and tradeoffs without requiring an immediate document change. |
| `WITHDRAW_REVISION` | Safely withdraws one eligible managed revision while preserving an audited recovery copy. |
| `RESTORE_WITHDRAWN_REVISION` | Restores one previously withdrawn managed revision from its audited recovery copy. |

Literal operations can use exact supplied text. Semantic operations resolve document concepts and may require planning or bounded assessment before execution. `MOVE` and `COPY` must name both source and destination clearly. `DELETE` must distinguish content inside a section from deletion of the whole section.

### Managed revision withdrawal and restore

Lifecycle actions are NOT content deletion. For an explicit lifecycle tool call:

- Set `operation` to `WITHDRAW_REVISION` and provide the exact managed `sourceFilename`. Do not provide `withdrawalOperationId`; V2 generates it and returns it with the audited backup location.
- Set `operation` to `RESTORE_WITHDRAWN_REVISION` and provide either the exact withdrawn `sourceFilename` or its returned `withdrawalOperationId`. A filename restores directly when it identifies one withdrawn record; V2 asks for the operation ID only when multiple records match.
- Direct natural-language requests such as “withdraw managed revision research-concept-r02.md” or “restore withdrawn revision research-concept-r02.md” remain supported without `operation`.
- Do not translate an uncertain phrase such as “delete r02” into `DELETE`. Clarify whether the user means managed-revision withdrawal or deletion of content. A request such as “delete this section” remains a content `DELETE`.

Withdrawal and restore bypass semantic target resolution, planning, patches, models, tutor, and reviewer. Treat the returned `operationId`, filenames, backup location, consistency audit, and `SelfAudit` as the completion evidence.

## Planning, tutoring, and review

V2 may expose three bounded responsibilities:

- **Planner:** converts a resolved request into a scoped action and identifies required clarification.
- **Tutor:** evaluates supplied mathematical context, notation, assumptions, and conceptual consequences. It advises; it does not publish.
- **Reviewer:** assesses coherence, scope, unsupported claims, references, and notation. It advises; it does not publish.

The tutor and reviewer role files are manual/reference contracts. Their presence does not promise automatic invocation and does not select a model or profile. The execution tool reports the effective profile and budget actually applied by the runtime. Treat those returned effective values—not requested labels or role-file text—as authoritative.

## Completion and recovery

A successful change returns observable completion evidence. Preserve it:

- **Receipt:** identifies the completed operation and its outcome.
- **Manifest:** summarizes the affected managed artifacts and publication result.
- **Recovery state:** reports whether recovery or another user action is required after an interrupted or incomplete operation.
- **Restart guidance:** follow only the restart or resume action reported by V2; do not invent a revision or replay a successful request blindly.
- **Consistency audit:** use the reported audit result to confirm managed state is consistent before continuing.
- **`SelfAudit`:** treat a failed or incomplete SelfAudit as unresolved, even if an edit appears locally visible.

If execution is ambiguous, blocked, interrupted, or inconsistent, do not claim completion. Resolve the returned clarification or recovery instruction and run `paper_proposal_v2_execute` again only when directed by that observable state.

## Limits

- V2 edits existing managed proposals; initial proposal creation is unsupported.
- Use only `paper_proposal_v2_execute` for proposal execution.
- Do not claim that a requested profile, role file, or prompt controls the effective model or budget.
- Do not expose or ask users to supply internal patch, index, hash, offset, or publication mechanics.
- Do not modify proposal infrastructure, extensions, roles, tests, or this skill during normal proposal work.
