# Paper Proposal V2 examples and help

Use `/skill:paper-proposal` for guidance. Every proposal operation is executed with `paper_proposal_execute` and a natural-language request. Most examples below assume the proposal already exists and is managed by V2; the first example covers creating that initial version.

## Creating the first managed version

When no managed proposal exists yet, call `paper_proposal_execute` with `operation: CREATE_INITIAL_REVISION` and the idea as `instruction`:

```json
{
  "operation": "CREATE_INITIAL_REVISION",
  "instruction": "A paper proposing a distribution-free calibration test for conformal prediction sets under covariate shift."
}
```

This is explicit and user-triggered only: it never runs automatically from a chat turn or any other route, and it is rejected outright when a managed proposal already exists (it never overwrites or duplicates one). The engine loads the paper-guide directory once and composes v1 from that guide content plus the supplied idea — title, section heading, and filename slug are all derived from the idea, never a fixed generic skeleton. A successful call returns the created filename, revision, and document hash as completion evidence.

## Chat deliberation

For a non-mutating tutor conversation, call `paper_proposal_execute` with `operation: CHAT_DELIBERATION`:

> Discuss whether the bag definition in section 3.1 should use finite-set notation. Do not edit the proposal.

Pass the returned `conversationId` in a follow-up to reuse the bounded in-session conclusions. Chat works when persistent scientific workflow is disabled, does not require a managed proposal, and does not promise survival across restarts. It creates no proposal, receipt, audit record, document mutation, or delegated task authority. An explicit `CHAT_DELIBERATION` request stays chat even when its wording mentions a document or lifecycle action.

On the first turn of a new deliberation (no `sourceFilename` and no prior `confirmBase`), the engine resolves the latest managed revision and asks for confirmation before proceeding: `status: "base_confirmation_required"` with either a single `proposedBase` (resend with `confirmBase: true` to accept it, or `sourceFilename` to override) or, if more than one active revision exists, a `MULTIPLE_ACTIVE_REVISIONS` warning plus the full candidate list (an exact `sourceFilename` is then required). No path or filename is ever guessed or hardcoded.

By default, the tutor assesses every turn. When a turn proposes a concrete change (an `ACCEPT_WITH_REVISIONS`- or `PROPOSE_ALTERNATIVE`-type decision), the engine additionally runs the reviewer and, if needed, a bounded repair loop (at most 2 repair cycles) before returning its conclusion — this runs by default, with no separate flag to enable it. A purely discussion turn runs the tutor alone. Each turn's result also carries a non-blocking `growthAdvisory` suggesting materialization once the accumulated approved changes exceed roughly 4 sections or 40% of the document.

Deliberation is locked: once `CHAT_DELIBERATION` opens, follow-up turns stay in chat even if they use edit verbs — the engine never infers a document edit from wording alone while the conversation is open:

> Now apply that conclusion to the definition of training bags.

The turn above is still handled in-chat, not as a document edit. To leave chat, either materialize the conversation as a draft (below) or send an explicit close:

```json
{ "operation": "CLOSE_DELIBERATION", "conversationId": "chat-…" }
```

`CLOSE_DELIBERATION` discards the conversation's in-session state (turns, tutor/reviewer conclusions, accumulated growth tally). Reusing the same `conversationId` afterward is rejected as terminated, not resumed — start a new `CHAT_DELIBERATION` instead, which resolves its base the same way as any new deliberation.

## Materialize chat as a standalone draft

Materialization is the only mutating exit from `CHAT_DELIBERATION` that does not edit the managed primary document. Send the existing `conversationId` and a `draftMaterialization` object:

```json
{
  "operation": "INITIAL_CREATE",
  "route": "<configured-draft-directory>/<metadata-derived-name>.<allowed-extension>",
  "authorized": true
}
```

The authorization applies only to the current turn. The exact route must be relative, normalized, inside the configured draft directory, use an allowed extension, differ from the dynamically resolved managed primary document, and identify a target that does not exist or resolve through a symlink. `UPDATE` and `REPLACE` are always rejected from chat.

When `route` is omitted, V2 returns a metadata-derived proposal and writes nothing. On a later turn, set `approveProposedRoute: true` and explicitly authorize `INITIAL_CREATE`; V2 uses only the exact pending route. A supplied invalid or conflicting route is rejected unchanged and is never silently rewritten.

Success returns the exact route, `INITIAL_CREATE`, written UTF-8 byte count, confirmation that the managed primary document is intact, and terminal completion. Materialization carries the consolidated session-local chat content without another tutor or reviewer call and does not resume deliberation.

## Maintenance handoff

`MAINTENANCE` is distinct from chat and document editing. It returns an explicit external-controller handoff and may carry a `maintenance-…` task ID, but V2 does not create a worker, resume a task, grant document authority, or persist maintenance state. Use it only when an external controller has a narrowly scoped, justified maintenance action to delegate.

## Editing examples

### Modify

Call `paper_proposal_execute` with:

> In the methodology section, modify the paragraph defining the loss so it states that the expectation is over both data and augmentation randomness. Preserve the notation used in the following equation.

### Move

Call `paper_proposal_execute` with:

> Move the paragraph beginning “We next impose compactness” from the motivation section to immediately before the assumptions list. Remove it from its current location.

### Copy

Call `paper_proposal_execute` with:

> Copy the exact sentence “All logarithms are natural unless noted otherwise.” from the notation section to the start of the appendix. Preserve the original sentence in the notation section.

### Delete content but keep the section

Call `paper_proposal_execute` with:

> In the limitations section, delete only the sentence claiming the method has no computational overhead. Keep the section and all other content.

### Delete a section

Call `paper_proposal_execute` with:

> Delete the entire section headed “Preliminary Ablations,” including its content. Do not delete similarly named references elsewhere.

### Cleanup

Call `paper_proposal_execute` with:

> Clean up the notation subsection structurally: normalize list formatting and remove duplicate blank lines. Do not change mathematical meaning.

### Conceptual revision

Call `paper_proposal_execute` with:

> Revise the convergence argument so it consistently assumes local Lipschitz continuity rather than global smoothness. Update only the directly affected explanation and assumptions, and flag consequences that require clarification.

### Deliberation

Call `paper_proposal_execute` with:

> Deliberate on whether the identifiability assumption should remain explicit or be replaced by an invariance argument. Compare mathematical consequences, notation impact, and risks without changing the proposal.

## Managed revision lifecycle

To withdraw an eligible managed revision, call `paper_proposal_execute` with `operation: WITHDRAW_REVISION`, its exact `sourceFilename`, and a clear instruction. Omit `withdrawalOperationId`; V2 generates and returns it.

To restore it, call the same tool with `operation: RESTORE_WITHDRAWN_REVISION` and either the exact withdrawn `sourceFilename` or the returned `withdrawalOperationId`. If more than one withdrawn record has that filename, use the operation ID requested by the clarification.

Lifecycle actions are distinct from content deletion. “Delete r02” requires clarification; “delete this section” remains a content `DELETE`.

## Clarification and ambiguity

V2 does not silently choose among plausible targets. If it returns a clarification, answer it and call `paper_proposal_execute` again.

Ambiguous request:

> Delete the consistency paragraph.

Better follow-up after V2 reports two matches:

> Use the consistency paragraph in the section headed “Asymptotic Guarantees,” the one beginning “Under compactness.” Delete that paragraph only.

If the target still cannot be resolved, provide an exact quote plus its semantic location. Do not provide offsets, hashes, revision names, or internal patch fields.

## Reading the result

Before claiming completion, check the returned outcome and the available receipt, manifest, effective profile/budget, recovery or restart guidance, consistency audit, and `SelfAudit`. A clarification, blocked recovery state, failed consistency audit, or incomplete `SelfAudit` means the operation is not complete.
