## Exploration: cli-paper-e2e

Full end-to-end validation — drive the `papersmith` CLI to create a paper FROM SCRATCH
and prove each skill and subagent path works (paper-ingestion, proposal-deliberation,
proposal-implementation, remote-execution, kaggle-accounts, skill-audit, plus the CLI
surface itself).

Baseline measured: working tree as read 2026-09-09 (no CodeGraph index in this repo —
`.codegraph/` absent, so this exploration used Read/Glob/Grep directly; indexing is the
user's decision). All six `skills/*/SKILL.md` read first. No implementation files created.

### Current State

The `papersmith` CLI (`src/papersmith/cli.py`, entry `papersmith.cli:main`) registers
10 subcommands: `init`, `upgrade`, `status`, `ingest`, `deliberate`, `implement`, `run`
(executor), `remote`, `target`, `audit`. Thin argparse layer — every handler resolves a
workspace dir and forwards to either `core/` logic or a `bridges/` subprocess call:

| CLI surface | Skill script actually invoked | Bridge |
|---|---|---|
| `ingest <pdf\|url>` | `skills/paper-ingestion/scripts/extract_pdf.py` (via micromamba when present, 3600s timeout) + download/classify/index in `core/ingest.py` | `core/ingest.py` |
| `deliberate --action/--request` | `skills/proposal-deliberation/cli.mjs --serve` (STATUS, RESOLVE_TARGET, CREATE_INITIAL_REVISION, CREATE_SUCCESSOR + accept-token flow, WITHDRAW/RESTORE, MAINTENANCE) | `bridges/deliberation.py` + `bridges/node.py` |
| `implement --action` | `skills/proposal-implementation/scripts/implementation_cli.py` (`env/name/plan/apply/admit/handoff/compose/probe/verify`; aliases `materialize→apply`, `benchmark→probe`) | `bridges/implementation.py` |
| `remote pack/push/status/pull/sync` | `skills/remote-execution/scripts/remote_cli.py` (`generate-job/submit/status/fetch/reconcile`) | `bridges/remote.py` |
| `run <profile>` | dispatches local / `remote_cli.py submit` / ssh-sbatch per `compute_targets`; appends to `.papersmith/runs_ledger.jsonl` | `core/executor.py` |
| `audit [--check-drift]` | `skills/skill-audit/scripts/audit_cli.py roster` **hardcoded to `--subject skills/skill-audit`** + generator/manifest drift | `bridges/audit.py` |
| `init/target/status/upgrade` | workspace topology + kit copy + manifest (`core/init.py`), target listing/checks, status snapshot | `core/` directly |
| kaggle-accounts | **No `papersmith` subcommand.** Reachable only as `python3 skills/kaggle-accounts/scripts/accounts_cli.py` (`validate/remove/list/discover/materialize`) or indirectly via `target check` (`list --json`) and the remote adapter's `workers()` subprocess | none |

A from-scratch paper run (per `README.md` + `core/init.py`) is:
`pipx install .` → `setup_env install` → `setup:harnesses` → `papersmith init <dir> --title
--topic --remote` → `status --json` → `ingest <pdf|url>` → `deliberate --action status`
→ (`deliberate --action init`, successors, `implement …`, `remote pack/push/pull`,
`run`, `audit --check-drift`, `target`). `init` creates `.papersmith/`,
`guidance/reference-papers/`, `proposals/{drafts,deliberated,receipts}/`,
`implementations/`, `kaggle-inbox/`, `journal/` plus kit copy, generated docs, manifest.

Existing e2e coverage (`openspec/config.yaml`: e2e = `node:test *-e2e.test.mjs`, 5 files):
all five (`publish`, `move-copy`, `semantic-modify`, `successor-acceptance`,
`delete-cleanup`) drive the deliberation **TS engine via jiti in tmp dirs** — never the
`papersmith` binary. Python side (18 `tests/test_*.py`) covers bridges/executor/
remote/ingest/init with subprocess doubles, `FakeAdapter`, and a fake `kaggle`
executable — no network, no real account, no multi-command workspace journey.
**No test today runs `papersmith init` … `audit` in one workspace.** The skill-audit
`walkthrough` move drives a documented flow against a shared box, but only for audit
subjects — not for the CLI journey.

### Affected Areas
- `src/papersmith/cli.py` — argparse surface any journey asserts against
- `src/papersmith/core/init.py` — workspace topology + `--no-npm` vs npm paths
- `src/papersmith/core/ingest.py` — classify/download/extract/index seam (network + 1.5 GB Surya weights on first run)
- `src/papersmith/bridges/deliberation.py`, `node.py` — accept-token flow, node_modules precondition
- `src/papersmith/bridges/implementation.py` — alias + required-flag forwarding
- `src/papersmith/bridges/remote.py`, `src/papersmith/core/executor.py` — consent gate, gate authorization, smoke/campaign modes
- `src/papersmith/bridges/audit.py` — hardcoded single-subject roster + drift check
- `skills/kaggle-accounts/scripts/accounts_cli.py` — no CLI bridge; e2e must use `FakeAdapter`/fake executable, never live credentials
- `tests/` + `openspec/config.yaml` — where the new e2e layer registers (`npm run test:all` must keep passing under `strict_tdd: true`)

### Approaches
1. **Shell-driven journey script** — one bash script: tmp workspace, `papersmith init --no-npm`, tiny fixture PDF, offline flags, `FakeAdapter` backend; asserts exit codes + artifact existence step by step
   - Pros: closest to real user path; exercises the installed binary; cheap to run manually/CI smoke
   - Cons: weak assertions; outside `npm test`/`pytest` runners; flaky env deps (npm, micromamba, node) leak in
   - Effort: Low
2. **pytest CLI e2e suite** (`tests/test_cli_paper_e2e.py`) — `tmp_path` fixtures, subprocess the CLI entry, fake the heavy boundaries (stub download/Marker via fixture PDF + monkeypatched extract, fake `kaggle` exe on PATH, `--no-npm` init)
   - Pros: CLI is Python so the harness matches; `tmp_path` + fakes are established patterns here; strong assertions on ledgers/manifests/indexes; runs inside `npm run test:all`
   - Cons: node-engine legs covered only as black box; splits e2e across two runners conceptually
   - Effort: Medium
3. **node:test CLI e2e suites** — spawn the `papersmith` binary via `child_process` per skill leg, alongside the existing five `*-e2e.test.mjs` files
   - Pros: extends the existing e2e home (`npm test`); natural for deliberation legs; per-skill journey files mirror the topic
   - Cons: Node spawning Python CLI is awkward; slowest (npm install, engine cold starts); fixture/fake story weaker than pytest
   - Effort: Medium/High

### Recommendation
Approach 2 (pytest hermetic CLI journey) as the real gate — one `init → status →
ingest(fixture PDF) → deliberate status/init → implement verify/probe → remote
pack/status (FakeAdapter) → run --dry-run → audit` flow with every network/heavy
boundary faked — plus Approach 1 as a thin manual/CI smoke wrapper reusing the same
fixtures. Keep the five existing node e2e files as the engine-internal legs; do not
duplicate them. Explicitly out of scope for e2e: live Kaggle (FakeAdapter only),
real Marker/Surya weights, real `npm install` inside init (use `--no-npm` + prebuilt
node_modules).

### Risks
- Heavy first-run costs (Surya ~1.5 GB, `npm install` 180s, Marker 3600s timeout) — e2e must fake or fixture all three or it is not a gate anyone runs
- Live credentials/quota: any e2e touching real Kaggle spends money — hard-require FakeAdapter/fake executable, forbid network
- Consent + gate-authorization interplay (`submit --consent`, `gate` record, smoke vs campaign exemptions) is the most likely journey stall point
- Known CLI gaps the journey will expose rather than fix: no `papersmith` subcommand for kaggle-accounts; `audit` hardcoded to the skill-audit subject (general skill audit unreachable via CLI)
- `init` npm path vs `--no-npm` path diverge; journey must pin one and document the other as manual
- Review budget: keep the new suite under ~800 lines or split per-leg follow-ups

### Ready for Proposal
Yes — propose the pytest hermetic journey (Approach 2) with the shell smoke wrapper (Approach 1); file proposal under `openspec/changes/cli-paper-e2e/`.
