# Exploration: halves-nobody-joined (2026-08-20)

Defect class: a capability exists in one place and no doctrine on the path that
reaches it tells anyone to use it, create it, or where to put it.

## Findings, ranked

**F1 — Flow A never asks for `revision` and `premises`.** CONFIRMED by reading.
Three places assert the ask: `SKILL.md:913`, `SKILL.md:984` (`declare-first`
blames the user for skipping it), `assets/kit/src_benchmark/__init__.py:21`.
Flow A (`SKILL.md:438-563`) contains no such step: every "revision" hit there is
the `--revision` flag of `admit`/`verify`, and `premises` appears zero times.
Step 5 says the file is "copied verbatim and never populated". First pass of
every new target dead-ends at a rung whose named remedy does not exist.
Live-target evidence: its `premises` uses `unit` where the kit says
`statisticalUnit` — the drift you get when nobody asks.

**F2 — `distribution`'s shard-merge refusal has no producer.**
Reader: `implementation_cli.py:579-581` `distribution_state(..., merged=None)`,
`:659` `shardsDisagree`, `:674` `shardsArrived`; doctrine `SKILL.md:1560-1567`.
No producer: `cmd_verify:5120-5123` never passes `merged`; `verify` has no flag
for it; none of `remote_cli.py`'s eight subcommands merges; `shard_io.py`'s
`read_shards`/`disagreements` have no production caller in the forge.
`remote-execution/SKILL.md:428` cites a `merge()` that does not exist there.
Only self-written fixtures exercise it (`tests/...:2384-2389`, `:2410-2413`) —
the exact failure `SKILL.md:313-317` warns about. Crosses skills.

**F3 — `smokeReady` and job staleness are computed and consumed by nothing.**
Producer: `implementation_cli.py:4884-4942`, merged into probe at `:2145-2148`.
The ladder (`:2090-2106`) branches on five things, neither of them. Zero
occurrences of `smokeReady`/`readiness`/`smoke`/`job folder`/`staleness`/
`reconcile`/`generate-job`/`remote_cli` in `SKILL.md` or `usage.md`.
A campaign can be launched on a job that never rehearsed.

**F4 — `kaggle-accounts` has an undocumented fifth command that writes plaintext
tokens.** `accounts_cli.py:690-764` `cmd_materialize` writes
`store/workers/<user>/token` 0600; it is the only producer of a
`CredentialHandle` above the adapter seam (`credentials.py:108`). Its SKILL.md
lists four commands (`:76-79`), names only `store/accounts.json` (`:198-203`),
and `cmd_remove:767-780` deletes the store entry while the materialized token
survives. Security-adjacent; carries a real decision.

**F5 — `coupling` computed by both commands, named by no doctrine.**
`implementation_cli.py:4002-4144`, reported at `:2141` and `:5186`. Zero
occurrences of "coupling" in SKILL.md/usage.md; absent from the Output
Contract's eleven statuses (`SKILL.md:1755-1756`).

**F6 — `remoteExecution: drift`/`unreliable` name a fix nobody is told to run.**
`implementation_cli.py:4781-4788`, doctrine `SKILL.md:1035-1044` says "reconcile
by hand"; `remote_cli reconcile` is named only in a Python docstring
(`implementation_cli.py:4750`), never in SKILL.md, usage.md or Decision Gates.

**F7 — target vocabulary leaked past the guard.** `implementation_cli.py:4039`
`record_name = contract.get("record") or "latent.json"` — the live target's own
filename (`.../MIL_CREDA_Benchmark/__init__.py:142`). The guard
(`tests/...:4698-4720`) scans a fixed word list, so a leak using a new word
passes. Not the same class — a generality defect. Fix: default to `None`.

**#8 — `generate-job` (found before this exploration, still open).** Wider than
one command: NONE of `remote_cli.py`'s eight subcommands appears in
`proposal-implementation`'s SKILL.md or usage.md. Third leg: `SKILL.md:370-388`
argues `tools/` must exist and no step creates one, no table row places one, and
the kit ships no template for it.

## Clean, stated as results
`paper-ingestion` (all inventories); `proposal-deliberation`'s public operation
set; `proposal-implementation`'s asset register (mechanically enforced, both
directions); `probe`'s ten-rung ladder (all documented); `implementation_cli`'s
nine subcommands; `remote-execution`'s own assets.

## Unchecked
No shell in that phase: F2 and F3 unverified by execution. `proposal-deliberation`'s
50+ engine modules unscanned — the largest unexamined surface. `implementation_cli.py`
read in regions, not whole. `remote_cli.py` per-flag doctrine coverage not traced.

## Also noticed
`remote-execution/SKILL.md:398-400` says probe's `remoteExecution` fact "does not
exist yet (a later slice builds it)". It exists (`implementation_cli.py:4842`,
`:2145`). The `prose` staleness check only ever reads targets, never the forge.
