# Spec: Nothing Agreed Stays In The Conversation

## Purpose

The discipline this change replaces depends on the agent at three points: opening a
discussion when something needs deciding, recording the answer where the record can
see it, and using `settle` instead of typing a line by hand. This change is one
change with two halves because it moves two of those three points from a promise the
agent might forget into a mechanism the CLI enforces.

**Half 1 — `close-discussion-gate`.** Moves the *second* point. `close` refuses when
the record does not hold an answer to a question that was asked. This is the gate.

**Half 2 — `proactive-discussion-publication`.** Moves the *first* point. At the exact
places the engine has already computed that something is undecided, its output
publishes a directly runnable `discuss` command naming that specific undecided thing,
rather than depending on the agent to remember `discuss` exists.

**The third point — using `settle` instead of hand-editing a checklist file — is out
of scope and stays a promise.** The bound that makes this survivable is measured, not
assumed, and is stated below rather than softened.

## Non-Goal, Stated Exactly

> **The gate proves a decision reached the record. It never proves the operator
> authored it.** An agent can open a question and answer it itself, and nothing
> downstream can tell. That happened in this very session.

This sentence governs both halves. Half 1 cannot distinguish an operator's answer
from an agent's own; Half 2's new publication points make it *easier*, not harder,
for an agent to run the very `discuss --answer` command it just self-served, because
the command is now printed for it. Neither half is a provenance guarantee, and this
document does not soften that into one, per the constraint that this statement not be
weakened anywhere it is repeated (`cmd_close`'s docstring, `SKILL.md`).

## Boundary: What Remains Outside Both Halves

An agreement typed by hand directly into a checklist file, instead of placed through
`settle`, is detected by neither half and prevented by neither half. **Measured
bound:** `cmd_gate` reads `agreements_state` **zero times**. Its only real call sites
in `implementation_cli.py` are the holder-resolution paths at (module-relative)
`agreements_state(...)["holders"]` used inside the settle write path (twice — the
create-path holder search and the attach-path holder search) and the two read
surfaces, `cmd_close` (the `AGREEMENT_DISAGREES` axis) and `cmd_verify` (the reported
`agreements` block). `cmd_gate` — the command that decides whether a launch or a spend
may proceed — never calls it.

A hand-edited agreement therefore corrupts the *record of what was decided*: a reader
of the checklist file believes something was agreed that never went through `discuss`
→ `settle`, or vice versa. **It cannot cause a launch or a spend**, because nothing
that gates a launch or a spend ever reads that state. This is the bound that keeps
"the third point stays a promise" survivable, and it must be stated as measured fact
in the shipped docstrings and `SKILL.md`, not asserted from memory.

## Capabilities

### New Capabilities

- `close-discussion-gate` — `close` refuses while the last ledger event carrying a
  distinct question text is unanswered, and publishes the runnable command that
  retires each one. (Unchanged from the proposal.)
- `proactive-discussion-publication` — at the specific points the engine has already
  computed an undecided thing, its output publishes a runnable, `shlex.quote`-escaped
  `discuss` command naming that specific thing, instead of leaving the agent to
  remember to ask.

### Modified Capabilities

- None. `openspec/specs/` does not exist in this repository; capabilities are
  declared per change, exactly as the proposal states.

---

## ADDED Requirements — Domain A: `close-discussion-gate`

### Requirement: `close` refuses on an unanswered discussion

`close` MUST refuse with code `DISCUSSION_UNANSWERED` when at least one distinct
question text has no answered event as its last occurrence in ledger order, and MUST
succeed when none does.

#### Scenario: Red-first — succeeds today, refuses after the change

- GIVEN a target whose ledger holds a `discuss` event with `asked="what should the
  experiment contract still add?"` and no later event carrying that exact text
- WHEN `close` is run before this change lands
- THEN `close` succeeds (recorded as the red baseline)
- WHEN `close` is run after this change lands, against the identical ledger
- THEN `close` refuses `DISCUSSION_UNANSWERED`, naming that exact text
- AND both runs are recorded together as one red-then-green proof, per
  `strict_tdd: true`

#### Scenario: Zero open on the reference target

- GIVEN the live reference target's ledger (27 `discuss` events, 12 distinct `asked`
  texts)
- WHEN `close` evaluates every bucket under the shipped rule
- THEN the open count is exactly 0, matching the measured fact in the proposal

### Requirement: Bucketing is by exact trimmed question text, never by witness identity

A `discuss` event MUST be grouped into a bucket keyed on `asked.strip()`. Grouping by
`(about.kind, about.operand)` — the identity key `_settle_discussed_events` already
uses for its own, narrower purpose — MUST NOT be reused for this gate.

#### Scenario: Mutation proof — identity grouping cross-answers distinct questions

- GIVEN a fixture reproducing the measured shape: N distinct question texts, all
  sharing the identical witness identity `(kind="record", operand=None)`
- WHEN one of the N texts is answered and the gate is evaluated
- THEN the shipped exact-text rule reports the other N−1 texts still open
- AND a mutated build that groups by identity instead reports all N texts answered
- AND the mutation MUST cause the test to fail — identity grouping is not an
  acceptable implementation of this requirement

### Requirement: A bucket's state is the LAST event in ledger order, never a
per-event reading, never answered-once

For a given exact text, the bucket MUST be evaluated by inspecting only the event
that occurs **last in ledger append order** (file order, never a comparison of `at`
timestamps, which are second-granularity and can tie). It is open only when that
specific last event has no non-empty `answered`. A rule that reads a single event's
own `status` field in isolation, or a rule that is satisfied by *any* answered event
regardless of position ("answered-once"), MUST NOT be used.

#### Scenario: Five open, two answered, evaluates to zero open

- GIVEN the measured recurring text with 7 events for one exact question, in order:
  open, open, open, open, **answered**, open, **answered**
- WHEN the gate evaluates this bucket
- THEN the result is "not open" (the last event, position 7, is answered)

#### Scenario: Mutation proof — per-event reading refuses forever

- GIVEN the same 7-event fixture
- WHEN a mutated build evaluates "any event with no answer" as open
- THEN it reports 5 open events for a text that is not actually open
- AND the mutation MUST cause the test to fail

#### Scenario: Mutation proof — answered-once silently accepts a stale answer

- GIVEN a fixture built as ask → answer → ask (the third event is a fresh, unanswered
  re-ask of byte-identical text)
- WHEN the shipped last-word rule evaluates this bucket
- THEN it reports the bucket open (the last event has no answer)
- WHEN a mutated build evaluating "any answered event satisfies this" (answered-once)
  evaluates the same bucket
- THEN it reports the bucket answered — silently passing over the fresh, unanswered
  re-ask
- AND the mutation MUST cause the test to fail

### Requirement: A later, differently-worded question never reopens an earlier
answered one (doctrine preservation)

`settle`'s own documented rule for `SETTLE_DISCUSSION_UNANSWERED` — "ANY answered
event satisfies this, never newest-wins" — protects a *clarifying* question, worded
differently, from retroactively erasing an earlier answer under identity grouping.
This gate MUST preserve that guarantee even though it groups by a different key:
because grouping is by exact text, a differently-worded clarification forms its own,
separate bucket and can never enter an already-answered bucket at all.

#### Scenario: A clarifying question does not reopen the original

- GIVEN a bucket for text A that is answered (last event answered)
- WHEN a new `discuss` event asks text B (differently worded, even about the same
  witness identity) and receives no answer
- THEN the gate reports text A's bucket as not open
- AND reports text B's bucket as open, independently
- AND the two buckets MUST NOT be conflated by any shared identity field

### Requirement: Gate position — after `AGREEMENT_DISAGREES`, before the position
refresh

The discussion check MUST run as a third, independent axis in `cmd_close`, positioned
after the `AGREEMENT_DISAGREES` check and before the call that refreshes the position
section. The refresh MUST NOT be able to run, and MUST NOT be able to alter ledger
state, before this check has had a chance to refuse.

#### Scenario: Refusal fires before any refresh side effect

- GIVEN a target that would both refuse `DISCUSSION_UNANSWERED` and have an
  otherwise-clean position refresh available
- WHEN `close` is run
- THEN the refusal is raised before `cmd_position`'s refresh runs
- AND no position-section bytes are rewritten as a side effect of the failed `close`
  call

### Requirement: The refusal names every open text and a runnable, correctly
quoted retirement command

The `DISCUSSION_UNANSWERED` refusal MUST enumerate every distinct open text (not a
count) and MUST print, per text, a directly runnable `discuss --answer` command whose
`--question` argument is escaped with `shlex.quote`. The module MUST `import shlex`
to do this; it does not today.

#### Scenario: Apostrophe-bearing text is retired by the printed command

- GIVEN an open question whose exact text contains an ASCII apostrophe (matching one
  of the 3 of 12 live texts with this shape, e.g. containing `render's docstring`)
- WHEN `close` refuses and prints its retirement command
- THEN that exact printed string is executed as a subprocess (not merely read as
  text), the same discipline `OfferCommandTests.test_expand_contract_command_string_
  is_runnable_and_writes_nothing` already applies to `expand-contract`
- AND the subprocess exits successfully and appends an `answered` event for that
  exact text
- AND a subsequent `close` no longer reports that text as open

### Requirement: No second retirement path

A `discuss --retire` verb, or any other way for a bucket to stop being open, MUST NOT
be added. The only retirement path is `discuss --answer`, so the reason for closing a
question always reaches the record — a cheaper exit that clears the gate without a
recorded reason is explicitly rejected.

#### Scenario: The only way to close a bucket is answering it

- GIVEN an open bucket
- WHEN any command other than `discuss --answer` against the identical exact text is
  attempted (e.g., a hypothetical `--retire` flag, if one existed)
- THEN no such flag exists in the shipped argument parser, and the gate remains open
  until `discuss --answer` is run

### Requirement: Pure reader — no ledger schema change

This domain MUST NOT alter the shape of any `discuss`, `settle`, `offer`, or `close`
ledger event. It reads events that already exist.

#### Scenario: Existing events remain readable and unchanged

- GIVEN the live reference target's ledger, captured before this change
- WHEN the same ledger is read after this change lands
- THEN every event's field set is byte-for-byte unchanged
- AND the new gate is computed purely by reading, never by rewriting, any event

---

## ADDED Requirements — Domain B: `proactive-discussion-publication`

### Requirement: A settle collision publishes a specific, runnable discuss command

When `cmd_settle`'s create path detects that a placement's operand already appears in
one or more existing agreements (`SETTLE_COLLIDES_UNNAMED`), the refusal MUST name
every colliding agreement's exact text — not merely a count, which is the current,
insufficient shape — and MUST additionally print a directly runnable, `shlex.quote`-
escaped `discuss` command whose `--about` names the same witness kind and operand
this settle attempt resolved, and whose `--question` text enumerates the operand and
every colliding text, asking which one (if any) this placement supersedes.

This is a distinct question from the one settle's create path already requires be
discussed and answered before reaching this point (`SETTLE_NOT_DISCUSSED` /
`SETTLE_DISCUSSION_UNANSWERED`, which cover "should this witness be placed at all").
The collision question — "which existing agreement, if any, does this replace" — is
never asked by that earlier check, and only the engine, having just computed
`collides`, can name it specifically.

#### Scenario: Collision refusal names texts, not a count

- GIVEN two existing agreements whose text contains the operand `RAMP_CEILING`, and a
  new settle attempt for the same operand with no `--supersedes`
- WHEN `settle` refuses `SETTLE_COLLIDES_UNNAMED`
- THEN the refusal message lists both colliding texts verbatim (not "2 existing
  agreement(s)")
- AND prints one runnable `discuss` command whose question names the operand and both
  colliding texts

#### Scenario: The published command is runnable for an apostrophe-bearing collision

- GIVEN a colliding text containing an apostrophe
- WHEN the published command is executed as a subprocess
- THEN it succeeds and appends a `discuss` event whose `asked` text matches exactly
  what was printed

### Requirement: Probe's `piloted` status publishes a specific, runnable discuss
command

When `cmd_probe` computes `next_step == "piloted"` — a pilot whose measured scale sits
below the protocol's declared target, "neither absent nor done" — its output MUST
include a directly runnable, `shlex.quote`-escaped `discuss` command whose question
names the target/name pair and the declared scale the protocol asks for, asking
whether to accept the pilot's reduced scale as final or continue toward the declared
one.

This formalizes existing prose (`SKILL.md`: "ask the user what they want to do next
and invent no work") into a mechanism, exactly this domain's purpose.

#### Scenario: A piloted probe publishes the question

- GIVEN a target whose most recent record ran below the protocol's declared scale
- WHEN `probe` is run and reports `nextStep: "piloted"`
- THEN the output includes a runnable `discuss` command asking whether the pilot's
  scale is accepted as final or should continue toward the declared scale
- AND the question text names the declared scale, not the currently-achieved count
  (see the stability requirement below)

### Requirement: Verify publishes one discuss command per unwritten local remedy
finding

For every finding id present in `verify`'s `audit.localRemediesNotWritten` list, the
`verify` output MUST include one directly runnable, `shlex.quote`-escaped `discuss`
command naming that exact finding id, asking whether its local remedy is written now
or deliberately deferred (and why).

This follows the code's own documented framing of this exact field: "a local remedy
nobody wrote out is not a defect in the audit, but it is the difference between a
change that settles inline and one that costs a session. Reported so it is a
decision, not a silence." The engine already frames this as a decision; this
requirement gives that decision a runnable command instead of leaving it as prose.

#### Scenario: Each unwritten local remedy gets its own command

- GIVEN `verify` reports `audit.localRemediesNotWritten: ["finding_7", "finding_12"]`
- WHEN the output is inspected
- THEN it contains two distinct runnable `discuss` commands, one naming `finding_7`
  and one naming `finding_12`
- AND neither command's question text is a generic "is there anything to discuss?" —
  each names its specific finding id

### Requirement: Published question text MUST be reproducible from stable
identity alone, and MUST NOT embed a value that varies between calls while the
underlying decision has not changed

This is the requirement that keeps this domain from silently defeating Half 1's own
guarantee that the gate "cannot refuse forever." Half 1 buckets by **exact text**. If
a publication point's question text embeds a measurement that changes between calls
for an unchanged decision — most concretely, `probe`'s currently-achieved repetition
count, which climbs on every poll while the pilot-vs-declared-scale decision has not
changed — then every call publishes a **distinct** text, an agent that dutifully runs
each one opens a **new**, never-to-be-revisited bucket every time, and `close`'s
`DISCUSSION_UNANSWERED` refusal accumulates every stale variant forever. This is the
identical unsatisfiable-across-a-boundary failure the proposal already rejected for
session/revision scoping, reappearing through a different door if this requirement is
not honored.

Every publication point in this domain (settle collision, probe piloted, verify's
local-remedy findings) MUST derive its question text only from identifiers that are
stable for the life of the decision: an operand and a fixed set of colliding texts, a
target/name pair and a **declared** (not achieved) scale, or a finding id. None of
these MAY vary while the decision they represent is still open.

#### Scenario: The same declared scale produces byte-identical text across polls

- GIVEN two `probe` calls against the same target, at two different achieved
  repetition counts, both still short of the same declared target scale
- WHEN the published `discuss` command is compared between the two calls
- THEN the `--question` argument is byte-for-byte identical
- AND no reference to the currently-achieved count appears inside the question text

#### Scenario: Mutation proof — embedding the achieved count breaks the invariant

- GIVEN a mutated build whose piloted-question text embeds the currently-achieved
  repetition count
- WHEN `probe` is polled twice at two different counts, both still below the declared
  scale
- THEN the two published question texts differ
- AND a test asserting byte-identical text across the two polls MUST fail against
  this mutation — proving the requirement is load-bearing, not decorative

### Requirement: `prose.staleRevisions` and `prose.unresolvedSymbols` MUST NOT
publish a discuss action

These two `verify`-reported findings are explicitly excluded from this domain, for
reasons grounded in their own documented behavior, not merely omitted by oversight:

1. **Volume is unbounded per call.** `prose_state` scans every `.py`, `.md`, and
   `.ipynb` file under the target for every symbol-shaped token and every managed-
   revision mention. A live target can report dozens of hits in one `verify` call,
   unlike the bounded, per-call cardinality of a settle collision (one write attempt)
   or a piloted probe (one state).
2. **The engine already declines to judge these as decisions.** `prose_state`'s own
   docstring: a historical mention of an old revision is "legitimate and common... so
   this is reported and never drifts a status: telling the two apart is a reading,
   and a check that guessed would spend its credibility on the wrong ones." This is
   the opposite of "the engine already knows something is undecided" — it is the
   engine explicitly declining to have an opinion on which findings are real.
3. **Coupling risk into Half 1's gate.** Every published `discuss` text becomes a
   bucket `close` can refuse on. Publishing one command per prose finding would let a
   stale docstring mention — an editorial nit unrelated to the experiment contract —
   block a `close` the same way an unresolved agreement does, corrupting Half 1's own
   proportionality.

#### Scenario: A stale revision mention produces no discuss command

- GIVEN `verify` reports a non-empty `prose.staleRevisions` list
- WHEN the output is inspected
- THEN it contains no runnable `discuss` command referencing any entry in that list

### Requirement: `agreements.witness.unwitnessed` MUST NOT publish a discuss
action

This finding is excluded for a reason distinct from the prose findings above:
`agreements_state`'s own docstring classifies `unwitnessed` as one of three witness
states, and states plainly that it is "reported, never a failure." It is a legitimate
resting state — some agreements are not mechanically witnessable at all — not an open
question awaiting resolution. The engine has not detected something undecided here;
it has detected something that is allowed to stay exactly as it is.

#### Scenario: An unwitnessed agreement produces no discuss command

- GIVEN `verify` reports a non-empty `agreements.witness.unwitnessed` list
- WHEN the output is inspected
- THEN it contains no runnable `discuss` command referencing any entry in that list

### Requirement: Every command published under this domain reuses the identical
`shlex.quote` discipline as Half 1

No publication point in this domain MAY construct a command string by naive string
interpolation or single-quote wrapping. All three publication points (settle
collision, probe piloted, verify local-remedy findings) MUST route through the same
quoting discipline Half 1 introduces (`import shlex`; `shlex.quote` on every embedded
argument value), never a second, independently-written quoting path.

#### Scenario: An apostrophe-bearing colliding text does not break the collision
command

- GIVEN a colliding agreement text containing an apostrophe
- WHEN the published `discuss` command for that collision is executed as a subprocess
- THEN it succeeds — the same proof discipline required for Half 1's retirement
  command, applied here to a second, independently-constructed command string

---

## Cross-Domain Requirement: The Non-Goal Applies To Both Halves Identically

Neither domain may be documented, in `cmd_close`'s docstring, `SKILL.md`, or anywhere
else, in language that implies a discussion opened through this change's new
publication points, and answered, carries more authorship weight than one an agent
opened and answered entirely on its own. Publishing the command lowers the friction to
ask; it does not raise the bar on who is allowed to answer.

#### Scenario: Documentation states the non-goal without softening

- GIVEN `SKILL.md`'s treatment of both `close-discussion-gate` and
  `proactive-discussion-publication`
- WHEN the non-goal sentence is located
- THEN it appears verbatim (or with only the necessary grammatical adaptation) as
  written in this spec's "Non-Goal, Stated Exactly" section, in every place these two
  domains are documented

---

## Test Obligations (`strict_tdd: true`)

Every requirement above that introduces a new refusal, a new bucketing rule, or a new
publication point MUST be shown red before green, per `openspec/config.yaml`'s
`strict_tdd: true`. The following mutation proofs are explicitly required, each tied
to a requirement above and each built to fail under a specifically weaker
implementation, never merely asserted:

| # | Requirement | Mutation that MUST make the test fail |
|---|---|---|
| 1 | Exact-text grouping | Swap to `(about.kind, about.operand)` identity grouping |
| 2 | Last-word-in-ledger-order | Swap to per-event `status` reading |
| 3 | Last-word-in-ledger-order | Swap to answered-once |
| 4 | Doctrine preservation | Fold a differently-worded clarification into the same bucket as an answered original |
| 5 | Retirement command quoting (Half 1) | Remove `shlex.quote`, run against an apostrophe-bearing text |
| 6 | Retirement command quoting (Half 2) | Remove `shlex.quote` from the settle-collision command, run against an apostrophe-bearing text |
| 7 | Stable question text (Half 2) | Embed the achieved repetition count in the piloted-probe question |

## Constraints Carried Forward Unchanged

- `openspec/config.yaml` sets `strict_tdd: true` — see Test Obligations above.
- `FORGE_VOCABULARY_FLOOR` (word-boundary regex) and `FORGE_LEXICON` rule B (derived
  from the target's live module basenames) MUST be run — never reasoned about — and
  report zero violations across every shipped file this change touches, in both
  domains.
- `CoreNamesNoDomainTests` does a plain substring scan of `_core/implementation/*.py`
  against `src`, `tests`, `tools`, `Notebooks`, `Data`, `Results`, `Models`. Neither
  domain touches `_core/implementation/`, so this constraint is satisfied by scope,
  not by a new guard — but any fixture text drawn from the reference target (for
  either domain's tests) MUST stay inside `tests/`, unguarded, and prefer synthetic
  text reproducing shape (repeat, apostrophe, collision, shared identity) over literal
  target strings.
- Gate: `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` **and**
  `npm test`. Baseline to preserve: `Ran 2039 tests, OK, skipped=3`; node 385/385.
  `README.md` changed on this branch (`60a46d1`) and two tests read it — any red-first
  proof touching README-adjacent fixtures must account for that baseline, not assume
  the pre-`60a46d1` shape.
- No event schema change to `discuss`, `settle`, `offer`, or `close` events, in either
  domain.
- No change under `.claude/skills/_core/implementation/`.
- No `discuss --retire` verb, in either domain.

## Risks Carried Into Design

| Risk | Note |
|---|---|
| Half 2's exact publication surface (message text vs. a new structured field on `probe`/`verify` output) is left to the design phase | This spec commits to the observable contract — a runnable, correctly quoted command naming a specific undecided thing — not to a JSON key name or an internal helper name |
| `SETTLE_COLLIDES_UNNAMED`'s enumerated-texts requirement changes existing message wording | Any existing test asserting the current count-only wording needs updating; flagged for the tasks phase to enumerate |
| Live frequency of `piloted` and `localRemediesNotWritten` states on the reference target is not measured in this phase | The design/tasks phase should measure it, the same discipline the proposal applied to the 27-discuss-event ledger, rather than assuming low cardinality |
| Volume risk for excluded findings (prose, unwitnessed) could resurface if a future change relaxes the MUST NOT requirements above | Both exclusions are argued from the findings' own documented semantics, not from convenience, and should not be revisited without re-deriving those semantics |

## Traceability to the Proposal

- Half 1's every settled rule (exact-text grouping, last-word ordering, `discuss
  --answer` as sole retirement, `shlex` quoting, gate position) is carried into Domain
  A unchanged from `openspec/changes/nothing-agreed-stays-in-the-conversation/
  proposal.md` and engram `sdd/nothing-agreed-stays-in-the-conversation/propose`
  (#1322).
- Half 2's three publication points and two exclusions are derived from this phase's
  own reading of `implementation_cli.py` (`cmd_settle`'s `SETTLE_COLLIDES_UNNAMED`
  path at the collision check preceding `_render_settled_line`; `cmd_probe`'s
  `next_step == "piloted"` branch; `cmd_verify`'s `audit.localRemediesNotWritten`
  list; `agreements_state`'s three-state witness docstring; `prose_state`'s own
  documented refusal to judge a stale mention), cross-checked against engram
  `sdd/nothing-agreed-stays-in-the-conversation/explore` (#1319) for the shape of
  `agreements_state`, `_settle_discussed_events`, and the witness three-state design.
- The stability requirement (Half 2's most load-bearing addition) has no precedent in
  the proposal and is derived in this phase from the interaction between Half 1's
  exact-text bucketing and Half 2's new publication points — stated here because
  neither half's own document would have surfaced it in isolation.
