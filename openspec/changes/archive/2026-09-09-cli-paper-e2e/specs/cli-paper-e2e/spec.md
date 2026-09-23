# cli-paper-e2e Specification

## Purpose

Hermetic pytest gate proving the from-scratch paper journey (`init → status → ingest → deliberate → implement → remote → run → audit`) in one `tmp_path` workspace with all external boundaries faked. Test-only; it exercises `src/papersmith/cli.py`, `core/`, `bridges/` without changing them.

## Requirements

### Requirement: Workspace Init and Status

The suite MUST create an isolated workspace via `init --no-npm` and prove it healthy via `status` before any later leg runs.

#### Scenario: Fresh init passes status

- GIVEN an empty `tmp_path` with prebuilt node_modules available
- WHEN the suite runs `init --no-npm` then `status`
- THEN both exit 0 with no network access and status reports ready

#### Scenario: Dirty workspace fails fast

- GIVEN a workspace with uncommitted fixture edits
- WHEN the suite runs `status`
- THEN status reports drift naming the offending paths (currently rc 0 — non-zero exit is a known CLI gap, findings-only)

### Requirement: Ingest Leg With Stubbed Extraction

The suite MUST ingest the fixture PDF via stubbed download and Marker extract, producing the lean `.md` plus figure files.

#### Scenario: Fixture PDF becomes readable markdown

- GIVEN an initialized workspace containing the fixture PDF
- WHEN the suite runs `ingest` with the extract stub
- THEN it exits 0 and the paper folder holds the `.md` with LaTeX equations

### Requirement: Deliberate Leg

The suite MUST drive `deliberate status` and `deliberate init` against the ingested paper without a live model call.

#### Scenario: Deliberation initializes and reports

- GIVEN the ingested paper folder
- WHEN the suite runs `deliberate init` then `deliberate status`
- THEN init exits 0 and status names the current managed revision

### Requirement: Implement Leg

The suite MUST run `implement verify` and `implement probe` against the deliberated revision in the target venv.

#### Scenario: Verify and probe pass offline

- GIVEN the current managed revision and isolated venv
- WHEN the suite runs `implement verify` then `implement probe`
- THEN verify reports clean and probe names its next step without executing notebooks

### Requirement: Remote Leg With FakeAdapter

The suite MUST exercise `remote pack` and `remote status` through FakeAdapter plus a fake `kaggle` exe on PATH, never live Kaggle.

#### Scenario: Pack and status round-trip via fake

- GIVEN a verified implementation and fake `kaggle` exe on PATH
- WHEN the suite runs `remote pack` then `remote status`
- THEN pack writes the job folder and status folds the ledger without network

### Requirement: Dry-Run and Audit Leg

The suite MUST finish with `run --dry-run` and `audit`, including a drift probe that exposes (never fixes) known CLI gaps.

#### Scenario: Dry run and audit close the journey

- GIVEN a packed job folder
- WHEN the suite runs `run --dry-run` then `audit` plus the drift probe
- THEN the run plans without launching and audit reports gaps as findings only

### Requirement: Hermeticity Constraints

The suite MUST NOT touch the network, live Kaggle, real Surya weights, Marker, or real `npm install` on any path.

#### Scenario: Offline gate stays offline

- GIVEN no network and no credentials in the environment
- WHEN the full suite runs end to end
- THEN every leg passes and no socket, weight download, or install occurs

#### Scenario: Live-backend attempt is refused

- GIVEN a test that points at the real Kaggle service
- WHEN the suite executes it
- THEN it refuses before any credential read or quota spend

### Requirement: Suite Budget and Registration

The suite MUST stay under ~800 lines, register in `npm run test:all`, and keep `strict_tdd: true` green.

#### Scenario: Registered gate stays green and small

- GIVEN the new `tests/test_cli_paper_e2e.py` under ~800 lines
- WHEN CI runs `npm run test:all` under `strict_tdd: true`
- THEN the journey gate passes and the five node e2e engine legs stay untouched
