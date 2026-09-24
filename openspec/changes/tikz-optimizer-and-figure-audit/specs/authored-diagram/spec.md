# Authored Diagram Specification (delta)

## ADDED Requirements

### Requirement: Source Optimization

`figure optimize` MUST rewrite a diagram's TikZ source as a **candidate**, and
MUST commit it only after the two text guards and (by default) a compile have
accepted it. It MUST NOT remove a library it cannot prove unused, MUST NOT
delete a `% node:` marker under any flag, and MUST be idempotent: optimizing an
already-optimized source MUST produce byte-identical output.

#### Scenario: An unused library is pruned, a needed one is added

- GIVEN a source loading a library whose syntax does not appear, and using
  syntax that requires a library it does not load
- WHEN `figure optimize` runs
- THEN the first is removed, the second added, and both appear in `changes`

#### Scenario: A library the optimizer cannot recognize is kept

- GIVEN a source loading a library outside the detection map
- WHEN `figure optimize` runs
- THEN that library remains loaded

#### Scenario: Optimization is idempotent

- GIVEN any source
- WHEN `figure optimize` runs twice
- THEN the second run's text equals the first run's

#### Scenario: Markers survive every flag

- GIVEN a source carrying `% node: <label>` markers
- WHEN `figure optimize` runs, with and without `--strip-comments`
- THEN every marker is still present and the manifest cross-check still passes

#### Scenario: Repeated styles factor without moving anything

- GIVEN two sites with byte-identical option lists carrying no positional key
- WHEN `figure optimize` runs
- THEN one `\tikzset` style is introduced and both sites reference it

#### Scenario: A candidate that would fail stop A never reaches disk

- GIVEN a source whose candidate would declare a plotting construct
- WHEN `figure optimize` runs, including under `--no-compile`
- THEN it refuses `DIAGRAM_PLOTS_DATA` and the original is byte-identical

#### Scenario: A failing compile rolls back rather than refusing

- GIVEN a candidate that does not compile
- WHEN `figure optimize` runs
- THEN the call reports `verdict: "rolled_back"` with the diagnostics, exits 0,
  and the original is byte-identical

### Requirement: Honest Memory Guards

Static guards for runaway macro expansion MUST report as warnings in the
optimize report. No hard TeX memory limit may be claimed unless it has been
measured against the real toolchain; the guards MUST NOT imply one.

#### Scenario: A self-recursive macro is named

- GIVEN a source defining a macro that expands to itself
- WHEN `figure optimize` runs
- THEN the report names it as a warning
