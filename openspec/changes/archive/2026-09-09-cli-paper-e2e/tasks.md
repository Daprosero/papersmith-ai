# Tasks: CLI Paper End-to-End Journey

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 600–750 (test ~550–700, smoke ~40, config +5, PDF binary excluded) |
| 400-line budget risk | High |
| 800-line custom budget risk | Low |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 (stacked) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Fixtures + stub helpers + init/status legs | PR 1 | `pytest tests/test_cli_paper_e2e.py -k "Helper or Init"` | N/A (unit-level, no deploy) | Delete `tests/fixtures/e2e/` + helper block |
| 2 | Ingest/deliberate/implement/remote/run/audit legs + journey | PR 2 | `pytest tests/test_cli_paper_e2e.py -k "Ingest or Deliberate or Implement or Remote or Run"` | `bash scripts/cli-paper-smoke.sh` (after Unit 3) | Revert per-leg classes only |
| 3 | Hermeticity guards + smoke wrapper + registration + budget | PR 3 | `npm run test:all` | `bash scripts/cli-paper-smoke.sh` offline | Delete `scripts/cli-paper-smoke.sh`, revert `openspec/config.yaml` |

Decisions: reuse `tests/fixtures/research-concept-r01.md` as canned `.md` (LaTeX-proven, no new golden); `_link_node_modules` symlinks prebuilt root install (no checked-in stub); `unittest`+`tmp_path` resolves to pytest-run `unittest.TestCase` classes (repo standard, `strict_tdd:true`). Threat matrix all `N/A` — omitted.

## Phase 1: Fixtures and stub helpers

- [x] 1.1 Commit `tests/fixtures/e2e/paper.pdf` (1-page, <10KB) for ingest leg
- [x] 1.2 Add `_make_workspace` + `_link_node_modules` in `tests/test_cli_paper_e2e.py` (tmp_path, symlink prebuilt install)
- [x] 1.3 Add `_stub_extract` in `tests/test_cli_paper_e2e.py` (mock.patch download+extract, copy `research-concept-r01.md` + 1 fig)
- [x] 1.4 Add `_fake_kaggle_bin` in `tests/test_cli_paper_e2e.py` (`#!sh exit 0` exe, monkeypatch PATH-prepend)

## Phase 2: Init/status/ingest/deliberate legs

- [x] 2.1 `TestInitStatus` in `tests/test_cli_paper_e2e.py`: fresh `init --no-npm`→`status` exit 0; dirty workspace fails naming paths
- [x] 2.2 `TestIngest` in `tests/test_cli_paper_e2e.py`: stubbed ingest exit 0, paper `.md` with LaTeX + fig exists
- [x] 2.3 `TestDeliberate` in `tests/test_cli_paper_e2e.py`: `deliberate init`→`status` exit 0, names managed revision, no model call

## Phase 3: Implement/remote/run/audit legs

- [x] 3.1 `TestImplement` in `tests/test_cli_paper_e2e.py`: `implement verify` clean + `probe` names next step, no notebook exec
- [x] 3.2 `TestRemote` in `tests/test_cli_paper_e2e.py`: `remote pack`→`status` via `FakeAdapter` (`test_remote_execution.py`) + fake exe, job + ledger fold
- [x] 3.3 `TestRunAudit` in `tests/test_cli_paper_e2e.py`: `run --dry-run` plans only + `audit` drift probe reports gaps as findings
- [x] 3.4 Ordered journey test in `tests/test_cli_paper_e2e.py`: init→audit green in one workspace via in-process `main([...])`

## Phase 4: Guards, smoke, registration

- [x] 4.1 RED guard in `tests/test_cli_paper_e2e.py`: `socket.socket` patched to refuse on any connect
- [x] 4.2 RED guard in `tests/test_cli_paper_e2e.py`: live `submit` without `--consent` refuses pre-adapter; `KAGGLE_*` stripped, no `~/.kaggle` read
- [x] 4.3 Create `scripts/cli-paper-smoke.sh`: init/status/ingest/dry-run/audit reusing `tests/fixtures/e2e/`
- [x] 4.4 Register e2e layer in `openspec/config.yaml`; assert `wc -l tests/test_cli_paper_e2e.py` <800, `npm run test:all` green, 5 node e2e legs untouched
