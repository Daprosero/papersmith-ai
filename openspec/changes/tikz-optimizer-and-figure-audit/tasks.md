# Tasks: TikZ Optimization And Figure-Prose Auditing

## WU-1 — `paper_tikz.py`: libraries, header, comments

- [x] `scan_libraries` / `detect_required_libraries` / `merge_libraries` (dedup, sorted, one line)
- [x] `normalize_header` (insert when absent; warn, never swap, an author's class)
- [x] `strip_directives_and_comments` preserving `% node:` and `%!`
- [x] Direct module-level `import paper_tikz` in `paper_cli.py` (same commit — `ModuleCompletenessTests`)

## WU-2 — `paper_tikz.py`: factoring, idempotency, guards

- [x] Conservative `\tikzset` factoring (no positional key, no `#1`, no coordinate/node reference)
- [x] Structural idempotency (generated `ps-` styles are never re-factored)
- [x] `scan_memory_guards` — static, toolchain-independent, warnings only

## WU-3 — `paper_figure.optimize_figure` / `optimize_source`

- [x] Always-run `cross_check_manifest` + `scan_data_boundary` on the candidate, including `--no-compile`
- [x] Compile-validation of the candidate, then atomic commit; rollback on any non-`success`
- [x] Dry-run helper `render_optimized_text`

## WU-4 — `paper_figure_audit.py`

- [x] `extract_entities`, `normalize`, `audit_semantics`
- [x] Three finding keys, three-valued verdict, no `status` key
- [x] Reuse `check_excluded` and convert its `Refused` into a finding
- [x] Direct module-level `import paper_figure_audit` in `paper_cli.py`

## WU-5 — wiring

- [x] `figure optimize` / `figure audit` nested namespace
- [x] `verify` eighth check `figure-semantics`
- [x] `paper_coupling_evidence.Evidence.figure_semantics` + `gather()` invocation
- [x] MCP registry roster updated (`figure` declared `out`, not exposed with a misleading hint)

## WU-6 — agents

- [x] `diagram-author.md` optimization rubric
- [x] `figure-auditor.md` (new), `stretch: verify`, full return contract
- [x] `SKILL.md` delegation sentence

## WU-7 — sync

- [x] `SKILL.md` verb table, verify section, frontmatter description, verb count
- [x] Full suite + kit regeneration + generator drift check
- [x] Spec delta for `authored-diagram` and `diagram-obligation`

## M1 — the memory-guard measurement (executed, result recorded)

Measured on the checkout's own TeX Live 2026 toolchain:

- `kpsewhich -var-value=main_memory` answers `5000000` by default and `1000`
  when `main_memory=1000` is exported → kpathsea **does** read the variable
  from the environment, so it is not a `texmf.cnf`-only knob.
- `latexmk` has **no** `--cnf-line` flag, but it does not scrub its child
  environment, so an exported value reaches pdfTeX.
- **UNPROVEN:** that a low value actually aborts a runaway expansion — a probe
  document compiled at `main_memory=1000` with no complaint.

Decision, per the plan's own rule: **static guards plus the existing compile
`timeout` only.** No hard TeX memory limit is set, claimed, or implied, and
`paper_tikz.scan_memory_guards`' docstring records these three results so the
next reader inherits the measurement rather than the assumption.
