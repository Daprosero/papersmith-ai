# implementation-cli-seal Specification

## Purpose

A stdout characterization seal for `proposal-implementation`'s CLI. Captures
byte-exact stdout and exit status for all 20 subcommands against a fixed
corpus, proving preservation across the later profile-driven extraction, and
hosts the two sanctioned behaviour changes (F3, F5) under a declared-delta
discipline. Governs the seal only, not the CLI's existing runtime behavior.

## Requirements

### Requirement: Seal Capture Scope

The seal MUST run all 20 subcommands (20 `cmd_*` functions, 20 `COMMANDS`
entries) against a fixed fixture corpus, invoked through the per-skill
launcher's own entry point — never through the engine module directly, and
never through whichever file `CLI_INVOCATION`/`CLI_PATH` happens to resolve
to internally — capturing raw stdout bytes and exit status, and MUST digest
each.

(Previously: the entry point was implicit in `CLI_INVOCATION`; this
requirement pinned the twenty subcommands but never named the entry point
itself, so a launcher/engine split — introduced by Cut 1 — could silently
seal the wrong file.)

#### Scenario: Every subcommand is captured

- GIVEN the corpus and the 20 registered subcommands
- WHEN capture runs
- THEN each has a digest+exit status, or is in the unsealed set with a reason

#### Scenario: A new subcommand is detected

- GIVEN a 21st subcommand added to `COMMANDS`
- WHEN the coverage check runs
- THEN it fails, naming the uncaptured subcommand

#### Scenario: The sealed entry point is the launcher, not the engine

- GIVEN the engine now lives at
  `_core/implementation/engine/implementation_engine.py`, separate from the
  per-skill launcher
- WHEN the seal invokes any case
- THEN the invoked path is the launcher's literal file, and if `CLI_PATH`
  instead resolved to the engine, the case's digest would move

### Requirement: Corpus Coverage By Construction

The corpus MUST provably exercise: all 14 provenance sites; all 14 findings
sites (populated `tests/findings.py`: `remedy_block`, `adoption`, `uses`,
`introduces`); the 5 hardcoded-path refusals with and without
`IMPLEMENTATION_PROPOSALS`; `Data/` present and absent, crossed with a
document declaring a dataset and a document declaring none (the
declared/undeclared axis); a marker-owned and a hand-authored revision
family; a tie.
(Previously: `Data/` present and absent was a single axis, with no case
distinguishing a declared-dataset document from one declaring none.)

#### Scenario: Coverage is asserted

- GIVEN the corpus
- WHEN a coverage test runs
- THEN it confirms every site above is reached by at least one case,
  including all four combinations of the `Data/`-presence ×
  dataset-declared axis

#### Scenario: A dropped case is caught

- GIVEN a corpus case covering one refusal's `IMPLEMENTATION_PROPOSALS` state
  is removed
- WHEN the coverage test runs
- THEN it fails, naming the uncovered site

#### Scenario: A dropped declared/undeclared case is caught

- GIVEN the corpus case exercising a dataset-declared document with `Data/`
  absent is removed
- WHEN the coverage test runs
- THEN it fails, naming that uncovered combination

### Requirement: Normalization Before Digesting

The seal MUST normalize exactly six sources before digesting —
`_now_iso8601()`, absolute `str(target)`, `CLI_INVOCATION`, `--session` ids,
git shas, `source_digest`/`suite_digest` — each with its own named mutation
test.

#### Scenario: A disabled normalizer reddens

- GIVEN one normalizer is switched off
- WHEN capture is compared to its golden
- THEN it fails, distinguishable from a normalizer never written

#### Scenario: Two immediate captures agree

- GIVEN the corpus run twice in succession
- WHEN both are normalized and digested
- THEN digests match; any differing source is unnormalized, not stored

### Requirement: Digests Committed As Generated Goldens

Digests MUST be committed under `tests/`, not `.gitignore`d, so a seal
captured in one session serves a cut in another.

#### Scenario: Digests survive a clean checkout

- GIVEN a fresh clone at the capturing commit
- WHEN the seal comparison runs with no prior local state
- THEN stored digests are present and readable

### Requirement: Unsealed Commands Are Explicit And Exact

A subcommand whose nondeterminism normalization cannot reach MUST be recorded
in an explicit unsealed set with a reason, not stopping the change. That set
MUST be asserted by an exact-membership test.

#### Scenario: An unrecorded addition is caught

- GIVEN a subcommand added to the unsealed set without updating the test
- WHEN the membership test runs
- THEN it fails

#### Scenario: An unrecorded removal is caught

- GIVEN a subcommand goes from unsealed to sealed (digest added) without
  updating the test
- WHEN the membership test runs
- THEN it fails

### Requirement: Seal Is Mutation-Provable

The comparison MUST detect a single-byte change in any captured output.

#### Scenario: One byte breaks the seal

- GIVEN a stored golden for one subcommand
- WHEN one byte of its captured stdout is mutated and compared
- THEN the comparison goes red

### Requirement: F3 Declared-Delta Discipline

The five refusal messages currently spelling `FORGE_ROOT / 'proposals'` MUST
read via `proposals_root()`. This delta MUST be documented, with before/after
text for all five, in `f3-message-delta.md`, which MUST exist before any
digest is captured. It is the only sanctioned pre/post difference.

#### Scenario: The delta predates the capture

- GIVEN `f3-message-delta.md` with all five before/after pairs
- WHEN the seal is captured
- THEN captured messages match the declared "after" text, and the delta
  document predates the digests

#### Scenario: `cmd_handoff` is unaffected

- GIVEN `cmd_handoff` already omits the path
- WHEN the seal is captured
- THEN its output is unchanged by F3

### Requirement: F5 Zero-Delta Identity Refactor

`PRODUCT_DATA = PRODUCT_DIRS[1]` replacing the bare `"Data"` literal in
`expected_dirs` MUST be applied only after capture, and MUST produce zero
seal delta, since `PRODUCT_DIRS[1] == "Data"`.

#### Scenario: F5 leaves every digest unchanged

- GIVEN a seal captured after F3 but before F5
- WHEN F5 is applied and the seal re-captured
- THEN every digest is byte-identical to the pre-F5 capture


### Requirement: The Required Leaf's One-Line Sibling Cost Is A Declared, Bounded Exception

`proposal-implementation/impl_profile.py` MUST gain exactly one line per
`documents[N]` entry declaring `dataset_marker: None`, and this is the only
sanctioned edit to the sibling's tree under this capability. The bar this
capability is held to is no longer `git diff --name-only … → 0 files` on
that tree; it is that `tests/seal/`'s 28 digests stay byte-identical,
`npm test` stays 595/595, and the Python suite stays `OK (skipped=6)`.

#### Scenario: The one declared line does not move a digest

- GIVEN `proposal-implementation/impl_profile.py` with its `dataset_marker:
  None` line added
- WHEN `tests/seal/`'s 28-case corpus re-runs
- THEN `git diff --exit-code tests/seal/` exits 0

#### Scenario: Every other sibling directory stays at zero files

- GIVEN this capability's complete diff
- WHEN every path under `proposal-implementation/` other than
  `impl_profile.py` is inspected
- THEN none of them appear in the diff

### Requirement: The Second Skill's Own Seal Gains The Dataset-Declared/Undeclared Axis, Read Before Accepted

`tests/experiments_seal/` MUST add cases exercising `documents[0]`'s real
declared dataset marker present and absent in its bound document's bytes,
crossed with `Data/` present and absent. Digests in this corpus MAY move
when this capability's behavior legitimately changes; each moved digest
MUST be read and accepted by hand before being committed, never regenerated
in bulk. `tests/seal/`'s existing 28 digests remain untouched by this
addition.

#### Scenario: A new declared-dataset case is captured and its digest accepted by hand

- GIVEN `documents[0]`'s real dataset marker landed and a corpus case
  exercising `Data/` absent for that same document
- WHEN the second skill's seal is captured
- THEN the new case has a digest, and its content was read before being
  committed

#### Scenario: The sibling's 28 are unaffected by the new axis

- GIVEN the dataset axis added to `tests/experiments_seal/`
- WHEN `git diff --exit-code tests/seal/` runs
- THEN it exits 0

### Requirement: Non-Interference With Sibling Suites

The change MUST NOT alter either existing suite's pass/fail outcome beyond
F3's sanctioned delta. `npm test` MUST remain 595/0. The Python suite's
pinned invariant is `skipped=6` and `OK` (no failures, no errors) — `Ran`'s
total count MAY grow as tests are added by this and later cuts and MUST NOT
be pinned to a fixed number.

(Previously: pinned both `Ran 2849` and `skipped=6`. `Ran` was already stale
at `f4e9960` (`Ran 2874`), so the exact-count pin broke on ordinary test
growth across cuts while `skipped=6` held across all three. This corrects
the spec to the invariant that actually survived measurement.)

#### Scenario: Both baselines hold
- GIVEN the change applied after this capability lands
- WHEN both suites re-run, output redirected to files
- THEN `npm test` shows 595 pass/0 fail and the Python suite shows `OK
  (skipped=6)`, with `Ran` at or above its pre-cut count

#### Scenario: `proposal-deliberation` is untouched
- GIVEN the change is scoped to `proposal-implementation`'s shared engine
- WHEN the change's diff is inspected
- THEN no file under `proposal-deliberation` is modified

#### Scenario: A `skipped` count movement is caught
- GIVEN `skipped=6` is the pinned invariant
- WHEN the Python suite runs after this capability lands
- THEN a `skipped` count other than 6 fails the assertion, distinct from
  `Ran` growing, which is expected and unasserted

#### Scenario: Shipping the second skill moves nothing in the existing 28
- GIVEN `experimental-implementation` is added under `.claude/skills/`
- WHEN `proposal-implementation`'s existing 28-case seal is re-compared to its
  committed goldens
- THEN every digest and exit status is byte-identical to its pre-addition golden

### Requirement: The Per-Document Vocabulary Fold Is Sealed By A Drift-Control Fixture

A committed two-document corpus fixture, where document 0's own claim
vocabulary and text are clean while document 1's own claim vocabulary names
a genuinely drifted module, MUST be captured and proven by real-subprocess
assertion, demonstrating that `fidelityByDocument`'s fold reflects only its
own document's four conditions. The inverse arrangement (document 0 drifted,
document 1 clean) MUST also be captured as the control proving the fold is
not merely reporting document 0's status twice. The existing 28-case corpus
under `tests/seal/` MUST remain untouched by this addition.

(Correction after verify: the original requirement text said "captured and
digested", implying a digest artifact. What was built proves the same
property via real-subprocess assertion in `TwoDocumentDriftControlTests`,
which is the mechanism design.md classifies as Integration. The distinction
matters: a digest proves *these exact bytes did not move*; an assertion
proves *this document's status differs from that one's*. The drift control
needs the assertion: its whole point is that document 0 stays clean while
document 1 drifts, and a digest of that pair would freeze a difference
rather than demonstrate one.)

#### Scenario: A clean document 0 beside a drifted document 1 is proven independent
- GIVEN the drift-control fixture with document 0 clean and document 1
  drifted under its own claim vocabulary
- WHEN the real-subprocess assertion runs
- THEN document 0's fidelity status is unaffected and document 1's reports
  drift, both independently computed

#### Scenario: The inverse control is proven
- GIVEN the same fixture family with document 0 drifted and document 1
  clean under their own vocabularies
- WHEN the real-subprocess assertion runs
- THEN document 0's fidelity status reports drift and document 1's is
  unaffected, both independently computed

#### Scenario: The existing 28 remain untouched
- GIVEN the drift-control fixture added alongside `tests/seal/`
- WHEN `git diff --exit-code tests/seal/` runs
- THEN it exits 0

### Requirement: A Declared Second Document's Own Vocabulary Is Exercised, Not Only Its Directory And Label

At least one sealed two-document case MUST exercise a document declaring
its own per-document `claim_key`/`locus_key`/`remedy_locus_key`/
`notation_keys`/`citation_pattern`, distinct from the other document's, so
the seal proves the declared vocabulary is read and threaded — not merely
that a second `documents` entry with its own directory and label resolves.

#### Scenario: A per-document vocabulary difference is observable in the captured output
- GIVEN a two-document fixture where document 1 declares its own citation
  pattern and notation keys, different from document 0's
- WHEN a case touching a citation or notation payload is captured
- THEN the captured output reflects document 1's own declared values for
  document 1, and document 0's own for document 0

## ADDED Requirements

### Requirement: The Second Skill Ships Its Own Seal, Added Beside The Existing One

`experimental-implementation` MUST have its own committed stdout-characterization
seal, capturing digest and exit status for its own single-document corpus, added
beside `tests/seal/` rather than inside it. The existing 28-case corpus and its
goldens MUST remain untouched by this addition.

#### Scenario: The existing corpus is provably untouched
- GIVEN the second skill's own seal is added
- WHEN `git diff --exit-code tests/seal/` runs
- THEN it exits 0, both before and after the addition

#### Scenario: The second skill's own corpus is captured and digested
- GIVEN `experimental-implementation`'s single-document fixture profile and its own
  corpus
- WHEN its seal is captured
- THEN each case has a digest and exit status, or is in an explicit unsealed set
  with a reason

#### Scenario: A one-byte change in the second skill's seal is caught
- GIVEN a stored golden from the second skill's own seal
- WHEN one byte of its captured stdout is mutated and compared
- THEN the comparison goes red

### Requirement: The Two-Document Branch Is Sealed By Its Own Corpus, Separate From The Existing 28

A fixture profile declaring two documents, exercised against a corpus of its
own, MUST capture byte-exact stdout and exit status for every pair-shaped
branch this change introduces, digested and committed the same way as the
existing 28-case corpus. The existing single-document corpus under
`tests/seal/` MUST remain untouched by this addition — `git diff --exit-code
tests/seal/` MUST exit 0 both before and after the two-document corpus is
added.

#### Scenario: The existing 28 digests are unaffected by the new corpus existing
- GIVEN the two-document corpus added alongside `tests/seal/`
- WHEN `git diff --exit-code tests/seal/` runs
- THEN it exits 0 — no existing digest moved

#### Scenario: A pair-shaped branch is captured and digested
- GIVEN the two-document fixture profile and its corpus
- WHEN the two-document seal is captured
- THEN each pair-shaped case has a digest and exit status, or is in an
  explicit unsealed set with a reason

#### Scenario: A one-byte change in a pair-shaped case is caught
- GIVEN a stored two-document golden
- WHEN one byte of its captured stdout is mutated and compared
- THEN the comparison goes red

### Requirement: `compose` And `admit` Leave The Unsealed Set

Once `implementation-block-locator` resolves correctly for a document
declaring `\tag{}`-shaped entries (this domain's `documents[1]`, the
mathematical proposal), `compose` and `admit` MUST be removed from
`tests/experiments_seal/unsealed.json` and become sealed cases with their
own digests — their prior exclusion (`design.md D8/D11`: "this domain does
not build a locator for the shape it does not have") no longer holds once
a locator is declared.

#### Scenario: `compose` and `admit` are no longer in the unsealed set
- GIVEN this capability landed
- WHEN `tests/experiments_seal/unsealed.json` is read
- THEN it contains neither `compose` nor `admit`

#### Scenario: Both have digests like every other sealed command
- GIVEN the second skill's seal is recaptured
- WHEN `compose`'s and `admit`'s cases run
- THEN each has a digest and exit status, not an unsealed-set entry

### Requirement: Every Digest That Moves When The Locator Starts Matching Is Individually Read Before Acceptance

`verify-a`/`verify-b` were previously sealed against a locator (`TAG_RE`)
that matched nothing in this domain's document, so every declared locus
read as `unknown_loci`. Once the locator resolves correctly, these
digests — and any other case whose output changes because loci now
resolve — MUST be recaptured, and each moved digest MUST be read and
defended by hand in the verify report before being committed, mirroring
the discipline already exercised on 6 of 20 cases moved by a prior slice.
Bulk regeneration without individual review MUST NOT be treated as
acceptance.

#### Scenario: A moved digest is named and its content read
- GIVEN `verify-a`/`verify-b` move because the locator now finds real
  tags instead of reporting every locus as unknown
- WHEN the verify report is written
- THEN it names each moved case and states what the new output shows,
  before the new digest is committed

#### Scenario: A digest regenerated without individual review is caught
- GIVEN a bulk regeneration that updates every digest without any moved
  case being named or read
- WHEN the verify report is checked against the moved-digest list
- THEN the gap is caught — a moved digest with no accompanying reading is
  not an accepted seal

### Requirement: The Crossing Check's Refusals Are Added As Their Own Sealed Cases

`implementation-cross-document-agreement`'s two refusal kinds, the
no-crossing-declared refusal, and the per-discrepancy acknowledgment MUST
each be exercised by at least one case in the second skill's seal,
digested and committed the same way as every other sealed case.

#### Scenario: Each new refusal kind has a sealed case
- GIVEN the crossing check's refusal kinds
- WHEN the second skill's seal is captured
- THEN each kind has at least one case with its own digest
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
