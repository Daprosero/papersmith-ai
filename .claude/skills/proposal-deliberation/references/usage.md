# Proposal Deliberation — examples and help

See [SKILL.md](../SKILL.md) for the full tutor-role conditioning and workflow discipline. This page is worked examples only: checking `STATUS` before deciding a base, creating the first managed version, resolving a locus, building `resolvedDecisions`, and the preview → accept → publish cycle. Every call below is a real, verified invocation of `node .claude/skills/proposal-deliberation/engine/cli.mjs` — none of it requires `ANTHROPIC_API_KEY` or any model configuration.

## Checking `STATUS` before deciding a base

Before running the decision tree in [SKILL.md's "Resolving the base version"](../SKILL.md#resolving-the-base-version), call `STATUS` — read-only, keyless, no model call:

```bash
node .claude/skills/proposal-deliberation/engine/cli.mjs '{ "operation": "STATUS" }'
```

Against a `proposals/` directory holding a managed `r01`/`r02` pair, one managed-looking-but-unmarked `r03` (missing the `<!-- proposal-workspace:artifact:v1 -->` marker, so it does NOT count as managed), and an unrelated `initial-idea.md`:

```json
{
  "status": "ok",
  "operation": "STATUS",
  "managedRevisions": [
    { "filename": "research-concept-r01.md", "lineage": "ROOT", "revisionNumber": 1, "isLatest": false },
    { "filename": "research-concept-r02.md", "lineage": "ROOT", "revisionNumber": 2, "isLatest": true }
  ],
  "latest": "research-concept-r02.md",
  "multipleActive": false,
  "candidates": [],
  "nonManagedFiles": ["initial-idea.md", "research-concept-r03.md"]
}
```

Pass `sourceFilename` to classify one candidate base against that same inventory in the same call:

```bash
node .claude/skills/proposal-deliberation/engine/cli.mjs '{ "operation": "STATUS", "sourceFilename": "research-concept-r01.md" }'
```

```json
{ "...": "same fields as above, plus:", "sourceClassification": "OLDER_MANAGED", "newerRevisionNumbers": [2] }
```

```bash
node .claude/skills/proposal-deliberation/engine/cli.mjs '{ "operation": "STATUS", "sourceFilename": "initial-idea.md" }'
```

```json
{ "...": "same fields as above, plus:", "sourceClassification": "UNMANAGED" }
```

`sourceClassification` is one of `LATEST`, `OLDER_MANAGED` (with `newerRevisionNumbers`), `UNMANAGED`, or `NOT_FOUND` (the filename is not present in `proposals/` at all, or it is not a real basename). Never mutating: no `proposals/` file is ever created, moved, or changed by a `STATUS` call — a confirmed backup move (SKILL.md's decision tree) is something *you* do afterward with a plain file move, never the engine. `STATUS` also answers on a project that has **no `proposals/` directory yet** — the exact pre-creation state `CREATE_INITIAL_REVISION` exists for — with the same empty inventory (`latest: null`, empty `managedRevisions`/`nonManagedFiles`), so the "run `STATUS` first" step never has a chicken-and-egg failure. A `proposals/` that exists but cannot be read still fails closed with an error instead of reporting "empty."

## Creating the first managed version

When no managed proposal exists yet, call the engine with `operation: CREATE_INITIAL_REVISION` and the idea as `instruction`:

```bash
node .claude/skills/proposal-deliberation/engine/cli.mjs '{
  "operation": "CREATE_INITIAL_REVISION",
  "instruction": "A paper proposing a distribution-free calibration test for conformal prediction sets under covariate shift."
}'
```

This is explicit and user-triggered only: it never runs automatically, and it is rejected outright when a managed proposal already exists (it never overwrites or duplicates one). The engine loads the project's `guidance/paper-guide` directory once and composes v1 from that guide content plus the supplied idea — title, section heading, and filename slug are all derived from the idea, never a fixed generic skeleton. A successful call returns the created filename, revision, and document hash as completion evidence.

## Open one `--serve` process for the whole deliberation

The engine host's own cold start (jiti compiling its TS sources) is paid once per spawned process. A single version already needs at least three calls — resolve, preview, accept — so start ONE persistent process and keep it open for the whole deliberation instead of spawning a fresh `cli.mjs` invocation per call:

```bash
node .claude/skills/proposal-deliberation/engine/cli.mjs --serve
```

Every example below is a JSON line sent to that same process's stdin, in order.

## Resolving a locus before deciding

Before you can build a `resolvedDecisions` entry, you need the engine's own resolved entry ID for the locus you intend to touch. Send a `RESOLVE_TARGET` line to the `--serve` process above — this is read-only, makes no model call, and needs no `ANTHROPIC_API_KEY`. It uses the exact same resolver (`loadDocumentState` → `resolveSuccessorTarget` → `ambiguityGate`) `orchestrator.ts` calls internally for `CREATE_SUCCESSOR`, so the returned `entryId` is guaranteed to match what `CREATE_SUCCESSOR` itself would resolve for the identical `sourceFilename`/query:

```json
{ "operation": "RESOLVE_TARGET", "sourceFilename": "research-concept-r05.md", "query": "Assumptions stationarity" }
```

Write the query as **distinctive words from the target heading**, not as a sentence describing it. The resolver scores a heading by how many query words appear as substrings of its heading line, so only the rare words help. Drop punctuation (the query is truncated at the first `,;:.`), drop the section number, and keep accents exactly as the heading spells them — matching is accent-sensitive. Stopwords are filtered out for you.


```json
{ "status": "resolved", "operation": "RESOLVE_TARGET", "entryId": "…", "blocked": false, "question": null }
```

- If `blocked` is `false`, `entryId` is the real value to use as `targetEntryId`/`anchorEntryId`/`sourceEntryIds`/`destinationAnchorId` in your decision.
- If `blocked` is `true`, the query matched more than one candidate — `question` lists them and names the terms that matched all of them. **Remove those terms; never add more.** Extra words match more headings, so "narrowing" a blocked query widens it. Never guess between the listed candidates.
- If the reason is `SUCCESSOR_TARGET_NOT_FOUND`, no heading line matched — you described the section's content instead of its title. Name the heading. A successor locus is never resolved from body text, so a near-miss can never silently hand you the wrong section.

Do this once per independent locus in the batch you are about to apply. To resolve several loci in one call, send `queries` (an array of `{ "query": "..." }`) instead of `query`:

```json
{ "operation": "RESOLVE_TARGET", "sourceFilename": "research-concept-r05.md", "queries": [{ "query": "Assumptions stationarity" }, { "query": "Main convergence theorem" }] }
```

```json
{ "status": "resolved", "operation": "RESOLVE_TARGET", "results": [{ "query": "Assumptions stationarity", "entryId": "…", "blocked": false, "question": null }, { "query": "Main convergence theorem", "entryId": "…", "blocked": false, "question": null }] }
```

## Building `resolvedDecisions` and applying

### Replace (the common case: rewrite a paragraph, definition, or block)

```bash
node .claude/skills/proposal-deliberation/engine/cli.mjs '{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Tighten the definition of stationarity to require strict, not weak, stationarity.",
  "selectedEntryId": "Assumptions stationarity",
  "resolvedDecisions": [
    { "kind": "replace", "targetEntryId": "<entryId from the resolve step>", "replacementText": "A process is strictly stationary when its full joint distribution is shift-invariant..." }
  ]
}'
```

### Insert

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Add a remark after the main theorem clarifying the role of the boundedness assumption.",
  "selectedEntryId": "Main convergence theorem",
  "resolvedDecisions": [
    { "kind": "insert", "anchorEntryId": "<entryId>", "position": "after", "content": "**Remark.** Boundedness is used only to control the tail of the empirical process; ..." }
  ]
}
```

### Delete

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Remove the sentence claiming the method has no computational overhead — it is unsupported.",
  "selectedEntryId": "Limitations",
  "resolvedDecisions": [
    { "kind": "delete", "targetEntryId": "<entryId>", "instructionEvidence": "Remove the sentence claiming the method has no computational overhead.", "reason": "unsupported claim" }
  ]
}
```

### Move (literal — content carried byte-for-byte)

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Move the paragraph beginning \"We next impose compactness\" from the motivation section to immediately before the assumptions list.",
  "selectedEntryId": "Assumptions compactness",
  "resolvedDecisions": [
    {
      "kind": "move",
      "sourceEntryIds": ["<source entryId>"],
      "destinationAnchorId": "<destination entryId>",
      "position": "before",
      "moveMode": "LITERAL",
      "removeSource": true,
      "cleanupLevel": "NONE"
    }
  ]
}
```

### Copy (adaptive — content reworded to fit its new context)

An `ADAPTIVE` relocation requires you to supply the reworded text yourself in `transformedContent` — the engine never invents it, and neither should you without a stated basis:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Copy the notation convention for logarithms from the notation section to the start of the appendix, adapting it to refer back to the notation section.",
  "selectedEntryId": "Notation conventions",
  "resolvedDecisions": [
    {
      "kind": "copy",
      "sourceEntryIds": ["<source entryId>"],
      "destinationAnchorId": "<appendix start entryId>",
      "position": "inside_start",
      "moveMode": "ADAPTIVE",
      "removeSource": false,
      "cleanupLevel": "NONE",
      "transformedContent": "As established in the notation section, all logarithms are natural unless noted otherwise."
    }
  ]
}
```

### Multiple independent loci in one version

Use `selectedEntryIds` (plural) instead of `selectedEntryId`, one query per entry, and supply one decision per resolved locus:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Tighten stationarity and add the boundedness remark in the same version.",
  "selectedEntryIds": ["Assumptions stationarity", "Main convergence theorem"],
  "resolvedDecisions": [
    { "kind": "replace", "targetEntryId": "<entryId 1>", "replacementText": "..." },
    { "kind": "insert", "anchorEntryId": "<entryId 2>", "position": "after", "content": "..." }
  ]
}
```

A batch that mixes in-place kinds (`replace`/`insert`/`delete`) with a relocation (`move`/`copy`) still completes in a single accept call, but publishes as two versions — see SKILL.md's "One version per homogeneous batch."

## Preview, then accept

Every `CREATE_SUCCESSOR` call above only previews. A real run looks like:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "modelCalls": 1,
  "plannerCalls": 1,
  "tutorCalls": 0,
  "reviewerCalls": 0,
  "mutations": 0,
  "status": "awaiting_acceptance",
  "targetFilename": "research-concept-r06.md",
  "acceptanceToken": "…",
  "patchCount": 1,
  "manifestStatus": "NOT_PUBLISHED",
  "nextAction": "accept_successor"
}
```

(`modelCalls`/`plannerCalls` are always `1` here as a bookkeeping artifact of routing through the ambient-supplied planner — no network or model call is made. `tutorCalls`/`reviewerCalls` are always `0`: those roles are yours, in-conversation, not the engine's.)

The preview also carries a `mathDelta` naming every mathematical atom that existed before and is gone after — display equations, inline math, `\tag` values, LaTeX macros, `(Ec. N)` citations:

```json
"mathDelta": { "lost": [{ "id": "display:2a32c3fe", "kind": "display", "text": "x_{t+1}=A x_t" }], "added": [] }
```

Publishing requires echoing every lost id in `acknowledgedMathRemovals`; leave one out and the accept answers `MATH_REMOVALS_NOT_ACKNOWLEDGED` and writes nothing. Editing an equation counts as removing its previous form. Say out loud to the user what is leaving the document before you acknowledge it.

To publish, reuse the SAME `--serve` session opened at the top of this page — send the resolve line, then the preview line, then an accept line with `acceptSuccessor: true`, the returned `acceptanceToken`, and any `acknowledgedMathRemovals`, all over the same stdin:

```json
{"operation":"RESOLVE_TARGET","sourceFilename":"research-concept-r05.md","query":"..."}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"research-concept-r05.md","instruction":"...","selectedEntryId":"...","resolvedDecisions":[{"kind":"replace","targetEntryId":"<entryId from the resolve line>","replacementText":"..."}]}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"research-concept-r05.md","instruction":"...","selectedEntryId":"...","resolvedDecisions":[{"kind":"replace","targetEntryId":"<entryId from the resolve line>","replacementText":"..."}],"acceptSuccessor":true,"successorAcceptanceToken":"<the acceptanceToken from the preview line>","acknowledgedMathRemovals":["<every mathDelta.lost[].id from the preview line>"]}
```

The final line returns `status: "published"`, the new filename, `receiptId`, `manifestStatus: "COMMITTED"`, and `auditStatus`/`selfAuditStatus: "PASS"`. The acceptance token is single-use and lives only in that `--serve` process's memory — a preview from one process cannot be accepted by another invocation of `cli.mjs`. Keeping resolve, preview, and accept on the same stdin also means the engine's cold start is paid once for all three, not three times.

## Rejections are the safety net, not a bug

If your resolution or decision was wrong, the engine rejects it instead of silently doing something else:

- `WRONG_TARGET_ENTRY_ID` — re-resolve the locus (previous section) and rebuild the decision; do not reuse a stale or guessed ID.
- `ALTERED_REPLACEMENT_TEXT` — for an exact byte-preserving edit, copy the original block into `replacementText` unchanged.
- `NO_MATCHING_DECISION` / `AMBIGUOUS_MATCHING_DECISIONS` — every resolved locus in the request needs exactly one decision claiming it.
- `SOURCE_EQUALS_DESTINATION` / `HIERARCHY_CYCLE_DESTINATION_DESCENDANT` / `NO_OP_PLAN` — the described relocation or replacement is structurally impossible; go back to the user rather than forcing a shape that would satisfy validation without satisfying the request.

## The operations this host accepts

`STATUS`, `RESOLVE_TARGET`, `CREATE_INITIAL_REVISION`, `CREATE_SUCCESSOR`, `WITHDRAW_REVISION`,
`RESTORE_WITHDRAWN_REVISION`, `CHAT_DELIBERATION`, `CLOSE_DELIBERATION`, `MAINTENANCE`. Anything
else is refused by name with `UNKNOWN_OPERATION` rather than routed as something else.

Three of them are accepted but outside this skill's flow, and the distinction matters when reading
a response:

- `CHAT_DELIBERATION` / `CLOSE_DELIBERATION` hand a deliberation turn to the engine. SKILL.md tells
  you to hold the thread yourself instead, so you never open one. Their state is in memory only —
  nothing is written, nothing survives the process, and no conversation can reach another.
- `MAINTENANCE` answers `delegation_permitted` for external upkeep work. It carries no authority
  over the proposal (`documentAuthority: "FORBIDDEN"`) and mutates nothing.

`tests/proposal-deliberation-cli-operation-surface.test.mjs` pins this list. Adding or removing an
operation is a public change and must edit that test too.

## Managed revision lifecycle

To withdraw an eligible managed revision:

```bash
node .claude/skills/proposal-deliberation/engine/cli.mjs '{
  "operation": "WITHDRAW_REVISION",
  "sourceFilename": "research-concept-r05.md",
  "withdrawalReason": "superseded by a cleaner formulation"
}'
```

Omit `withdrawalOperationId` — the engine generates and returns it along with the audited backup location. To restore:

```bash
node .claude/skills/proposal-deliberation/engine/cli.mjs '{
  "operation": "RESTORE_WITHDRAWN_REVISION",
  "sourceFilename": "research-concept-r05.md"
}'
```

If more than one withdrawn record shares that filename, the engine asks for the exact `withdrawalOperationId` instead of guessing. Withdrawal and restore bypass target resolution, `resolvedDecisions`, and all planning — they are deterministic file operations with an audited recovery copy, unaffected by the ambient-model rewrite.

## Reading the result

Before telling the user an edit is complete, check the returned `status`, `manifestStatus`, `auditStatus`, `selfAuditStatus`, and `recoveryStatus`. Anything other than `published` / `COMMITTED` / `PASS` / `PASS` / `not_required` means the operation is not done — follow only the recovery or clarification the engine itself reports; never invent a revision or replay a request blindly.
