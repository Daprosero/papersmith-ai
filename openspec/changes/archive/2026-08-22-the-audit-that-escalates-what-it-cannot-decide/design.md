# Design: the-audit-that-escalates-what-it-cannot-decide

## Technical Approach

Seven additions to one module, all of them projections of state the tool already holds rather
than new rosters beside it. The digest is `sha256` over `tree_digest`'s own output, so no second
walk exists. The escalatable list is a **filter over `notes`**, not a parallel array. The stage
roster and the per-stage artifact demand are **derived from a doctrine table**, exactly as the
move roster already is. Rung one turns a supplied candidate into a real `walkthrough` gate, and
the only new authority anyone gains is the authority to *propose a gate* — the verdict stays
where it already was, in the exit code of a real process.

The invariant that shapes every decision below: **the model proposes, the tool disposes.** A
reading of prose is a hypothesis generator. It may name candidates; it may never name a fact.

## Architecture Decisions

### Decision: the freeze is one hash over `tree_digest`, and `## Frozen` carries its own recipe

| Option | Tradeoff | Decision |
|---|---|---|
| Embed the per-file map in the report | Hundreds of lines per report; unreviewable | Rejected |
| A summary hash with no exclusion record | Two runs disagree over a stray `__pycache__` and neither is wrong | Rejected |
| `frozen_digest(root, exclude) = sha256("\n".join(f"{p} {h}"))` over `tree_digest`'s sorted map | One line per report, re-derivable, `SingleWalkTests` stays green because it calls `tree_digest` | **Chosen** |

Every subcommand payload gains `"frozen": {"digest": "sha256:<hex>", "exclude": [...],
"subject": "<path>"}`. The report's `## Frozen` carries `- Digest:`, `- Subject:`, and
`- Exclude:` (`(none)` when empty) — self-describing, so re-derivation needs no out-of-band
argument. Each `### F<n>.` block carries `- Digest: sha256:<full hex>`; a finding is a claim
about bytes, and a truncated hash is a claim about *some* bytes.

Verification lives in `check-report`, **confirmed**, with one new optional flag. `--subject
<path>` re-derives from disk and compares; without it, the payload carries `"rederived": false`
and only finding-vs-`## Frozen` consistency is checked. A check that silently weakens itself is
the shape this doctrine hates, so the omission is *reported*, borrowing `comparison: not-run`'s
existing idiom rather than inventing a second one.

### Decision: note kinds get one constructor, so the partition can be total without an exclusion list

A literal scan cannot work: `audit_cli.py:735` emits `"kind": kind` from a variable, which hides
three of the four escalatable kinds. And `stall` dicts (`:1031,1040,1057`) carry a `"kind"` key
that is a *verdict*, not an undecidability, so a scan of every `"kind":` literal classifies the
wrong things.

So: `note(kind, detail, path, searched)` becomes the only way an entry enters `notes[]`, and
`DOCTRINE_SIDE_NOTES: {status: (kind, detail)}` (hoisted from the inline dict at `:723-734`)
becomes the only place a `doctrine_side` status becomes a kind. `stalled(kind, index, detail)`
is its sibling for walkthrough verdicts.

`ESCALATION_BUCKETS = {"escalatable": (...), "consequence": (...), "deterministic-exclusion":
(...)}` is the named constant, held like `FORBIDDEN_SUPPORT` and `ADJUDICATIONS`.
`EscalationPartitionTests` reads `audit_cli.py`'s syntax tree and asserts: every constant string
in a `note()` `kind` position, plus every kind in `DOCTRINE_SIDE_NOTES`'s values, appears in
**exactly one** bucket; the buckets are pairwise disjoint; and **no dict literal outside
`stalled()` carries a `"kind"` key at all**. That last clause is what makes it total — a new
kind cannot be emitted by bypassing the constructor without turning the lock red. A step
entry's `"kind": "setup"|"gate"` is built by the step-entry helper, never by a bare dict, so it
does not collide.

### Decision: rung one is a control-gated candidate expansion, and the control is what distinguishes acceptance from indifference

Escalatable notes gain `"escalation": {"rung": "probe"|"readers", "probe": <move>|null,
"needs": "candidates"|null, "refusal": <regex>|null}`. Rung one is selected when the emitting
recipe declares `probe: "refusal"` — because then the tool already holds the program's own
refusal pattern, which is the entire input a gate needs. Otherwise the rung is `readers`.

Candidates enter through one new recipe block, not N hand-written steps:

```json
"candidateGates": {"refusal": "unrecognized arguments|invalid choice",
                   "argv": ["python3", "{subject}/scripts/x.py", "{candidate}"],
                   "candidates": ["--foo", "--bar"]}
```

`{candidate}` is a fourth token, valid only inside `candidateGates.argv`; `STRUCTURE_TOKENS`
is untouched and `GATE_TOKENS = STRUCTURE_TOKENS | {"candidate"}`. One declared `refusal`
derives **both** expectations, so nothing is restated:

| Generated gate | `expect` | Meaning |
|---|---|---|
| Control, first, one absurd nonce candidate | `{"exit": "any", "stderr": <refusal>}` | The refusal channel is **live** |
| One per candidate, in order | `{"exit": "any", "absent": <refusal>}` | The program must **not** refuse this |

The control's expectation is deliberately inverted, which means a dead refusal channel stalls at
the control's own index and leaves every candidate `unreached` through the machinery that
already exists — no special case, no new branch. **This is the answer to "accepted versus never
had an opinion":** a program that ignores unknown flags silently passes the control's absence
check, the control stalls, and no candidate is ever reported as accepted. Acceptance is only
ever reported against a channel proven to be capable of refusing.

`exit: "any"` is deliberate: a program may exit nonzero for reasons unrelated to the flag. The
refusal *message* is the program's own words about that flag, which is the same evidence
`probe_code_side` already trusts.

**When no probe applies and no readers are available**, the note's rung is `readers`, the
surface stays in `## Undecidable`, and the report's stage rows say `skipped: <reason>`. That is
the honest terminal state: exit stays `0` (a verdict was reached about what could not be
decided), the payload's `escalatable` array is non-empty, and `check-report` requires the
surface to appear. It never becomes clean and never becomes silence.

### Decision: `reading-diff` is a subcommand, and four independent barriers keep it away from `closed_seen`

A flag or a recipe field would route a supplied reading through `run_roster`, which is the one
function that writes `closed_seen`. A subcommand is the only shape where the barrier is
structural rather than conventional.

Input: `--surface <name> --reading <path> --reading <path>`, exactly twice; any other count is
`Unprobeable`. Each reading file is `{"surface", "site", "members": [...], "reader": "<label>"}`.
Output: `{"surface", "agreement": "single-reading"|"divergent", "shared", "onlyIn": {...},
"comparison": "not-run", "candidates": <shared>, "limit": "<the weaker claim, in words>"}`. Exit
`0` for either verdict, `2` for inability. No `unregistered` key exists in that payload — not an
empty one, none.

| Barrier | Shape |
|---|---|
| B1 | `run_reading_diff` never calls `doctrine_side`, `probe_code_side`, or `finish` — asserted over its AST subtree |
| B2 | `closed_seen` is assigned `True` at exactly one site in the module, and that site is inside `run_roster`, fed only by a `doctrine_side` status |
| B3 | `comparison` is the constant `"not-run"` in the emitted payload, asserted as a literal |
| B4 | Behavioural: drive the real subcommand with readings that are a strict superset of a code side; assert the payload carries **no** `unregistered` key |

Each is seen RED by inversion, B1 by planting the call.

Two readings agreeing prove the prose has **one reading**. The `limit` field says so in the
payload, so a report copying the output cannot quietly upgrade it to "closed".

### Decision: setup is a step kind, and its failure is an inability, not a stall

Recipe field `"kind": "setup" | "gate"`, defaulting to `"gate"` — precedent `"reset": true`.
A `setup` step needs no `expect`; a `setup` step that *declares* one is `Unprobeable`, because a
setup step asserting something about the subject is a gate wearing the wrong label.

| Situation | Payload | Exit |
|---|---|---|
| Setup step succeeds | step outcome `setup-ok`, never `passed` | continues |
| Setup step fails (nonzero, missing argv[0], timeout) | `{"status": "setup-failed", "index", "name", "detail"}`, `stall: null`, `unreached: []` | `2` |
| Recipe declares zero gates | `Unprobeable` — a walkthrough of only setup asserts nothing | `2` |

`stall` stays `null` and `unreached` stays empty on `setup-failed` because nothing was ever
gated: a void run has no unchecked gates, it has no run. The corresponding `## Move outcomes`
row becomes `skipped: setup failed at step <n>`, which is the existing mechanism doing exactly
the right thing. The payload also gains `"gates": {"declared": n, "passed": m}`, counting only
`kind == "gate"` steps, so a fixture that happened to work can never again be counted as
evidence about the subject. `setup-failed` is emitted directly rather than through
`Unprobeable`, whose fixed `{"error", "status"}` shape cannot name an index.

### Decision: the stage roster is derived, and a marker's own shape decides what its stage demands

`SKILL.md` gains `| Stage | Models | Demands |`. The `Demands` cell holds a **`REPORT_SHAPE`
key**, not prose — so the demand is one vocabulary, already held to the doctrine table in both
directions by `ReportSchemaSelfDescriptionTests`. Numbers live in cells; the heading carries
none, per `DoctrineNumeralTests`.

| Stage cell | Models | Demands |
|---|---|---|
| `0. Freeze the subject` | 0 | `frozen` |
| `1. Decide by tool` | 0 | `undecidable` |
| `2. Two blind readings, over that list only` | 2 | `reading-diff` |
| `3. Differential drive, one box with the skill and one without` | 2 | `drives` |
| `4. Partition the two transcripts` | 1 | `found-by` |

`stage_roster(text)` mirrors `move_roster`: column 0's leading digit is the id, column 2 is the
key. Unlike moves there is **no `textual` escape valve** — a stage row with no leading digit, an
unknown `REPORT_SHAPE` key, or a table that is not singular is `Unprobeable`.

The demand's meaning derives from the marker's own shape, reusing the `startswith("## ")`
discriminator `check-report` already applies at `:1258`:

- A `## ` marker → the section must exist.
- A `- ` marker → no finding may carry that field's declared not-run value, from
  `FIELD_NOT_RUN = {"found-by": "not-compared"}`.

And the split that makes conditionality work without a second roster: **an item is conditional
exactly when the stages table names it.** The unconditional section sweep skips those keys; a
`ran` row demands them; a `skipped: <reason>` row demands nothing. Per-finding field checks
stay unconditional — every finding carries `- Found by: both | one | not-compared` with no
default, exactly as `evidence-marker` has none — and stage 4's `ran` only tightens the accepted
values.

Stage 3's asymmetry is enforced structurally: a finding whose `## Drives` attribution is the
skill-less box and whose target is the subject is a category error, and is rejected.
`## Undecidable` blocks carry `- Kind:`, `- Rung: probe|readers`, and, when the rung is `probe`,
`- Probe: <move>` whose `## Move outcomes` row must be `ran`. That single cross-section rule is
the enforceable half of "the model proposes, the tool disposes": you cannot declare a probe was
the answer and then skip the move.

### Decision: which additions are fields, which are sections, and in what order they land

| Addition | Shape | Why |
|---|---|---|
| `- Found by:` | Per-finding field | An axis of one finding, like `- Evidence:` |
| `- Digest:` | Per-finding field | Binds one finding to the bytes it is about |
| `## Frozen` | Section | One fact about the whole run |
| `## Stage outcomes` | Section | Mirrors `## Move outcomes` exactly |
| `## Undecidable`, `## Reading diff`, `## Drives` | Sections | Stage artifacts, conditional |
| `## Disputed severity` | Section, bare-heading | Demands nothing of undisputed findings; an empty section and a surface nobody looked at must not look the same (R6) |

`## Disputed severity`, when non-empty, requires two `- Position:` lines per dispute, each with
a `` `file:line` `` citation, recorded verbatim. No ranking, no vocabulary.
`SeverityVocabularyTests` asserts the only occurrences of `severity|CRITICAL|WARNING|SUGGESTION`
in the whole skill directory are that heading and its `REPORT_SHAPE` marker.

**Co-edit atomicity:** every `REPORT_SHAPE` addition lands in one commit with its
`## The shape of a report` row, `references/example-report.md`, and
`openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md`.
`ReportSchemaSelfDescriptionTests` and `FirstDamageReportTests` make every other ordering red.

### Decision: the one new numbered move is 9

The moves table runs `0`–`8` plus one textual row (`SKILL.md:50-59`). `reading-diff` appends as
**move 9**, never inserts — renumbering would silently change what `- Move: 3` means in every
already-shipped report. Stages 0–1 add no move; stages 2–4 are categorically not moves.

## Data Flow

    tree_digest(subject) ──→ frozen_digest ──→ every payload's `frozen`
                                                      │
    roster ──→ note(...) ──→ notes[] ──filter(ESCALATION_BUCKETS)──→ escalatable[]
                                                      │
                                     rung=probe ──────┴────── rung=readers
                                          │                        │
                       candidateGates + refusal              reading-diff
                                          │                   (two supplied
                       control gate (refusal present)          readings)
                                          │                        │
                       candidate gates (refusal absent)      shared → candidates
                                          │                        │
                                   walkthrough verdict ◄───────────┘
                                          │
    SKILL.md stages table ──→ stage_roster ──→ check-report ──→ violations[]
                                                     ▲
                             report `## Stage outcomes` (ran | skipped: reason)

The loop back from `reading-diff` to `walkthrough` is the whole point: a reading never leaves
that path as a fact, only as a candidate for a gate.

## File Changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/skill-audit/scripts/audit_cli.py` | Modify | `frozen_digest`, `note`/`stalled` constructors, `DOCTRINE_SIDE_NOTES`, `ESCALATION_BUCKETS`, `escalation` hints, step `kind` + `setup-failed`, `candidateGates`, `run_reading_diff`, `stage_roster`, `FIELD_NOT_RUN`, four `REPORT_SHAPE` keys, `check-report --subject` |
| `.claude/skills/skill-audit/SKILL.md` | Modify | Stages table; moves row 9; subcommand row; six report-shape rows; escalation and setup Decision Gates; the five-model-run statement; the "presence, never independence" limit at the stage rows |
| `.claude/skills/skill-audit/references/usage.md` | Modify | Worked `reading-diff` invocation; exit table extended; `setup-failed` documented |
| `.claude/skills/skill-audit/references/probes/skill-audit.first-run.json` | Modify | Step 0 declared `"kind": "setup"`; a `candidateGates` block |
| `.claude/skills/skill-audit/references/probes/skill-audit.reading-*.json` | Create | The shipped reading pair for the worked invocation |
| `.claude/skills/skill-audit/references/example-report.md` | Modify | Co-edited per report-shape addition |
| `openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md` | Modify | Same, in the same commits |
| `tests/test_skill_audit.py` | Modify | New locks; the seven named locks co-edited |

No file under `implementations/`, no other skill, and **not** `openspec/config.yaml`.
`NothingWasRepairedTests` needs **no exemption widening**: nothing added here writes.
`reading-diff` reads two files and emits; `frozen_digest` calls `tree_digest` and hashes;
`candidateGates` runs inside the existing walkthrough box under its existing lifecycle.

## Interfaces / Contracts

`reading-diff` payload: `{surface, agreement, shared, onlyIn{a,b}, comparison:"not-run",
candidates, limit, frozen}`. Exit `0` any verdict, `2` inability.
`walkthrough` payload gains `steps[].kind`, `gates{declared,passed}`, and, on failure,
`status:"setup-failed"` with `index`/`name`/`detail` at exit `2`.
`roster`/`structure` payloads gain `escalatable[]` and `frozen{}`.
`check-report` payload gains `rederived: bool`; exits unchanged at `0`/`1`/`2`.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | `frozen_digest` stability and exclusion sensitivity; `stage_roster` derivation; marker-shape demand dispatch; `FIELD_NOT_RUN` |
| AST | `EscalationPartitionTests` totality; B1/B2/B3; `SingleWalkTests` still green with `frozen_digest` present |
| Integration | Control gate live and dead, over real processes; `setup-failed` exit `2`; `check-report --subject` mismatch; an `## Undecidable` `probe` rung whose move is `skipped` |
| Inversion | Every lock seen RED first; restore by inverse patch confirmed by `sha256`, never `git checkout --` |
| Suite integrity | `SuiteIntegrityTests` — no duplicate top-level class name, no duplicate `test_` name within a class |
| Counting | `python3 -m unittest discover -s tests` before and after; **1026** must rise by exactly the number added |

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|---|---|---|---|
| Subprocess execution | Applicable — candidate gates spawn one process per candidate | `shell=False`, argv lists, cwd always the box, `{candidate}` interpolated only inside `candidateGates.argv`, per-step timeout unchanged | A `candidateGates.argv` naming an unknown `{token}` → exit `2`; a candidate string containing a shell metacharacter reaches argv literally |
| Candidate provenance | Applicable — candidates may originate from a model's reading | Candidates only ever *propose a gate*; the verdict is the process's. `closed_seen` unreachable from `--reading` by B1–B4 | B4, and a reading superset producing zero `unregistered` |
| Refusal-channel trust | Applicable — a silent program would fake acceptance | Inverted control gate; a dead channel stalls before any candidate runs | A subject that ignores unknown flags → control stalls, candidates `unreached` |
| Executable-file classification | N/A — files are hashed, never classified or executed | — | — |
| Git repository selection | Applicable, unchanged — `{repoRoot}` resolved absolutely by the tool | Inherited from the prior change | Inherited |
| Commit state | Applicable — `frozen_digest` reads the worktree, not `HEAD` | Stated: the freeze is *the bytes audited*, deliberately including uncommitted work | A file edited mid-audit → finding-vs-`## Frozen` mismatch rejected |
| PR / push automation | N/A — no branches, no PRs; ordered commits on `main` | — | — |

## Migration / Rollout

No migration. Six ordered commits on `main`, in the proposal's slice order (1, 2, 3 independent;
then 4, 5, 6). Each reverts independently in reverse order; the step `kind` field defaults to
today's behaviour, so a reverted slice cannot disturb the baseline. The ~1,210-line forecast
against `review_budget_lines: 800` is acknowledged and accepted; scope is not silently shrunk.

## Open Questions

- [ ] The control gate consumes one extra process per candidate run. Cheap, but it does mean a
      candidate set of one costs two executions.
- [ ] `- Digest:` repeats a 64-character hash per finding. Verbose by choice — a prefix would be
      a claim about *some* bytes — but a report author will get it wrong, which is exactly what
      the check catches and also exactly what will be annoying.
- [ ] `check-report --subject` re-derives from the worktree. A report validated long after the
      audit will mismatch honestly, and the operator must read `rederived: false` as the weaker
      check it is.
