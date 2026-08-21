# Exploration: the-skill-that-audits-the-others (2026-08-21)

A maintenance skill that audits the other skills. Raw material: ~20 defects found
in this repository this week, all recorded under `openspec/changes/`.

## A. The taxonomy — how the defects were actually found

**No defect was found by reviewing a change for correctness, or by reading a diff.
Zero.** Reading found candidates, but only one kind of reading: **exhaustive
enumeration over a closed surface** — and enumeration was wrong twice and
incomplete once, each corrected only by execution.

So move 0 is **enumerate, never review**, and every enumeration is a candidate
until something runs.

| # | Move | Catches only here |
|---|---|---|
| 0 | Enumerate a closed surface both ways (parser leaves, returned dict keys, all call sites, all shipped assets) | orphans: a reader with no producer, a producer with no reader, a remedy with no command |
| 1 | Build the product from zero following **only** the doctrine, then diff against the producer's output | doctrine and producer drifting while both stay internally consistent |
| 2 | Run against the live subject on disk, never only fixtures | drift a synthetic fixture cannot exhibit, being built from the same doctrine |
| 3 | Fake the external boundary and assert **what crossed the wire** | everything about the wire; invisible without spending quota |
| 4 | Read the installed dependency as text and hold every version claim to it | doctrine claims about a third party |
| 5 | Read-only probe of the real dependency — a GET, never a write | facts about the environment; settles design forks by measurement |
| 6 | Invert every lock — break the guarded fact, watch it fire | a lock that is switched off; a fixture that cannot reach its own branch |
| 7 | Verify counts **rise**, not that they stay green | dead tests |

## The failure modes each move has, all of which already cost a phase

1. A test can pass off its own fixture's name — assert `assertNotIn(needle, fixture_name)` first.
2. A fixture that cannot reach the guarded branch makes its own assertion unfalsifiable. An inversion that does not fire is a defect in the test, never a pass.
3. A double replacing a function wholesale can never hold a claim about the process it would have run.
4. A green suite is not evidence; a passing test is not evidence.
5. `git status --porcelain <gitignored-dir>` is empty **by construction**. Only a before/after content manifest proves anything.
6. A live GET is evidence about the environment and proves nothing about the code. Never claim a receipt from a request.
7. Prove every new name is free before writing it (`rg --no-ignore --hidden`).
8. Restore by inverse patch, never `git checkout --`; confirm with `cmp` + `shasum -c`.

## B. From-zero vs today — the comparison mechanism

The precedent and the trap are both already here.
`test_it_writes_the_stage_one_tree_and_nothing_besides` compares the materializer's
tree against `doctrine_scaffold(...)`, and its docstring names why nothing caught
the drift before: *"the fixture that called itself doctrine-faithful was built by
this producer, so the superset it wrote was measured against itself and agreed
every time."*

Four soundness conditions, derived:
1. **Independent causes** — the doctrine side must never invoke the producer, not even to seed a directory.
2. **A stated, closed comparison domain** — or the diff is noise, and noise gets exempted until it means nothing.
3. **Both directions as three empty sets** — unregistered, duplicated, phantom. Different defects, different remedies.
4. **Reachable-red both ways** — adding a file must fail it; deleting a placing row must fail it.

Fifth, implied and unstated anywhere: the from-zero side is authored by a model
that just read the artefact and can reproduce it unconsciously. Mitigation:
**derive the doctrine side by parsing a table, not by reading prose.** Where no
table exists, the finding IS "there is no table".

Generality of the existing helpers: `markdown_table_rows` fully general;
`returned_keys`/`dict_literal_keys` general to Python; `subcommand_surface`
argparse-specific (4/5 subjects); `kit_assets`/`declared_assets` specific in form,
general in relation; `doctrine_scaffold` least general — its contract is the
general part.

Two language-independent derivations needing no parser:
- **The refusal message is the roster** — drive the CLI with a nonsense operation and the code enumerates its own accepted set, at runtime, in its own words.
- **The parser is the roster** — hand the documented invocation to the real process; an unrecognised flag never reaches the guard.

## C. Adjudication — which side is wrong

**The consumer decides, and its behaviour is established by execution against the
installed or live artefact — never by citing what a document says the consumer does.**

Evidence ladder, highest first: the installed consumer measured; two independent
consumers agreeing under constraints neither can be changed for; the live subject
on disk; fixtures the audit built; prose in either artefact (lowest — both sides
are claims until something executes).

Negative rule, proven twice: **a prose claim *about* a consumer is never consumer
evidence.**

**The exit that matters most: not adjudicable.** When enumeration finds no consumer
at all, the question is not which side is wrong — it is that this half has no other
half. Corpus instances: a shard-merge refusal with a reader, a doctrine and no
producer; `smokeReady` computed and branched on by nothing; `coupling` computed by
both commands and named by no doctrine; `repo.ref` written and read by nothing. The
remedy is to build the missing half or delete the orphan — a user decision with real
cost, which is the **structural** reason report-then-fix is the right ordering.

One check to avoid: "every reported fact must be branched on" is false by
construction — `coupling` is deliberately reported and never gating. The bar is
documentation, not consumption.

## F. How it invokes SDD — it cannot, and that is mechanical

Every `sdd-*` skill carries `disable-model-invocation: true`, `user-invocable: false`,
`metadata.delegate_only: true`. They are launchable only by the orchestrator, only
through a sub-agent, and only past the SDD Session Preflight hard gate.

So the audit's terminal state is a **handoff**, and the house already has the idiom:
`MAINTENANCE` answers `delegation_permitted`, `mutations: 0`,
`documentAuthority: FORBIDDEN`, `taskDelegation: PERMITTED`,
`explicitHandoffRequired: true`.

Recommended wiring: **the audit IS the exploration**, run under its own doctrine
because that doctrine requires a shell, and its report lands at the artefact key
`sdd-propose` consumes. The alternative — launching `sdd-explore` — is worse on
evidence: `sdd-explore` twice ran here **with no shell at all**, and the audit's
entire value is execution.

## G. Containment, derived from what this session's boxes did

Boxes at `implementations/_<name>`, never `/tmp` (`verify` refuses targets outside
`<forge>/implementations`, and `implementations/*` is gitignored). Prove the box was
cleaned, do not assert it. Never edit `Domain_Adaptation`, and prove it with a content
manifest, never `git status`. Fake the boundary; never dial it. The only permitted live
call is a read-only GET with the same authority the shipped code has. Never import an
installed service client — read it as text (importing `kaggle` runs `authenticate()`).
Forecast the churn before the fix chain starts: both changes this week exceeded the
review budget — 1,985 and 3,438 lines against 1,200 — with no exception accepted.

## Recommendation

Approach **B**: `.claude/skills/skill-firedrill/` with `scripts/` + its own test suite.
The mechanical moves (0, 1, 7, the manifest) are code; the judgement moves are doctrine
with a Decision Gates table and a mandatory report shape. Copy the derivation helpers
rather than share them — sharing means editing a 75-class suite inside a change about a
different skill, the exact scope creep both archive reports flagged.

First subject: **`proposal-deliberation`**, sliced, starting from the operation-set
divergence already in evidence.

**Falsifier:** find one corpus defect a prose-only runbook would have caught as
reliably. None found — every mechanized derivation here was written *because* a
hand-maintained equivalent had already lost an entry.

## Findings the exploration made while exploring

**`remote-execution/SKILL.md:12-15` contradicts its own frontmatter nine lines above.**
It opens *"Nothing here yet talks to a real service — that is a concrete adapter, still
to come"* while `:3` says the skill ships *"one concrete backend: adapters/kaggle.py"*,
and `c4ee27f` added `kaggle>=1.7` to requirements. Second stale "does not exist yet"
claim in that one file. No test can catch it: both halves are prose in the same file.
**New move: read every artefact's opening against its own frontmatter.**

**`proposal-deliberation`'s accepted-operation set exists in four places, three
hand-maintained, none derived.** `cli.mjs:297-320` is the truth; `usage.md:264-266`
restates all nine by hand; `tests/…-cli-operation-surface.test.mjs:31-41` restates all
nine by hand; `SKILL.md:245-251` names only **four**. And that test file's own header
records the incident it failed to prevent: *"A subsystem removal previously left a stale
operation name in that set … No test noticed; a manual smoke run did."* The suite written
to catch a stale operation name is itself a hand-restated roster. Residue is visible:
`SCIENTIFIC_WORKFLOW` still appears as a route stage while the CLI refuses it.

## Corrections to the brief

- The kit's import-closure defect is **already fixed on disk**; the surviving instance of that class is the three unparseable stage-2 templates.
- `proposal-deliberation` is **not untested** — 50 `.mjs` test files run by `npm test`. The accurate claim is that it is the largest surface never audited by these seven moves.
- `Limitaciones conocidas` does not exist in any `SKILL.md`; it is not part of the house shape (it lives in `README.md`).
- `skill-creator` does not govern here: it sets a 1000-token hard max while `proposal-implementation/SKILL.md` is 1,978 lines, and it defers to a `docs/skill-style-guide.md` that does not exist in this repository. **The five existing skills are the only authority.**

## Unchecked

No Bash and no Write in that phase: nothing was executed, so the operation-set
divergence, the two stale prose claims and `npm test`'s scope are **candidates, not
findings**, by this exploration's own standard. The two Engram-only changes were read
only through quotations. `implementation_cli.py`, `remote_cli.py`, `jobfolder.py` and
all 55 TS engine modules were read in regions, not whole.
