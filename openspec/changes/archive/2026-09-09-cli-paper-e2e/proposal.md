# Proposal: CLI Paper End-to-End Journey

## Intent

Problem: no test drives `papersmith init → audit` in one workspace. Node e2e covers only the TS deliberation engine via jiti; pytest covers bridges with fakes. Cross-skill CLI regressions (init/ingest/deliberate/implement/remote/run/audit) ship undetected. This change adds a hermetic pytest gate proving the full from-scratch paper journey offline.

## Scope

### In Scope
- `tests/test_cli_paper_e2e.py` (<~800 lines): `init --no-npm → status → ingest` (fixture PDF, stubbed extract) `→ deliberate status/init → implement verify/probe → remote pack/status` (FakeAdapter) `→ run --dry-run → audit` (+ drift) in `tmp_path`
- Faked boundaries: stubbed download/Marker, fake `kaggle` exe on PATH, `--no-npm` + prebuilt node_modules
- Thin shell smoke wrapper reusing the same fixtures for manual/CI
- Registration in `npm run test:all`; `strict_tdd` stays green

### Out of Scope
- Live Kaggle, real Surya weights/Marker, real `npm install`
- Fixing exposed CLI gaps (no kaggle-accounts subcommand; audit hardcoded subject) — expose only
- Duplicating the five existing node e2e engine legs

## Capabilities

> Contract between proposal and specs phases. Researched `openspec/specs/` (empty — only `.gitkeep`).

### New Capabilities
- `cli-paper-e2e`: hermetic CLI journey gate for the from-scratch paper run

### Modified Capabilities
- None — test-only change, no behavior requirements change

## Approach

Exploration Approach 2 as the gate (pytest hermetic journey; Python CLI matches pytest plus established `tmp_path`/fake patterns) with Approach 1 as a thin smoke wrapper. Node e2e files stay the engine-internal legs.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `tests/test_cli_paper_e2e.py` | New | Hermetic journey suite, <~800 lines |
| `scripts/cli-paper-smoke.sh` | New | Thin smoke wrapper reusing same fixtures |
| `openspec/config.yaml` | Modified | Register new e2e layer |
| `src/papersmith/cli.py`, `core/`, `bridges/` | Referenced | Exercised, not changed |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Surya/npm/Marker costs make gate unrunnable | High | Fake all three (fixture PDF, stubbed extract, `--no-npm`) |
| Live credentials/quota spent | Med | FakeAdapter + fake exe only; forbid network |
| Consent + gate-authorization stall | Med | Pin smoke/dry-run paths; document manual legs |
| Suite exceeds ~800 lines | Low | Split per-leg follow-ups |

## Rollback Plan

Delete the new test file and smoke wrapper; revert the `config.yaml` registration. No production code is touched, so runtime rollback is a pure revert with zero user impact.

## Dependencies

- Existing pytest `tmp_path`/fake patterns, FakeAdapter, fixture PDF, prebuilt node_modules
- Five node e2e files remain unchanged

## Success Criteria

- [ ] One pytest gate runs init→audit hermetically with no network
- [ ] New suite under ~800 lines; `npm run test:all` green under `strict_tdd: true`
- [ ] No live Kaggle, real weights, or real install in the e2e path
