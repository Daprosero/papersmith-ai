# Proposal: the-skill-that-audits-the-others

Change: `the-skill-that-audits-the-others` · New skill: `skill-audit` · Store: openspec (Engram disconnected)

## Intent

Twenty defects were found in this repository this week. **None was found by reviewing a
change for correctness, and none by reading a diff.** Every one was found by exhaustive
enumeration over a closed surface, and every enumeration was a candidate until something
ran — enumeration was wrong twice and incomplete once, each corrected only by execution.

That method exists today only as a habit in one session's head. This change makes it a
skill: a maintenance skill the user invokes against any other skill in this forge, which
tests the wiring, drives the subject **from zero** and compares against what is on disk,
**adjudicates by execution** which side is wrong, delivers a **damage report first**, and
hands off to SDD only on the user's acceptance.

**This phase had no Bash either.** That is the second consecutive SDD phase in this change
with no shell, and it is the same defect the exploration recorded about `sdd-explore`. Every
claim below is therefore marked **read-confirmed on disk** or **unchecked — needs a shell**.
Nothing is marked confirmed by execution, because nothing was executed. See §Verification
status and Risk R1.

## Verification status of the exploration's four unexecuted candidates

The exploration flagged four candidates and asked that they be settled before entering as
findings. Three are settled by reading disk; one cannot be settled without a shell.

| # | Candidate | Verdict | Evidence |
|---|---|---|---|
| 1 | `proposal-deliberation`'s four-way operation-set divergence | **Struck as framed. Reduced and kept.** | `cli.mjs:297-306` is the truth (9). `usage.md:264-266` restates all 9 and **agrees**. `tests/proposal-deliberation-cli-operation-surface.test.mjs:31-41` restates all 9 and **agrees**. `SKILL.md` names **8**, not 4 — the exploration read one scoped table (`:245-251`, headed "**Other** engine operations") as the whole roster. The missing one is `MAINTENANCE`, and `usage.md:274` documents its absence from the flow deliberately. **What survives: three of the four rosters are hand-restated and none is derived** — the structural weakness, not a contents mismatch |
| 2 | Two stale "does not exist yet" claims in `remote-execution/SKILL.md` | **Confirmed, read-only. And a third found.** | (a) `:12-15` "Nothing here yet talks to a real service — that is a concrete adapter, still to come … exercised against a `FakeAdapter` only" vs `:3` shipping `adapters/kaggle.py`; the file exists (`scripts/adapters/kaggle.py`). (b) `:537` "Probe's own `remoteExecution` fact does not exist yet" — it exists; `the-flow-names-what-it-needs/archive-report.md:314-315` records this exact claim as known-open and out of scope. (c) **New:** `:19` "Three modules exist so far" is followed by **four** `- \`scripts/…\`` bullets (`:21`, `:32`, `:50`, `:57`) and the skill ships eight scripts |
| 3 | `npm test`'s scope | **Partly settled; the load-bearing half is unchecked.** | `package.json:8` is `node --test "tests/**/*.mjs"`. **48** `.mjs` files match, not 50, all flat in `tests/`; the engine ships **no** test files of its own. **Unchecked:** node expands that glob only from v22; on an older runtime the pattern is a literal path and the command matches nothing while still exiting clean. Cannot be settled without running it |
| 4 | `SCIENTIFIC_WORKFLOW` residue | **Confirmed as residue, not yet adjudicable.** | `runtime-metrics.ts:3` and `:14` still declare it a `RouteMetricStage` while `cli.mjs:319` refuses it as an operation and the surface test asserts the refusal (`:79`). A stage is not an operation, so this is not automatically a defect: it is adjudicable only by finding who reads `routeStages`. **This is the change's demonstration of the "not adjudicable" exit** |

**A correction the exploration did not make, found while checking it:** `doctrine_scaffold`
(`tests/test_proposal_implementation.py:238-290`) — the precedent the whole from-zero
mechanism is modelled on — **calls the producer** (`impl.scaffold_gaps`) to decide which
paths to write. Only the file *contents* are doctrine-derived. So the precedent satisfies
soundness condition 1 for content and violates it for the path set: it cannot catch a path
missing from both sides. The new mechanism must not inherit this, and this is the concrete
evidence for deriving the doctrine side by parsing a table.

**Corrected counts:** 48 `.mjs` test files (not 50); 53 `.ts` files under `engine/`, 51
excluding `_pi-compat/` (not 55).

## Scope

### In scope

| Deliverable | Files |
|---|---|
| The skill | `.claude/skills/skill-audit/SKILL.md` (new) — seven-move table, Decision Gates, evidence ladder, mandatory report shape, handoff contract |
| Its front door | `.claude/skills/skill-audit/scripts/audit_cli.py` (new) — `roster`, `manifest`, `counts`, `check-report` |
| Copied derivation helpers | `markdown_table_rows`, `returned_keys`, `dict_literal_keys`, `subcommand_surface` — **copied** into `tests/test_skill_audit.py`, not shared |
| Its own suite | `tests/test_skill_audit.py` (new) — including the auditor run against the auditor |
| Reference | `.claude/skills/skill-audit/references/usage.md` (new) |
| First damage report | `openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md` (new) — report only |

### Out of scope — recorded with reasons

- **Fixing anything in `proposal-deliberation`.** Report-then-fix is the product rule, and the
  structural reason is the "not adjudicable" exit: when a half has no other half, the remedy
  is build-or-delete, a user decision with real cost. Shipping the auditor and a fix in one
  change would prove the ordering does not hold.
- **Fixing the three `remote-execution` stale-prose claims.** Real, confirmed, and already
  recorded as open by `the-flow-names-what-it-needs/archive-report.md:314-315`. They belong to
  a `remote-execution` change. Carried here only as the falsifier's test material (§Falsifier).
- **Auditing the other 51 engine modules, the 48 `.mjs` tests, `usage.md`'s error-code roster,
  or `exports.ts`.** One pass over that surface reproduces the 3,438-line overrun recorded this
  week. §First subject slices it; only slice A ships.
- **`skill-creator`'s constraints.** It caps a skill body at 1000 tokens while
  `proposal-implementation/SKILL.md` is far past that, and it defers to a
  `docs/skill-style-guide.md` this repository does not have. **The five existing skills are the
  only authority**; house shape below is measured from them.
- **Any edit under `implementations/`.** `Domain_Adaptation` is never touched, and that is
  proven by a content manifest, never by `git status --porcelain` (which is empty by
  construction for a gitignored directory).
- **Any call to a real service.** The one permitted live call is a read-only GET with the same
  authority the shipped code has; this change makes none.
- **Sharing the derivation helpers with `tests/test_proposal_implementation.py`.** Sharing means
  editing a 75-class suite inside a change about a different skill — the exact scope creep both
  archive reports flagged as WARNINGs.

## Capabilities

**New:** none. **Modified:** none. This change adds a skill, its scripts, its test suite and
one report. No `openspec/specs/` capability changes at the requirement level.

## Approach

### The name — `skill-audit`, and why not `skill-firedrill`

Measured house shape: `paper-ingestion`, `remote-execution`, `proposal-deliberation`,
`proposal-implementation`, `kaggle-accounts`. All five are `<subject>-<process-noun>`, two
lowercase hyphenated words, the second a multi-syllable noun naming what is done to the
subject. `skill-audit` is that construction exactly, with `skill` as the subject domain the
way `paper` is in `paper-ingestion`.

**Rejected: `skill-firedrill`.** Three counts. It is a coined compound where every house name
is a plain noun phrase. "Firedrill" means rehearsing a *response*, not verifying a *fact*.
And the house **already owns a word for rehearsal**: `remote-execution/SKILL.md:541-543`,
"A smoke run is a rehearsal, not a submission." A second word for an occupied concept is how
a vocabulary drifts — the failure this forge already polices with `FORGE_LEXICON`.

**Considered and rejected: `skill-conformance`.** Conformance testing presumes the
specification is right. This skill's whole contribution is that **either side can be wrong**
and execution decides. An auditor checks the books against reality and reports the
discrepancy without presuming which is at fault; that is the right word, and it is the
user's own.

**Stated cost:** `audit` already appears in this repository (`self-audit.ts`,
`consistency-audit.ts`, `verify`'s `audit` key), so the bare word is not greppable. Mitigated
by the *paths* being unique and rare: `.claude/skills/skill-audit/`, `tests/test_skill_audit.py`,
`audit_cli.py`. **Verified free** — `rg -i 'firedrill|skill-audit|skill_audit'` matches only
`explore.md`; `Glob` (which ignores `.gitignore`, so its negatives are real) finds no
`.claude/skills/skill-audit/` and no `tests/test_skill_audit.py`.

### What ships as code, and each script's interface

The exploration proposed moves 0, 1, 7 and the content manifest as code. **One change, forced
by evidence**: the copied helpers are Python-`ast`-based (`returned_keys`, `dict_literal_keys`)
or argparse-specific (`subcommand_surface`), and **the first subject is JavaScript**. Move 0
therefore cannot be one tool.

| Move | Ships as | Why |
|---|---|---|
| 0 enumerate | **code** — `roster` | Two derivations, one language-independent. See below |
| 1 from-zero vs today | **doctrine + a soundness gate** | The precedent (`doctrine_scaffold`) is subject-specific by nature; a general "build the product from zero" script is overbuild. What generalizes is the five soundness conditions, and one of them is mechanical (§self-audit) |
| 2 live subject on disk | doctrine | A rule about where a run points, not a program |
| 3 fake the boundary | doctrine | Per-subject test construction |
| 4 read the installed dependency as text | doctrine | One sentence with a hard rule: never import it (importing `kaggle` runs `authenticate()`) |
| 5 read-only probe | doctrine | Gated on the user; a GET, never a write |
| 6 invert every lock | doctrine | An agent action, not a program |
| 7 counts rise | **code** — `counts` | Language-agnostic and trivially general |
| containment | **code** — `manifest` | `git status --porcelain` is empty by construction for `implementations/` |
| the report itself | **code** — `check-report` | A report shape enforced by prose is a hand-maintained roster, which is the class this skill exists to find |

`audit_cli.py`, stdlib-only, argparse subparsers, `main(argv) -> int`, JSON to stdout with
`sort_keys=True` — the idiom of `remote_cli.py:1289-1454` and `accounts_cli.py`.

- **`roster --subject <dir> --surface <name>`** → three sets, never a boolean:
  `unregistered` (in code, in no doctrine), `phantom` (in doctrine, not in code), `duplicated`
  (restated by hand in more than one place). Derives the code side by whichever of two
  language-independent probes applies, declared per surface:
  1. **The refusal message is the roster.** Drive the subject with a nonsense token; the code
     enumerates its own accepted set at runtime in its own words. **Confirmed available for the
     first subject:** `cli.mjs:320` emits
     `UNKNOWN_OPERATION: … is not one of ${[...HOST_OPERATIONS, ...TOOL_OPERATIONS].join(', ')}`.
  2. **The parser is the roster.** Hand the documented invocation to the real process; an
     unrecognised flag never reaches the guard.

  Derives the doctrine side by **parsing a table** (`markdown_table_rows`), never by reading
  prose — the fifth soundness condition. **Where no table exists, the finding is "there is no
  table"**, emitted as a first-class result, not an error. Python subjects may additionally
  declare an `ast` derivation.
  **Rejected:** one AST tool covering both. It is Python-only and would have produced nothing
  at all for the first subject.
- **`manifest --root <dir> [--baseline <file>]`** → sorted `path → sha256` over a declared path
  set; with `--baseline`, three sets (`added`, `removed`, `changed`). Proves a box was cleaned
  and `Domain_Adaptation` was untouched.
  **Rejected:** `git status`. Empty by construction for a gitignored directory — recorded
  failure mode 5.
- **`counts --before <file> --after <file>`** → per-harness test counts and the delta, with the
  rule that a count which did not **rise** is a finding. Both harnesses, because they are
  disjoint: `python3 -m unittest discover -s tests` runs the four Python files (902 today) and
  `npm test` runs the 48 `.mjs` files; **no single command runs both**, a fact the report shape
  must force an auditor to state.
- **`check-report <file>`** → validates a damage report against the mandatory shape below.

### The report's shape, made mechanical

Taken from the corpus's own explore/proposal files and enforced by `check-report`:

1. **Ranked findings**, each with **both halves at `file:line`** — a finding naming one half is
   a candidate, not a finding.
2. **The move that found it**, by number.
3. **A per-finding marker: `CONFIRMED by execution` or `read-only`.** Mandatory, no default. A
   report with no `CONFIRMED` finding must say so in its first line.
4. **A per-finding adjudication**: `doctrine wrong` · `artefact wrong` · **`not adjudicable`**
   (no consumer exists — remedy is build-or-delete, a user decision with real cost).
5. **`## Clean, stated as results`** — what was enumerated and found sound, so an empty section
   is distinguishable from an unrun one.
6. **`## Unchecked`** — every surface read in regions rather than whole, every claim not
   executed. (This proposal has one; §Risks R1.)
7. **A falsifier.**
8. **A changed-line forecast** for the fix that would follow.

**Handoff, not invocation.** Every `sdd-*` skill is `disable-model-invocation: true`,
`user-invocable: false`, `delegate_only`. A skill cannot call SDD. So the audit's terminal
state is a handoff: **the audit IS the exploration**, run under its own doctrine because that
doctrine requires a shell, and its report lands where `sdd-propose` reads. The house has the
idiom — `MAINTENANCE`: `delegation_permitted`, `mutations: 0`,
`documentAuthority: FORBIDDEN`, `explicitHandoffRequired: true` (asserted at
`tests/proposal-deliberation-cli-operation-surface.test.mjs:88-95`). The acceptance question
uses `AskUserQuestion`, the idiom of `kaggle-accounts/SKILL.md:16-25`, never a question typed
into a reply.
**Rejected:** launching `sdd-explore`. It ran twice in this change with no shell, and this
skill's entire value is execution.

### How the audit survives its own audit

Without this the skill becomes the defect class it exists to find. `tests/test_skill_audit.py`
applies the skill's own moves to the skill:

- **Move 0 against itself.** Drive `audit_cli.py` with a nonsense subcommand, take argparse's
  own refusal as the roster, and hold it to the `| Subcommand | Derives | Emits |` table in
  `skill-audit/SKILL.md` — the same three empty sets. **Reachable-red both ways:** adding a
  subparser with no table row fires `unregistered`; deleting a table row fires `phantom`.
- **Move 1's soundness gate against itself.** Assert the doctrine side of that comparison is
  produced by `markdown_table_rows` over `SKILL.md` and **never** by importing `audit_cli` —
  the condition `doctrine_scaffold` violates. Enforced by asserting the derivation function's
  `ast` contains no reference to the producer module.
- **The seven-move table is complete and typed.** Exactly one row per move 0–7; each names a
  script or the literal `doctrine`; every `script` cell names a subcommand the roster check
  already proved exists.
- **The report schema is self-describing.** Every finding field `check-report` requires has a
  row in the report-shape table, and `check-report` rejects a report whose findings carry no
  `CONFIRMED`/`read-only` marker. Proven reachable-red with a planted report missing the marker.
- **The name guard.** `FORGE_VOCABULARY_FLOOR` and `FORGE_LEXICON` disjointness, copied, so the
  new skill cannot borrow a target's vocabulary.

### First subject and its slicing

`proposal-deliberation`: 51 engine modules, `cli.mjs`, `SKILL.md`, `references/usage.md`, 48
test files. Sliced **by closed surface**, not by module:

| Slice | Surface | Status |
|---|---|---|
| **A** | The 9 accepted operations, across 4 sites | **Ships.** The runtime prober works today (`cli.mjs:320`); report only |
| B | The 7 `RouteMetricStage` values (`runtime-metrics.ts:3`) | Later. The `not adjudicable` demonstration |
| C | The error codes `usage.md:255-260` names vs those the engine throws | Later |
| D | `exports.ts`'s public surface vs `SKILL.md` | Later |

Only **A** is in this change, and it produces a report, not a fix.

## Commit decomposition

| # | Commit | Depends on | Lines (est.) |
|---|---|---|---|
| 1 | Skill skeleton: `SKILL.md` doctrine core (seven-move table, evidence ladder, Decision Gates, handoff contract) + the moves-table self-audit test | — | ~350 |
| 2 | `audit_cli.py roster` (two runtime probes + table parser + three-set diff) + copied helpers + tests + inversions | 1 (the table it parses) | ~380 |
| 3 | `audit_cli.py manifest` + `counts` + tests + inversions | 1 | ~300 |
| 4 | `references/usage.md` + `check-report` + the report-schema self-application | 1, 2 | ~280 |
| 5 | The first damage report on `proposal-deliberation`'s operation surface | 2, 4 | ~120 |

**Independence:** 2 and 3 touch disjoint subcommands and disjoint test classes and can land in
either order once 1 exists. **Ordering constraints, named rather than assumed:** 2 must follow
1 because the roster check parses a table 1 introduces — landing 2 first would ship a check
whose only possible verdict is "there is no table", which is a true finding about the wrong
subject. 5 must follow 2 and 4 because a report that no `check-report` validated is exactly the
hand-maintained artefact this skill exists to replace.

## Test strategy

**Harness:** `python3 -m unittest discover -s tests`, baseline **902 green**. The scripts are
Python and all four existing Python suites are skill-script suites; a JS subject is driven as a
subprocess, exactly as `tests/proposal-deliberation-cli-operation-surface.test.mjs:53` drives
`cli.mjs`. Never pytest; `-k` misses new classes.

**RED before GREEN, every unit.** Every lock that passes on its first run is proven
reachable-red **by inversion**: break the guarded fact, watch it fire, **restore by inverse
patch — never `git checkout --`** — and confirm with `git diff --quiet`, `cmp` and `shasum -c`.
An inversion that does not fire is a defect in the test, never a pass.

**Named inversions, because each of these passes when first written:**

| Lock | Inversion |
|---|---|
| Subcommand roster (self-audit) | Add a subparser with no table row → `unregistered` fires; delete a table row → `phantom` fires |
| Seven-move table completeness | Delete move 5's row → fires naming the gap |
| "Doctrine side never imports the producer" | Add an `import audit_cli` to the derivation helper → fires |
| Report-marker requirement | Plant a report whose finding carries no `CONFIRMED`/`read-only` marker → `check-report` rejects |
| `manifest` change detection | Touch one byte in a box → `changed` is non-empty; restore by inverse patch |
| Lexicon/floor disjointness | Add one floor word to `FORGE_LEXICON` → fires; remove by inverse patch |

**Recorded failure modes, each of which already cost a phase here, and how each is answered:**
a test must not pass off its own fixture's name (`assertNotIn(needle, fixture_name)` first); a
fixture that cannot reach the guarded branch makes its own assertion unfalsifiable; a double
replacing a function wholesale can never hold a claim about the process it would have run
(hence subprocess, not mock, for every roster probe); a green suite is not evidence.

**Before adding any class, grep the name.** Verified free today (`rg --no-ignore --hidden`, and
`Glob`, whose negatives are real because it ignores `.gitignore`): `.claude/skills/skill-audit/`,
`tests/test_skill_audit.py`, `audit_cli.py`, and every occurrence of `firedrill`/`skill-audit`
outside `explore.md`.

**Containment.** Throwaway boxes under `implementations/_<name>`, never `/tmp` — `verify`
refuses targets outside `<forge>/implementations`, and `implementations/*` is gitignored.
Deleted in `addCleanup`, and the deletion is **proven by `manifest`, not asserted**.
`implementations/Domain_Adaptation` is never edited, proven the same way. `fd`/`rg` need
`--no-ignore --hidden` to see `implementations/` at all.

**Nothing is sent to a remote service.** No live call of any kind in this change.

## Falsifier

*Find one defect in this week's corpus that a prose-only runbook would have caught as reliably
as this mechanization.* **It partly succeeds, and the concession is recorded rather than
argued away.** The `remote-execution` stale-prose claims (§Verification status, #2) have both
halves in prose in one file; no roster derivation reaches them, and a human reading the opening
paragraph against the frontmatter catches all three immediately.

**What the mechanization recovers of that class, and what it does not:** claim (c) — `:19`
"Three modules exist so far" against four bullets — is a **numeral against the enumeration that
follows it**, which is mechanical and is added to `roster` as a check. Claims (a) and (b) are
not, and the skill therefore carries **one irreducibly textual move**: *read every artefact's
opening against its own frontmatter*, doctrine, marked in the moves table as having no code and
no lock. Naming that honestly is better than pretending the table is complete.

For every other class, no prose-only equivalent survives: each mechanized derivation in this
repository was written *because* a hand-maintained equivalent had already lost an entry, and
`tests/proposal-deliberation-cli-operation-surface.test.mjs:10-12` records that incident in its
own header — "No test noticed; a manual smoke run did" — in a file that is itself a
hand-restated roster.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **R1 — this proposal was written with no shell, so nothing is confirmed by execution.** Two consecutive phases in this change have now had none | **High** | Every claim is marked read-confirmed or unchecked. `sdd-design`/`sdd-apply` must run the four §Verification-status checks before the first RED. If a phase again has no shell, that is a **blocker to report, not a condition to work around** — it is the exact defect this skill exists to institutionalise against |
| **R2 — `npm test` may match nothing on this node runtime** and still exit clean, making "48 files run" false and every count-based claim about the JS side unsound | Med | Settled by one command in design: `node --version` and `npm test 2>&1 \| tail`. If the glob does not expand, `counts` must refuse the JS harness rather than report zero |
| R3 — the two runtime probes are the only language-independent derivations found. A subject exposing no refusal message and no parser is underivable | Med | `roster` emits "no derivation available for this surface" as a first-class result, never a silent pass. Verified present for the first subject only |
| R4 — copying the helpers means two copies that can drift | Med | Accepted deliberately: the alternative is editing a 75-class suite inside a change about a different skill. A meta-test asserts the copies are byte-identical to their originals, so drift is a red, not a discovery |
| R5 — "audit" is not greppable in this repository | Low | Paths carry the uniqueness; the bare word is never used as an identifier |
| R6 — the skill is built and never used, joining the orphan class it exists to find | Med | Commit 5 ships an actual report on a real subject. A skill with no report produced is an orphan by its own definition |
| R7 — the report is delivered and the user accepts a fix that then exceeds budget again | Med | The report shape **requires** a changed-line forecast (item 8), which is exactly what both changes this week lacked before starting |

## Review budget forecast (against 1200)

**~1,430 authored lines** (additions + deletions), across five slices of 120–380.

`Decision needed before apply: Yes`
`Chained PRs recommended: Yes`
`Chain strategy: stacked-to-main`
`400-line budget risk: Medium`
`1200-line session budget risk: High — forecast exceeds it`

**The honest note.** Both changes this week exceeded this budget — **1,985 and 3,438 lines
against 1,200** — and **no `size:exception` was ever accepted**. So the chain is not a
preference here; it is the only route that has ever been agreed to. Every slice is ≤380 lines,
under the 400 per-PR guard, with clear start, finish, verification and rollback. If slice 2
grows past 400 it splits at the seam between the two runtime probes.

## Rollback

Each slice is one commit against `main` and reverts independently, with the two ordering
constraints named above reversed on the way out (5 before 4 and 2; 2 and 3 before 1). The
change is **purely additive**: one new skill directory, one new test file, one new report. No
existing file is modified, so no revert can disturb the 902-green baseline or either existing
harness. Deleting `.claude/skills/skill-audit/` and `tests/test_skill_audit.py` restores the
repository exactly.

## Success criteria

- [ ] `skill-audit` exists with `SKILL.md`, `scripts/audit_cli.py`, `references/usage.md`, and frontmatter in house shape.
- [ ] `roster` derives `proposal-deliberation`'s 9 accepted operations **from the running CLI's own refusal message**, with no roster restated in the auditor.
- [ ] `roster` emits three sets, and "there is no table" is a first-class result rather than an error.
- [ ] The auditor is run against the auditor, and both directions of its subcommand roster are proven reachable-red by inversion.
- [ ] `check-report` rejects a report whose finding carries no `CONFIRMED`/`read-only` marker.
- [ ] `manifest` proves a throwaway box was cleaned and `implementations/Domain_Adaptation` was not touched — without `git status`.
- [ ] A damage report on `proposal-deliberation`'s operation surface exists, validated by `check-report`, containing at least one `not adjudicable` finding and a changed-line forecast.
- [ ] `discover -s tests` green at 902 + the new tests, with counts proven to have **risen**.
- [ ] Every §Verification-status row marked "unchecked" is either confirmed by execution or struck.

## Proposal question round

This phase had no way to ask interactively — no `AskUserQuestion`, no shell. Five questions
that would sharpen the proposal; the assumption each currently rests on is stated so it can be
corrected now rather than discovered in apply.

1. **Does the auditor ever fix anything?** This proposal says never — it reports, and SDD fixes
   on your acceptance. But a `phantom` row (doctrine names something code does not have) is
   sometimes a one-line deletion. Should there be an explicit, opt-in "obvious repairs" path, or
   is the wall absolute? *Assumed: absolute. The wall is the product.*
2. **What does the auditor do when it finds nothing?** A clean surface is a real result, and
   §Clean-stated-as-results is meant to make it visible. Is a report with zero findings still
   worth delivering to you, or should it just say "clean" and stop? *Assumed: full report
   always, because an empty §Clean section is how you tell a clean surface from an unrun one.*
3. **Who decides the slice?** This proposal slices `proposal-deliberation` by closed surface and
   ships only slice A. Should the auditor propose its own slicing and ask you before running, or
   take the surface as an argument? *Assumed: it asks, using `AskUserQuestion`, because a slice
   is a cost decision.*
4. **The irreducibly textual move.** The falsifier concedes that prose-against-prose staleness
   (three live instances in `remote-execution`) cannot be mechanized. Should the skill carry it
   as an unlocked doctrine move anyway, or should the skill only claim what it can prove?
   *Assumed: carry it, marked as having no lock.*
5. **The shell.** Two consecutive phases here have had no Bash, and this skill's entire value is
   execution. Should "no shell available" be a hard refusal in the skill's activation contract —
   it stops and says so rather than degrading to reading? *Assumed: yes, hard refusal.*

Answering, skipping, correcting the framing, or asking for a second round are all fine.
