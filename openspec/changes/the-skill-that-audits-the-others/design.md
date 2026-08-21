# Design: the-skill-that-audits-the-others

Change: `the-skill-that-audits-the-others` · New skill: `skill-audit` · Store: openspec (Engram disconnected)

## Shell status — read this first

**This phase had no Bash.** It also had no `codegraph_explore` and no `AskUserQuestion`; the
available tools were Read, Write, Edit, Grep and Glob only. That is the **fourth consecutive
phase** of this change with no shell (`sdd-explore` ×2, `sdd-propose`, `sdd-design`), and it is
the same defect class this change exists to institutionalise against.

Consequently **every claim below is `read-only`**. Nothing is `CONFIRMED by execution`. Claims
that can only be settled by running something are marked **UNCHECKED** inline and collected in
§Unchecked. Nothing was simulated: no command output is reported as if it had run.

What *is* new here is read-confirmed on disk and was not in the proposal — see §D2, which
changes the mechanism.

## Technical Approach

Three layers, matching the proposal's code/doctrine split.

| Layer | Artefact | Holds |
|---|---|---|
| Doctrine | `.claude/skills/skill-audit/SKILL.md` | Seven-move table, evidence ladder, Decision Gates, report shape, handoff contract |
| Mechanism | `.claude/skills/skill-audit/scripts/audit_cli.py` | `roster`, `manifest`, `counts`, `check-report` |
| Self-application | `tests/test_skill_audit.py` | The auditor audited by its own moves |

House shape, measured (not from `skill-creator`, which the proposal already struck): all five
existing `SKILL.md` files carry frontmatter of **exactly `name` and `description`**, on lines 2–3
(verified by grep across `.claude/skills/*/SKILL.md`; no `license`, `metadata`, or
`allowed-tools` anywhere). Decision Gates is a two-column `| Situation | Action |` table
(`paper-ingestion/SKILL.md:183-199`). The CLI idiom is
`def main(argv: list[str] | None = None) -> int` (`remote_cli.py:1454`,
`implementation_cli.py:5329`), argparse subparsers, `sys.exit(main())`, JSON on stdout.
Hashing is `hashlib.sha256(path.read_bytes()).hexdigest()` (`jobfolder.py:556-562`).
Subprocesses are `subprocess.run(shell=False, ...)`.

## Architecture Decisions

### D1 — The code side is a *process*, never a parse

**Choice**: `roster` derives the code side by driving the real subject as a subprocess and
reading the roster out of the subject's own refusal text. Read-confirmed:
`cli.mjs:319-321` throws `UNKNOWN_OPERATION: <json> is not one of ${[...HOST_OPERATIONS,
...TOOL_OPERATIONS].join(', ')}` — the complete accepted set, at runtime, in the subject's own
words, with zero parsing of its source.

**Also read-confirmed and load-bearing**: `validateRequest` is the *first* statement of `run()`
(`cli.mjs:333`), so the throw precedes `tool.execute` and any project I/O. The probe therefore
**needs no seeded project root and can mutate nothing by construction** — a stronger containment
guarantee than the existing surface test achieves with its `mkdtemp` seed.

**Alternatives rejected**: one Python-`ast` tool for both sides (Python-only; produces nothing at
all for a `.mjs` subject); reading `cli.mjs` with a regex (a second parser that drifts from the
first).

### D2 — A doctrine table is a roster site only if it *claims closure*, and the claim is checked verbatim

This is the design's one substantive change to the proposal's mechanism, forced by disk.

`proposal-deliberation/SKILL.md:243-252` is a table headed **`## Other engine operations`**, with
four rows, and its closing line says "the other three … None of the four". It is a **complement
set**. A naive `markdown_table_rows` diff against the runtime's nine would emit **five false
`unregistered` rows** — the auditor's first output on its first subject would be wrong, which is
precisely the failure the exploration recorded twice.

**Choice**: the probe descriptor declares each candidate doctrine site with an optional
`scope: "complement"` **plus the exact heading line**, and `roster` asserts that heading appears
**verbatim** at that path before honouring the scope claim. The editorial judgement is recorded
and its evidence is falsifiable: rename the heading to `## Engine operations` and the check fires.

**Consequence for slice A**: `SKILL.md` has *no* closed-roster table for this surface;
`usage.md:264-266` states all nine **in prose**, which soundness condition 5 forbids reading; the
`.mjs` test restates all nine as a JS array. So all three doctrine sites emit **`no-closed-roster`
as a first-class result**, and that *is* the finding the proposal predicted survives ("three of
four rosters are hand-restated, none derived"). Remedy: one table, one derivation.

**Alternative rejected**: infer scoping from heading words ("Other", "Additional"). Clever,
fragile, and unfalsifiable when it guesses wrong.

### D3 — Inability to look must never share an exit code with absence of findings

**Choice**: `roster` exits `0` for any verdict including findings, and **`2` when the probe could
not be driven or the extraction matched nothing**. An extraction that matches nothing **raises**;
it must never return an empty set.

**Rationale**: an empty code side silently yields `unregistered = ∅` and `phantom = <every
doctrine row>` — a broken probe dressed as a finding. This is failure mode 4 ("a green suite is
not evidence") in its most dangerous form.

### D4 — The probe descriptor is a recipe, not a roster

`roster` reads a JSON descriptor from
`.claude/skills/skill-audit/references/probes/<subject>.<surface>.json` — additive, inside the
auditor, so **no subject file is ever modified** (preserving the proposal's purely-additive
rollback). A wrong recipe fails loudly (D3); a wrong roster would agree silently. That asymmetry
is the whole justification.

```json
{ "surface": "accepted-operations",
  "probe": "refusal",
  "argv": ["node", "engine/cli.mjs", "{\"operation\":\"__AUDIT_NONCE__\",\"instruction\":\"probe\"}"],
  "cwd": "engine", "stream": "stdout", "exit": "any",
  "extract": "is not one of (?P<roster>.+?)\"?$", "split": ", ",
  "doctrineSites": [
    {"path": "SKILL.md", "table": "| Operation | Use it for |", "column": 0,
     "scope": "complement", "headingVerbatim": "## Other engine operations"},
    {"path": "references/usage.md", "table": null}] }
```

`stream` and `exit` are descriptor fields because the two probes genuinely differ: `cli.mjs`
writes JSON to **stdout** and **exits 1** on refusal (`cli.mjs:371-373`), while argparse writes
`invalid choice` to **stderr** and exits **2**. A single hardcoded contract would fit neither.

### D5 — Handoff, not invocation

Terminal state is a handoff, per the proposal: `mutations: 0`,
`documentAuthority: FORBIDDEN`, `explicitHandoffRequired: true` — the `MAINTENANCE` idiom
asserted at `tests/proposal-deliberation-cli-operation-surface.test.mjs:88-98`. The report lands
at `openspec/changes/<change>/` where `sdd-propose` reads. The audit **is** the exploration.

## How the from-zero side is derived without touching the producer

| | Code side | Doctrine side |
|---|---|---|
| Cause | A `node` subprocess's stdout | `markdown_table_rows` over `SKILL.md` |
| Input | The installed `cli.mjs`, unread as source | Markdown bytes |
| Shared symbol | none — there is no function to reuse, only bytes |

**Why `doctrine_scaffold` would have failed this gate.** `tests/test_proposal_implementation.py:267`
is `for gap in impl.scaffold_gaps(box, name):` — the doctrine side iterates **the producer** to
decide which paths to write. Its docstring (`:240`) says the target holds "exactly the paths
`scaffold_gaps` reports as wanted", and `:242-244` is careful to avoid shelling `materialize.py`
for *content* while leaving the *path set* producer-derived. A path missing from both
`scaffold_gaps` and `materialize.py` is therefore invisible to it, forever.

`roster` structurally cannot inherit this: the code side is a process boundary, so there is
nothing importable for the doctrine side to reuse. **Mechanised anyway**, because "structurally
cannot" is a claim: the self-audit parses the `ast` of the doctrine-derivation path and asserts
it names neither the probe module nor `subprocess`. Reachable-red by adding such a reference.

## The content-manifest tool

`manifest --root <dir> [--baseline <file>]` → sorted `{path: sha256}` over the declared root;
with `--baseline`, `{added, removed, changed}`. Symlinks are not followed; bytes are hashed, so
binaries are included rather than skipped.

**What it proves that nothing else can**: `git status --porcelain` over `implementations/` is
empty **by construction** (the directory is gitignored) — recorded failure mode 5. `manifest`
proves a throwaway box under `implementations/_<name>` was actually deleted, and that
`implementations/Domain_Adaptation` was byte-identical before and after. Two separate phases had
to hand-write this within one week; that recurrence is the case for shipping it.

## The auditor run against the auditor

`tests/test_skill_audit.py` applies the moves to the skill itself.

| Self-application | Catches what nothing else does |
|---|---|
| `roster` on `audit_cli.py` — argparse's own `invalid choice` refusal vs the `\| Subcommand \| Derives \| Emits \|` table in `SKILL.md` | A subparser shipped with no doctrine row; a doctrine row for a deleted subparser. No diff review and no other suite reads the *doctrine* side |
| Soundness gate on the derivation path (`ast`, D2/§from-zero) | The exact defect `doctrine_scaffold` carries today |
| Seven-move table: one row per move 0–7, each naming a subcommand `roster` already proved exists, or the literal `doctrine` | A move documented with a script that does not exist |
| `check-report` on the shipped report | A report shape enforced by prose — the class this skill exists to find |
| `FORGE_VOCABULARY_FLOOR` / `FORGE_LEXICON` disjointness (copied, `test_proposal_implementation.py:62-63`) | The new skill borrowing a target's vocabulary |
| Copied helpers byte-identical to their originals | Drift between the two copies (R4) |

All four helpers to copy live in **one** file — `markdown_table_rows:82`, `returned_keys:103`,
`dict_literal_keys:9017`, `subcommand_surface:9118` in `tests/test_proposal_implementation.py` —
so the byte-identity meta-test has a single source.

**UNCHECKED, and it gates slice 2**: argparse's `invalid choice` wording is Python-version
dependent (3.12 quotes each choice; later versions changed the rendering), and this repository's
`python3` version was not observable without a shell. Apply must run the probe, pin the observed
format, and rely on D3 so a wording change is a loud `exit 2`, never an empty roster.

## File Changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/skill-audit/SKILL.md` | Create | Doctrine: seven-move table, evidence ladder, Decision Gates, report shape, handoff contract, activation contract (hard refusal with no shell) |
| `.claude/skills/skill-audit/scripts/audit_cli.py` | Create | `roster`, `manifest`, `counts`, `check-report`; stdlib-only |
| `.claude/skills/skill-audit/references/probes/proposal-deliberation.accepted-operations.json` | Create | The slice-A descriptor (D4) |
| `.claude/skills/skill-audit/references/probes/skill-audit.subcommands.json` | Create | The self-audit descriptor |
| `.claude/skills/skill-audit/references/usage.md` | Create | Worked invocations |
| `tests/test_skill_audit.py` | Create | Self-application suite, copied helpers, inversions |
| `openspec/changes/.../audit-proposal-deliberation-operations.md` | Create | First damage report — report only, no fix |

**No existing file is modified.** Rollback is deletion of two paths plus the report.

## Interfaces

| Subcommand | Derives | Emits (JSON, `sort_keys=True`) | Exit |
|---|---|---|---|
| `roster --subject <dir> --probe-spec <file>` | Code side by process probe; doctrine side by table parse | `code`, `doctrine`, `unregistered`, `phantom`, `duplicated`, `numeralMismatch`, `notes` | 0 always; **2** if unprobeable |
| `manifest --root <dir> [--baseline <f>]` | sha256 per file | `files` or `{added, removed, changed}` | 0; 2 if root missing |
| `counts --before <f> --after <f>` | Parses `Ran N tests` (unittest) and `# pass N` (node:test) | `{harness: {before, after, delta}}`, `verdict: rose\|flat\|fell\|unreadable` | 0; 2 if unreadable |
| `check-report <file>` | The eight-item report shape | `violations` | 0 valid; 1 invalid; 2 unreadable |

`counts` answers R2 directly: if the node summary line is absent — the failure mode where the
glob expanded to nothing and the command still exited clean — the verdict is **`unreadable`**,
never `0`. `flat` is a finding, not a pass.

The numeral check rides inside `roster` (`numeralMismatch`) rather than as a fifth subcommand, so
the self-audit's subcommand roster stays a four-row closed set. It compares an **unhedged**
cardinal against the sibling bullet list that immediately follows it. Hedged numerals are
excluded — read-confirmed necessity: `cli.mjs:21` says "roughly 0.72s" and "~63 TS files", and a
check that fired on those would be noise, and noise gets exempted until it means nothing.
Live target, read-confirmed: `remote-execution/SKILL.md:19` says "Three modules exist so far"
above bullets at `:21`, `:32`, `:50`, `:57` — **four**, in a skill shipping eight scripts.

## Data Flow

    probe-spec ──→ subprocess(real subject) ──→ stdout/stderr ──→ extract ──→ code set
                                                                                │
    SKILL.md / usage.md ──→ markdown_table_rows ──→ doctrine set ───────────────┤
                                    │                                           ▼
                          heading-verbatim check                    three sets + notes
                                                                                │
                                                                                ▼
                                                    damage report ──→ check-report ──→ user
                                                                                │
                                                                    AskUserQuestion (accept?)
                                                                                │
                                                                                ▼
                                                              handoff to sdd-propose

## Commit decomposition and the budget

| # | Slice | Depends on | Est. |
|---|---|---|---|
| 1 | `SKILL.md` doctrine core + moves-table self-audit | — | ~350 |
| 2 | `roster` (probe + descriptor + table parse + three sets + numerals) + copied helpers + inversions | 1 | ~380 |
| 3 | `manifest` + `counts` + inversions | 1 | ~300 |
| 4 | `references/usage.md` + `check-report` + report-schema self-application | 1, 2 | ~280 |
| 5 | First damage report on the operation surface | 2, 4 | ~120 |

**Independence proven**: 2 and 3 touch disjoint subcommands, disjoint descriptor files and
disjoint test classes; either order once 1 exists.
**Ordering constraints, named**: 2 after 1 because it parses a table 1 introduces (landing 2
first ships a check whose only verdict is "there is no table" — a true finding about the wrong
subject). 5 after 2 and 4 because an unvalidated report is the hand-maintained artefact this
skill replaces.

**Where the cut falls.** The forecast is ~1,430 against a 1,200 session budget. Slices are
120–380, so every slice is inside the 400-line per-PR guard, but the session budget is not
satisfiable by re-slicing — only by deferring.

- Slice 5 **cannot** be deferred: R6 says a skill that produces no report is an orphan by its own
  definition.
- Slices 1, 2, 4 are the mechanism and its validation; deferring any leaves a skill that cannot
  run or a report nothing validated.
- **Slice 3 is the deferrable unit** → **1 + 2 + 4 + 5 = ~1,130, inside 1,200.**

Deferring slice 3 is affordable because of D1: the roster probe is refused *before* any project
I/O, so **slice A needs no throwaway box at all**, and `manifest`'s containment proof has nothing
to guard in slices 1/2/4/5. `counts` has nothing to measure either, since this change ships no
fix; the auditor's own rise from 902 is proven by running the harness, not by `counts`.
**Success criteria 6 and 8 move to the follow-up change with slice 3**, and that must be stated
rather than quietly dropped. If instead the user accepts a five-PR chain, the order is 1→2→3→4→5.

`Decision needed before apply: Yes`
`Chained PRs recommended: Yes`
`Chain strategy: stacked-to-main`
`400-line budget risk: Medium`
`1200-line session budget risk: Low if slice 3 defers; High otherwise`

## Testing Strategy

**Harness**: `python3 -m unittest discover -s tests`, baseline 902. Never pytest (`-k` misses new
classes). A `.mjs` subject is driven as a subprocess, exactly as
`proposal-deliberation-cli-operation-surface.test.mjs:53` drives `cli.mjs`.

**RED before GREEN, every unit.** Every lock that passes on first write is proven reachable-red by
inversion: break the guarded fact, watch it fire, **restore by inverse patch — never
`git checkout --`** — and confirm with `git diff --quiet`, `cmp` and `shasum -c`. An inversion
that does not fire is a defect in the test, never a pass.

| Lock | Inversion |
|---|---|
| Subcommand roster (self-audit) | Add a subparser with no table row → `unregistered`; delete a table row → `phantom` |
| Seven-move table completeness | Delete move 5's row → fires naming the gap |
| Doctrine side never imports the producer | Add `import subprocess` to the derivation helper → fires |
| **Extraction matched nothing raises (D3)** | Corrupt the descriptor's `extract` → **exit 2**, not an empty `code` set |
| **Complement heading verbatim (D2)** | Change `## Other engine operations` in the fixture → fires |
| Report-marker requirement | Plant a finding with no `CONFIRMED`/`read-only` marker → `check-report` rejects |
| `counts` on a node run that matched nothing | Feed a summary-less capture → `unreadable`, never `0` |
| `manifest` change detection | Touch one byte in a box → `changed` non-empty; restore by inverse patch |
| Lexicon/floor disjointness | Add a floor word to `FORGE_LEXICON` → fires |

**Failure modes each answered**: assert `assertNotIn(needle, fixture_name)` first; a fixture that
cannot reach the guarded branch makes its own assertion unfalsifiable; **subprocess, never mock,
for every roster probe** — a double replacing a function wholesale cannot hold a claim about the
process it would have run.

**Names verified free this phase** (read-only, by `Glob`, whose negatives are real because it
ignores `.gitignore`): `.claude/skills/skill-audit/`, `tests/test_skill_audit.py`, `audit_cli.py`
— `Glob('**/{skill-audit,skill_audit,audit_cli}*')` returned **no files**; `firedrill|skill-audit|skill_audit|audit_cli`
matches only this change's own `explore.md` and `proposal.md`.

**Containment**: boxes at `implementations/_<name>`, never `/tmp`; deleted in `addCleanup`.
`implementations/Domain_Adaptation` is never edited. **Nothing is sent to a remote service; this
change makes no live call of any kind.**

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED test |
|---|---|---|---|
| Documentation-like paths | **N/A** — the auditor classifies nothing as executable; it reads markdown as text and runs only the argv a descriptor names | — | — |
| Git repository selection | **N/A** — no `git` invocation ships. `manifest` exists precisely *because* `git status` is unusable here | — | — |
| Commit state | **N/A** — `mutations: 0`; the skill never stages or commits | — | — |
| Push state | **N/A** — no remote of any kind | — | — |
| PR commands | **N/A** — the terminal state is a handoff to the user, never a PR | — | — |
| **Subprocess composition** (added; the matrix's fifth row generalised) | **Applicable** — `roster` executes descriptor-supplied argv | `subprocess.run(shell=False, ...)`, argv as a list, never a string; no shell metacharacter path; nonce is a fixed literal, never user text; `cwd` resolved under `--subject` and refused if it escapes; timeout enforced | Descriptor with `cwd: "../.."` → refused; descriptor argv containing `;` → passed as one literal argument, not interpreted; a hanging subject → timeout, exit 2 |

## Migration / Rollout

No migration. Purely additive: two new directories and one report. Each slice reverts
independently, ordering constraints reversed on the way out (5 before 4 and 2; 2 and 3 before 1).

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **R10 — four consecutive phases with no shell.** Every claim in explore, proposal and design is read-only | **High** | Apply MUST run the §Unchecked list before the first RED. **If apply also has no shell, that is a blocker to report, not a condition to work around** — this skill's entire value is execution |
| **R11 — Engram is down**, so every artefact of this cycle lives only on disk under `openspec/changes/the-skill-that-audits-the-others/` | High | Accepted; noted so a later phase does not search Engram, find nothing, and conclude the phase never ran |
| **R12 — argparse's refusal wording is Python-version dependent** and unverified here | Med | D3: a non-matching extraction raises and exits 2. Apply pins the observed format |
| **R13 — the descriptor is a new hand-maintained artefact**, the very class this skill hunts | Med | It is a *recipe*, not a roster (D4): wrong recipes fail loudly, and the `headingVerbatim` claim is mechanically falsifiable |
| R3 — a subject with no refusal message and no parser is underivable | Med | `roster` emits "no derivation available" as a first-class result. Verified present for the first subject only |
| R4 — copied helpers drift | Med | Byte-identity meta-test against `tests/test_proposal_implementation.py`; drift is a red, not a discovery |
| R6 — the skill is built and never used | Med | Slice 5 ships a real report and cannot be deferred |
| R14 — the design overruns the 800-word artefact guidance | Low | Deliberate: the phase brief specifies seven mandatory contents. Density is carried by tables |

## Unchecked

Every item below needs a shell, and each is a §Verification-status row or a new one this phase
added.

- [ ] `node --version` and `npm test 2>&1 | tail` — does the glob expand, and is it 371 pass? (R2)
- [ ] `python3 --version` and argparse's exact `invalid choice` rendering (R12, gates slice 2)
- [ ] The `cli.mjs` nonce probe actually emits the nine-name refusal, from a cwd with no project root (D1)
- [ ] `SCIENTIFIC_WORKFLOW` has no producer: grep shows it only in `runtime-metrics.ts:3,14,16`, but no call site of `recordRouteMetric` was enumerated. Slice B's `not adjudicable` demonstration is a **candidate**, not a finding
- [ ] `python3 -m unittest discover -s tests` green at 902 before the first RED

## Open Questions

- [ ] **Budget**: defer slice 3 (`manifest` + `counts`, moving success criteria 6 and 8 to a
      follow-up) to fit ~1,130 inside 1,200, or accept a five-PR chain at ~1,430? Design
      recommends deferring slice 3.
- [ ] The proposal's five questions remain unanswered — no interactive tool was available in this
      phase either. Their stated assumptions are carried forward unchanged.
