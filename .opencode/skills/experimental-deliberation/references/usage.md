# Experimental Deliberation — examples and help

See [SKILL.md](../SKILL.md) for the tutor-role conditioning, the canonical form, and the discipline around external validation. This page is worked examples only: checking `STATUS`, creating v1, resolving a locus, building `resolvedDecisions`, and the preview → accept → publish cycle.

Every request below is sent through this skill's own launcher, which is what supplies the domain profile:

```bash
node skills/experimental-deliberation/cli.mjs
```

None of it requires `ANTHROPIC_API_KEY` or any model configuration — no call on this path reaches a network or a model. The response shapes shown are the ones the engine's own public projection emits; treat field names as exact and field values as illustrative.

## Checking `STATUS` before deciding a base

Read-only, keyless, no model call. Run it before reading a source, loading a document, or touching anything in `experiments/`:

```bash
node skills/experimental-deliberation/cli.mjs '{ "operation": "STATUS" }'
```

Against an `experiments/` directory holding a managed `v01`/`v02` pair, one managed-looking-but-unmarked `v03` (missing the artifact marker, so it does **not** count as managed), and an unrelated `draft-plan.md`:

```json
{
  "status": "ok",
  "operation": "STATUS",
  "managedRevisions": [
    { "filename": "experiments-domain-shift-baseline-sweep-v01.md", "lineage": "domain-shift-baseline-sweep", "revisionNumber": 1, "isLatest": false },
    { "filename": "experiments-domain-shift-baseline-sweep-v02.md", "lineage": "domain-shift-baseline-sweep", "revisionNumber": 2, "isLatest": true }
  ],
  "latest": "experiments-domain-shift-baseline-sweep-v02.md",
  "multipleActive": false,
  "candidates": [],
  "nonManagedFiles": ["draft-plan.md", "experiments-domain-shift-baseline-sweep-v03.md"]
}
```

Pass `sourceFilename` to classify one candidate base in the same call:

```bash
node skills/experimental-deliberation/cli.mjs '{ "operation": "STATUS", "sourceFilename": "experiments-domain-shift-baseline-sweep-v01.md" }'
```

```json
{ "...": "same fields as above, plus:", "sourceClassification": "OLDER_MANAGED", "newerRevisionNumbers": [2] }
```

`sourceClassification` is one of `LATEST`, `OLDER_MANAGED` (with `newerRevisionNumbers`), `UNMANAGED`, or `NOT_FOUND`. `STATUS` never mutates: no file in `experiments/` is created, moved or changed by it. A confirmed backup move is something *you* do afterwards with a plain file move. `STATUS` also answers on a project with no `experiments/` directory yet — the exact pre-creation state `CREATE_INITIAL_REVISION` exists for — with an empty inventory. A directory that exists but cannot be read fails closed with an error instead of reporting "empty."

## Creating the first managed version

Only when `STATUS` reports zero managed revisions. Both required sources must exist on disk first:

```
guidance/data-paper/<paper-name>/<paper-name>.md    (required)
proposals/                                          (required — at least one document)
guidance/paper-guide/<name>/<name>.md               (optional)
```

Because [v1 is checked, not exempt](../SKILL.md#creating-v1-checked-by-the-same-gate-as-every-successor), the idea text itself must already carry both of this domain's declared labels, `**Dataset:** …` and `**Validation scheme:** …`, and **each on its own line**: both rules match at line start, so folding a declaration into the middle of a sentence does not satisfy them.

```bash
node skills/experimental-deliberation/cli.mjs '{
  "operation": "CREATE_INITIAL_REVISION",
  "instruction": "Domain shift baseline sweep. Testing whether the proposed adaptation term improves held-out accuracy under domain shift without target labels. Claim C1: the method needs no target labels. Claim C2: the gain survives a reduced labelled budget.\n\n**Dataset:** domain-shift-benchmark (standard train/validation/test split as distributed).\n\n**Validation scheme:** paired Wilcoxon signed-rank test, 5 seeds, 3 repetitions per seed."
}'
```

Driven verbatim (2026-09-13), against a fixture carrying both required sources:

```json
{
  "status": "created",
  "operation": "CREATE_INITIAL_REVISION",
  "targetFilename": "experiments-domain-shift-baseline-sweep-v01.md",
  "targetRevision": "v01",
  "targetSha256": "1a792177fd2a918c25c26310e482d2b27ba5240ea0b8060cef1a144c78fb2264",
  "canonicalMetadata": { "schemaVersion": 1, "title": "Domain shift baseline sweep.", "sectionHeading": "Testing whether the proposed adaptation term improves held-out accuracy under domain shift without target labels." },
  "mutations": 1,
  "receiptId": "experiments-domain-shift-baseline-sweep-v01.md:v01",
  "manifestStatus": "NOT_TRACKED",
  "nextAction": null
}
```

Two things to read carefully in that response. The **filename slug is derived from the first sentence of your idea** — the title and section heading come from the idea text too, never from a fixed skeleton — so write that first sentence as the lineage name you want; a short, standalone first sentence (`"Domain shift baseline sweep."`) is what produced the clean `domain-shift-baseline-sweep` slug above. And `targetRevision` reports **`v01`, the same label the filename carries** — `artifact.revisionLabel(1)`, read from this domain's own profile, never a hardcoded `r01`: the filename is the authority and the label agrees with it.

If a required source directory is absent:

```json
{
  "status": "blocked",
  "operation": "CREATE_INITIAL_REVISION",
  "nextAction": "supply_required_source",
  "blockers": [{ "code": "REQUIRED_SOURCE_MISSING", "message": "Required source \"guidance/data-paper\" is missing; CREATE_INITIAL_REVISION cannot proceed without it." }]
}
```

If a managed revision already exists, it blocks with `MANAGED_PROPOSAL_ALREADY_EXISTS` — it never overwrites or duplicates one.

### v1 is checked before it is written

**v1 is checked, not exempt.** Source fragments are pasted in verbatim under a `## Paper Guide Reference` heading, one `### <path>` per fragment — but `CREATE_INITIAL_REVISION` runs the composed candidate through the identical `violations()` gate `CREATE_SUCCESSOR` runs, before any write (see [SKILL.md](../SKILL.md#creating-v1-checked-by-the-same-gate-as-every-successor)). If a pasted fragment carries a filled report-table cell, or a URL with no verification tag, v1 is refused outright:

```json
{
  "status": "blocked",
  "blockers": [{ "code": "INITIAL_REVISION_CANONICAL_FORM_VIOLATION", "message": "…: url-without-verification-marker -- https://example.org/untagged-source must be followed by [pending-verification] or [verified: YYYY-MM-DD]; an unmarked URL claims a search that left no trace" }]
}
```

Driven for real: a source fragment containing one bare URL and nothing else wrong never becomes a file on disk. So there is nothing to repair in v1 for either of those two conditions *after* creation — a v1 that exists already satisfies them, exactly as any successor does; asking the reader to check for a violation that would have blocked the write is asking them to repair a file that cannot exist. What is still worth a read once v1 is created is what the gate does **not** check: whether a pasted source fragment says what you meant it to, and whether the idea text you sent is the document you actually want to build on.

## Open one `--serve` process for the whole deliberation

The acceptance token lives only in that process's memory, and the host's cold start is paid once per process. Resolve, preview and accept are three calls; send all three — and every later version's calls — down the same stdin:

```bash
node skills/experimental-deliberation/cli.mjs --serve
```

Every example below is one JSON line to that process.

## Resolving a locus before deciding

```json
{ "operation": "RESOLVE_TARGET", "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md", "query": "Baselines comparison" }
```

```json
{ "status": "resolved", "operation": "RESOLVE_TARGET", "entryId": "…", "blocked": false, "question": null }
```

Write the query as **distinctive words from the target heading**, not a sentence describing it. The resolver scores a heading by how many query words appear as substrings of its heading line, so only rare words help. Drop punctuation (the query truncates at the first `,;:.`), drop the section number, keep accents exactly as the heading spells them.

- ✅ `"Baselines comparison"`
- ❌ `"## 4. Baselines: comparison table"` — punctuation truncates it to `"4"`

If `blocked` is `true`, the query matched more than one candidate — **remove the terms the question names, never add more**. Adding words to "narrow" a query widens it. If the reason is `SUCCESSOR_TARGET_NOT_FOUND`, no heading matched: you described the section's content instead of its title.

An experiment whose heading carries its own `[exp:E1]` declaration resolves from a query of just `E1` (measured), so keep the declaration in the heading rather than in the body.

Several loci in one call:

```json
{ "operation": "RESOLVE_TARGET", "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md", "queries": [{ "query": "Baselines comparison" }, { "query": "Experiment E1 protocol" }] }
```

```json
{ "status": "resolved", "operation": "RESOLVE_TARGET", "results": [{ "query": "Baselines comparison", "entryId": "…", "blocked": false, "question": null }, { "query": "Experiment E1 protocol", "entryId": "…", "blocked": false, "question": null }] }
```

## What a well-formed experiment block looks like

This is the shape to put in `replacementText`. It satisfies every canonical-form rule: empty report cells, a tagged URL, a baseline row carrying both a repository and a venue year, a criterion under its bold label, and a declared identifier a claim can cite.

```markdown
## Experiment [exp:E1] — labelled-budget sweep

Sustains claim C1 [tests:E1]: the method needs no target labels.

**Hypothesis.** Held-out accuracy of the adapted arm does not fall below the source-only arm as the labelled budget shrinks.

**Variables.** Independent: labelled examples per class (k). Dependent: held-out accuracy, macro-F1. Controlled: architecture, optimiser, seed set.

**Data and splits.** The benchmark's own train/validation/test partition, unchanged.

**Protocol.** Five seeds per cell; paired comparison against the source-only arm on the same seeds; Wilcoxon signed-rank at alpha = 0.05.

- **Success criterion:** the adapted arm's mean held-out accuracy is not lower than the source-only arm's at every value of k, with the paired test not rejecting equality.

**Priority.** Core. **Estimated cost.** 30 runs, roughly 6 GPU-hours.

### Expected report

| Arm | k=1 | k=5 | k=20 |
| --- | --- | --- | --- |
| Source only |  |  |  |
| Adapted |  |  |  |

![Held-out accuracy against labelled examples per class](figures/accuracy-vs-k.png)

### Baselines

| Baseline | Repository | Venue |
| --- | --- | --- |
| Alpha-Net | [repository](https://example.org/alpha-net) [pending-verification] | ICML 2015 |
| Beta-Net | https://example.org/beta-net [verified: 2026-09-08] | NeurIPS 2019 |
```

Three things to notice, each of which is a rule and not a style choice:

- The report table's body cells are **empty**, and its first header cell is `Arm`, so the fabricated-value rule applies to every column past the first.
- The baselines table's first header cell is **`Baseline`**, which is the only thing that exempts its cells from that rule. Spell it that way when you want the exemption; do not when you do not.
- Both URLs are tagged, one per style. `[verified: 2026-09-08]` says a search on that date reached it; `[pending-verification]` says nobody has.

## Building `resolvedDecisions` and applying

Every `CREATE_SUCCESSOR` preview needs `changeSummary`, or it is blocked with `CHANGE_SUMMARY_REQUIRED`.

### Replace (the common case)

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "instruction": "Add the missing venue year to the Beta-Net baseline row and tag its repository URL.",
  "selectedEntryId": "Baselines comparison",
  "changeSummary": {
    "what": "Completed the Beta-Net baseline row with its venue year and a verification tag.",
    "why": "A baseline without a venue year and a checkable repository is not a comparison a reviewer can follow."
  },
  "resolvedDecisions": [
    { "kind": "replace", "targetEntryId": "<entryId from the resolve step>", "replacementText": "| Baseline | Repository | Venue |\n| --- | --- | --- |\n| Alpha-Net | [repository](https://example.org/alpha-net) [verified: 2026-09-08] | ICML 2015 |\n| Beta-Net | [repository](https://example.org/beta-net) [verified: 2026-09-08] | NeurIPS 2019 |\n\n" }
  ]
}
```

### Insert

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "instruction": "Add an ablation experiment removing the adaptation term, after the main experiment.",
  "selectedEntryId": "Experiment E1 labelled budget sweep",
  "changeSummary": {
    "what": "Added ablation experiment E2, removing the adaptation term.",
    "why": "Claim C1 attributes the gain to that term, and nothing currently isolates it."
  },
  "resolvedDecisions": [
    { "kind": "insert", "anchorEntryId": "<entryId>", "position": "after", "content": "## Experiment [exp:E2] — adaptation term ablation\n\nSustains claim C1 [tests:E2] …\n\n" }
  ]
}
```

### Delete

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "instruction": "Remove the sentence claiming the adapted arm outperforms every published baseline — nothing has been run.",
  "selectedEntryId": "Motivation",
  "changeSummary": {
    "what": "Removed an asserted outcome from the motivation section.",
    "why": "This document plans work that has not happened; an asserted result is a fabricated one."
  },
  "resolvedDecisions": [
    { "kind": "delete", "targetEntryId": "<entryId>", "instructionEvidence": "Remove the sentence claiming the adapted arm outperforms every published baseline.", "reason": "asserted outcome in a plan" }
  ]
}
```

### Move (literal) and copy (adaptive)

```json
{
  "kind": "move",
  "sourceEntryIds": ["<source entryId>"],
  "destinationAnchorId": "<destination entryId>",
  "position": "before",
  "moveMode": "LITERAL",
  "removeSource": true,
  "cleanupLevel": "NONE"
}
```

A `LITERAL` relocation carries the content byte-for-byte (omit `transformedContent`). An `ADAPTIVE` one requires you to supply the reworded text yourself in `transformedContent` — the engine never invents it, and neither should you without a stated basis.

### Several loci in one version

Use `selectedEntryIds` (plural), one query per entry, and one decision per resolved locus:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "instruction": "Tighten E1's success criterion and complete the baselines table in the same version.",
  "selectedEntryIds": ["Experiment E1 labelled budget sweep", "Baselines comparison"],
  "changeSummary": { "what": "…", "why": "…" },
  "resolvedDecisions": [
    { "kind": "replace", "targetEntryId": "<entryId 1>", "replacementText": "…" },
    { "kind": "replace", "targetEntryId": "<entryId 2>", "replacementText": "…" }
  ]
}
```

## Preview, then accept

Every `CREATE_SUCCESSOR` above only previews:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "status": "awaiting_acceptance",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "targetFilename": "experiments-domain-shift-baseline-sweep-v03.md",
  "acceptanceToken": "…",
  "patchCount": 2,
  "modelCalls": 1,
  "plannerCalls": 1,
  "tutorCalls": 0,
  "reviewerCalls": 0,
  "mutations": 0,
  "manifestStatus": "NOT_PUBLISHED",
  "nextAction": "accept_successor",
  "preservationDelta": { "lost": [], "added": [] },
  "mathDelta": { "lost": [], "added": [] }
}
```

`patchCount` is **2** for a one-decision batch, and that is not a mistake: on an all-`replace` batch the engine appends its own edit over the `## Changes` block from your `changeSummary`. `modelCalls`/`plannerCalls` are always `1` as a bookkeeping artifact of routing through the ambient-supplied planner — no network or model call is made. `tutorCalls`/`reviewerCalls` are always `0`: those roles are yours, in this conversation.

`mathDelta` is a permanent legacy alias for the identical `preservationDelta` object; read either. A version that drops something looks like this:

```json
"preservationDelta": {
  "lost": [
    { "id": "url:https://example.org/beta-net", "kind": "url", "text": "https://example.org/beta-net" },
    { "id": "baseline:3f2a19c4", "kind": "baseline", "text": "Beta-Net" }
  ],
  "added": []
}
```

Say out loud to the user what is leaving the document before you acknowledge it. Then publish by resending the identical request with the acceptance fields appended:

```
{"operation":"RESOLVE_TARGET","sourceFilename":"experiments-domain-shift-baseline-sweep-v02.md","query":"Baselines comparison"}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"experiments-domain-shift-baseline-sweep-v02.md","instruction":"…","selectedEntryId":"Baselines comparison","changeSummary":{"what":"…","why":"…"},"resolvedDecisions":[{"kind":"replace","targetEntryId":"<entryId>","replacementText":"…"}]}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"experiments-domain-shift-baseline-sweep-v02.md","instruction":"…","selectedEntryId":"Baselines comparison","changeSummary":{"what":"…","why":"…"},"resolvedDecisions":[{"kind":"replace","targetEntryId":"<entryId>","replacementText":"…"}],"acceptSuccessor":true,"successorAcceptanceToken":"<from the preview line>","acknowledgedRemovals":["url:https://example.org/beta-net","baseline:3f2a19c4"]}
```

Leave a lost id out and the accept answers `MATH_REMOVALS_NOT_ACKNOWLEDGED` and writes nothing. (`acknowledgedMathRemovals` is accepted as an equivalent field name; the two are merged into one set.)

The acceptance token is single-use and lives only in that `--serve` process's memory: a preview from one process cannot be accepted by another invocation.

### Resolved: the accept turn publishes in this domain

A successful publish returns `status: "published"`, the new filename, `targetSha256`, `receiptId`, `manifestStatus: "COMMITTED"`, and `auditStatus`/`selfAuditStatus: "PASS"`. **This domain reaches that.** Driving the full `resolve → preview → accept` cycle above against a real project (2026-09-13), on a v01 created exactly as shown earlier in this page, produced:

```json
{"status":"resolved","operation":"RESOLVE_TARGET","entryId":"composite:72:0cd72369d4fa6c88","blocked":false,"question":null,"text":"## Testing whether the proposed adaptation term improves held-out accuracy under domain shift without target labels.\n\n…"}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"experiments-domain-shift-baseline-sweep-v01.md","status":"awaiting_acceptance","targetFilename":"experiments-domain-shift-baseline-sweep-v02.md","acceptanceToken":"l6k6lEbqwNH9Ghqb5IKWdBa47_mXmyBpOw457pbh25U","patchCount":2,"manifestStatus":"NOT_PUBLISHED","nextAction":"accept_successor"}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"experiments-domain-shift-baseline-sweep-v01.md","status":"published","targetFilename":"experiments-domain-shift-baseline-sweep-v02.md","targetSha256":"f6f79c273001ca9657f51c322bacfc8fc480e6cd453efcac31d27cec7e12292c","receiptId":"experiments-domain-shift-baseline-sweep-v02.md:v02","manifestStatus":"COMMITTED","auditStatus":"PASS","selfAuditStatus":"PASS","nextAction":null}
```

(`entryId` and `acceptanceToken` are session-specific, like every other illustrative field on this page; `status`, `manifestStatus`, `auditStatus` and `selfAuditStatus` are not.)

The successor stood on disk beside its source. An earlier diagnosis of this path, on 2026-09-08, reported `INVALID_TARGET_REVISION` and blamed a hardcoded `-r(\d+)\.md$` in the shared core. Re-measured, that cause is not in the source and never described this code: `nextSuccessorTarget`, `parseManagedRevision` and `strictRevisionLabel` all read the revision pattern from this domain's own profile (`DOMAIN.artifact.revisionPattern`, `"v"`), so a `…-v0N.md` successor parses and validates exactly as an `…-r0N.md` one would in the mathematical sibling. See [SKILL.md](../SKILL.md#resolved-the-accept-turn-publishes-in-this-domain) for the full re-measurement.

Everything up to and including the write is real and worth running: resolution, patch compilation, candidate validation, the canonical-form rules, `preservationDelta`, the source-authority detection, and the publish itself all execute exactly as documented above. Still, read `status`, `manifestStatus`, `auditStatus` and `selfAuditStatus` before telling the user an edit landed — anything other than `published` / `COMMITTED` / `PASS` / `PASS` means it did not.

## When the candidate breaks the canonical form

A candidate violating any canonical-form rule fails validation, and the accept turn answers:

```json
{ "status": "blocked", "category": "recovery", "message": "CANDIDATE_VALIDATION_FAILED", "patchCount": 0, "nextAction": "inspect_error" }
```

**The public response does not name which rule failed.** The projection that builds it keeps `status`, `category` and `message` and drops the validation detail. So the message is where to start, not where to finish — go back to the bytes you wrote and check them against the rules, in this order:

1. Every external URL followed immediately by `[pending-verification]` or `[verified: YYYY-MM-DD]` — including URLs inside table cells and Markdown link targets.
2. Every report-table body cell past column one free of digits.
3. Every baselines-table body row carrying a repository URL and a four-digit venue year, with the year coming from the venue and not from a verification tag.
4. Every `[tests:X]` / `(Exp. X)` citation resolving to an `[exp:X]` this document declares, and no identifier declared twice.
5. Well-formed Markdown: complete blocks, blank-line separation preserved at block boundaries.

The same projection applies to a source-authority block:

```json
{ "status": "blocked", "category": "recovery", "message": "SOURCE_AUTHORITY_CONFLICT" }
```

That fires when a line asserts an achieved result. The right fix is almost always to rewrite the sentence as planned work, not to acknowledge it. When the sentence genuinely quotes somebody else's published result, echo the conflict ids in `acknowledgedSourceConflicts` on the accept turn — and tell the user which sentence and whose result it is before you do.

## Rejections are the safety net, not a bug

- `CHANGE_SUMMARY_REQUIRED` — the preview turn carried no `changeSummary`.
- `WRONG_TARGET_ENTRY_ID` — re-resolve the locus and rebuild the decision; never reuse a stale or guessed ID.
- `ALTERED_REPLACEMENT_TEXT` — for an exact byte-preserving edit, copy the original block unchanged.
- `NO_MATCHING_DECISION` / `AMBIGUOUS_MATCHING_DECISIONS` — every resolved locus needs exactly one decision claiming it.
- `OVERLAPPING_PATCHES` — two edits over one span. On an all-`replace` batch the engine appends its own edit over the `## Changes` block, so do not also target that block yourself.
- `SOURCE_EQUALS_DESTINATION` / `HIERARCHY_CYCLE_DESTINATION_DESCENDANT` / `NO_OP_PLAN` — the relocation or replacement described is structurally impossible. Go back to the user rather than forcing a shape that satisfies validation without satisfying the request.
- `MULTIPLE_ACTIVE_REVISIONS` — a tied latest across lineages. Ask for the exact `sourceFilename`.

## The operations this host accepts

`STATUS`, `RESOLVE_TARGET`, `CREATE_INITIAL_REVISION`, `CREATE_SUCCESSOR`, `WITHDRAW_REVISION`, `RESTORE_WITHDRAWN_REVISION`, `CHAT_DELIBERATION`, `CLOSE_DELIBERATION`, `MAINTENANCE`. Anything else is refused by name with `UNKNOWN_OPERATION` rather than routed as something else.

Three are accepted but outside this skill's flow:

- `CHAT_DELIBERATION` / `CLOSE_DELIBERATION` hand a deliberation turn to the engine. SKILL.md tells you to hold the thread yourself, so you never open one. Their state is in memory only — nothing is written, nothing survives the process.
- `MAINTENANCE` answers `delegation_permitted` for external upkeep work. It carries no authority over the document and mutates nothing.

Every operation except `STATUS` and `RESOLVE_TARGET` requires a non-empty `instruction` string, or the host rejects the envelope with `INSTRUCTION_REQUIRED`.

## Managed revision lifecycle

```bash
node skills/experimental-deliberation/cli.mjs '{
  "operation": "WITHDRAW_REVISION",
  "instruction": "Withdraw the superseded plan.",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v03.md",
  "withdrawalReason": "superseded after the protocol search was redone"
}'
```

Omit `withdrawalOperationId` — the engine generates and returns it with the audited backup location. The **base revision cannot be withdrawn**: aiming this at `…-v01.md` answers `blocked` with the warning `BASE_REVISION_WITHDRAWAL_BLOCKED` and changes nothing (measured). To restore:

```bash
node skills/experimental-deliberation/cli.mjs '{
  "operation": "RESTORE_WITHDRAWN_REVISION",
  "instruction": "Restore the withdrawn plan.",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v03.md"
}'
```

If more than one withdrawn record shares that filename, the engine asks for the exact `withdrawalOperationId` instead of guessing. Withdrawal and restore bypass target resolution, `resolvedDecisions` and all planning — they are deterministic file operations with an audited recovery copy.

## Reading the result

Before telling the user an edit is complete, check `status`, `manifestStatus`, `auditStatus`, `selfAuditStatus` and `recoveryStatus`. Anything other than `published` / `COMMITTED` / `PASS` / `PASS` / `not_required` means the operation is not done. Follow only the recovery the engine itself reports; never invent a revision or replay a request blindly.
