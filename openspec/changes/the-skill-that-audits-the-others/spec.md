# Spec Delta: the-skill-that-audits-the-others

Change: `the-skill-that-audits-the-others` · New capability: `skill-audit` (`.claude/skills/skill-audit/`, `tests/test_skill_audit.py`) · Store: openspec (Engram disconnected).

No prior spec exists for this capability, so every requirement below is ADDED and self-contained. Groups map one-to-one onto the proposal's five commits and are satisfiable in that order; Groups 2–4 are doctrine that Groups 5–11 lock.

**Terminology.** A **surface** is a closed set a subject enumerates somewhere (accepted operations, subcommands, error codes, shipped assets). The **code side** of a surface is what the running subject accepts; the **doctrine side** is what a parseable table in the subject's own documentation states. A **finding** names both halves at `file:line`; naming one half is a **candidate**. A **lock** is a test asserting a fact about the subject. An **inversion** breaks the guarded fact and observes the lock fire. A **box** is a throwaway directory under `implementations/_<name>`. **Doctrine** is `.claude/skills/skill-audit/SKILL.md`.

**Evidence settled by execution before this spec** (the proposal could not run these; they are not restated as open):
- `npm test` genuinely runs on this machine: 371 pass, 0 fail. Proposal risk R2 downgrades to a portability note.
- `doctrine_scaffold` calls the producer — `tests/test_proposal_implementation.py:267` (`impl.scaffold_gaps`) and `:270` (`impl.IGNORE_ENTRIES`) — under a docstring at `:240` claiming a doctrine-faithful target. Soundness condition 1 must be stated in a form that fails it.
- `remote-execution/SKILL.md` opening is stale three ways: `:12-15` denies a real service adapter that `:3` ships; `:14` names five CLI commands where `:3` names eight; `:19` says "Three modules exist so far" above four `- \`scripts/…\`` bullets (`:21`, `:32`, `:50`, `:57`) in a skill shipping eight `scripts/**.py` files.
- `SCIENTIFIC_WORKFLOW` is declared a `RouteMetricStage` at `engine/runtime-metrics.ts:3` and `:14`, and refused as an operation at `engine/cli.mjs:319-320`, with the refusal asserted at `tests/proposal-deliberation-cli-operation-surface.test.mjs:79`. A stage is not an operation, so this is the change's `not adjudicable` demonstration, not a defect.
- `skill-audit`, `skill_audit` and `audit_cli` are free. `firedrill` is **not**: it already occurs at `implementations/Domain_Adaptation/src/MIL_CREDA_Benchmark/harness.py:1072`, invisible to any search that honours `.gitignore`. The rejected name was occupied and the default search would have said otherwise.

---

## Group 1 — The skill exists and refuses to degrade (commit 1)

### ADDED Requirement: The skill MUST exist in the measured house shape

The skill MUST ship at `.claude/skills/skill-audit/` with `SKILL.md`, `scripts/audit_cli.py`, and `references/usage.md`. Its name MUST be two lowercase hyphenated words of the form `<subject>-<process-noun>`, the shape all five existing skills share. `skill-creator` MUST NOT be treated as authority here: it caps a body at 1000 tokens that `proposal-implementation/SKILL.md` already exceeds by orders of magnitude, and it defers to a style guide this repository does not contain. `audit_cli.py` MUST be stdlib-only, MUST expose `main(argv) -> int`, MUST use argparse subparsers, and MUST emit JSON to stdout with `sort_keys=True`.

#### Scenario: The front door is a real process

- GIVEN `audit_cli.py` on disk
- WHEN it is invoked as a subprocess with any valid subcommand
- THEN it SHALL exit with an integer status and SHALL write parseable JSON to stdout
- AND it SHALL import nothing outside the standard library.

#### Scenario: The name was proven free before it was written

- GIVEN the identifiers `skill-audit`, `skill_audit`, `audit_cli`
- WHEN the repository is searched with `.gitignore` disabled and hidden files included
- THEN no match SHALL exist outside this change's own artifacts.

### ADDED Requirement: The audit MUST refuse to run without a shell

The activation contract MUST make an unavailable shell a hard refusal, not a degradation to reading. An audit that cannot execute cannot adjudicate, and every claim it produced would be a candidate marked `read-only` with no `CONFIRMED` finding anywhere — which is the exact condition that cost three consecutive phases in this change. The refusal MUST name the missing capability and MUST produce no report.

#### Scenario: No shell

- GIVEN an environment where the skill cannot execute a subprocess
- WHEN the audit is invoked
- THEN it SHALL refuse and SHALL name the missing shell as the reason
- AND it SHALL NOT emit a report, a finding, or a candidate.

### ADDED Requirement: The moves table MUST be complete, typed, and never sized by an underived numeral

Doctrine MUST carry one parseable table with exactly one row per move 0 through 7, plus exactly one row for the irreducibly textual move that has no code and no lock. Each row MUST name either a subcommand of `audit_cli.py` or the literal `doctrine`, and every named subcommand MUST be one the roster check has already proven exists. Any numeral in this skill's own doctrine that states the size of an enumeration MUST be derived by the self-audit or MUST be absent — including in headings. A hand-written count of the skill's own moves is the defect class this skill exists to find, and the proposal already carries one instance of it.

#### Scenario: A move loses its row

- GIVEN move 5's row is deleted from the table
- WHEN the self-audit runs
- THEN it SHALL fail and SHALL name the missing move by number.

#### Scenario: A row names a subcommand that does not exist

- GIVEN a row whose `script` cell names a subcommand absent from argparse's own refusal output
- WHEN the self-audit runs
- THEN it SHALL fail and SHALL name that cell.

---

## Group 2 — The moves, as doctrine (commit 1)

### ADDED Requirement: Move 0 — enumerate a closed surface both ways, never review

The audit MUST begin by enumerating a closed surface from both sides and MUST NOT begin by reviewing a change for correctness or reading a diff. Every enumeration MUST be treated as a candidate until something executes; enumeration by reading was wrong twice and incomplete once in the corpus this skill is derived from. Move 0 MUST also compare any numeral in the subject's prose against the enumeration that immediately follows it.

#### Scenario: A numeral against the list beneath it

- GIVEN a document line stating a count immediately above a bulleted enumeration whose length differs
- WHEN move 0 runs over that document
- THEN a finding SHALL be emitted naming the numeral's `file:line` and the enumeration's `file:line`.

#### Scenario: Reading alone never produces a finding

- GIVEN a surface enumerated only by reading, with nothing executed
- WHEN the audit reports
- THEN every entry SHALL be marked `read-only` and SHALL be reported as a candidate.

### ADDED Requirement: Move 1 — build from zero following only the doctrine, then diff

The audit MUST construct the expected artifact from the doctrine alone and diff it against the producer's actual output, subject to the five soundness conditions in Group 4. This is the only move that catches doctrine and producer drifting while each stays internally consistent.

#### Scenario: Both sides agree and both are wrong together

- GIVEN a from-zero side seeded by calling the producer
- WHEN the comparison runs
- THEN the soundness gate SHALL reject the comparison before its result is read.

### ADDED Requirement: Move 2 — run against the live subject on disk, never only fixtures

At least one probe of every audited surface MUST drive the subject as it exists on disk. A synthetic fixture is built from the same doctrine as the artifact under audit and therefore cannot exhibit the drift being looked for.

#### Scenario: A fixture-only audit

- GIVEN an audit whose every probe ran against a constructed fixture
- WHEN it reports
- THEN it SHALL carry no `CONFIRMED by execution` finding for that surface
- AND the surface SHALL appear under `## Unchecked`.

### ADDED Requirement: Move 3 — fake the external boundary and assert what crossed it

Where a subject has an external boundary, the audit MUST substitute a double at that boundary and assert on what crossed the wire. The boundary MUST be faked, never dialled. Assertions about the wire are otherwise invisible without spending quota.

#### Scenario: A subject with no external boundary

- GIVEN a subject that makes no outbound call
- WHEN move 3 is considered
- THEN it SHALL be recorded as not applicable with that reason
- AND it SHALL NOT be recorded as clean, passed, or skipped without a reason.

### ADDED Requirement: Move 4 — read the installed dependency as text

Every doctrine claim about a third-party dependency MUST be held against the installed dependency read as text. The audit MUST NOT import an installed service client to inspect it; importing `kaggle` runs `authenticate()`.

#### Scenario: A version claim about a third party

- GIVEN doctrine asserting a symbol or behaviour of an installed package
- WHEN move 4 runs
- THEN the package's source SHALL be read from disk as text
- AND no import of that package SHALL occur.

### ADDED Requirement: Move 5 — read-only probe, a GET and never a write

A live probe MAY be made only with the user's explicit consent, MUST be read-only, and MUST carry no more authority than the shipped code carries. Its result is evidence about the environment and MUST NOT be reported as evidence about the code.

#### Scenario: A live probe's result is scoped

- GIVEN a consented read-only GET that succeeds
- WHEN it is written into the report
- THEN it SHALL be recorded as an environment fact
- AND no finding SHALL cite it as evidence about the subject's code.

### ADDED Requirement: Move 6 — invert every lock

Every lock the audit relies on MUST be proven to fire by breaking the fact it guards. A lock that does not fire under inversion is a defect in the lock and MUST be reported as one.

#### Scenario: A lock that does not fire

- GIVEN a lock whose guarded fact is broken by inversion
- WHEN the suite runs and the lock still passes
- THEN a finding SHALL be emitted against the lock
- AND the lock SHALL NOT be counted as evidence for anything.

### ADDED Requirement: Move 7 — verify counts rise, not that they stay green

The audit MUST compare per-harness test counts before and after, and a count that did not rise MUST be a finding. Both harnesses MUST be reported separately because they are disjoint and no single command runs both: `python3 -m unittest discover -s tests` and `npm test`.

#### Scenario: Tests added and the count unchanged

- GIVEN a before-count equal to the after-count on a harness where tests were added
- WHEN `counts` runs
- THEN a finding SHALL be emitted naming that harness.

#### Scenario: A harness whose selector may match nothing

- GIVEN a harness whose test command could expand to an empty file set while still exiting clean
- WHEN `counts` cannot establish that the selector matched files
- THEN it SHALL refuse that harness rather than report zero.

### ADDED Requirement: The irreducibly textual move MUST be carried and marked unlocked

Doctrine MUST carry one move with no code and no lock: read every artifact's opening against its own frontmatter. Its row MUST state that it has no lock. Prose-against-prose staleness in a single file cannot be mechanized, and three live instances exist in `remote-execution/SKILL.md`; claiming the table is complete would be the same defect the skill exists to find.

#### Scenario: The unlocked move is honestly typed

- GIVEN the moves table
- WHEN the self-audit reads the textual move's row
- THEN that row SHALL name no subcommand and SHALL be marked as carrying no lock.

---

## Group 3 — The failure modes of the moves themselves (commit 1 doctrine, locked in commits 2–4)

Each of these already cost a phase in this repository. Each is a requirement, not a caveat.

### ADDED Requirement: A test MUST NOT pass off its own fixture's name

Every lock matching a needle against generated output MUST first assert the needle is absent from the fixture's own name and path.

#### Scenario: The needle is in the fixture name

- GIVEN a fixture whose name contains the needle the assertion searches for
- WHEN the lock runs
- THEN the lock SHALL fail on the precondition, before its own assertion.

### ADDED Requirement: A fixture that cannot reach the guarded branch MUST fail its own lock

Reachability of the guarded branch MUST be established, not assumed. An assertion over a branch the fixture cannot enter is unfalsifiable.

#### Scenario: The branch is never entered

- GIVEN a fixture that cannot reach the guarded branch
- WHEN the lock runs
- THEN it SHALL fail as unreachable rather than pass.

### ADDED Requirement: A wholesale double MUST NOT stand in for a process claim

Every roster probe MUST drive the subject as a subprocess. A double that replaces a function wholesale can never hold a claim about the process it would have run.

#### Scenario: A mocked roster probe

- GIVEN a roster probe implemented by patching the subject's function
- WHEN the self-audit inspects the probe
- THEN it SHALL fail and SHALL name the probe.

### ADDED Requirement: A green suite MUST NOT be reported as evidence

Greenness MUST NOT appear as evidence for any finding or for any clean result. Evidence is a named execution with a named observation.

#### Scenario: A clean result with no observation

- GIVEN a `## Clean, stated as results` entry whose only support is that the suite passed
- WHEN `check-report` validates the report
- THEN it SHALL reject the entry.

### ADDED Requirement: Containment MUST NOT be proven by `git status`

`git status --porcelain` over a gitignored directory is empty by construction. Every claim that a box was cleaned or that a directory was untouched MUST be proven by a before/after content manifest.

#### Scenario: A cleanliness claim backed by porcelain

- GIVEN a containment claim citing `git status`
- WHEN `check-report` validates it
- THEN it SHALL reject the claim and SHALL name the manifest as the required evidence.

### ADDED Requirement: A live GET MUST NOT be claimed as a receipt

A successful request proves the environment answered. It proves nothing about the subject's code and MUST NOT be recorded as a receipt.

#### Scenario: A request reported as a code fact

- GIVEN a finding whose evidence is a live request's success
- WHEN `check-report` validates it
- THEN it SHALL reject the finding.

### ADDED Requirement: Every new name MUST be proven free before it is written

Before any new class, path, or identifier is authored, the repository MUST be searched with `.gitignore` disabled and hidden files included, because `implementations/` is otherwise invisible to the default search.

#### Scenario: A name already occupied in the ignored tree

- GIVEN a candidate name occurring only under `implementations/`, as `firedrill` does at `implementations/Domain_Adaptation/src/MIL_CREDA_Benchmark/harness.py:1072`
- WHEN the default search is used
- THEN it SHALL report no match and that negative SHALL NOT be accepted as evidence
- AND the search with `.gitignore` disabled and hidden files included SHALL be the deciding one.

### ADDED Requirement: Inversions MUST be restored by inverse patch

An inversion MUST be undone by applying its inverse, never by `git checkout --`, and the restoration MUST be confirmed by content comparison. Checkout restores from the index and can silently discard an unrelated edit made in the same window.

#### Scenario: Restoration is proven

- GIVEN an inverted production line restored by inverse patch
- WHEN the restoration is confirmed
- THEN the file SHALL be byte-identical to its pre-inversion content
- AND no other file SHALL differ.

---

## Group 4 — The from-zero comparison's soundness conditions (commit 2)

### ADDED Requirement: Condition 1 — the doctrine side MUST NOT reference the producer at all

The from-zero side MUST derive both its **contents and its element set** without invoking, importing, or reading any symbol of the producer — not to seed a directory, not to decide which paths to write, and not to source a constant. This MUST be enforced mechanically by asserting the derivation function's syntax tree contains no reference to the producer module. The precedent this mechanism is modelled on fails exactly here: `doctrine_scaffold` derives file contents from doctrine but takes its path set from `impl.scaffold_gaps` (`tests/test_proposal_implementation.py:267`) and one file's contents from `impl.IGNORE_ENTRIES` (`:270`), under a docstring claiming a doctrine-faithful target (`:240`). A comparison built that way cannot catch an element missing from both sides, which is the defect the comparison exists to catch.

#### Scenario: The precedent's own shape is rejected

- GIVEN a derivation function that calls the producer to obtain the set of elements to build
- WHEN the soundness gate runs
- THEN it SHALL fail and SHALL name the producer reference
- AND the comparison's result SHALL NOT be read.

#### Scenario: A producer constant is borrowed

- GIVEN a derivation function that imports a constant from the producer module
- WHEN the syntax tree is inspected
- THEN the gate SHALL fail and SHALL name that constant.

### ADDED Requirement: Condition 2 — the comparison domain MUST be stated and closed

Every comparison MUST declare its domain before running. An open domain makes the diff noise, and noise gets exempted until the comparison means nothing.

#### Scenario: An undeclared domain

- GIVEN a comparison with no declared domain
- WHEN the soundness gate runs
- THEN it SHALL refuse to run the comparison.

### ADDED Requirement: Condition 3 — both directions MUST be reported as three empty sets

Every comparison MUST produce `unregistered` (in code, in no doctrine), `phantom` (in doctrine, not in code) and `duplicated` (restated by hand in more than one place), never a boolean. They are different defects with different remedies.

#### Scenario: A boolean verdict

- GIVEN a comparison reporting pass or fail
- WHEN the self-audit inspects it
- THEN it SHALL fail and SHALL name the missing sets.

### ADDED Requirement: Condition 4 — the comparison MUST be reachable-red in both directions

Adding an element to the code side MUST fire `unregistered`; deleting a row from the doctrine side MUST fire `phantom`. Both MUST be proven by inversion.

#### Scenario: Only one direction fires

- GIVEN a comparison where deleting a doctrine row produces no failure
- WHEN the inversion runs
- THEN the comparison SHALL be reported as defective, not as passing.

### ADDED Requirement: Condition 5 — the doctrine side MUST be derived by parsing a table, never by reading prose

The from-zero side is authored by a reader who has just read the artifact and can reproduce it unconsciously. The doctrine side MUST therefore come from a parseable table. Where the subject has no such table, "there is no table" MUST be the finding, emitted as a first-class result.

#### Scenario: A subject with no parseable table

- GIVEN a surface whose documentation states the set only in prose
- WHEN `roster` runs against it
- THEN it SHALL emit `no table` as a result with the searched `file:line` range
- AND it SHALL NOT raise, SHALL NOT exit non-zero as an error, and SHALL NOT report the surface as clean.

---

## Group 5 — `roster` (commit 2)

### ADDED Requirement: `roster` MUST derive the code side by executing the subject

`roster --subject <dir> --surface <name>` MUST derive the code side by whichever of two language-independent probes the surface declares, and MUST NOT contain any restatement of a subject's roster. The two probes are: (1) **the refusal message is the roster** — drive the subject with a nonsense token and take the accepted set the subject enumerates in its own refusal; (2) **the parser is the roster** — hand the documented invocation to the real process, where an unrecognised flag never reaches the guard. Probe 1 is confirmed available for the first subject at `engine/cli.mjs:320`. A Python subject MAY additionally declare a syntax-tree derivation. One syntax-tree tool covering all subjects is rejected: it is Python-only and would produce nothing for the first subject, which is JavaScript.

#### Scenario: The refusal message yields the accepted set

- GIVEN `proposal-deliberation`'s CLI driven as a subprocess with a nonsense operation
- WHEN `roster` reads the refusal
- THEN it SHALL recover the nine accepted operation names from the refusal text alone
- AND no operation name SHALL appear as a literal anywhere in the auditor.

#### Scenario: The token must be present, not absent

- GIVEN the subject's guard fires only when the token is present, per `engine/cli.mjs:319`
- WHEN the probe omits the token entirely
- THEN no refusal is produced and `roster` SHALL report the probe as having yielded nothing
- AND it SHALL NOT report an empty accepted set.

#### Scenario: A surface with neither probe available

- GIVEN a surface that exposes no refusal message and no parser
- WHEN `roster` runs
- THEN it SHALL emit `no derivation available for this surface` as a first-class result
- AND it SHALL NOT pass silently.

### ADDED Requirement: `roster` MUST report a hand-restated set as `duplicated`

A set restated by hand in more than one place MUST be reported even when every restatement currently agrees. Agreement today is not derivation; the corpus records a stale operation name that survived because every restatement agreed with the stale one.

#### Scenario: Three agreeing hand-restatements

- GIVEN a set restated in a reference document and in a test file, both agreeing with the running code
- WHEN `roster` runs
- THEN both restatements SHALL appear under `duplicated`
- AND the surface SHALL NOT be reported as clean.

#### Scenario: Enumeration disagrees with execution

- GIVEN a read-derived enumeration of a surface that differs from the set the running subject emits
- WHEN both are available
- THEN the executed set SHALL decide
- AND the discrepancy SHALL be reported as a defect in the enumeration, not silently overwritten.

---

## Group 6 — `manifest` and `counts` (commit 3)

### ADDED Requirement: `manifest` MUST prove containment by content, not by version control

`manifest --root <dir> [--baseline <file>]` MUST emit a sorted `path → sha256` mapping over a declared path set, and with `--baseline` MUST emit `added`, `removed` and `changed`. It MUST be the sole evidence that a box was cleaned and that `implementations/Domain_Adaptation` was not edited.

#### Scenario: A box is proven cleaned

- GIVEN a box created under `implementations/_<name>` and removed in cleanup
- WHEN `manifest` runs against the parent after the test
- THEN the box's paths SHALL appear under `removed`
- AND the deletion SHALL NOT be asserted by any other means.

#### Scenario: The target is proven untouched

- GIVEN a baseline manifest of `implementations/Domain_Adaptation` taken before the suite
- WHEN the suite finishes and `manifest` runs again
- THEN `added`, `removed` and `changed` SHALL all be empty.

#### Scenario: One changed byte is detected

- GIVEN a single byte altered inside a box
- WHEN `manifest --baseline` runs
- THEN `changed` SHALL be non-empty and SHALL name that path.

### ADDED Requirement: `counts` MUST report both harnesses separately and require a rise

`counts --before <file> --after <file>` MUST report per-harness counts and the delta, MUST state that no single command runs both harnesses, and MUST treat a count that did not rise as a finding.

#### Scenario: A single-harness report

- GIVEN a report claiming a repository-wide count from one harness
- WHEN `check-report` validates it
- THEN it SHALL reject the claim.

---

## Group 7 — Adjudication (commit 4)

### ADDED Requirement: The consumer decides, and only execution establishes what the consumer does

When both halves of a surface disagree, the audit MUST adjudicate by the behaviour of the installed or live consumer, established by execution. The evidence ladder, highest first, is: the installed consumer measured; two independent consumers agreeing under constraints neither can be changed for; the live subject on disk; fixtures the audit built; prose in either artifact. Prose is lowest because both sides are claims until something executes.

#### Scenario: Prose against prose

- GIVEN a disagreement whose only evidence on both sides is prose
- WHEN adjudication runs
- THEN neither side SHALL be declared wrong
- AND the finding SHALL be marked `read-only` and reported as a candidate.

### ADDED Requirement: A prose claim about a consumer is never consumer evidence

A statement in any document describing what a consumer does MUST NOT be used as evidence of what that consumer does. This rule was proven twice in the corpus and MUST be stated in doctrine.

#### Scenario: A document describes the consumer

- GIVEN an adjudication citing a reference document's description of the consumer's behaviour
- WHEN `check-report` validates the finding
- THEN it SHALL reject the citation as consumer evidence.

### ADDED Requirement: `not adjudicable` MUST be a distinct required outcome with its own report section

Every finding MUST carry exactly one adjudication of `doctrine wrong`, `artefact wrong`, or `not adjudicable`. `not adjudicable` means enumeration found no consumer at all: the question is not which side is wrong but that this half has no other half. Its remedy is build-or-delete, a user decision with real cost, and that is the structural reason report-then-fix is the correct ordering. The report MUST carry a section for these findings distinct from the ranked findings. The audit MUST NOT apply the rule "every reported fact must be branched on"; it is false by construction, because facts are deliberately reported without gating. The bar is documentation, not consumption.

#### Scenario: A half with no other half

- GIVEN a value declared and enumerated in code that no consumer reads or branches on
- WHEN adjudication runs
- THEN the finding SHALL be marked `not adjudicable`
- AND it SHALL appear in its own report section with build-or-delete named as the remedy.

#### Scenario: A reported-but-never-gating value is not a finding

- GIVEN a value that is computed, documented, and deliberately never branched on
- WHEN adjudication runs
- THEN no finding SHALL be emitted on the ground that nothing branches on it.

#### Scenario: A stage is not an operation

- GIVEN `SCIENTIFIC_WORKFLOW` declared a route stage at `engine/runtime-metrics.ts:3` and `:14` and refused as an operation at `engine/cli.mjs:319-320`
- WHEN adjudication runs
- THEN the finding SHALL be `not adjudicable` pending a consumer of `routeStages`
- AND it SHALL NOT be reported as a defect.

---

## Group 8 — The report and `check-report` (commit 4)

### ADDED Requirement: The report MUST satisfy a mechanically enforced shape

`check-report <file>` MUST validate a damage report and MUST reject one that omits any of: (1) ranked findings, each naming **both halves at `file:line`**; (2) the move number that found each; (3) a per-finding marker of `CONFIRMED by execution` or `read-only`, mandatory with no default; (4) a per-finding adjudication from the three values in Group 7; (5) `## Clean, stated as results`; (6) `## Unchecked`; (7) a falsifier; (8) a changed-line forecast for the fix that would follow. A report with no `CONFIRMED` finding MUST say so in its first line. A shape enforced only by prose is a hand-maintained roster, which is the class this skill exists to find.

#### Scenario: A finding with no marker

- GIVEN a report whose finding carries neither `CONFIRMED by execution` nor `read-only`
- WHEN `check-report` runs
- THEN it SHALL reject the report and SHALL name the finding.

#### Scenario: A finding naming one half

- GIVEN a finding citing a single `file:line`
- WHEN `check-report` runs
- THEN it SHALL reject it as a candidate rather than a finding.

#### Scenario: An entirely read-only report

- GIVEN a report in which no finding is marked `CONFIRMED by execution`
- WHEN `check-report` runs
- THEN it SHALL require that fact in the report's first line
- AND SHALL reject the report if it is absent.

#### Scenario: An empty clean section is distinguishable from an unrun one

- GIVEN a surface that was enumerated and found sound
- WHEN the report is written
- THEN it SHALL appear under `## Clean, stated as results` with the enumeration that supports it
- AND a surface that was never enumerated SHALL appear under `## Unchecked` instead.

### ADDED Requirement: The report MUST be delivered before any fix, and the terminal state MUST be a handoff

The audit MUST deliver its report before proposing or making any repair, and MUST make no repair of its own. Its terminal state MUST be a handoff whose shape matches the house's existing `MAINTENANCE` idiom — `mutations: 0`, `documentAuthority: FORBIDDEN`, `explicitHandoffRequired: true` (asserted at `tests/proposal-deliberation-cli-operation-surface.test.mjs:92-97`). A skill cannot invoke SDD: every `sdd-*` skill is `disable-model-invocation: true`, `user-invocable: false`, `delegate_only`. The audit **is** the exploration, run under its own doctrine because that doctrine requires a shell, and its report MUST land where `sdd-propose` reads. Any question put to the user MUST use the interactive question facility, never a question typed into a reply. Launching `sdd-explore` is rejected on evidence: it ran twice in this change with no shell.

#### Scenario: A one-line phantom is still not repaired

- GIVEN a `phantom` finding whose remedy is a single-line deletion
- WHEN the audit completes
- THEN it SHALL report the finding and SHALL make no edit
- AND the terminal state SHALL be a handoff carrying zero mutations.

#### Scenario: A clean surface still produces a full report

- GIVEN an audit that found nothing
- WHEN it completes
- THEN it SHALL still deliver the full report shape, including a populated `## Clean, stated as results`.

#### Scenario: The slice is the user's decision

- GIVEN a subject larger than one closed surface
- WHEN the audit is invoked
- THEN it SHALL propose a slicing and ask before running
- AND it SHALL ask through the interactive question facility.

---

## Group 9 — The auditor survives its own audit (commits 1–4)

### ADDED Requirement: The auditor MUST be audited by its own moves

`tests/test_skill_audit.py` MUST apply the skill's own moves to the skill. Without this, the skill joins the defect class it exists to find. At minimum: move 0 against `audit_cli.py`'s own subcommand surface, taking argparse's refusal as the roster and holding it to the doctrine's subcommand table with the same three empty sets; the Group 4 soundness gate applied to the auditor's own derivation function; the moves table's completeness and typing; the report schema's self-description, so every field `check-report` requires has a row in the report-shape table; and the repository's vocabulary-floor and lexicon disjointness guards, copied, so the new skill cannot borrow a target's vocabulary.

#### Scenario: A subparser with no table row

- GIVEN a subparser added to `audit_cli.py` and no matching doctrine row
- WHEN the self-audit runs
- THEN `unregistered` SHALL be non-empty and SHALL name that subcommand.

#### Scenario: A table row with no subparser

- GIVEN a doctrine table row deleted while its subparser remains
- WHEN the self-audit runs
- THEN `phantom` SHALL be non-empty and SHALL name that row.

#### Scenario: The auditor's own doctrine side imports its producer

- GIVEN an `import audit_cli` added to the auditor's derivation helper
- WHEN the soundness gate runs
- THEN it SHALL fail and SHALL name the import.

#### Scenario: A planted report with no marker

- GIVEN a report fixture whose finding carries no marker, and whose filename does not contain the marker text
- WHEN `check-report` runs against it
- THEN it SHALL reject the report.

### ADDED Requirement: The copied derivation helpers MUST be byte-identical to their originals

`markdown_table_rows`, `returned_keys`, `dict_literal_keys` and `subcommand_surface` MUST be copied into `tests/test_skill_audit.py`, not shared. Sharing means editing a 75-class suite inside a change about a different skill — the exact scope creep both archive reports flagged. A lock MUST assert each copy is byte-identical to its original, so drift becomes a red rather than a later discovery.

#### Scenario: A copy drifts

- GIVEN one copied helper edited in either location
- WHEN the drift lock runs
- THEN it SHALL fail and SHALL name the helper and both locations.

---

## Group 10 — The first damage report (commit 5)

### ADDED Requirement: A validated damage report on `proposal-deliberation`'s operation surface MUST ship

The change MUST produce one report at `openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md`, covering the accepted-operation surface only, validated by `check-report`, containing at least one `CONFIRMED by execution` finding, at least one `not adjudicable` finding, and a changed-line forecast. It MUST report only; it MUST NOT fix anything in `proposal-deliberation`. The other three slices — route-metric stages, error codes, and the public export surface — are named and deferred.

#### Scenario: The report is validated by the tool it ships beside

- GIVEN the delivered report
- WHEN `check-report` runs against it
- THEN it SHALL be accepted
- AND the report SHALL name the three hand-restated locations of the operation set with the executed set as the deciding evidence.

#### Scenario: Nothing in the audited subject changes

- GIVEN a baseline manifest of `.claude/skills/proposal-deliberation/`
- WHEN the change is complete
- THEN `added`, `removed` and `changed` SHALL all be empty for that subtree.

---

## Cross-cutting requirements

### ADDED Requirement: Containment MUST hold for every execution the audit performs

Throwaway boxes MUST live at `implementations/_<name>` and never in the system temporary directory, because `verify` refuses targets outside `<forge>/implementations` and `implementations/*` is gitignored. Every box MUST be removed in cleanup and the removal MUST be proven by `manifest`. `implementations/Domain_Adaptation` MUST never be edited, proven the same way. External boundaries MUST be faked and never dialled. The only permitted live call is a consented read-only GET. No installed service client MUST ever be imported. Churn MUST be forecast before any fix chain begins.

#### Scenario: A box outside the permitted root

- GIVEN a box created under the system temporary directory
- WHEN the containment lock runs
- THEN it SHALL fail and SHALL name the path.

#### Scenario: No remote call is made by this change

- GIVEN the complete suite for this change
- WHEN it runs
- THEN no outbound network request SHALL be issued.

### ADDED Requirement: Every new lock MUST be proven reachable-red

Under this project's `strict_tdd` setting, every lock that passes on its first run MUST be proven reachable-red by inversion, restored by inverse patch, and confirmed by content comparison. An inversion that does not fire is a defect in the lock, never a pass. Greenness alone is never evidence a lock runs.

#### Scenario: A lock's reachable-red proof

- GIVEN a new lock that passes on first run
- WHEN the fact it guards is inverted
- THEN the lock SHALL fail
- AND restoring by inverse patch SHALL return it to green with no other file altered.

### ADDED Requirement: The change MUST be purely additive

No existing file may be modified. The change adds one skill directory, one test file and one report, so any slice reverts independently and neither existing harness baseline can be disturbed.

#### Scenario: A revert restores the repository exactly

- GIVEN any slice reverted
- WHEN both harnesses run
- THEN each SHALL return to its pre-change count
- AND no existing test SHALL have changed.

---

## Explicit non-goals

| Non-goal | Reason |
|---|---|
| Fixing anything in `proposal-deliberation` | Report-then-fix is the product rule, and the `not adjudicable` exit makes the remedy a user decision with real cost. Shipping the auditor and a fix together would prove the ordering does not hold. |
| Fixing the stale `remote-execution/SKILL.md` opening | The three claims at `:12-19` are confirmed by reading disk here and belong to a `remote-execution` change; they are carried only as the falsifier's test material. A **separate** stale claim in that file is already recorded as open at `the-flow-names-what-it-needs/archive-report.md:314-315` — that record covers the `remoteExecution` fact claim, not these three, and the proposal conflated them. |
| Auditing the other engine modules, the `.mjs` suites, the error-code roster, or the public export surface | One pass over that surface reproduces the 3,438-line overrun recorded this week. Only the operation-surface slice ships. |
| Correcting `openspec/config.yaml`'s test commands | Its `apply`/`verify` commands select one Python file by pattern and use a glob that differs from `package.json`'s — a genuine instance of this skill's defect class, found while writing this spec. It is a config change with its own blast radius and belongs to its own change. Recorded, not fixed. |
| Sharing the derivation helpers with `tests/test_proposal_implementation.py` | Sharing means editing a 75-class suite inside a change about a different skill. |
| An AST-based single tool for move 0 | Python-only. The first subject is JavaScript, so it would have produced nothing at all. |
| An opt-in "obvious repairs" path | The wall between reporting and fixing is the product. |
| `skill-creator`'s constraints | It caps a body at a size an existing skill already exceeds and defers to a style guide this repository does not have. The five existing skills are the only authority. |

## Acceptance

- `python3 -m unittest discover -s tests` green at 902 plus the new tests, with the count **proven to have risen**, and `npm test` green at 371 with its selector proven to have matched files.
- Every new lock proven reachable-red by inversion and restored by inverse patch.
- `roster` recovers `proposal-deliberation`'s nine accepted operations from the running CLI's own refusal, with no operation name restated anywhere in the auditor.
- "There is no table" and "no derivation available" are both first-class results, reachable in tests.
- `check-report` rejects a report whose finding carries no `CONFIRMED`/`read-only` marker, proven with a planted fixture whose name does not contain the marker text.
- `manifest` proves a box was cleaned and `implementations/Domain_Adaptation` untouched, with no use of `git status` anywhere in the suite.
- The delivered damage report validates, carries at least one `CONFIRMED by execution` finding, at least one `not adjudicable` finding, and a changed-line forecast.
- The auditor's own subcommand roster is reachable-red in both directions.

One in-scope item carries no behavioural delta and therefore no requirement: the moves table is referred to throughout the proposal as the "seven-move table" while it enumerates moves 0 through 7. The heading is corrected at apply time under the Group 1 numeral rule, and is stated here so it is not read as scope creep.
