# Proposal: Nothing Agreed Stays In The Conversation

## What this change is

`close` becomes the operator's *cierre*. In their words: closing is when **everything agreed passes to the engine, and once it finishes the flow restarts and asks again whether I want the pilots or to keep deliberating.**

The restart half already works and needs nothing built. `cmd_offer` refuses `OFFER_UNANSWERED` when `--answer` is omitted, above `resolve_target`, and its own docstring commits to never reading a prior `offer` event's `answer` back to satisfy an omitted one — verified in source. The flow already asks again, every time.

What is missing is the half that makes reaching the restart mean anything: `close` today finishes over two axes, the position ladder (`impl_availability.position_honest`) and `AGREEMENT_DISAGREES`. Both ask whether a **written** claim is true. Neither asks whether a decision was ever written down at all. So a question is opened through `discuss`, answered out loud in the conversation, and `close` succeeds with the ledger still holding it open. The next session opens against a record that does not contain the decision and re-decides it freely.

**`close` gains exactly one refusal: a question whose exact `asked` text has no answered event after it. Nothing else changes.**

## What was cut, and why it is not coming back

The prior draft of this proposal had a second half — a report of "orphan agreements", a line in `AGREED.md` with no `settle` event — later re-scoped into porting `proposal-deliberation`'s derived-state index into `proposal-implementation`. **Both are cancelled, and the premise under both was false.**

The premise was that deliberation's index refuses on a hand edit and that implementation lacked parity. It does not. `document-state.ts`'s `loadDocumentState` **always** rebuilds the index from current bytes; the stored copy is a validated read cache. On a hand edit the sha changes, the cached lookup misses, `loadDerivedState` returns nothing, and unless `readOnly` the code **silently overwrites the stale cache** — no throw, no report, nothing surfaced to the operator. `INCOMPATIBLE_COMMITTED_STATE` cannot fire on that path: it needs an unchanged `documentSha256` with a differing `parserVersion`, and a hand edit changes the sha first.

Meanwhile `impl_position.write_spliced(..., expect_digest=...)` → `POSITION_HOLDER_MOVED` is a **real** compare-and-swap refusal at implementation's own write layer, keyed on a whole-file digest captured at read time, and `cmd_settle`'s four modes all converge on it. There was never parity to reach. Implementation is already ahead where it counts, and nothing is imported from `_core/deliberation` by this change.

The orphan-agreement report died separately and for its own reason: `implementations/Domain_Adaptation/.gitignore` ignores `.implementation/`, so a fresh clone carries all 113 `AGREED.md` checklist lines and zero ledger events. Any gate of that shape refuses all 113 forever after clone. That wall is the clone boundary, and every clone crosses it.

**Do not resurrect either. This proposal is one refusal.**

## The rule, stated exactly

At `close`, after `AGREEMENT_DISAGREES` and before the `cmd_position` refresh, read every `kind: "discuss"` event and bucket by the **exact, trimmed `asked` text**. A bucket is **open** when the **last event in ledger order** carrying that text has no non-empty `answered`. Any open bucket refuses `DISCUSSION_UNANSWERED`, naming every open text and printing a runnable `discuss --answer` command per text.

Three parts of that sentence are load-bearing and each was measured rather than reasoned about.

**Group by exact text, never by witness identity.** All 27 live `discuss` events on the reference target share the identical degenerate identity `{"kind": "record", "operand": null}`, because `--about record` is the operand-less kind and `offer`'s own published command hardcodes it. `_settle_discussed_events` groups by `(about.kind, about.operand)`, which is correct for `settle`'s narrow one-placement-to-one-witness binding and catastrophically wrong here: one bucket would hold every question ever asked, and answering any one of nine distinct questions would mark all nine answered. Exact-text grouping mirrors `_locate_settled_text`'s own exact-text discipline.

**"Open" means no answered event carries this text, never "this event has no answer".** `cmd_discuss` with `--answer` **appends a new event**; the original's `status` stays `"open"` forever. Measured on the live ledger: the text `what should the experiment contract still add before a campaign may be gated?` has seven events — five `open`, two `answered` — and it is not open. A per-event reading refuses forever, which is the failure class this repository has caught repeatedly.

**Last-in-ledger-order, not timestamp comparison.** `_now_iso8601` is second-granularity and two events can share a second; `impl_position.read_events` returns append-only file order, which is the true causal order. The rule uses position in the file and never compares `at` strings.

## Question settled here, 1: a recurring question answered once is not answered forever

`offer`'s `expand-contract` branch publishes a fixed question string, so every restart of the flow can re-ask the same bytes. Under a naive answered-once rule an answer from a month ago silently satisfies today's gate. The operator asked for this to be decided here, not deferred. It is decided against answered-once, and the evidence is the operator's own behaviour.

The full live shape of that recurring text, measured:

| `at` | status |
|---|---|
| 2026-08-29T06:15:44Z | open |
| 2026-08-30T01:50:36Z | open |
| 2026-08-30T01:50:48Z | open |
| 2026-08-30T02:13:49Z | open |
| 2026-08-30T04:13:30Z | **answered** |
| 2026-09-01T04:29:52Z | open |
| 2026-09-01T05:43:13Z | **answered** |

The operator re-asked on 09-01 and **answered it again**, 74 minutes later. They did not lean on the 08-30 answer, and under answered-once they would not have had to. Observed practice is already re-answer-on-re-ask; the last-word rule writes down what is already being done rather than inventing a policy.

**It costs nothing today.** Across all 12 distinct texts in the 27-event ledger, the last event in ledger order is `answered` in every single case. The open count is **0** under the last-word rule, exactly as it is under answered-once. The two rules differ on no live question.

**The failure asymmetry decides it.** If last-word is wrong, `close` refuses over a question that arguably has an answer — loud, and recoverable in one `discuss --answer` call whose exact text the refusal itself prints. If answered-once is wrong, `close` silently passes over a question re-asked today whose only answer predates the state it was asked about — silent, and precisely the leak this change exists to close. A loud recoverable error beats a silent one.

**It cannot refuse forever.** A re-ask is the only thing that reopens a bucket, and a re-ask is a deliberate act by whoever ran `discuss`. One `discuss --answer` always closes it. A fresh clone has an empty ledger, therefore zero buckets, therefore zero open — true rather than a false positive.

**Session and revision scoping are rejected, on evidence.** `cmd_discuss` registers only `--target --name --about --question --answer` — no `--session`, no `--revision` — and the appended event carries neither. Scoping to either would need a `discuss` event schema change this proposal otherwise avoids entirely. Worse, both reopen questions **nobody re-asked**: every new session, or every revision bump, would reopen all 12 texts at once and demand an answer per session forever. That is the unsatisfiable-across-a-boundary failure that killed the cancelled half, rebuilt on a different boundary.

**The settle doctrine is honoured, not contradicted.** `settle`'s `SETTLE_DISCUSSION_UNANSWERED` documents "ANY answered event satisfies this, never newest-wins — a later clarifying question must never retroactively erase an earlier answer, which would teach a caller not to ask one." That rationale is about **identity** grouping, where a later event in the bucket is usually a *differently worded* clarification. Under exact-text grouping a clarifying question has different text and forms its own bucket; it can never enter an answered question's bucket at all. Exact-text grouping therefore already delivers what "never newest-wins" was protecting, by construction, and the last-word rule only reaches the one case that doctrine never contemplated: the byte-identical question asked again. A test must prove the doctrine's own scenario still holds — a later differently-worded question does not reopen an earlier answered one.

**The retirement path is `discuss --answer`, and no new verb is added.** The operator already retires questions this way: the live ledger's 2026-09-01T06:04:15Z event answers *"Does this agreement belong in this record at all?"* with *"No. It leaves the record: nothing here can make it true or false, and an agreement nobody can act on is noise."* That is a retirement, with its reason, using the verb that exists. A `discuss --retire` verb is explicitly rejected: it would be a second exit that clears the gate **without the reason reaching the record**, and a hurried agent takes the cheaper exit.

**The published command must be shell-quoted, and this is a measured defect risk, not a precaution.** `discuss` requires `--question` as well as `--answer`, so retiring a question means re-supplying its exact text. **3 of the 12 live question texts contain an ASCII apostrophe** (`render's docstring`, `The bag figure's ... the agreement's`, `RAMP_CEILING's comment`). `offer`'s existing `expand-contract` string hardcodes single quotes and gets away with it only because its own fixed text has none. A naive single-quoted command would be broken for a quarter of the live corpus. `shlex.quote` is required, and `shlex` is **not currently imported** by `implementation_cli.py`. The proof must execute a published command for an apostrophe-bearing text as a subprocess, the same discipline `OfferCommandTests.test_expand_contract_command_string_is_runnable_and_writes_nothing` already uses.

## Question settled here, 2: the non-goal, in these words

**The gate proves a decision reached the record. It never proves the operator authored it.**

An agent can open a question and answer it itself, and nothing downstream can tell. That happened in this very session. The CLI cannot know who typed: `discuss` takes text on argv or stdin and records it. Neither deliberation's `documentSha256` nor implementation's own `POSITION_HOLDER_MOVED` changes this — both are optimistic concurrency over one in-flight write, not an authorship audit.

This is stated in the artifact, in the `cmd_close` docstring, and in `SKILL.md`, and it is not to be softened into an implied provenance guarantee.

## Measured facts this proposal rests on

Every one of these was read off the live reference target or the source during this phase, not inherited.

- 27 `discuss` events, **12 distinct `asked` texts**, all sharing `{"kind": "record", "operand": null}`.
- Under last-word-in-ledger-order: **0 open**. Under answered-once: **0 open**. The rules agree today.
- The recurring `offer` text has **7** events (5 open, 2 answered) — not the 5 an earlier draft asserted — and was answered **twice**.
- **3 of 12** texts contain an apostrophe.
- `cmd_offer` refuses `OFFER_UNANSWERED` on omitted `--answer` and reads no prior answer back.
- `cmd_discuss` registers no `--session` and no `--revision`; the event carries neither.
- `shlex` is not imported by `implementation_cli.py`.
- `openspec/specs/` does not exist in this repository.

## Scope

### In Scope

- `_open_discussions(target, name)` — a new reader beside `_settle_discussed_events`, deliberately **not** reusing it. Buckets `discuss` events by `event["asked"].strip()` and returns the buckets whose last event in ledger order has no non-empty `answered`.
- `DISCUSSION_UNANSWERED` in `cmd_close`, a third independent axis after `AGREEMENT_DISAGREES` and before the `cmd_position` refresh.
- The refusal names every distinct open text and prints a `shlex.quote`-escaped, directly runnable `discuss --answer` command per text.
- `import shlex`.
- Doc updates in `SKILL.md` and `references/usage.md`: the new refusal, the last-word rule and why it does not contradict `settle`'s doctrine, the retirement path, and the authorship non-goal.
- Red-first tests with mutation proofs for each rule.

### Out of Scope

- **Any orphan-agreement report, index, gate, baseline, or adoption boundary.** Cancelled; the premise was false and the clone boundary is permanent.
- **Anything imported from `_core/deliberation`.**
- A `discuss --retire` verb, or any second way for a question to stop being open.
- Any change to the `discuss`, `settle`, `offer`, or `close` ledger event schemas. This is a pure reader of events that already exist.
- Session or revision scoping of an answer, and the `discuss` flags that would require.
- Any flow-restart machinery. `cmd_offer` already does it.
- Editing the reference target's `AGREED.md` or ledger.
- Any change under `.claude/skills/_core/implementation/`.

## Capabilities

### New Capabilities

- `close-discussion-gate`: `close` refuses while the last ledger event carrying a distinct question text is unanswered, and publishes the runnable command that retires each one.

### Modified Capabilities

- None. `openspec/specs/` does not exist in this repository; capabilities are declared per change.

## Approach

1. **`_open_discussions`** reads the ledger once, buckets by trimmed `asked`, and returns `{text: last_event}` for buckets whose last event is unanswered. It does not filter on `status` — `status` is per-event and is not the question's state. `_settle_discussed_events` is left exactly as it is; merging the two into one helper whose caller cannot tell which grouping rule it received is the mistake to avoid.
2. **`cmd_close`** gains the third axis in the documented position — after the agreement check, before the refresh — for the reason the existing comment already gives: the refresh must not be able to alter what the refusal is about.
3. **The refusal message** lists each open text and its `shlex.quote`d command. This follows the "publishes a runnable command" discipline `offer` already keeps.
4. **Red-first throughout** (`strict_tdd: true`): each rule is shown failing before it passes, and each rule is proven by a mutation a weaker rule would survive.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `.claude/skills/proposal-implementation/scripts/implementation_cli.py` | Modified | `import shlex`, `_open_discussions` (new), `cmd_close` |
| `.claude/skills/proposal-implementation/SKILL.md` | Modified | `close` refusal set, last-word rule, retirement path, authorship non-goal |
| `.claude/skills/proposal-implementation/references/usage.md` | Modified | Same |
| `tests/test_proposal_implementation.py` | Modified | Red-first + mutation proofs + subprocess proof |
| `.claude/skills/_core/implementation/*.py` | **Not touched** | No shared-core symbol is needed |
| `implementations/Domain_Adaptation/**` | **Not touched** | Read as a fixture source only |

## Review Workload Forecast

| Component | Est. changed lines |
|---|---|
| `_open_discussions` incl. this file's docstring density | ~70 |
| `cmd_close` refusal + comment + docstring paragraph | ~60 |
| `SKILL.md` + `usage.md` | ~60 |
| Tests (red-first, 3 mutation proofs, doctrine-preservation, apostrophe subprocess, refusal shape) | ~250 |
| **Total** | **~440** |

**Decision needed before apply: No**
**Chained PRs recommended: No**
**400-line budget risk: Medium**

This is the small change the operator expected — one reader, one refusal — and the prior forecast's High/chained verdict for ~550–900 lines belonged to a two-slice scope that no longer exists. It lands slightly over 400 for one reason worth stating plainly: this module's docstrings routinely run 30–60 lines per function and its test file is over 17,000 lines, so line count here tracks prose density rather than reviewer burden. Roughly 250 of the 440 are tests.

It should not be chained. There is no split that leaves both halves independently deliverable: a refusal without its tests is unverified, and a refusal without its docs is undocumented behaviour in a skill whose contract *is* its docs. If apply overruns materially, stop and re-decide with the operator rather than shipping a half-guard.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The gate refuses forever because grouping reads per-event | Medium | Measured: 5 open events for the recurring text, and it is not open. A test builds that exact 5-open/2-answered shape and asserts 0 |
| Identity grouping is reused by mistake and cross-answers questions | Medium | All 27 live events share one identity. A mutation test swaps the grouping key and must fail |
| The last-word rule is read as contradicting `settle`'s "never newest-wins" | Medium | Reconciled in this proposal, the docstring and `SKILL.md`; a test proves a later differently-worded question does not reopen an earlier answer |
| A stale answer silently satisfies today's gate | **Closed by design** | The last-word rule; measured against the operator's own re-answer behaviour |
| The published command is not runnable for a real question text | **High without `shlex`** | 3 of 12 live texts carry an apostrophe. A test executes a published command for such a text as a subprocess |
| An agent answers its own question to clear the gate | Medium | Unmitigable by this CLI. Stated as an explicit non-goal in three places, never softened |
| Forge picks up target vocabulary | Low | `FORGE_VOCABULARY_FLOOR` (word-boundary regex) and `FORGE_LEXICON` rule B (derived from the target's live module basenames — must be **run**, never reasoned about). `CoreNamesNoDomainTests` substring-scans `_core/implementation/*.py`, which this change does not touch |
| Fixture text drawn from the reference target leaks domain words | Medium | Fixtures live in `tests/`, deliberately unguarded; no target string reaches a scanned surface. Prefer synthetic texts that reproduce only the *shape* (repeat, apostrophe, shared identity) |

## Rollback Plan

The change is a **pure reader**. No event schema changes, no `AGREED.md` bytes change, no persisted state is introduced.

Revert the commit. `cmd_close` returns to its two-axis ladder and closes exactly as it does today. Any `discuss` event written meanwhile is an ordinary event the old code already reads and ignores. Nothing on disk needs editing, in this repository or in any target. Verify by running `verify` and `close` against `implementations/Domain_Adaptation/MIL-CREDA`.

## Dependencies

- `implementations/Domain_Adaptation/MIL-CREDA` remains readable as a fixture source (27 `discuss` events across 12 distinct texts).
- Gate: `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` **and** `npm test`. Baseline to preserve: `Ran 2039 tests, OK, skipped=3`; node 385/385.

## Success Criteria

- [ ] **Red-first**: `close` succeeds today on a state whose newest event for a text is unanswered, and refuses `DISCUSSION_UNANSWERED` after the change. Both runs recorded.
- [ ] **Mutation proof, grouping key**: replacing exact-`asked`-text grouping with `about`-identity grouping makes a test fail, built on the measured all-events-share-one-identity case.
- [ ] **Mutation proof, open rule**: replacing "the last event carrying this text is answered" with "this event has no answer" makes a test fail, built on the measured 5-open/2-answered shape with expected open count 0.
- [ ] **Mutation proof, last-word rule**: replacing last-word with answered-once makes a test fail on an ask-answer-ask sequence.
- [ ] **Doctrine preserved**: a later, differently-worded question does not reopen an earlier answered one.
- [ ] The refusal names each open text and prints a command that is **executed as a subprocess** in test — including one text containing an apostrophe — and observed to retire that question.
- [ ] Measured on the reference target and recorded: open count under the shipped rule (expected **0**).
- [ ] `FORGE_VOCABULARY_FLOOR` and `FORGE_LEXICON` rule B are **run** and report zero violations across shipped skill files.
- [ ] Baseline preserved: 2039 Python tests OK (skipped=3), node 385/385.

## Proposal question round

Settled in this document rather than deferred, per instruction. Two assumptions remain the operator's to overturn:

1. **Last-word-per-question-text is the answer scope.** It costs nothing today (0 open under either rule) and matches the operator's own observed re-answer-on-re-ask behaviour. Overturn it if a question re-asked mechanically by `expand-contract` should *not* require a fresh answer before the next `close`.
2. **The refusal is a hard gate at `close`, not a report at `verify`/`probe`.** This follows the codebase's own stated "gating stays at close" convention, and unlike the cancelled agreement half there is no clone boundary making it unsatisfiable. Overturn it if the gate should first ship as a report for one adoption pass.
