```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:f54a167b44abe7856a78dd2895dd8c0f130deb2f7956ab3a43163be230c16b69
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 9/9
scenarios: 14/14
test_command: python3 -m unittest discover -s tests
test_exit_code: 0
test_output_hash: sha256:aece186dc35f871b91ed3c1b4a85ce5c4b81542dc8a9c0a8055bd9ba13b451bf
build_command: python3 -m compileall -q .claude/skills/remote-execution/scripts tests
build_exit_code: 0
build_output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## Verification Report — the-distribution-that-spans-every-account

**Change**: `the-distribution-that-spans-every-account` · Domain: `remote-execution` ·
Mode: full artifact set (proposal + spec + design + tasks) · Store: openspec.
Repository: `/Users/diego/Proyectos/papersmith-ai`, branch `main` at `5ac8905`, worktree clean.

**Verdict: PASS WITH WARNINGS.** All 9 spec requirements and all 14 scenarios were
driven with inputs I built myself — not read off passing tests — and every one
held. One WARNING: two prose spots in `SKILL.md` (the frontmatter `description`
and the intro paragraph) enumerate `remote_cli` subcommands and were not updated
to include `distribute`, even though the `packer.py` bullet's re-derivation
(explicitly promised by tasks 11.3/11.4) was done correctly. No CRITICAL issues.

---

## 1. Evidence I measured myself

| Command | Exit | Result |
|---|---|---|
| `python3 -m unittest discover -s tests` | 0 | **1157 tests, OK** (baseline 1125 + 32; matches the claimed 1125 → +24 → +8 progression) |
| Same suite, under a from-scratch outbound-socket guard (`sitecustomize.py` on a scratch `PYTHONPATH`, never site-packages) | 0 | **1157 tests, OK, zero blocked outbound connection attempts** (log file the guard would have written on any blocked attempt was never created) |
| `python3 -m compileall -q .claude/skills/remote-execution/scripts tests` | 0 | clean |

My first socket-guard attempt printed a stderr line via `atexit` that broke two
unrelated tests asserting exact subprocess stderr content — a guard artifact of
my own construction, not a defect in the code under test. Fixed the guard to
log to a file instead of stderr and re-ran; confirmed clean.

## 2. The `distribute` CLI, driven end to end with my own doubles

Built an independent `MyFakeAdapter` (not copied from `tests/test_remote_execution.py`)
and drove `remote_cli.main(["distribute", …])` for real, monkeypatching only
backend resolution (unavoidable without a live credential), exactly as the
suite's own harness does but with my own double:

- **Fits entirely**: 5 workers × cap 2, 10 units → exit 0, `places=10`, `assigned=10`, `unplaced=[]`.
- **Partial with named remainder**: 5 workers × cap 2, 12 units → exit 0, `places=10`, `unplaced=["u10","u11"]` — exact identities, not a count.
- **No account healthy**: one worker unauthorized, one unreachable → exit 1, `places=0`, `unplaced=["u0","u1","u2"]`, both `skipped` reasons named.
- **Write-nothing**: `(relpath, sha256)` snapshot of the whole target tree before and after all four CLI runs above — **byte-identical**, zero files added or removed. `adapter.submit_calls == []` throughout.

## 3. The opacity boundary — hostile inputs, not just parallel fixtures

- Same-length structured (`shard-0`…) vs. opaque (hex, newline, leading dash,
  comma, empty string) unit lists against identical worker state produce
  **structurally identical** shapes (`places`, per-worker counts, unplaced count).
- Adversarial identifiers driven directly through `packer.distribute()` —
  a comma, an embedded newline, a leading dash, an empty string, internal
  spaces, a 200-char token — **all round-trip byte-identical**, individually checked.
- Same adversarial set (comma/slash/space/200-char) driven **through the CLI's
  JSON output** — confirmed byte-identical end to end, proving `--unit`'s
  repeatable-flag design (never comma-separated) actually holds at the CLI layer.

## 4. The aggregate is real — mutation-proofed myself

5 workers at cap 2, 3 unreachable:

| State | `places` |
|---|---|
| Real (3 of 5 unreachable) | **4** |
| Guard disabled (`if False and …`) | **10** — reproduces the real defect |
| Operator inverted (`!=` → `==`, not disabled) | **6** — a *different* wrong number, confirming disabling (not inverting) is what reproduces the documented bug |

Original `packer.py` confirmed byte-identical (sha256) before and after every
mutation — all mutants ran from scratch temp files, never the real file.

Also independently reproduced the opacity lock's reachable-red proof: inserting
`units = sorted(units)` into a scratch copy of `distribute()` changes the
assignment against a **deliberately unsorted** fixture; the real file's sha256
is unchanged.

## 5. Ragged round-robin — exact tuple, not repeat-equality

`w1(2), w2(1), w3(2)` over six units → `w1=(u_a,u_d)`, `w2=(u_b,)`,
`w3=(u_c,u_e)`, `unplaced=(u_f,)`, `places=5` — the exact worked example in
`design.md`. A second independent call against a fresh adapter reproduces the
same explicit tuple (not merely `result1 == result2`, which the task notes is
near-vacuous for a stable-but-wrong order).

## 6. Nothing collapses

- `Assignment.plan` is a whole `Plan` (all 6 fields), never a bare `granted` int.
- `Distribution`'s fields are exactly `{units, places, assignments, unplaced, skipped}` — **no `complete` boolean**.
- `unplaced` is a tuple of identity strings, confirmed non-count (`("does-not-fit",)`, not `1`).
- Conservation: every unit appears exactly once across `assignments` ∪ `unplaced` — checked with 7 units over 2 ragged workers.
- Worker accounting: `{assignments} ∪ {skipped}` equals `adapter.workers()` exactly.

## 7. Edge inputs — honest results or honest refusals

| Case | Result |
|---|---|
| Duplicate identifiers | `PackerError` naming the identifier and both positions |
| Empty unit list | `places=0` — **computed, not skipped**: `requested=len(units)=0` clamps every worker; this is correct per the suite's own test, not a bug (my first pass wrongly expected `places=4`, corrected on inspection) |
| More workers than units | surplus workers stay in `assignments` with `units=()`, never moved to `skipped` |
| Zero healthy workers (workers exist) | honest result, `places=0`, all units `unplaced`, every worker named in `skipped` |
| Zero workers at all | `PackerError`, reusing `select()`'s exact first-refusal message |

## 8. The `select()`/`distribute()` drift lock

Both exact reason strings — `"live capacity evidence unavailable…"` and
`"no capacity granted right now…"` — appear verbatim in `select()`'s raised
message and in `distribute()`'s `Skip.reason`, driven independently on both
paths. `select()`'s happy-path return shape (`Plan`, first healthy worker) is unchanged.

## 9. The roster-derivation mechanism — proven genuine, not coincidental

`tests/test_proposal_implementation.py`'s `subcommand_surface()` reads
`remote_cli.py`'s `_build_parser` via `ast.parse` and reports leaf subcommands.
I ran it directly against the real file (`distribute` present, 9 leaves total),
then against a scratch copy with the `distribute` subparser block deleted:
`distribute` disappears from the derived roster and nothing else changes. The
mechanism genuinely reads the parser; the passing cross-skill test is not
coincidental. Real file confirmed untouched throughout.

## 10. Scope, duplicates, docstrings

- `git show --stat` on both commits (`5157d26`, `5ac8905`): touches only
  `.claude/skills/remote-execution/` (incl. `SKILL.md`), `tests/test_remote_execution.py`,
  one row of `.claude/skills/proposal-implementation/SKILL.md`, and this
  change's own `openspec/changes/…` artifacts. Not `openspec/config.yaml`, not
  `implementations/Domain_Adaptation`.
- Duplicate class/method scan, re-derived myself with `ast`, **scoped per class**
  (a flat scan across all classes gives false positives for legitimately-shared
  method names in different classes — my first pass made this mistake and I
  caught it): **62 top-level classes, 428 `test_` methods, all unique** when
  qualified as `ClassName.method_name`. Matches the apply record exactly.
- `plan()`'s docstring and the module docstring were re-derived (new paragraph
  structure covering three arities), not appended to — confirmed by reading
  `packer.py:1-44` and `:93-117` directly.

## 11. Pre-existing findings — confirmed present, not introduced or worsened

- `MODULE_SCRIPTS` (`tests/test_remote_execution.py:11001`) includes
  `packer.py` and `remote_cli.py` (both touched by this change) but **not**
  `tests/test_remote_execution.py` itself. Independently counted **230**
  occurrences of the four target-vocabulary literals in that test file
  (close to the claimed 225; exact method of counting likely differs slightly,
  same finding, same order of magnitude).
- `openspec/config.yaml` still pins `test_command` to `test_extract_pdf.py`
  only, on all three lines that reference it — confirmed unchanged.

Both predate this change and are explicitly listed as non-goals in the proposal
and spec; my drives simply confirm neither was silently fixed nor silently worsened.

---

## Issues

### CRITICAL

None.

### WARNING

**WARNING-1 — `SKILL.md`'s frontmatter description and intro prose do not mention `distribute`.**

Two spots enumerate `remote_cli` subcommands and both predate-and-postdate this
change unchanged:
- Line 3 (YAML frontmatter `description`): "`the full remote_cli front door
  (submit … status, poll, fetch … reconcile, generate-job, smoke record,
  readiness)`" — no `distribute`.
- Line 14 (intro prose): "the CLI a user would invoke directly (`submit`,
  `status`, `poll`, `fetch`, `reconcile`)" — no `distribute` either.

The `packer.py` bullet (lines 67-79) *was* correctly re-derived per tasks
11.3/11.4 and documents `distribute()` well. No test enforces frontmatter/intro
consistency with the parser (the AST-derived roster guard lives in the
*other* skill, `proposal-implementation`, and only checks its own table). This
is a genuine, uncovered documentation gap — a reader relying on the
frontmatter or intro alone would not learn `distribute` exists — but the
design/tasks artifacts scoped re-derivation narrowly to the `packer.py` bullet,
so this is not a broken spec requirement.

### SUGGESTION

**SUGGESTION-1 — the empty-units `places=0` behavior is easy to misread as "not computed."**

`distribute(units=())` reports `places=0`, which is correct (every worker's
`requested=0` clamps its grant to zero) but easy to misread as "capacity
unknown" rather than "capacity gated by an empty request." A one-line docstring
clarification on `distribute()` (analogous to the suite's own test comment,
`"computed, not skipped"`) would help a future reader avoid the same
first-pass mistake I made during this verification.

---

## 12. Task completion

All boxes across Phases 1-12 in `tasks.md` are `[x]`. Every checked item I
sampled matches code on disk and was independently re-derived by driving the
shipped code, not by reading the checkbox.

## 13. Final verdict

**PASS WITH WARNINGS** — 0 CRITICAL, 1 WARNING, 1 SUGGESTION. Every requirement
and scenario in the spec was proven by driven runtime evidence I produced
myself: the CLI, the arithmetic, the opacity lock (including its reachable-red
mutation), the aggregation mutation proof, the ragged round-robin's exact
tuple, and the write-nothing guarantee. Nothing was launched to Kaggle at any
point during this verification.
