---
name: skill-audit
description: "Trigger: audit a skill, a CLI, or any subject that enumerates a closed set — accepted operations, subcommands, error codes, shipped assets — for the gap between what the running code accepts and what its own documentation claims. Derives both halves rather than reading either: the code side by driving the subject as a real process and taking the roster out of its own refusal message, the documented side by parsing a table. Reports; never repairs. Refuses outright without a shell, because an audit that cannot execute cannot adjudicate. Stdlib-only, no venv, no network."
---

# Skill Audit

This skill looks for one defect: a closed set that is stated by hand in more
places than it is derived, so the statements drift from the running code and
from each other. Every roster restated by hand is a roster that eventually
loses one. The audit finds them by deriving both halves and comparing, and then
it **stops** — the report is the deliverable, and the repair belongs to whoever
owns the subject.

## Activation

The audit needs to run things. Without a shell it must **refuse**.

If the `Bash` tool is unavailable, say so, name `Bash` as the missing
capability, and stop. Emit **no report**, **no finding**, **no candidate**, and
no partial verdict. Do not fall back to reading the subject's source and
describing it: reading is what produces a document full of claims marked
`read-only` with nothing `CONFIRMED by execution` anywhere, and a document like
that reads as an audit while carrying none of an audit's authority. This skill
does not degrade to reading; it refuses.

The refusal is the correct output, not a failure of the audit. An audit whose
every claim is a candidate has told the user nothing they could not have read
themselves.

## Scope, and who chooses it

A subject larger than one closed surface is not audited in one pass. Propose a
slicing — one closed surface per slice, each nameable in a line — and **ask**,
through the interactive question facility. Never type a question into a reply
and continue as though it had been answered; a question nobody was asked has an
assumed answer, and an assumed answer is exactly what this skill exists to find
in other people's documents.

If the facility is unavailable, carry the assumption **explicitly**, in the
report's own words, as an assumption rather than as a decision.

## The moves

Every move is a way of getting a fact that reading cannot give you. Move by
move, in order; the numbering is the order.

| Move | Ships as | Lock |
| --- | --- | --- |
| 0. Enumerate a closed surface from both sides, and never begin by reviewing a diff | `roster` | `tests/test_skill_audit.py` |
| 1. Build the expected artifact from the documentation alone, then diff it against the producer's output | `structure` | `tests/test_skill_audit.py` |
| 2. Drive the subject as it exists on disk, never only a fixture built from the same document | `roster` | `tests/test_skill_audit.py` |
| 3. Fake every external boundary and assert on what crossed it, never dial it | `doctrine` | `tests/test_skill_audit.py` |
| 4. Read an installed dependency as text; importing a service client authenticates it | `doctrine` | `tests/test_skill_audit.py` |
| 5. Probe live only with consent, read-only, and scope the result to the environment | `doctrine` | `tests/test_skill_audit.py` |
| 6. Invert every lock the audit leans on, and watch it fire | `doctrine` | `tests/test_skill_audit.py` |
| 7. Compare per-harness test counts before and after; a count that did not rise is a finding | `doctrine` | `tests/test_skill_audit.py` |
| 8. Drive the whole documented flow in order, against one real shared box, and name the first step that breaks its own declared expectation | `walkthrough` | `tests/test_skill_audit.py` |
| 9. Compare two supplied readings of one prose surface by mechanical diff, and never let the comparison close | `reading-diff` | `tests/test_skill_audit.py` |
| Read every artifact's opening paragraphs against its own frontmatter and its own shipped files | `doctrine` | no lock — irreducibly textual, and carried anyway |

The last row has no code and no lock, and says so. Prose contradicting prose
inside a single file cannot be mechanized, and dropping the row to make the
table tidy would be the same defect this skill exists to find.

Move 7's mechanism — a `counts` subcommand reading `Ran N tests` and `# pass N`
— is **deferred** to the follow-up change `the-manifest-that-proves-containment`
along with `manifest`. Until it lands, move 7 is carried out by running each
harness by hand and reading the figures, and this row names `doctrine` rather
than a subcommand that does not exist.

### Move 0, in detail

Enumerate the closed set from the running code and from the documentation, as
two independent derivations, before forming any opinion about either. Treat
every enumeration produced by reading as a **candidate** until something
executes. Move 0 also compares any unhedged numeral in the subject's prose
against the enumeration that immediately follows it.

### Move 1, in detail

Construct what the documentation says the producer should emit, from the
documentation alone, and diff it against what the producer actually emits. This
is the only move that catches the document and the producer drifting apart while
each stays internally consistent. It is only sound under the conditions below.

### Move 8, in detail

Every earlier move probes one closed surface in isolation. This one drives the
documented flow itself, step by step, against a real shared box, and asks
whether each step's own declared expectation still holds once it actually
runs. A step matching its own expectation is `passed`, whatever its exit code
— a documented refusal is a pass. The first step whose observation
contradicts what it declared is the stall, named by its index; every gate at
or after that index is `unreached`, and the report carries it under
`## Unchecked`, never under clean. A step declaring no expectation at all is
refused before it runs: a gate that asserts nothing is not a gate.

### Move 9, in detail

Every earlier move derives at least one side of a comparison from a real
process or a real table. This one takes both sides as given -- two supplied
readings of one prose surface -- and asks only whether they agree, never
whether either is right. Two readers agreeing proves the prose has **one
reading**, never that it is closed, and `comparison` stays the literal
`not-run` for a surface compared this way, permanently. Four independent
barriers hold this: an AST lock proving the subcommand never calls
`doctrine_side`, `probe_code_side`, or `finish`; a structural lock proving
`closed_seen` is assigned `True` at exactly one site, inside `run_roster`,
fed only by a `doctrine_side` status; the literal `not-run` comparison, held
as a constant rather than a computed value; and a behavioural lock proving a
reading naming more than a real code side never yields an `unregistered`
key at all. A supplied reading may propose a candidate for a later gate; it
may never itself close a comparison.

## The stages

A differential audit against a second subject runs in six stages, cheapest
first. Each is a row in a table, never a numbered heading -- the same reason
move numbering lives in the moves table rather than in headings of its own.
Stage 2 is not itself differential: it demands the subject be driven from
ignorance whenever anything is reachable to drive, and every report --
differential or not -- carries all six stage rows.

| Stage | Models | Demands |
| --- | --- | --- |
| 0. Freeze the subject | 0 | `frozen` |
| 1. Decide by tool | 0 | `undecidable` |
| 2. Drive from ignorance | 1 | `user-drive` |
| 3. Two blind readings, over that list only | 2 | `reading-diff` |
| 4. Differential drive, one box with the skill and one without | 2 | `drives` |
| 5. Partition the two transcripts | 1 | `found-by` |

Six model runs, total, and only if every stage after the first three
actually runs -- one for stage 2's drive from ignorance, two for stage 3's
blind readings, two for stage 4's differential drive, one for stage 5's
partition -- stated here, before any of them is launched.

Each `Demands` cell holds a `REPORT_SHAPE` key, not prose, held to "The shape
of a report" table below in both directions by
`ReportSchemaSelfDescriptionTests`. A stage is conditional exactly because
this table names it: `## Stage outcomes` records it `ran` or
`skipped: <reason>`, mirroring `## Move outcomes` exactly, and only a `ran`
row demands the artifact its own `Demands` cell names -- a `skipped` row
demands nothing. A zero-model audit, stages 0 and 1 `ran` and stages 2
through 5 all `skipped`, is a valid report on its own terms, never a partial
one -- **except stage 2**, whose skip is accepted under exactly one reason,
below.

One cross-section rule ties `## Undecidable` back to `## Move outcomes`: an
entry claiming `- Rung: probe` must name a move whose own row there reads
`ran`. Declaring a probe was the answer and then skipping the move it names
is refused, structurally.

### The binding ruling: an audit never reports without driving

Stage 2 accepts exactly one skip reason:

    - Stage: 2: skipped: no reachable surface (stage 1)

accepted only when stage 1's row reads `ran` and `## Undecidable` is
**non-empty** with every entry's `- Kind:` reading `no-closed-roster`. An
empty `## Undecidable` section is not the same claim as a section full of
`no-closed-roster` entries: a cleanly-decided surface never enters that
section at all, so its presence there is exactly what distinguishes "nothing
was reachable" from "nobody looked." Any other stage 2 skip reason --
including a genuinely empty `## Undecidable` -- is rejected as
`driver-required`: an audit never reports on a subject without driving it,
and the zero-model path is never a caller's shortcut to assert. "Optional"
applies only to stages 3 through 5, after a successful drive, never to
stage 2 itself.

A stage-3/4/5 row MAY read `skipped: offered, declined` -- available, the
operator chose not to take it -- distinguishable at a glance from any other
`skipped: <reason>` text, which always means "could not run." That text is
legal only once stage 2 itself reads `ran` and `## User drive`'s own
`- Outcome:` reads `agree`: equivalence reached is what makes the question
worth asking in the first place. Without that agreement, no question was
asked, and `check-report` rejects the `offered, declined` text wherever it
appears on 3 through 5 -- stage 2's own row may never carry it at all.

Stages 3 through 5 carry no lock over the one fact that would matter most:
whether the two readers, or the two drives, were actually blind, isolated,
and out of contact with each other. `check-report` can enforce that an
artifact exists and has the shape this table names. It cannot enforce that
the process which produced it never let the two sides talk, because this
tool only ever calls `subprocess.run()` and holds no authority over what
happens on either side of that call. A stage row in this table, like the
moves table's own textual row, is an operator's declaration -- never a
proof.

## The from-zero comparison and its soundness conditions

A from-zero comparison that quietly consults the producer proves nothing, and
proves it convincingly. All of these hold or the comparison's result is not read.

| Condition | What it forbids |
| --- | --- |
| The documented side never references the producer | Not a call, not an import, not a borrowed constant, and not to decide which elements to build. Enforced by parsing the derivation function's syntax tree |
| The comparison's domain is declared and closed | An open domain makes the diff noise, and noise gets exempted until the comparison means nothing |
| Both directions report as sets, never as a boolean | `unregistered`, `phantom` and `duplicated` are different defects with different remedies |
| The comparison is proven reachable-red both ways | Adding to the code side fires `unregistered`; deleting a documented row fires `phantom` |
| The documented side comes from a parseable table, never from prose | The reader who writes the from-zero side has just read the artifact and will reproduce it unconsciously |
| The from-zero side never references the subject | Not the `{subject}` token, not a hand-typed absolute or repo-relative path to it. The mirror of the first row: a from-zero build that reads from the subject is not a build, it is a copy wearing one |

Where the subject has no such table, **"there is no closed roster here" is the
finding**, emitted as a first-class result with the range that was searched. It
is not an error, not an exception, and not a clean verdict.

A documented table counts as a roster site only if the recipe declares its scope
and quotes its heading, and the quoted heading is then checked against disk. A
table headed `## Other engine operations` is a complement set; diffing it
against the full runtime roster would emit a screenful of confident nonsense on
the auditor's very first subject.

## How the moves fail

Each of these has already cost a phase in this repository. Each is a
requirement, not a caveat.

| Failure | Requirement |
| --- | --- |
| A lock passes off its own fixture's name | Assert the needle is absent from the fixture's name and path **first**, before the assertion that looks for it |
| A fixture cannot reach the guarded branch | Establish reachability; an assertion over a branch the fixture never enters is unfalsifiable, and it passes |
| A wholesale double stands in for a process | Drive the subject as a subprocess. A double replacing a function cannot hold a claim about the process it would have run |
| A green suite is offered as evidence | Greenness is never evidence. Evidence is a named execution with a named observation |
| Containment is proven by `git status` | `git status --porcelain` over an ignored directory is empty by construction. Prove it by a before/after content manifest |
| A live request's success is claimed as a receipt | It proves the environment answered. It proves nothing about the subject's code |
| A new name is proven free by the default search | The default search honours `.gitignore`. Search with it disabled and hidden files included, or the negative is worthless |
| An inversion is undone with `git checkout --` | Restore by inverse patch and confirm by content comparison; checkout restores from the index and silently discards unrelated work |

## The evidence ladder

When both halves disagree, the consumer decides, and only execution establishes
what the consumer does. Highest first:

| Rank | Evidence |
| --- | --- |
| Strongest | The installed consumer, measured by running it |
| | Two independent consumers agreeing under constraints neither can be changed for |
| | The live subject on disk, driven as a process |
| | Fixtures the audit built |
| Weakest | Prose, in either artifact |

Prose is last because both sides are claims until something executes. A
statement in any document describing what a consumer does is **never** evidence
of what that consumer does — that rule was proven twice in this repository's
own history, and it is stated here so it is not rediscovered a third time.

## Adjudication

Every finding carries exactly one adjudication, and there is no default.

| Adjudication | Means | Remedy |
| --- | --- | --- |
| `doctrine wrong` | The documentation states something the running code does not do | Correct the document |
| `artefact wrong` | The running code does something its own documentation forbids or omits | Correct the code |
| `not adjudicable` | Enumeration found no consumer at all | See below |

### Not adjudicable

`not adjudicable` is not a softer verdict; it is a different question. The
question is not which half is wrong but that **this half has no other half** — a
value declared and enumerated with nothing anywhere reading it or branching on
it. Its remedy is build-or-delete, a user decision with real cost, and that is
the structural reason report-then-fix is the correct ordering: an auditor that
repaired what it found would have to guess this one.

These findings get their **own report section**, distinct from the ranked
findings, so a reader can see at a glance which findings are defects and which
are open questions about intent.

Do not apply the rule "every reported fact must be branched on". It is false by
construction: facts are deliberately reported without gating anything, and the
bar for such a value is documentation, not consumption. A value that is
computed, documented, and deliberately never branched on is **not** a finding.

## The shape of a report

`check-report` enforces this. A shape enforced only by prose is a
hand-maintained roster, which is the class this skill exists to find.

| Item | Required content | Rejected when |
| --- | --- | --- |
| `ranked-findings` | Findings, ordered, each naming **both halves** at `file:line` | A finding cites a single `file:line`; that is a candidate, not a finding |
| `move-number` | The move that found each finding | A finding names no move |
| `move-outcomes` | `## Move outcomes`, one row per move named in the moves table above, each `ran` or `skipped: <reason>` | A move has no row, or a `skipped` row carries no reason |
| `evidence-marker` | Per finding, `CONFIRMED by execution` or `read-only` | A finding carries neither; there is no default, and a missing marker is never read as confirmed |
| `found-by` | Per finding, `both`, `one`, or `not-compared` | A finding carries none of the three; there is no default, and a missing marker is never read as `one` |
| `adjudication` | Per finding, one of the adjudications above | A finding carries none, or carries a value outside the table |
| `clean-section` | `## Clean, stated as results`, with the enumeration that supports each entry | An entry's only support is that a suite passed |
| `unchecked-section` | `## Unchecked`, naming what was not enumerated | A surface that was never enumerated is absent, or is reported as clean |
| `falsifier` | The observation that would overturn this report | Absent |
| `changed-line-forecast` | The size of the fix that would follow, in changed lines | Absent |
| `frozen` | `## Frozen`, naming the digest every finding's own `- Digest:` must agree with | A report carries no `## Frozen`, or a finding's digest disagrees with it |
| `repair-units` | `## Repair units`, a table naming each unit's findings and its own changed-line forecast, a grouping distinct from move or adjudication | A finding belongs to no unit or to more than one, or a forecast cell is not an integer |
| `disputed-severity` | `## Disputed severity`, bare heading; when non-empty, exactly two `- Position:` lines per dispute, each citing `file:line`, recorded verbatim, with no ranking | The heading is absent, or a dispute's positions are unpaired, or a position carries no citation |
| `stage-outcomes` | `## Stage outcomes`, one row per stage named in the stages table above, each `ran` or `skipped: <reason>` | A stage has no row, or a `skipped` row carries no reason |
| `undecidable` | `## Undecidable`, bare heading, demanded when stage 1 is `ran`; when non-empty, each entry names `- Kind:`, `- Rung:` (`probe` or `readers`), and, when the rung is `probe`, `- Probe: <move>` | The heading is absent while stage 1's row reads `ran`, or a `probe` rung names a move whose own `## Move outcomes` row is not `ran` |
| `user-drive` | `## User drive`, demanded when stage 2 is `ran`; the driver's `argv`, `argv[0]`'s resolved path, its `cwd`, the env names passed, the ignorance control gate's outcome, the box digest before and after, and the two-column enforceable / declared-only table | Absent while stage 2's row reads `ran`; or the declared-only column is empty, because a drive claiming to have proven everything has misread what it did; or the box digest disagrees with `## Frozen` |
| `reading-diff` | `## Reading diff`, demanded when stage 3 is `ran` | Absent while stage 3's row reads `ran` |
| `drives` | `## Drives`, demanded when stage 4 is `ran`; no finding may attribute itself to the skill-less drive while naming the subject as its own target | Absent while stage 4's row reads `ran`, or a finding commits that category error |
| `not-adjudicable` | `## Not adjudicable`, bare heading; when non-empty, each entry names the absent half, its `- Evidence:`, and the `## Repair units` unit it belongs to | The heading is absent, or a finding whose `- Adjudication:` reads `not adjudicable` sits under `## Ranked findings` instead |

A report in which **no** finding is marked `CONFIRMED by execution` must say so
in its **first line**. A clean surface still gets the full report shape,
including a populated `## Clean, stated as results`: an empty clean section and
a surface nobody looked at must never look the same. `- Found by:` is the
independence axis and travels alongside `- Evidence:`'s obtained axis on every
finding; `## Disputed severity` demands nothing of an undisputed report, and
carries no vocabulary of its own beyond that one heading.

## The subcommands

| Subcommand | Derives | Emits |
| --- | --- | --- |
| `roster` | Code side by driving the subject as a process; documented side by parsing a table | `code`, `doctrine`, `unregistered`, `phantom`, `duplicated`, `numeralMismatch`, `notes` |
| `check-report` | The report shape above, from a report file | `violations` |
| `structure` | Declared side by parsing a structure table; on-disk side by walking `--subject`; from-zero side by walking a recipe-built scaffold inside an empty box | `sides`, `outcome`, `onlyIn`, `missingFrom`, `notes`, `containment` |
| `walkthrough` | An ordered recipe of steps, each run for real against one shared box, each held to its own declared expectation | `steps`, `stall`, `unreached`, `containment` |
| `reading-diff` | Two supplied readings of one prose surface, given directly rather than derived | `agreement`, `shared`, `onlyIn`, `comparison`, `candidates`, `limit`, `frozen` |

`roster` exits `0` for **any** verdict, findings included, and `2` when the
probe could not be driven or the extraction matched nothing. Inability to look
never shares an exit code with absence of findings. An extraction that matches
nothing **raises**; returning an empty set would make every documented row a
phantom finding, which is a broken probe wearing a result's clothes.

`check-report` exits `0` for a valid report, `1` for an invalid one, and `2`
when the report cannot be read.

`structure` exits `0` for **any** verdict — agreement, a two-side outcome, or
a three-way divergence — and `2` only when a side cannot be derived, when its
from-zero box is not empty and so cannot be adopted, or when the from-zero
build wrote outside its own box. None of those three is a finding; each is an
inability to look.

`walkthrough` exits `0` for **any** verdict, a stall included — a stall is a
finding on its own, never an inability to look. It exits `2` only when the
flow itself could not be entered: a step declaring no expectation at all, its
shared box already occupied, or the very first step's own command missing.

`reading-diff` exits `0` for **either** verdict — agreement or divergence —
and `2` only when it could not look: something other than exactly two
`--reading` flags, a reading file that cannot be read, or a reading whose
`members` list is missing or empty. It never calls `doctrine_side`,
`probe_code_side`, or `finish`, and `comparison` is always `not-run` for the
surface it names.

## The shipped files

This skill's own `structure` recipe (`references/probes/skill-audit.structure.json`)
points its declared side at this table. Rows exist because a file was added
on disk, never the reverse: a file is deleted first, and its row follows in
the same change.

| Path | Holds |
| --- | --- |
| `SKILL.md` | this doctrine |
| `scripts/audit_cli.py` | the CLI implementing every move that ships as code |
| `references/usage.md` | one worked invocation per subcommand |
| `references/example-report.md` | a report `check-report` accepts |
| `references/probes/skill-audit.subcommands.json` | the self-probe recipe for `roster` |
| `references/probes/skill-audit.structure.json` | the self-probe recipe for `structure` |
| `references/probes/skill-audit.first-run.json` | the self-probe recipe for `walkthrough` |
| `references/probes/proposal-deliberation.accepted-operations.json` | the first subject's `roster` recipe |
| `references/probes/skill-audit.reading-a.json` | the first supplied reading of the worked `reading-diff` invocation |
| `references/probes/skill-audit.reading-b.json` | the second supplied reading of the worked `reading-diff` invocation |

## Decision Gates

| Situation | Action |
| --- | --- |
| No shell | Refuse; name `Bash`; emit no report, no finding, no candidate |
| Subject spans more than one closed surface | Propose a slicing and ask before running |
| The interactive question facility is unavailable | Carry the assumption explicitly in the report, as an assumption |
| The subject's documentation states the set only in prose | Emit `no-closed-roster` with the searched range; do not raise, do not report clean |
| The subject exposes neither a refusal message nor a parser | Emit `no derivation available for this surface`; do not pass silently |
| The extraction matched nothing | Exit `2`. Never an empty code side |
| A recipe claims a table's scope | Check the quoted heading against disk before honouring the claim |
| A set is restated by hand in more than one place | Report every restatement under `duplicated`, even when they all agree |
| A finding's only evidence is prose on both sides | Mark it `read-only`, report it as a candidate, declare neither side wrong |
| Enumeration found no consumer at all | Mark it `not adjudicable`; put it in its own section; name build-or-delete |
| A finding's remedy is a single-line deletion | Report it. Make no edit |
| The report is written | Hand off. Do not proceed to repair |
| A new name is needed | Search with `.gitignore` disabled and hidden files included, before writing it |
| A lock passed on its first run | Invert it, watch it fire, restore by inverse patch, confirm by content comparison |
| A throwaway directory is needed | Put it under `implementations/_<name>` and remove it; never the system temporary directory |
| A from-zero box already holds files | Exit `2` naming the path; never adopt a non-empty box |
| Any of `structure`'s three sides normalises to zero members | Exit `2`; never hand an empty set to the comparison |
| A `structure` recipe step names an unknown `{token}` | Exit `2`; only `{repoRoot}`, `{subject}`, and `{box}` interpolate |
| A from-zero build changes the subject | Exit `2` as `build-escaped-the-box`; never reported as a finding |
| A declared cell's shape cannot be produced by a walk | Set it aside as `shape-not-walkable`; never expand it against the disk |
| A `walkthrough` step declares no expectation | Exit `2`; a gate that asserts nothing is not a gate |
| A `walkthrough` step's argv[0] is missing at index 0 | Exit `2`; the flow was never entered |
| A `walkthrough` step's argv[0] is missing after index 0 | Report it as the stall; a documented command that is not there is a fact about the flow |
| A `walkthrough` step matches its own `expect` | Report it `passed`, whatever its exit code |
| A gate is reached after a `walkthrough` stall | Report it `unreached`, under `## Unchecked`, never as clean |
| A `walkthrough` step declares `"reset": true` | Empty the shared box before running that step |
| A note's kind is absent from `ESCALATION_BUCKETS` | Fail the totality lock; every kind must classify into exactly one bucket |
| An escalatable note's recipe declares `probe: "refusal"` | Rung `probe`; propose the noted candidates as `walkthrough` gates before any reader is invoked |
| An escalatable note has no such recipe, and no readers are available | Rung `readers`; the surface stays in `## Undecidable`, honestly, never silently |
| A recipe declares `candidateGates` | Generate an inverted control gate first, then one gate per candidate; never restate the refusal pattern by hand |
| The control gate does not observe its own declared refusal | Every candidate becomes `unreached`; no candidate may be reported accepted against a channel not proven capable of refusing |
| A `candidateGates.argv` names an unknown `{token}` | Exit `2`; only `{repoRoot}`, `{subject}`, `{box}`, and `{candidate}` interpolate, and `{candidate}` only inside this block |
| A consequence kind is produced by an already-escalatable surface | Never escalate it a second time as an independent entry |
| `reading-diff` is invoked with other than exactly two `--reading` flags | Exit `2`; the comparison needs exactly two supplied readings |
| Two supplied readings agree | Report `agreement: "single-reading"`; `comparison` stays `not-run`, never `closed` |
| A stage's `## Stage outcomes` row is `ran` | Demand the artifact its own `Demands` cell in the stages table names |
| A stage's `## Stage outcomes` row is `skipped` | Demand nothing that stage's `Demands` cell names |
| An `## Undecidable` entry claims `- Rung: probe` | Its `- Probe: <move>` must name a move whose own `## Move outcomes` row is `ran` |
| A finding attributes itself to the skill-less drive and names the subject as its target | Reject it; that drive never ran the skill's own machinery and cannot make a claim with the subject as its target |

## Handoff

The audit's terminal state is a **handoff**, never an invocation and never a
repair.

| Field | Value |
| --- | --- |
| `mutations` | `0` |
| `documentAuthority` | `FORBIDDEN` |
| `explicitHandoffRequired` | `true` |

The audit makes no edit to the subject. Not to the documentation, not to the
code, not the one-line deletion that would close a `phantom`. The wall between
reporting and repairing **is** the product: an audit that repairs is an audit
whose findings nobody reviewed.

This skill cannot invoke a spec-driven-development phase. Every `sdd-*` skill is
`disable-model-invocation: true`, `user-invocable: false`, and delegate-only, so
there is nothing here to call. What this skill can do is **be** the exploration:
it runs under a doctrine that requires a shell, and it lands its report where a
proposal phase reads. Handing the report to the user, with the repair units and
the changed-line forecast already in it, is the whole terminal state.
