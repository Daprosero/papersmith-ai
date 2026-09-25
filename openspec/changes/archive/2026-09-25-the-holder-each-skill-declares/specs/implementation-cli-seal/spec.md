# Delta for implementation-cli-seal

## ADDED Requirements

### Requirement: The Experiments-Seal Holder Rename Is A Declared, Sanctioned Digest Delta

`tests/experiments_seal/corpus.py:344`'s `Trial/AGREED.md` MUST be renamed to
`experimental-implementation`'s declared holder filename
(`Trial/Experimental_AGREED.md`). This rename MUST be documented, before any
digest is re-captured, in a delta document naming every case whose captured
stdout embeds the holder path (`position_state`'s `holder` key; `cmd_position`
and `cmd_settle`'s printed sites) — mirroring this specification's existing
F3 declared-delta discipline. Digest movement caused by this rename is
sanctioned; digest movement in any other experiments-seal case is not.

#### Scenario: The delta document predates the recapture
- GIVEN a delta document naming the fixture rename and every case whose
  stdout embeds the holder path
- WHEN the experiments-seal corpus is re-captured
- THEN the delta document exists before any of the new digests are committed

#### Scenario: Only the named cases move
- GIVEN the delta document's list of affected cases
- WHEN the experiments-seal corpus is re-captured after the rename
- THEN only the cases the delta document names have moved digests; every
  other experiments-seal case is byte-identical to its pre-rename golden

#### Scenario: An unnamed digest movement is caught
- GIVEN a case not listed in the delta document
- WHEN its digest is found to have moved after the rename
- THEN the movement is treated as an undeclared defect, not accepted as part
  of the sanctioned delta

### Requirement: The Proposal Seal's 28 Digests Stay Byte-Identical Under This Change

`tests/seal/`'s 28 sealed digests for `proposal-implementation` MUST remain
byte-identical throughout this change, because `proposal-implementation`
declares the holder filename (`AGREED.md`) it already uses today — a
zero-migration declaration. This is a hard zero-delta gate for this change,
distinct from the experiments-seal delta above: no digest movement here is
sanctioned, at any slice of this change.

#### Scenario: The 28 digests are unaffected by the declared-holder mechanism
- GIVEN this change's full declared-holder, resolution-order, create-on-absent,
  and repair mechanism is shipped
- WHEN `tests/seal/`'s 28-case corpus is re-run and compared to its committed
  goldens
- THEN every digest and exit status is byte-identical

#### Scenario: Any movement in the proposal seal blocks the change
- GIVEN any one of `tests/seal/`'s 28 digests differs from its golden after
  this change
- WHEN the seal comparison runs
- THEN the change does not proceed, and the difference is fixed or reverted —
  never accepted as a new golden, unlike the experiments-seal's declared delta
