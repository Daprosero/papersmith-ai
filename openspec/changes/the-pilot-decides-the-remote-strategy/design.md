# Design: the-pilot-decides-the-remote-strategy

Change: `the-pilot-decides-the-remote-strategy` · Store: hybrid (this file + engram `sdd/the-pilot-decides-the-remote-strategy/design`) · Input: proposal (#1261), spec (#1263), explore (#1255), and the orchestrator's four settled shapes plus the 8th-key consequence.

**Verification note, stated first because it bounds every claim below.** This phase had no shell tool (Read/Edit/Write/Grep/Glob only). Nothing was executed as a process. Every symbol cited here was **re-located by name in the source** and read; no line number was inherited from the proposal or the explore. Where a claim needs a process, it is marked **MEASURE** and belongs in tasks. `Glob` does not honour `.gitignore`, so its negatives are real evidence.

**Two inherited citations are wrong and are corrected here.** (a) The explore and the proposal both place `impl_position.py` under `proposal-implementation/scripts/`; it is at `.claude/skills/_core/implementation/impl_position.py`. (b) The proposal's affected-areas table asks for a `proposal` **fold branch in `impl_position`**. There is no fold to branch: `impl_position.read_events` is kind-agnostic (it parses lines and returns them; a corrupt line is skipped), and every kind-selective scan lives in `implementation_cli.py` — `last_gate`/`last_close`, `_find_or_mint_authorization`'s `consumed` set, `_verify_gate_authorization`'s record lookup. **`impl_position.py` needs no change in this change at all.**

---

## Technical approach

Three slices, in the carried order, sharing one discipline: every new precondition is verified by re-deriving a fact the engine already computes, never by reading a value a caller typed or a record repeats back.

1. **Rehearsal placement** — one branch at `remote_cli.cmd_fetch`'s existing placement decision, plus a pure-argv pairing check above all I/O. Independent, closes the live artifact-leak hole first.
2. **Classification** — one pure rule in `_core/implementation/`, fed rows that `remote_execution_jobs_state()` already opens and currently throws away. Purely additive; nothing refuses on it yet.
3. **Proposal event + 8th binding key** — the schema change, last, because it is the only slice that can invalidate a token.

---

## Architecture decisions

### D1 — Refusal code names, and the check that was run

**Choice.** Three new `gate` codes and one distinguishing code, all under the existing `GATE_<SUBJECT>_<CONDITION>` shape that `GATE_AUTHORIZATION_REQUIRED/UNKNOWN/MISMATCH/STALE/CONSUMED` already establishes:

| Code | Fires when |
|---|---|
| `GATE_PROPOSAL_UNKNOWN` | the token's `proposalDigest` is `null`, or no `proposal` event carries that digest, or the event that does no longer re-digests to it |
| `GATE_PROPOSAL_MISMATCH` | a genuine proposal exists and the token names it, but it does not name **this** job |
| `GATE_PROPOSAL_STALE` | the proposal's own campaign identity (`commit`, `jobSet`) no longer equals what this gate just re-derived |
| `GATE_ELECTION_REQUIRED` | a job in this unit classifies `optional` and this invocation elected nothing for it |
| `GATE_ELECTION_MISMATCH` | `--elect` names a job that is not in this unit, or one that does not classify `optional` |
| `GATE_AUTHORIZATION_SUPERSEDED` | see D6 |

**No `GATE_PROPOSAL_CONSUMED`, deliberately.** A campaign proposal is multi-use by definition — the spec's "proposal survives a same-campaign retry" requirement *is* the absence of a consumed marker. The authorization stays single-use; the asymmetry is the mechanism, not an oversight.

**No `GATE_PROPOSAL_REQUIRED`, and no `--proposal` flag** — see D4.

`remote-execution` has no code tokens at all: every refusal there is a `RemoteCLIError(message)` with a distinct sentence (`remote_cli.py`, `class RemoteCLIError`; the `.partial/` and `--force` refusals are the pattern). The fetch refusals therefore get **distinct wording, not a code string** — inventing a code convention in the skill that has none would be a second mechanism beside a working one.

**The vocabulary check, executed rather than reasoned.** Rule B's denylist is not a list to consult; it is derived at run time from live disk. I executed its algorithm against the live tree:

- `Glob implementations/*/src/*/*.py` → the only non-`_`-prefixed target is `Domain_Adaptation` (`_ensayo_position` is skipped by `target_words`'s own `startswith((".", "_"))` rule).
- Applied `WORD_SPLIT_RE` and `MINIMUM_WORD = 3` to that target's directory, package (`CREDA`, `MIL_CREDA`, `MIL_CREDA_Benchmark`) and module basenames.
- Subtracted the live `FORGE_LEXICON` keys.

**Derived rule-B denylist, right now: `bags, ceiling, conditional, contamination, creda, global, latent, mil, renyi, schedules`.** Rule C floor, read from source: `kaggle, t4, ceiling, ramp, transfer, creda, milcreda, latent`.

Matched with `\b…\b` against every word this change introduces — `proposal, election, elect, superseded, rehearsal, strategy, necessity, execution, budget, local, seconds, optional, campaign, remote, smoke, dest` — **zero hits on either list.** `local` appears in the derived set but is an admitted `FORGE_LEXICON` key, so it is subtracted before the denylist exists. Guarded surface confirmed as `SKILL.md`, `references/usage.md`, `assets/**`, `scripts/**` — `_core/` is outside it, so the new module's name is unguarded here regardless.

**MEASURE:** run the suite. A hand-executed derivation over live disk is evidence, but the authoritative verdict is `test_rule_b_finds_no_target_vocabulary_in_the_forge` actually going green, and the denylist changes the day a target is added.

### D2 — The local budget is a `generate-job` flag in `run-config.json`

**Choice.** `generate-job --local-budget-seconds N` → `run_config["localBudget"] = {"seconds": N}`, written verbatim beside `accelerator`, in `jobfolder.generate_job`'s existing conditional-block section. Omission writes no key at all.

**Rationale — it is the same site, not a new one.** Both comparanda live there and behave identically: `--smoke-required-evidence` (repeatable) lands at `run.smoke.requiredEvidence` only `if smoke_required_evidence`; `--accelerator-kind`/`--accelerator-architecture` land at `accelerator: {kind, architectures}` only `if has_accelerator`, and their joint omission "leaves `generate_job()` writing no `accelerator` block at all — silence." A budget declared here inherits three properties for free: it is target-authored, it is per-job, and its absence is silence rather than a default.

**Seconds, and a block rather than a scalar.** `search_cost_forecast` returns `{"projectedSeconds": …}`, so the comparison is seconds against seconds with no unit conversion anywhere. `{"seconds": N}` mirrors `accelerator`'s two-key block so a second axis can join later without a schema break.

**Alternatives rejected.** (a) The benchmark declaration / `__steps__` — that is the forge's contract surface, read by `search` and `verify`, and would put a per-job number in a target-wide place. (b) A `probe`/`gate` flag — makes the threshold argv-derivable per invocation, the exact defect `_authorization_binding`'s docstring names when it excludes `justification` from the digest. (c) A forge constant — the spec forbids it outright.

**Asymmetry that must be stated, not hidden.** `search.costForecast` is **target-scoped** (one declared search per target); the budget is **job-scoped**. The comparison is therefore one projection against N budgets. That is honest and intended — the projection is what the full run costs, the budget is what each job's owner will tolerate — but it means two jobs can never be separated by the forecast alone, only by their own budgets.

### D3 — The classification seam consumes one already-paid-for walk

**Choice.** New module `.claude/skills/_core/implementation/impl_execution_strategy.py`, sibling to `impl_availability.py` and following its contract exactly: keyword-only, no I/O, never raises, never composes caller prose.

```
classify_remote_necessity(*, jobs: list[dict], results_status: str,
                          cost_forecast: dict | None) -> dict
```

`jobs` rows carry `job`, `accelerator`, `localBudget`, `smokeReady`. `results_status` and `cost_forecast` are keyword-only **with no defaults** — the same discipline `launch_available` applies to `disagreements`, for the same reason: a caller that forgets one fails the call loudly instead of being read as an absence.

**Where the rows come from, and why there is no second discovery.** `remote_execution_jobs_state()` already walks `_discovered_job_folders()`, already calls `JOBFOLDER.read(job_dir)` per folder, and already has `run_config` in hand — then keeps only `job`, `product`, `staleness` and discards the rest. The change reads `accelerator` and `localBudget` **out of that same open `run_config`, in that same loop**. No new walk, no new reader, no second `JOBFOLDER.read`.

`cmd_gate` needs the same verdict and must not walk again. It already calls `_position_write_evidence(target, name)`, which already calls `remote_execution_jobs_state(target)` and keeps only `["smokeReady"]`. Widen that return to carry `jobs` as well, from the *same call*. Both `probe` and `gate` then classify from one function's output. (`cmd_probe` calls `remote_execution_jobs_state` twice today — directly and through `_position_write_evidence`. That is pre-existing cost, not drift: same function, same answer. This change does not add a third.)

**Verdict rule, ordered, and every branch reachable:**

| # | Condition | Verdict | `reason` |
|---|---|---|---|
| 1 | `results_status == "current"` | `local-sufficient` | `results.current` |
| 2 | the job declares an `accelerator` block | `must-remote` | `accelerator.declared` |
| 3 | `localBudget.seconds` and `projectedSeconds` are both numbers, projected **>** budget | `must-remote` | `budget.exceeded` |
| 4 | same, projected **≤** budget | `local-sufficient` | `budget.within` |
| 5 | otherwise | `optional` | `budget.undeclared` \| `forecast.unprojectable` \| `results.unmeasured` |

Rule 1 first: if the target's own record already sits at declared full scale (`results_state` sets `current`, and downgrades to `piloted` when any axis is below `targetScale`), there is no run left to send, hardware or not. Rule 2 asks only what the target **declared**; it never asks what this machine **has**, because a pure rule cannot look and because "does this laptop have the card" is a different question from "does this job need one".

**`optional` means the recorded facts do not decide — never "you may skip it".** That is precisely why it requires a human election (D5), and rule 5's `reason` always names *which* fact was missing. Nothing is inferred, nothing is defaulted.

### D4 — The proposal is carried by the token, not by a second typed digest

**Choice.** `proposalDigest` becomes the 8th `_AUTHORIZATION_BINDING_KEYS` entry and is **engine-derived on both sides** — the digest of the newest `proposal` event on this target's ledger whose campaign identity matches — never read from argv. There is **no `--proposal` flag** and no `GATE_PROPOSAL_REQUIRED`.

**Rationale.** `--authorization` exists because `offer` and `gate` are separate processes and the human must carry something across; that carry is what proves the offer was read. A second typed digest carries the same guarantee twice, and typing it would make the binding partly argv-derivable — the exact defect `_authorization_binding` names when it excludes both `worker` and `justification`. A token minted under proposal P is worthless the moment P is not the ledger's proposal any more, so **the token already is the carrier**.

**New verb.** `propose` appends `{"kind": "proposal", "digest", "jobs": [...], "workers": [...], "dependsOn": [...], "rationale", "campaign": {"commit", "jobSet"}, "session", "at", "proposeOrdinal"}` via `impl_position.append_event`, minted by the same `sha256(json.dumps(payload, sort_keys=True))` form `_find_or_mint_authorization` and `cmd_close`'s `positionDigest` already use. `rationale` is human-authored and non-blank, exactly as `gate`'s `justification` is. `proposeOrdinal` is the count of prior `proposal` events, for the same reason `mintOrdinal` exists: `_now_iso8601()` has second-level precision and two proposals in one second would otherwise collide.

**The staleness keys are structurally distinct, and that is the whole retry guarantee.**

| | Keys | Moves when |
|---|---|---|
| authorization `STALE` | `commit`, `entrypoint`, `rung`, `revisionSha256`, `positionStatus` | a job fails, a position is re-derived, a revision is edited |
| proposal `STALE` | `commit`, `jobSet` | the pin moves, or a job folder is added/removed |

A transient per-job failure moves `positionStatus` and `rung` — invalidating the token (re-mint with `offer`, cheap) and touching **none** of the proposal's keys. `entrypoint` is deliberately absent from the proposal: it is per-job, and a campaign has several.

**Ordering inside `cmd_gate` is load-bearing, and it is what keeps the existing tests green.** The new checks go where `_verify_gate_authorization` already runs — immediately after it, before the `gate` event is appended — never at the top of the ladder:

```
EMPTY_JUSTIFICATION → GATE_AUTHORIZATION_REQUIRED → REVISION_UNREADABLE
  → position/availability ladder → job-folder discovery
  → _verify_gate_authorization  (4 codes, order unchanged)
  → _verify_gate_proposal       (UNKNOWN → MISMATCH → STALE)   ← new
  → _verify_optional_election   (REQUIRED → MISMATCH)          ← new
  → append gate event → append authorization-consumed
```

Nothing is sent from `cmd_gate` at all — `remote_cli.submit()`'s own `_verify_launch_authorization()` reads the `gate` event back later — so "before any send is attempted" is satisfied by any position in this ladder, and the latest safe one costs the fewest fixtures.

**Three literals must stay in sync, and nothing enforces it today.** The 7 keys are spelled three times: the `_AUTHORIZATION_BINDING_KEYS` tuple, `_authorization_binding`'s returned dict, and `cmd_gate`'s inline `gate_binding` dict. The constant's own docstring claims it exists "so the two derivations cannot drift"; it is a comment, not a check. This change adds the 8th key to all three and adds one structural test asserting both dicts' key sets equal `set(_AUTHORIZATION_BINDING_KEYS)`.

### D5 — The election is argv, per invocation, and is never stored as an answer

**Choice.** `gate --elect <job>` (repeatable). Every job in the unit that classifies `optional` must be named by this invocation's own `--elect`, or `gate` refuses `GATE_ELECTION_REQUIRED`. The elected list is recorded on the `gate` event as `elected: [...]` — a fact of that transition, additive, read by nobody in this change (`remote_cli`'s fold selects on `kind == "gate"` and ignores unknown fields).

**The operator's standing rule applies here, and it decides the shape.** A question whose answer is stored and reused was explicitly rejected in the sibling change: the question gets asked every time. A stored `election` ledger event is exactly the rejected shape — one recorded "yes" satisfying every later gate. An argv election is the accepted shape, and it already has a precedent in this exact function: `justification` is human-authored, non-blank, required on every single gate, recorded on the transition, and "never inferred from a general 'go ahead'."

**"Is it single-use like an authorization?" The question does not arise, and that is the answer.** An election is not a token and never outlives its process, so there is nothing to consume and no `authorization-consumed` analogue to build. Single-use is a property something needs only because it persists.

**Alternatives rejected.** (a) A `kind: "election"` ledger event with its own digest and consumed marker — the rejected stored-answer shape, plus a third mint/verify mechanism beside two working ones. (b) A report field on `probe` — the operator ruled this out directly: reporting `optional` is not electing it. (c) Deriving election from the proposal's `jobs` list — the proposal is authored once per campaign and would then silently elect every optional job for every later gate, which is the stored answer again wearing the proposal's clothes.

### D6 — A pre-change token and a tampered token are distinguished, and the distinction can never widen the gate

**Choice.** Distinguish. Add `GATE_AUTHORIZATION_SUPERSEDED`.

`_verify_gate_authorization` today builds `own_binding` from the record, re-digests it with `session`/`at`/`mintOrdinal`, and sets `record = None` on any mismatch — collapsing "nothing minted this" and "the event was edited" into `GATE_AUTHORIZATION_UNKNOWN`, deliberately, because both are equally honest answers. With an 8th key, a **legitimate 7-key token** joins that collapse: `record.get("proposalDigest")` is `None`, the 8-key recompute misses, and it reads as tampering.

The discriminator is a second hash over a payload the function already has:

- 8-key recompute matches its own `token` → genuine, continue.
- else, `"proposalDigest" not in record` **and** the 7-key recompute matches its own `token` → `GATE_AUTHORIZATION_SUPERSEDED`.
- else → `GATE_AUTHORIZATION_UNKNOWN`, unchanged.

The second clause is a measurement, not a guess: an editor who merely deleted `proposalDigest` from a post-change event would fail the 7-key recompute too, because that event's token was computed *with* the key.

**It is diagnostic only.** Both codes refuse, both remedies are "re-mint with `offer`", and forging a "pre-change" token means authoring a ledger event — which the mechanism already treats as unvouched and which gains nothing, since `SUPERSEDED` refuses as hard as `UNKNOWN`. State that limit in the code comment so nobody later reads `SUPERSEDED` as a weaker verdict.

**Alternative rejected — accept the collision and state it (the spec's own position).** One extra hash buys back the tamper signal at exactly the moment the schema change makes tampering plausible. **Also rejected — stamp `schemaVersion` on the `authorization` event.** A version field is trusted prose; a re-digest that succeeds or fails is evidence. It also changes the digest payload, which is this same migration one layer down.

### D7 — Rehearsal placement, and the second hole that making `--dest` optional opens

**Choice.** `cmd_fetch` gains a pure-argv pairing check **above every filesystem call**, before `target = Path(target).resolve()`:

- `smoke=True` with a non-`None` `dest` → refuse: a rehearsal's destination is computed and cannot be chosen.
- `smoke=False` with `dest=None` → refuse: a real fetch has no computed destination.

Then the existing placement decision gains one branch, and only `final_dest` moves:

```
if smoke:      final_dest = target/product/LEDGER_DIRNAME/REHEARSAL_DIRNAME/submission_id
elif verdict == "current":  final_dest = Path(dest).resolve()
else:          final_dest = target/product/LEDGER_DIRNAME/QUARANTINE_DIRNAME/submission_id
```

with a new `REHEARSAL_DIRNAME = "rehearsal"` beside the existing `QUARANTINE_DIRNAME = "quarantine"`. `SMOKE_LEDGER_FILENAME` is the precedent for a rehearsal-specific constant in this module.

**The 8-step contract is preserved by construction, not by re-verification.** Steps 0–7 all read `final_dest` and `partial_dest`, which are computed *after* this branch and unchanged in form. `.partial/`, `--force`, `os.replace`, and ledger-write-last are not touched. The re-fetch guard, the leftover-`.partial` guard, `observed_concurrency` and `LEDGER.append()` last all keep their exact order.

**The second hole, which the discard decision creates and must close in the same slice.** `remote_cli.py`'s fetch parser declares `--dest` as `required=True`. Under `--smoke` argparse would demand it before `cmd_fetch` ever ran, so the flag must lose `required=True` — and the instant it does, a *real* fetch with no `--dest` reaches `Path(None)`. Both directions are closed by the one pairing check above, which is why it is a pairing check and not a smoke-only refusal.

**Deletion stays rejected** (carried decision): it fires only if a follow-up command runs at all, and `cmd_smoke_record` reads the artifact and never touches it again.

---

## Data flow

```
generate-job --local-budget-seconds ──→ run-config.json {localBudget:{seconds}}
                                        run-config.json {accelerator:{...}}
                                                   │
                       _discovered_job_folders ─→ JOBFOLDER.read ─┐
                                                                 ▼
                                            remote_execution_jobs_state()
                                          {jobs[+accelerator,+localBudget], smokeReady}
                                                   │                    │
                       results.status ─────────────┤                    │
                       search.costForecast ────────┤        _position_write_evidence
                                                   ▼                    ▼
                                   classify_remote_necessity(**facts)  (pure, no I/O)
                                                   │                    │
                                    probe report ◄─┘                    ▼
                                                                 cmd_gate ladder
propose ─→ position.jsonl {kind:"proposal", digest} ──┐                 │
                                                      ▼                 ▼
offer ─→ {kind:"authorization", …, proposalDigest} ─→ _verify_gate_authorization
                                                    → _verify_gate_proposal
                                                    → _verify_optional_election
                                                    → {kind:"gate", …, elected:[…]}
                                                                        │
                                       remote_cli.submit ◄──────────────┘
```

---

## File changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/_core/implementation/impl_execution_strategy.py` | Create | `classify_remote_necessity`, pure, sibling to `impl_availability.py` |
| `.claude/skills/remote-execution/scripts/remote_cli.py` | Modify | `REHEARSAL_DIRNAME`; `cmd_fetch` pairing check + placement branch; `--dest` loses `required=True` |
| `.claude/skills/remote-execution/scripts/jobfolder.py` | Modify | `generate_job(local_budget_seconds=…)` → `run_config["localBudget"]`; `validate_run_config` accepts it |
| `.claude/skills/proposal-implementation/scripts/implementation_cli.py` | Modify | widen `remote_execution_jobs_state` rows and `_position_write_evidence`; `cmd_propose`; `_proposal_digest`/`_verify_gate_proposal`/`_verify_optional_election`; 8th key in three literals; `--elect`; `probe` reports classification |
| `.claude/skills/_core/implementation/impl_position.py` | **Unchanged** | corrected: no fold to branch (see header) |
| `tests/test_remote_execution.py` | Modify | placement, pairing refusals, 8-step ordering preserved |
| `tests/test_proposal_implementation.py` | Modify | classification, proposal, election, `SUPERSEDED`; 23-argv audit below |
| `.claude/skills/*/SKILL.md`, `references/usage.md` | Modify | the four new codes, `propose`, `--elect`, the budget flag |

---

## What breaks — producers **and** products

**Producers.** The three binding literals (D4). `cmd_fetch`'s signature (`dest` becomes optional). The fetch parser. `remote_execution_jobs_state`'s row shape and `_position_write_evidence`'s return — both widened, both additive.

**Products — measured on this disk, not assumed.**

| Instance class | Live count | Verdict |
|---|---|---|
| `authorization` events already written under 7 keys | **0** (`Glob` finds two `position.jsonl`; the `Domain_Adaptation` one contains the string `authorization` zero times) | `SUPERSEDED` exists for other clones and replays, **not** for a live migration here |
| Job folders (`tools/<service>/<job>/run-config.json`) | **0** (`implementations/Domain_Adaptation/tools/` holds three loose `.py` files) | no existing job folder becomes `optional`, because none exists |
| Already-fetched smoke artifacts at caller-chosen paths | unknown, outside the repo tree | **untouched**: not moved, not deleted, not invalidated. This change constrains future fetches only. Stated so nobody expects a cleanup that is not designed |
| `gate` events already written | 0 relevant | untouched; `elected` is additive and `remote_cli`'s fold ignores unknown fields |
| `ledger.jsonl` / `smoke.jsonl` | untouched | no schema change reaches them |

**The consequence with zero live instances but real future force:** any job folder generated *after* this change without `--local-budget-seconds`, and with no `accelerator` block, classifies `optional` and therefore needs `--elect` at every gate. That is intended — it is rule 5 saying the facts do not decide — but it must be documented at the flag, or it will read as a bug.

**The prose audit.** `test_an_authorization_minted_before_a_later_contract_change_still_gates` (tests, ~13570) has a docstring asserting `_AUTHORIZATION_BINDING_KEYS` "still names no contract fact". `proposalDigest` is a ledger fact, not a `__steps__` contract fact, so the sentence stays true — but it is the one test whose prose is *about* the key set, so it is individually audited rather than assumed. (Prose outliving its mechanism is a recurring defect in this repository.)

---

## The `--authorization` migration, audited individually

The brief said ~30. **Measured: 29 textual occurrences in `tests/test_proposal_implementation.py`, of which 23 are argv pairs and 6 are prose/comments.**

| Class | Count | Effect of the 8th key | Action |
|---|---|---|---|
| Value `"unminted-placeholder"`, expecting a refusal from **above** the token check (`POSITION_*`, `NOT_READY`, `SEQUENCE_NOT_REACHED`, or rc 2) | **14** | none — the ladder refuses before `_verify_gate_authorization` runs, and D4 adds nothing above it | **untouched** |
| Value `token`, minted by `offer` and verified by `gate` in the same test, asserting `UNKNOWN`/`MISMATCH`/`STALE`/`CONSUMED`-after-first | **3** | none — mint and verify both recompute over 8 keys | **untouched** |
| Value `token`, asserting `returncode == 0` (a gate that must succeed) | **5** | breaks: with no `proposal` event, `_verify_gate_proposal` refuses `GATE_PROPOSAL_UNKNOWN` | **add a `propose` call to the fixture** |
| Literal digest `"f" * 64`, asserting `GATE_AUTHORIZATION_UNKNOWN` | **1** | none — a 64-hex string no event carries stays unknown under any key count | **untouched** |
| Handmade `{"kind": "authorization", …}` events | **0 — measured, none exist** | n/a | none |
| Handmade `{"kind": "authorization-consumed", …}` events | **2** | none — they carry only `token`/`session`/`at` | **untouched** |
| Handmade tokenless `{"kind": "gate", …}` event (the pre-mechanism test) | **1** | none — it refuses at `GATE_AUTHORIZATION_REQUIRED`, above everything new | **untouched** |

**The finding that resizes this slice.** The migration is *not* the digest, and it is not 30 tests. It is **five fixtures that need a campaign proposal before their gate can succeed** — and it is only five *because* D4 declined to add `--proposal` to argv and placed the new checks below `_verify_gate_authorization`. Both of those decisions were made partly for this reason, and the alternative (an early `GATE_PROPOSAL_REQUIRED` argv check) would have added a mechanical two-token edit to 14 further fixtures.

---

## Interfaces

```
classify_remote_necessity(*, jobs, results_status, cost_forecast) -> dict
  # jobs: [{"job": str, "accelerator": dict|None,
  #         "localBudget": dict|None, "smokeReady": bool}]
  # -> {"jobs": {job: {"necessity": "must-remote"|"local-sufficient"|"optional",
  #                    "reason": str}},
  #     "summary": {"mustRemote": int, "localSufficient": int, "optional": int}}
```

No default on any keyword. No I/O. Never raises. Never authors a sentence a caller reads aloud.

---

## Testing strategy — every lock proven reachable (`strict_tdd: true`)

This repository's own convention, read from the suite, is a docstring line: *"Mutation-proven: `<exact mutation>` turns this red — verified below, then reverted."* Every new refusal gets one.

| Layer | What | Mutation that must turn it RED |
|---|---|---|
| Unit | `classify_remote_necessity` — one test per verdict class and per `reason` | invert the `>` in rule 3; delete rule 1's short-circuit; make rule 5 fall through to `local-sufficient` |
| Unit | keyword-only, no defaults | give `results_status` a default and assert the call still fails |
| Integration | `GATE_PROPOSAL_UNKNOWN` | drop the `proposalDigest is None` branch from `_verify_gate_proposal` |
| Integration | `GATE_PROPOSAL_MISMATCH` | widen the job-membership test to `any(...)` over all proposals |
| Integration | `GATE_PROPOSAL_STALE` | remove `jobSet` from the proposal's campaign identity |
| Integration | proposal **survives** a same-campaign retry | add `positionStatus` to the proposal's staleness keys — the retry test must go red |
| Integration | `GATE_ELECTION_REQUIRED` | default `--elect` to "every optional job" |
| Integration | `GATE_ELECTION_MISMATCH` | drop the not-in-unit / not-optional check |
| Integration | `GATE_AUTHORIZATION_SUPERSEDED` vs `UNKNOWN` | delete the 7-key fallback recompute — the pre-change token must collapse back to `UNKNOWN` |
| Integration | the four existing authorization codes still fire in order | reorder `_verify_gate_proposal` above `_verify_gate_authorization` — the `UNKNOWN`/`MISMATCH`/`STALE`/`CONSUMED` tests must go red |
| Integration | three binding literals agree | add a key to `_authorization_binding` only |
| Integration | `fetch --smoke` refuses `--dest` **before** I/O | move the pairing check below `target.is_dir()` and assert with a non-existent target |
| Integration | `fetch --smoke` lands outside `Results/shards/` | make the `smoke` branch fall through to `Path(dest)` |
| Integration | real `fetch` with no `--dest` refuses | delete the second half of the pairing check |
| Integration | the 8-step ordering survives | the existing `.partial/`, `--force`, `os.replace`, ledger-last tests run unchanged against a rehearsal fetch |
| Vocabulary | rule B and rule C over the new identifiers | executed as the suite, not reasoned (D1) |

**Mutation hygiene, mandatory in the task text.** A same-size source edit can leave a stale `__pycache__/*.pyc` in play, so the mutated source never executes and a dead lock reads as live. Every mutation step MUST delete the touched module's `__pycache__` before re-running, and SHOULD prefer a length-changing edit. This applies to `implementation_cli.py`, `remote_cli.py`, `jobfolder.py` and the new `_core` module alike, including where the test drives the CLI as a subprocess — Python invalidates on mtime **and size**, and a same-second, same-size edit satisfies both.

**Suite scope.** Both suites run: `python3 -m unittest discover -s tests` for `test_proposal_implementation.py` and `test_remote_execution.py`. `openspec/config.yaml`'s `test_command` pins the Python half to `test_extract_pdf.py` only and would run **none** of this change's tests; do not read it as coverage.

---

## Threat matrix

The five rows of `references/threat-matrix.md` are git/PR-automation boundaries and are almost all `N/A` here; the boundary this change actually moves is not one of its rows, so it is added rather than fabricated into them.

| Boundary | Applicability | Design response | Planned RED test |
|---|---|---|---|
| Documentation-like paths | N/A — no file-kind classification changes; `guard_entrypoint`'s policy is untouched | — | — |
| Git repository selection | N/A — no new `git` invocation; the pin machinery is untouched | — | — |
| Commit state | N/A — nothing stages, commits or reads the index | — | — |
| Push state | N/A — no VCS push surface | — | — |
| PR commands | N/A — no PR automation | — | — |
| **Filesystem destination composed from a service-supplied `submission_id`** | **Applicable** — the rehearsal branch routes *every* rehearsal through a path built from `submission_id`, a component today reached only by the quarantine branch | `final_dest.resolve()` must remain under `target/product/LEDGER_DIRNAME`; refuse otherwise, before `adapter.fetch()` | a `submission_id` containing `..` (and one that is absolute-path-shaped) must refuse and write nothing |

**MEASURE before writing that guard:** whether `submission_id` is already shape-validated anywhere in `remote_cli`/`ledger`. This phase did not establish it, and a second validator beside an existing one is its own defect.

---

## Migration / rollout

Three slices, revertible independently, in the carried order. Slice 1 (placement) and slice 2 (classification) invalidate nothing. Slice 3 invalidates every live 7-key token — of which there are **zero on this disk** — and the remedy is always re-minting via `offer`, never editing a stored event. Reverting slice 3 restores the 7-key digest and invalidates any token minted under it, symmetrically.

## Open questions

- [ ] **MEASURE** — run the vocabulary suite; the hand-executed rule-B derivation (D1) is evidence, not the verdict.
- [ ] **MEASURE** — is `submission_id` shape-validated today? Decides whether the traversal guard is new or a duplicate.
- [ ] Should `offer` surface a `propose` action when no proposal exists for the campaign? Fails closed either way (`GATE_PROPOSAL_UNKNOWN`), so this is legibility, not safety — deferrable to tasks.
