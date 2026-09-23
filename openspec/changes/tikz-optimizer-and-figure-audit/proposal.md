# Proposal: TikZ Optimization, And A Figure That Answers To Its Own Prose

## Intent

`render` can prove a diagram compiles and that its manifest matches its source. Nothing can
make the source smaller, and nothing checks whether the diagram and the methodology text are
describing the same pipeline. Close both, without inventing a refusal vocabulary, without a
second CLI entrypoint, and without giving any module a disk read `paper_coupling_evidence.py`
does not own.

## Scope

### In Scope

- **`paper_tikz.py`** — pure text-to-text transforms: library scan/detect/merge (pruning only
  what the syntax map can *prove* unused), standalone header normalization (insert when absent,
  never swap an author's class), marker-preserving comment stripping (never by default),
  conservative `\tikzset` factoring (no positional keys, no placeholders, no baked-in
  coordinates), structural idempotency, and static memory guards that report rather than claim a
  TeX limit nobody measured.
- **`figure optimize`** — the pipeline: transform, always-run stop A and manifest cross-check on
  the *candidate*, compile-validation, atomic commit; rollback on any non-`success` verdict.
- **`paper_figure_audit.py`** — manifest components against section prose, plus the
  `components_from` fact list against both, with a three-valued verdict and the plan's three
  finding keys.
- **`figure audit`** — the standalone verb, writing `figure_audit.json` beside the figure's ledger.
- **`verify`'s eighth check** — `figure-semantics`, computed in `gather()` and read as a dict by
  the AST-locked `paper_verify.py`.
- **`figure-auditor` agent** and a `diagram-author` optimization rubric.

### Out of Scope

- No second entrypoint, no new runtime dependency, no real TikZ AST.
- No change to `render`/`place`, the repair-budget ledger, stop A's meaning, or any existing
  refusal code's meaning.
- No new refusal code anywhere; the roster's pinned count is unchanged.
- No per-harness fork of agent instructions.

## Approach

Two skill-local modules plus a delegating pipeline, mirroring how this skill already splits by
concern. The optimizer is pure and the auditor is pure over inputs; everything that touches a
disk, a manifest, or a compiler stays in `paper_figure.py` or
`paper_coupling_evidence.py` — the modules that already own those privileges.

## Risks

- `\tikzset` factoring changing rendering — mitigated by four conservative preconditions,
  compile-validation by default, and rollback on any failure.
- A library pruned that was actually needed — mitigated by pruning only libraries the syntax map
  can detect and prove absent; anything unprovable is kept.
- A guard claiming more than it measured — mitigated by shipping static guards only, and saying
  so in the module docstring.
