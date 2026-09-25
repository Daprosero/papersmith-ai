# Experiments-Seal Declared Delta (D11 step 3)

Per `implementation-cli-seal`'s "The Experiments-Seal Holder Rename Is A
Declared, Sanctioned Digest Delta" and `design.md` D11.

## What changed

`tests/experiments_seal/corpus.py:344` — `Trial/AGREED.md` renamed to
`Trial/Experimental_AGREED.md`, matching `experimental-implementation`'s own
declared holder (`skills/experimental-implementation/impl_profile.py`,
Phase 1, task 1.6).

## Why every listed case moves

Every case below embeds the holder path in its own captured stdout, at one
of these printed sites:

- `position_state`'s `"holder"` key (`implementation_engine.py`, the
  `position_state` return dict).
- `cmd_position`'s printed `holder` field and `.implementation/position.jsonl`
  event's `"holder"` key.
- `cmd_settle`'s printed `holder` field and `.implementation/position.jsonl`
  event's `"holder"` key.

## Pre-recapture failing case IDs (measured, this run)

Captured via `.venv/bin/python -m pytest tests/test_experiments_seal.py -v`
at the state after `corpus.py`'s rename lands, **before any recapture**:

- `verify-a`
- `verify-b`
- `verify-a-declared`
- `verify-b-declared`
- `verify-b-undeclared`
- `position-e1`
- `verify-t`

Plus the corpus fingerprint check itself
(`DigestComparisonTests::test_the_corpus_fingerprint_matches`), which always
moves whenever `tests/experiments_seal/corpus.py`'s own bytes change
(`CORPUS_FINGERPRINT_SOURCE = Path(__file__)`).

## Recapture, verified against this exact list

`.venv/bin/python tests/experiments_seal_capture.py` was run once, after this
delta document existed. The recaptured moved set, computed by comparing the
pre-recapture golden to the post-recapture golden key by key, is exactly:
`__corpus_fingerprint__`, `position-e1`, `propose`, `verify-a`,
`verify-a-declared`, `verify-b`, `verify-b-declared`, `verify-b-undeclared`,
`verify-t`. `propose` is the pre-existing declared non-deterministic case
(`NON_DETERMINISTIC_CASE_IDS`, `tests/experiments_seal/unsealed.json`'s own
recorded reason, a timestamp) and moves on every recapture regardless of this
change; it is not part of the rename's sanctioned delta but its movement is
expected and harmless. Every other case's digest is byte-identical to its
pre-rename golden.

## Sanctioned delta, and nothing else

This list is recorded from the pre-recapture failure set (D11 step 3), before
the experiments seal is recaptured (D11 step 5). Only these named cases are
allowed to move once `tests/experiments_seal_capture.py` runs. Any other
digest movement is an undeclared defect, not part of this sanctioned delta.

The proposal seal (`tests/seal/`) is untouched by this rename —
`proposal-implementation` already declares `AGREED.md`, its zero-migration
declaration — and stays a hard zero-delta gate throughout this change
(verified separately at every commit: `git diff --stat tests/seal/digests.json`
empty).
