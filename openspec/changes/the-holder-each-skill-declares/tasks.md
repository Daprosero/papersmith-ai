# Tasks: The Holder Each Skill Declares

## Resolved TDD Mode

**Mode: ON** — `openspec/config.yaml:1` declares `strict_tdd: true`; `rules.apply.test_command`
and `rules.verify.test_command` both name `npm run test:all` (`:18,:20`), which runs
`npm run test:node && npm run test:py` (Node `node --test` + `.venv/bin/python -m pytest`).
Source: `openspec/config.yaml` (project configuration), not invented. Every production
task below is preceded by its own RED test task; GREEN and REFACTOR are separate steps.
Use `.venv/bin/python`, never a bare `python3.12` (yields ~29 environmental failures).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~800–1090 (per proposal.md's five-slice forecast) |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Suggested split | Single PR — maintainer-approved `size:exception`, tolerance ~1600 authored lines |
| Delivery strategy | exception-ok |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

The proposal's five slices (declaration → resolution+seal-rename → create-on-absent →
repair → references) are preserved below as the **ordering** of Phases 1–5 only. They are
not PR boundaries — this change ships as one unsplit PR under the accepted `size:exception`,
per `design.md`'s "Migration / Rollout" section.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|------------------|--------------------|
| 1 | Declared holder leaf (Phase 1) | PR 1 | `.venv/bin/python -m pytest tests/test_implementation_profile.py tests/test_experimental_implementation.py tests/test_implementation_domain_mutation.py -k holder -v` | `npm run test:all` (full suite must stay green) | `git revert` the slice commit; leaf becomes unread then unrequired, by-shape resolution untouched |
| 2 | Resolution order + doctrine + experiments-seal rename (Phase 2) | PR 1 | `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k "holder_resolution or HOLDER_UNDECLARED" -v` | `.venv/bin/python -m pytest tests/test_implementation_seal.py tests/test_experiments_seal.py` | `git revert` restores `POSITION_HOLDER_ABSENT`/`SETTLE_HOLDER_ABSENT`; a holder already created survives, picked up again by-shape once it holds an item |
| 3 | Create-on-absent + declared-identity independence (Phase 3) | PR 1 | `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k create_on_absent -v` | `.venv/bin/python -m pytest tests/test_implementation_seal.py -x` (zero-delta) | `git revert`; no target is left with a forked checklist since creation only ever writes the declared name |
| 4 | D4 repair path (`position --repair-header`) (Phase 4) | PR 1 | `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k repair -v` | `.venv/bin/python -m pytest tests/test_implementation_seal.py -x` (zero-delta) | repair never edits without a human decision; `git revert` leaves at most human-authorized repairs, which live in the target repo's own history |
| 5 | `references/usage.md` + both `SKILL.md` (Phase 5) | PR 1 | manual doc cross-check (5.3) | N/A — documentation-only, no executable scenario | `git revert`; depends only on Phase 1, independently removable |

## Phase 1: The Declared Holder Leaf (Slice 1 — behaviour-free)

Spec: `implementation-declared-holder` — "The Declared Holder Is A Required PROFILE Leaf",
"The Declared Holder Leaf Carries A Heading Scaffold".

- [x] 1.1 **(BLOCKING — nothing else in this change can run before this)** Add the
      `"holder": {"filename": ..., "headings": (...), "scaffold": ...}` section to every
      test-synthesized profile, before the requirement that would enforce it exists:
      `tests/test_implementation_profile.py` (`_cut2_profile` `:556-614`, `_CUT2_LEAVES`
      `:477-508` gains 3 entries, `_without_leaf` `:638-654` handles them via plain
      `section.key` removal — no indexed branch needed), `tests/test_experimental_implementation.py`
      (`_to_source` profile builders `:162`, `:220`, `:438`), `tests/test_implementation_domain_mutation.py`
      (inline `PROFILE = {` fixture `:652`), `tests/fixtures/two_documents/impl_profile.py`.
      Acceptance: every synthesized/fixture profile now carries the section (any legal
      placeholder filename, e.g. `Fixture_AGREED.md`, is acceptable here). Verification:
      `.venv/bin/python -m pytest tests/test_implementation_profile.py tests/test_experimental_implementation.py tests/test_implementation_domain_mutation.py -x`
      (must stay exactly as green as before — no requirement enforces the leaf yet).
- [x] 1.2 RED: write failing tests for the required-leaf refusal (omitting `holder.filename` /
      `holder.headings` / `holder.scaffold` each raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE`
      naming that exact dotted leaf, via the existing per-leaf walk pattern at
      `tests/test_implementation_profile.py:681-690`); the scaffold-heading agreement shape
      tier (a `headings` entry absent from `scaffold`; one present only inside a fenced
      region; one present only as a substring — each must raise
      `IMPLEMENTATION_DOMAIN_PROFILE_INVALID_HOLDER` naming the offending entry); and the
      threat-matrix row-1 adversarial filenames as one `subTest` each: `../x.md`, `/etc/x.md`,
      `a/b.md`, `""`, `"."`, `".."`, `"x.md\n"`, `"AGREED\x00.md"`, `"x.sh"`, `"AGREED"` (no
      suffix) — each must raise `IMPLEMENTATION_DOMAIN_PROFILE_INVALID_HOLDER`. Verification:
      `.venv/bin/python -m pytest tests/test_implementation_profile.py -k holder -v` (expect
      failures — confirms RED).
- [x] 1.3 GREEN: `skills/_core/implementation/impl_domain_profile.py:67-90` — append
      `("holder", "filename")`, `("holder", "headings")`, `("holder", "scaffold")` to
      `_REQUIRED_PRESENCE`. Do **not** use `_REQUIRED_NESTED` (`:59`) — its
      `..._UNSAFE_PATH` check (`:483-485`) demands absolute-and-existing, the inverse of a
      relative, usually non-existent holder filename. Presence is validated by the existing
      loop `:238-241`. Acceptance: 1.2's presence-refusal RED tests now GREEN. Verification:
      `.venv/bin/python -m pytest tests/test_implementation_profile.py -k holder -v`.
- [x] 1.4 GREEN: `skills/_core/implementation/impl_domain_profile.py` — new shape tier after
      the presence loop, refusing `IMPLEMENTATION_DOMAIN_PROFILE_INVALID_HOLDER` (joins
      `..._INVALID_CITATION_PATTERN` `:358-366`, `..._INVALID_BLOCK_LOCATOR` `:384-410`,
      `..._INVALID_CROSS_CITATION_PATTERN` `:433-442`). Four checks (D4): (1) `filename` is
      exactly one path component — non-empty, no `/` or `\`, not `.`/`..`, no NUL, no
      newline, `Path(filename).name == filename`; (2) `filename` ends `.md`; (3) `headings`
      is a non-empty sequence of `str`; (4) every `headings` entry occurs in `scaffold` as a
      full line, stripped-equal, outside a fenced region — `locate_headings`' own matching
      rule (`impl_position.py:366-389`). Note: `ImplementationProfileError` is not `Refused`
      (`impl_domain_profile.py:20-25`) — this refusal is invisible to `reachable_refusal_codes()`
      and does **not** move the pinned count. Acceptance: 1.2's shape/threat-matrix RED tests
      now GREEN. Verification: `.venv/bin/python -m pytest tests/test_implementation_profile.py -k "holder or INVALID_HOLDER" -v`.
- [x] 1.5 GREEN: `skills/proposal-implementation/impl_profile.py` — declare
      `"holder": {"filename": "AGREED.md", "headings": ("# Agreed", "## Ladder"), "scaffold": "# Agreed\n\n## Ladder\n"}`.
      Zero behavioural delta — this is the name already in use by the live target and by
      `tests/seal/corpus.py:272`. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -x` (must stay fully
      green, no new failures).
- [x] 1.6 GREEN: `skills/experimental-implementation/impl_profile.py` — declare
      `"holder": {"filename": "Experimental_AGREED.md", "headings": ("# Agreed", "## Ladder"), "scaffold": "# Agreed\n\n## Ladder\n"}`.
      Verification: `.venv/bin/python -m pytest tests/test_experimental_implementation.py -x`.
- [x] 1.7 Seal gate (D11 step 1) — both seals green, **no recapture of either**. Verification:
      `.venv/bin/python -m pytest tests/test_implementation_seal.py tests/test_experiments_seal.py`.
      Acceptance: both green; `git diff --stat tests/seal/digests.json tests/experiments_seal/digests.json`
      is empty. Neither seal's fingerprint covers `impl_profile.py`, so this step cannot move
      either digest set — confirm by diff, not by assumption.
- [x] 1.8 Full-suite gate for Phase 1. Verification: `npm run test:all`. Acceptance: green
      except these **named, pre-existing, dated 2026-09-24** environmental failures (do not
      chase): `test_forge_gate::GateInterpreterTests` ×3, `test_papersmith_kit::KitTests` ×3,
      `test_papersmith_bridges::BridgesTests::test_run_script_forwards_list_argv_and_environment`,
      `test_papersmith_executor::ExecutorTests::test_local_profile_runs_and_records_success`,
      `test_paper_writing::GroundingThresholdObligationTests`,
      `test_papersmith_yamllite::test_repo_papersmith_yaml_parses`,
      `test_proposal_implementation::ForgeVocabularyDerivedGuardTests::test_rule_b_finds_no_target_vocabulary_in_the_forge`.

## Phase 2: Resolution Order, Doctrine, Refusal Codes, Experiments-Seal Rename (Slice 2)

Spec: `implementation-declared-holder` (resolution/write-refusal/doctrine requirements),
`implementation-holder-repair` ("The Document-Count Comparison Is A Named, Shared
Predicate"), `implementation-engine-neutrality`, `implementation-cli-seal`.

- [x] 2.1 RED: one test per `holder_resolution`'s 5 `action` outcomes, from a built product
      folder: declared file exists → `"declared"`; declared absent + no by-shape candidate +
      `product.is_dir()` → `"create"`; declared absent + no candidate + not
      `product.is_dir()` → `"absent"`; declared absent + `byShape >= 1` → `"undeclared"`; more
      than one candidate for the caller's own question → `"ambiguous"`. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k holder_resolution -v`
      (expect failure — function does not exist yet, RED).
- [x] 2.2 GREEN: `skills/_core/implementation/engine/implementation_engine.py` — implement
      `holder_resolution(target: Path, name: str) -> dict`, placed immediately after
      `agreements_state` (after `:510`). Total, never-raising, uniform key set on every
      branch: `{"declared": str, "path": Path|None, "byShape": list[str], "read": Path|None,
      "write": Path|None, "create": bool, "action": str}`. `agreements_state`'s own **code**
      is not touched — only its docstring (task 2.11). Add `HOLDER_FILENAME`,
      `HOLDER_HEADINGS`, `HOLDER_SCAFFOLD` module-level constants beside `DOCUMENTS`
      (`:176`). Declared-name identity (D3): `(product / HOLDER_FILENAME).is_file()` —
      nothing else examined. A declared name absent from disk MUST return `path: None`
      (load-bearing for `tests/seal/`'s `verify-t` case, `corpus.py:283-295`). Acceptance:
      2.1's 5 RED tests now GREEN. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k holder_resolution -v`.
- [x] 2.3 RED: `_header_document_count_detail` asymmetry, asserted in **both** directions so a
      symmetric "fix" reddens this test — group-present-under-1-document-profile returns a
      detail string; group-absent-under-2-document-profile (the deliberate silent migration,
      `:12116-12125`) returns `None`. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k header_document_count_detail -v`
      (RED — function does not exist yet).
- [x] 2.4 GREEN: `implementation_engine.py` — extract `_header_document_count_detail(block: dict) -> str | None`,
      placed beside `_bound_to` (`:538-551`). Encodes exactly today's condition —
      `block.get("documents") is not None and len(DOCUMENTS) <= 1` — and nothing more.
      Repoint `cmd_position`'s inline check at `:12126` to call this helper instead of
      re-deriving the comparison. Acceptance: 2.3 GREEN;
      `POSITION_HEADER_DOCUMENT_COUNT_MISMATCH` still fires exactly as today (spec:
      "The existing check is unaffected by the extraction"). Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k "header_document_count_detail or HEADER_DOCUMENT_COUNT_MISMATCH" -v`.
- [x] 2.5 GREEN: repoint `position_state` (`:648-660`) to read through `holder_resolution`'s
      read path (declared-first, by-shape fallback). Code repoint only — doctrine text moves
      in 2.12 (B1). Acceptance: an arbitrarily-named existing checklist (e.g. `TASKS.md`) is
      still found and read (spec: "Read Falls Back To The By-Shape Scan"). Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k position_state -v`.
- [x] 2.6 RED: the D3 middle row — no file matches the declared filename, an item-holding
      `TASKS.md` exists → a write (`position` and `settle`, one test each) refuses with the
      new `HOLDER_UNDECLARED`, naming both exits (rename `TASKS.md` to the declared name, or
      declare `TASKS.md`'s own name in `PROFILE["holder"]["filename"]`); no write lands in
      `TASKS.md`. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k HOLDER_UNDECLARED -v`
      (RED — code not yet raised).
- [x] 2.7 GREEN: repoint `_chosen_holder` (`:11830-11856`) to dispatch on
      `holder_resolution(target, name)["action"]`: `"declared"`/`"create"` resolve directly;
      `"undeclared"` raises `HOLDER_UNDECLARED` (`WORK_STATE`) naming both exits;
      `"absent"` narrows `POSITION_HOLDER_ABSENT` to "no product folder" only (D9);
      `"ambiguous"` keeps existing `POSITION_HOLDER_AMBIGUOUS`. Repoint the docstring's stale
      cross-reference ("`:11839-11840`, lines 140-145") at `agreements_state`'s real doctrine
      lines and at `holder_resolution`. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k "chosen_holder or HOLDER_UNDECLARED or HOLDER_ABSENT" -v`.
- [x] 2.8 GREEN: repoint `cmd_position`'s holder sweep (`:12090-12142`) — declared-name lookup
      runs ahead of the `*.md` glob (the glob itself survives: `holder_digests` still needs a
      pre-image per candidate, `:12095-12108`, a different requirement from choosing a
      holder). Write path raises `HOLDER_UNDECLARED` for `"undeclared"`; narrows
      `POSITION_HOLDER_ABSENT` to "no product dir". Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k "cmd_position and (HOLDER_UNDECLARED or HOLDER_ABSENT)" -v`.
- [x] 2.9 GREEN: repoint `cmd_settle` (`:14368-14373`, `:14380-14398`, `:14552-14570`) per
      D10 — all five `settle` modes (create, `--attach`, `--remove`, `--reverse`, `--done`)
      resolve through `holder_resolution` and search exactly `[resolution["write"]]`. Narrow
      `SETTLE_HOLDER_ABSENT` to "no product dir"; new `HOLDER_UNDECLARED` for the undeclared
      case. Re-author `SETTLE_TEXT_AMBIGUOUS` (`:14392-14397`) and `SETTLE_HEADING_AMBIGUOUS`
      (`:14564-14569`) messages for a single holder (drop the "across N holder(s)"
      interpolation — both are now reachable only from duplicates *within* one file).
      Acceptance: 2.6's `settle` RED test now GREEN; also add and pass a test proving the
      stated cost of D10: on a target adopted with `TASKS.md`, `settle --done` can no longer
      tick an existing item (refuses `HOLDER_UNDECLARED`). Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k settle -v`.
- [x] 2.10 GREEN: `GATING_REFUSALS` (`:18402-18521`) — classify `HOLDER_UNDECLARED` as
      `WORK_STATE`. Question/command table (`:19274-19347`) — add `HOLDER_UNDECLARED`'s
      question naming both exits; re-author A5 (`SETTLE_HOLDER_ABSENT`, `:19284-19287`) and
      A6 (`POSITION_HOLDER_ABSENT`, `:19334-19337`) for the narrowed "no product folder"
      case — neither is retired. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k "refusal_question or GATING_REFUSALS" -v`.
- [x] 2.11 Doctrine amendments — A-series (D12 table). A1 `agreements_state` root doctrine
      (`:381-385`): **narrowed** — keep "found by shape, never by name" verbatim as the READ
      rule with its stated reason; add one paragraph that the declared name owns WRITES and
      the engine invents no filename because it holds none. A2 `_chosen_holder` docstring
      (`:11839-11848`): **amended (behaviour)** — narrowed to "no product folder to create a
      holder in"; stale cross-reference repointed (done in 2.7). A3 `cmd_settle` docstring
      (`:14369-14373`): **amended (behaviour)** — "settle writes only into the holder this
      skill declares, and creates that one when the product folder holds none." A4
      `cmd_settle` docstring item 12 (`:14149-14154`): **amended (prose)**, same commit as A3
      (it cites "the same doctrine `_chosen_holder` already states"). A5/A6: cross-check the
      question text landed in 2.10 matches this verdict. A7
      `tests/test_implementation_pair.py:477-485`: **amended** — the comment claiming "an
      empty product dir refuses `POSITION_HOLDER_ABSENT` before the install below ever gets
      to write anything" is false after D5; edited in detail at task 2.20. Verification:
      `.venv/bin/python -m pytest tests/test_implementation_pair.py -v`; manual read of each
      doctrine site against the D12 table in `design.md`.
- [x] 2.12 Doctrine amendments — B-series + literal-filename prose sweep. B1 `position_state`
      comment (`:644-646`): **narrowed**, gains a pointer to the declared-name write rule. B2
      `cmd_position` sweep comment (`:12090-12092`): **amended** — the sweep gains the
      declared lookup ahead of the glob. B3 `cmd_position` docstring (`:12036-12041`):
      **amended** — the sentence describing the changed mechanism. Prose sweep: amend the 7
      code-context `AGREED.md` mentions in `implementation_engine.py` to name the declared
      leaf instead (`:575`, `:2388`, `:12005`, `:18501`, `:18946`, `:18986`, `:18992` — the 4
      fact-assertions plus 3 engine-voice namings). **Leave standing** the 9 dated/target-specific
      mentions (`:304`, `:11083`, `:13892`, `:15746`, `:18866`, `:18916` in
      `implementation_engine.py`; `:20`, `:270`, `:1139` in `impl_position.py` — that file
      gets **no functional edit**, per `design.md`'s File Changes table). Amend the 2
      template-string sites (`:4887`, `:5029` — bytes written into a target's `__init__.py`,
      not docstrings); re-run both seals immediately after this specific edit, before
      committing it (measurement, not assumption). Verification: `grep -n "AGREED"
      skills/_core/implementation/engine/implementation_engine.py
      skills/_core/implementation/impl_position.py` — confirm the amend/leave-standing split
      matches the 7/9/2 counts named above; `.venv/bin/python -m pytest
      tests/test_implementation_seal.py -x` immediately after the `:4887`/`:5029` edit.
- [x] 2.13 RED: collision reproduction — run the experimental profile against a target
      already holding the proposal's declared `AGREED.md`; assert the experimental write can
      no longer land a `documents=` group into it. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k collision -v`
      (expect RED before 2.7–2.9 land; re-run after — expect GREEN, confirming the measured
      defect is now reproduced and closed as a test).
- [x] 2.14 Mutation tests — reachability proof for `HOLDER_UNDECLARED` and for the
      declared-name lookup itself. (a) Invert the write-refusal guard; the mutated build must
      write into the undeclared candidate, proving the restored guard is what prevents it.
      (b) Delete the declared-name lookup at exactly **one** of the five repointed sites
      (2.5, 2.7, 2.8, 2.9) and assert a cross-site comparison test reddens — the
      `implementation-block-locator` precedent this design cites. Beware the same-size
      `.pyc` trap: assert the mutated anchor count, never `git diff --stat`. Verification:
      manual guard-invert + targeted `.venv/bin/python -m pytest` re-run per mutated site.
- [x] 2.15 `tests/experiments_seal/corpus.py:344` — rename `Trial/AGREED.md` to
      `Trial/Experimental_AGREED.md`. **This MUST land in the same commit as tasks 2.1–2.14**
      (D11 step 2) — landing the resolution alone makes every experiments-seal write case
      refuse `HOLDER_UNDECLARED` against its own now-undeclared fixture name, producing an
      intermediate digest set nobody wants captured. Verification: `git diff --stat` confirms
      this edit is part of the same commit as tasks 2.1–2.14's diff.
- [x] 2.16 D11 step 3 — at the state after 2.15 lands (**unrecaptured**), run
      `.venv/bin/python -m pytest tests/test_experiments_seal.py`. Record the exact failing
      case IDs plus the fingerprint failure into a delta document (per
      `implementation-cli-seal`'s "The Experiments-Seal Holder Rename Is A Declared,
      Sanctioned Digest Delta" — the delta document MUST predate the recapture, naming every
      case whose stdout embeds the holder path: `position_state`'s `"holder"` key;
      `cmd_position`/`cmd_settle`'s printed sites at `:12376`/`:12404`/`:12411`,
      `:14610`/`:14615`). Verification:
      `.venv/bin/python -m pytest tests/test_experiments_seal.py -v` (capture output to the
      scratchpad, e.g. `/private/tmp/claude-501/.../scratchpad/experiments-seal-pre-recapture.txt`);
      the delta document lists exactly these case IDs.
- [x] 2.17 D11 step 4 — the zero-delta gate on the **proposal** seal, at the same unrecaptured
      state, and **at every subsequent commit through the end of Phase 5** — never run only
      once at the end. Verification: `.venv/bin/python -m pytest tests/test_implementation_seal.py -x`
      — MUST be green; `git diff --stat tests/seal/digests.json` MUST be empty.
- [x] 2.18 **PROHIBITION — standing for the remainder of this change (Phases 2 through 6):
      `tests/seal_capture.py` MUST NOT be run at any point.** It is the only mechanism that
      could silently absorb a proposal-side (`tests/seal/`) digest movement; its own docstring
      says it is invoked by hand "only when the roster or the sealed behaviour has genuinely
      changed" — neither has, for `tests/seal/`. Acceptance: no shell history, script, or task
      in this change invokes `tests/seal_capture.py`; `tests/seal/digests.json` is never
      regenerated. (`tests/experiments_seal_capture.py` at task 2.19 is the distinct,
      permitted script — do not confuse the two.) Verification: review shell history / task
      log for this change confirms `tests/seal_capture.py` was never invoked.
- [x] 2.19 D11 step 5 — recapture the **experiments** seal only. Verification:
      `.venv/bin/python tests/experiments_seal_capture.py`; `git diff --stat
      tests/experiments_seal/digests.json` non-empty (expected); `git diff --stat
      tests/seal/digests.json` stays empty.
- [x] 2.20 D11 step 6 — assert the recaptured moved set equals the list recorded in 2.16. Add
      a new test in `tests/test_experiments_seal.py`: every case whose output carries a
      holder path carries `Trial/Experimental_AGREED.md` and never `Trial/AGREED.md` (turns
      "the digests moved" into a checked claim, not an unexplained fact). Verification:
      `.venv/bin/python -m pytest tests/test_experiments_seal.py -x` (green, post-recapture).
- [x] 2.21 Update `tests/test_proposal_implementation.py`'s 6 `*_HOLDER_ABSENT` assertion
      sites (`:20061`, `:22968`, `:23510`, `:23756`, `:24008`, `:24281`) — each moves to the
      narrow "no product folder" case, or is repointed to assert `HOLDER_UNDECLARED`, per
      which condition each fixture actually now exercises. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -x`.
- [x] 2.22 `tests/test_implementation_pair.py:477-485` (A7) — amend the comment per 2.11's
      verdict, and move the fixture's pre-written checklist from `AGREED.md` to
      `Experimental_AGREED.md` (it encodes the two-document/experimental profile's collision
      case). Verification: `.venv/bin/python -m pytest tests/test_implementation_pair.py -x`.
- [x] 2.23 Update the 2 `AGREED` references in `tests/test_implementation_core.py`.
      Verification: `.venv/bin/python -m pytest tests/test_implementation_core.py -x`.
- [x] 2.24 Re-measure the pinned reachable-refusal-code count (interim, this phase adds
      `HOLDER_UNDECLARED` only — Phase 4 adds 2 more). Run `reachable_refusal_codes()`'s
      derivation against the shipped engine; rename
      `test_the_derivation_finds_the_measured_one_hundred_and_thirteen`
      (`tests/test_proposal_implementation.py:32285-32309`, currently five generations stale
      — it actually pins 118, not 113) to the number this run **actually measures at this
      point**, and update the pinned assertion at `:32324` to that observed number — **never**
      to a predicted number. Update `test_the_roster_classifies_every_reachable_code`
      (`:32242-32247`) to classify `HOLDER_UNDECLARED`. This pin is re-measured again at task
      4.11 once the two D4 codes land. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k "reachable_refusal_codes or roster" -v`.
- [x] 2.25 Full-suite + zero-delta seal gate for Phase 2. Verification: `npm run test:all`;
      `.venv/bin/python -m pytest tests/test_implementation_seal.py -x` (zero-delta, still
      green); `.venv/bin/python -m pytest tests/test_experiments_seal.py -x` (green,
      post-recapture). Acceptance: only the environmental failures named at 1.8 remain;
      `tests/seal/digests.json` unchanged since 1.7; `tests/experiments_seal/digests.json`
      reflects exactly the 2.20-verified delta and nothing else.

## Phase 3: Create-On-Absent + Declared-Name Identity (Slice 3)

Spec: `implementation-declared-holder` — "Create-On-Absent When No Candidate Exists",
"Declared-Name Identity Is Independent Of The Item-Holding Test",
"`SETTLE_HEADING_ABSENT` Still Fires For A Heading The Declaration Does Not Carry".

- [x] 3.1 RED: the High-risk creation test — declared absent, no candidate, product dir
      exists → after a write, the declared holder file is created with **exactly**
      `HOLDER_SCAFFOLD` bytes and zero checklist items, then **read back** through **both**
      `_chosen_holder` and `cmd_settle` without any absence refusal. Byte-equality assertion,
      not `assertIn`. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k create_on_absent -v`
      (RED — creation not implemented yet).
- [x] 3.2 GREEN: implement D5 in `implementation_engine.py` — when `action == "create"`, write
      `HOLDER_SCAFFOLD` to `resolution["write"]` via
      `impl_position.write_spliced(path, scaffold_bytes, expect_digest=impl_position.digest_bytes(b""))`
      **before** any block or item splice. Creation gated on `product.is_dir()` only — the
      engine **never** calls `mkdir` on `<name>/` (this belongs to `materialize`/`structure`;
      see `require_named_product_dir`, `:2760-2779`). Acceptance: 3.1 GREEN. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k create_on_absent -v`.
- [x] 3.3 RED: creation-refused — declared absent, no candidate, product dir **absent** → the
      narrowed `POSITION_HOLDER_ABSENT`/`SETTLE_HOLDER_ABSENT` fire (not create), and nothing
      is written to disk. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k create_refused -v`.
- [x] 3.4 GREEN: confirm/wire the `"absent"` action path (should already follow from 2.7/2.9's
      dispatch plus 3.2's `is_dir()` gate — add any missing wiring only if 3.3 does not pass
      immediately). Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k create_refused -v`
      (GREEN).
- [x] 3.5 RED: declared-name identity independent of the item-holding test (High-risk item
      5) — a freshly created, item-less declared holder appears in `agreements_state`'s
      `holders` list; `_chosen_holder` resolves it without raising absence; `cmd_settle`
      writes into it rather than raising `SETTLE_HOLDER_ABSENT`. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k declared_identity -v`
      (RED).
- [x] 3.6 GREEN: confirm/wire D3's identity rule. `holder_resolution`'s `"path"` key is
      populated by `(product / HOLDER_FILENAME).is_file()` alone, independent of
      `agreements_state`'s item-holding `holders` scan (which stays exactly as it is — its
      code is not touched, per D2). If 3.5 is still RED after 3.2, the gap is in a consumer
      not yet reading `holder_resolution`'s `"path"`/`"write"` keys — wire it there, never
      into `agreements_state`. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k declared_identity -v`
      (GREEN).
- [x] 3.7 RED then GREEN: heading-doctrine proof — after a create, `settle --under "## Ladder"`
      succeeds; `settle --under "## Nope"` still refuses `SETTLE_HEADING_ABSENT` with the
      same question it asks today (unamended). Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k SETTLE_HEADING_ABSENT -v`.
- [x] 3.8 Mutation tests — reachability proof. (a) Invert D5's `is_dir()` creation gate; the
      mutated build must then attempt a write outside an existing product dir — assert this
      is caught. (b) Invert `SETTLE_HEADING_ABSENT`'s guard; the mutated build writes under
      the undeclared heading, proving the restored guard is what prevents it. Assert the
      mutated anchor count, never `git diff --stat`. Verification: manual guard-invert +
      targeted `.venv/bin/python -m pytest` re-run per mutation.
- [x] 3.9 Full-suite + zero-delta seal gate for Phase 3. Verification: `npm run test:all`;
      `.venv/bin/python -m pytest tests/test_implementation_seal.py -x` (still zero-delta
      green).

## Phase 4: D4 Repair Path — `position --repair-header` (Slice 4)

Spec: `implementation-holder-repair` — all requirements.

- [x] 4.1 RED: `POSITION_REPAIR_CONFLICT` mutual exclusivity — `--repair-header` combined with
      any of `--sequence`, `--reconcile`, `--replace` refuses `POSITION_REPAIR_CONFLICT`
      (`INVOCATION_DEFECT`), same shape as `POSITION_SEQUENCE_AND_RECONCILE`
      (`:12070-12075`). Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k POSITION_REPAIR_CONFLICT -v`
      (RED).
- [x] 4.2 GREEN: add the `--repair-header` flag and its mutual-exclusivity guard to
      `cmd_position`'s argparse in `implementation_engine.py`. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k POSITION_REPAIR_CONFLICT -v`
      (GREEN).
- [x] 4.3 Confirm the repair-decision path calls the **same** `_header_document_count_detail`
      helper from task 2.4, never a re-derived comparison (spec: "The repair path uses the
      same helper, not a re-derived expression"). Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k "repair and header_document_count_detail" -v`.
- [x] 4.4 RED: D7 unambiguous-repair case — a poisoned target where every `documents=` entry
      either carries no `revision`, or carries a `label` the current profile does not
      declare → repair proceeds: header re-rendered **without** the `documents=` group,
      `revision`/`revisionSha256`/`derivedAt`/`session`/`target` unchanged, block body
      byte-identical. Byte-compare before/after. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k repair_unambiguous -v`
      (RED).
- [x] 4.5 GREEN: implement D7's repair branch in `cmd_position`'s `--repair-header` handling.
      Preconditions (**all four** must hold, else fall through to 4.8's ambiguous refusal):
      (1) `holder_resolution`'s `action == "declared"`; (2)
      `impl_position.locate_block(data, allow_legacy=True)` returns a block rather than
      raising; (3) `_header_document_count_detail(block)` is not `None`; (4) every
      `block["documents"]` entry either carries no `revision`, or carries a `label` this
      profile's `DOCUMENTS` does not declare. Repair = re-render via the existing `render()`
      path with the `documents=` key omitted (already byte-for-byte identical to
      pre-Cut-3 output, `impl_position.py:1106-1115`). Acceptance: 4.4 GREEN. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k repair_unambiguous -v`.
- [x] 4.6 RED: D7 unambiguous create-new case — a poisoned target where the evidence
      unambiguously supports creating this skill's own separate declared holder instead of
      touching the existing one → this skill's declared holder is created, the existing
      poisoned holder is left untouched. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k repair_create_new -v`
      (RED).
- [x] 4.7 GREEN: wire the create-new branch under `--repair-header`, reusing task 3.2's
      creation path when `action == "create"` for this target. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k repair_create_new -v`
      (GREEN).
- [x] 4.8 RED: D7 ambiguous cases (3 sub-cases), each → `HOLDER_REPAIR_AMBIGUOUS`, nothing
      written: (a) an entry carries a non-empty `revision` for a label this profile **does**
      declare; (b) `block["legacy"]` is true (`target` is `None`, `impl_position.py:241`);
      (c) more than one `*.md` carries a block — assert `POSITION_HOLDER_AMBIGUOUS` still
      fires and repair never runs (it must not become a second answer to that code).
      Verification: `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k repair_ambiguous -v`
      (RED).
- [x] 4.9 GREEN: implement `HOLDER_REPAIR_AMBIGUOUS` (`WORK_STATE`) — message names the
      decoded group entries, which labels this profile declares, and asks whether this
      header's recorded binding still means something under this profile (repair by dropping
      the group, or give this target its own declared holder). Add `HOLDER_REPAIR_AMBIGUOUS`
      and `POSITION_REPAIR_CONFLICT` to `GATING_REFUSALS` (`:18402-18521`) and the
      question/command table (`:19274-19347`). Acceptance: 4.8 GREEN. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k repair_ambiguous -v`.
- [x] 4.10 Mutation test — D7's ambiguity-detection guard reachability. Invert the ambiguity
      guard; the mutated build must pick an action (repair or create) instead of stopping,
      proving the restored guard is what forces the stop. Assert the mutated anchor count,
      never `git diff --stat`. Verification: manual guard-invert + targeted
      `.venv/bin/python -m pytest` re-run.
- [x] 4.11 Final re-measurement of the pinned reachable-refusal-code count. After
      `HOLDER_REPAIR_AMBIGUOUS` and `POSITION_REPAIR_CONFLICT` land (verify against source
      whether `INVOCATION_DEFECT` classification is walked by `reachable_refusal_codes()` —
      do not assume), run the derivation again and update the pin from task 2.24's interim
      value to this final measured number (predicted 118 + 3 − 0 = 121, but the assertion
      value MUST be the observed output of the run, never the prediction). Update
      `test_the_roster_classifies_every_reachable_code` to classify all 3 new codes total
      (`HOLDER_UNDECLARED`, `HOLDER_REPAIR_AMBIGUOUS`, `POSITION_REPAIR_CONFLICT`).
      Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k "reachable_refusal_codes or roster" -v`.
- [x] 4.12 Full-suite + zero-delta seal gate for Phase 4. Verification: `npm run test:all`;
      `.venv/bin/python -m pytest tests/test_implementation_seal.py -x` (zero-delta, still
      green).

## Phase 5: `experimental-implementation`'s Structural Gap (Slice 5 — depends only on Phase 1)

Spec: `experimental-implementation-skill` — "The Skill Ships `references/usage.md`
Documenting Its Holder Obligations".

- [x] 5.1 Create `skills/experimental-implementation/references/usage.md` (no
      `references/` directory exists today for this skill). Document this skill's holder
      obligations **only**: the declared filename (`Experimental_AGREED.md`), the
      create-on-absent behavior, and the write-refusal-into-an-undeclared-holder behavior —
      mirroring the holder section of `skills/proposal-implementation/references/usage.md`
      without mirroring its unrelated sections (e.g. kit assets this skill does not ship).
      Verification: `ls skills/experimental-implementation/references/usage.md` confirms the
      file now exists.
- [x] 5.2 Update `skills/proposal-implementation/SKILL.md` and
      `skills/experimental-implementation/SKILL.md` so holder naming follows each skill's own
      declaration. Verification: `grep -n "AGREED" skills/proposal-implementation/SKILL.md
      skills/experimental-implementation/SKILL.md` — confirm each names only its own declared
      holder.
- [x] 5.3 Verify `references/usage.md`'s stated obligations match shipped behavior
      (documentation-only capability, no executable scenario): cross-check the stated
      filename, create-on-absent behavior, and write-refusal behavior against the actually
      enforced `cmd_settle`/`cmd_position` behavior for `experimental-implementation` from
      Phases 2–4. Verification: manual read-through cross-check; record the result in this
      change's own verification notes (N/A for an automated command — this is a documentation
      fidelity check).
      **Result (2026-09-25):** cross-checked live against the real
      `experimental-implementation` launcher (scratch fixture under `implementations/`,
      deleted after). `holder_resolution`/`_chosen_holder`'s create-on-absent path wrote
      `<Name>/Experimental_AGREED.md` with the declared scaffold (`# Agreed\n\n## Ladder\n`)
      verbatim, before the position block was spliced beneath it — matches. A pre-existing
      `TASKS.md` holding checklist items produced `HOLDER_UNDECLARED` naming both exits
      (rename in the target, or declare the found name in `PROFILE["holder"]["filename"]`) —
      matches. `references/usage.md`'s example detail string was corrected to the exact
      observed format (`Method/TASKS.md holds checklist items under Method/, ...`). Also
      confirmed against `tests/test_experimental_implementation.py::HolderCollisionTests`
      (`engine.HOLDER_FILENAME == "Experimental_AGREED.md"`; a target holding the proposal's
      own `AGREED.md` resolves `"undeclared"` under this profile). No shipped behavior
      diverges from the stated obligations.

## Phase 6: Cross-Cutting Verification And Final Gate

Spec: `implementation-declared-holder` ("The Engine Uses No Default Or Fallback Holder
Filename Of Its Own", "The Never-Invents-A-File Doctrine Is Narrowed To The Read Path, Not
Retired"), `implementation-cli-seal` ("The Proposal Seal's 28 Digests Stay Byte-Identical").

- [x] 6.1 Grep-provable check: no engine-side default/fallback holder filename literal
      remains. Verification: `grep -n "AGREED"
      skills/_core/implementation/engine/implementation_engine.py
      skills/_core/implementation/impl_position.py` — every remaining hit must be one of the
      9 (+3 in `impl_position.py`) "leave standing" dated/target-specific quotations from
      task 2.12, never a Python default value or fallback expression.
      **Result (2026-09-25):** 7 hits remain (down from 18): `impl_position.py:20,270,1139`
      (all 3, byte-identical to `main`, confirmed by diff — file received no functional
      edit at all, per design). `implementation_engine.py:315,698,12303,14273` — of these,
      `:315` and `:14273` are the exact, byte-identical `main:304`/`main:13892` dated
      measurements (only their line numbers shifted, +11/+381, from unrelated insertions
      earlier in the file); `:698` and `:12303` are `main:575`/`main:12005` **amended**
      (not left standing) to name `PROFILE["holder"]["filename"]` and keep `AGREED.md`
      only as an illustrative `e.g. ... for proposal-implementation` example — exactly the
      form `implementation-engine-neutrality`'s own scenario sanctions ("distinguishing it
      from a comment merely illustrating one skill's own declared example value"). No
      remaining hit is a Python default or fallback expression. Grep-provable check PASSES.
      **Deviation noted, not a defect:** 4 of design D12's 9 "leave standing" engine-side
      sites (`main:11083,15746,18866,18916`) were in fact **amended** in Phases 2/4 to say
      "this skill's own declared holder" instead of the literal filename — verified by
      locating their exact surviving prose at `implementation_engine.py:11219-11220`
      (`This says only what the skill is FOR`), `:16185` (`expand-contract`), `:19320`
      (`@step` operand) and `:19370-19371` (`@record:level` operand). Unlike `:304`/`:13892`
      (genuine dated measurements — "zero hits across 114 checklist lines", "carries
      agreements ticked with no witness at all"), these 4 sites are generic mechanism
      descriptions with no date or number attached, and leaving them as a literal
      `AGREED.md` would have been **false** prose for `experimental-implementation` (whose
      own holder is `Experimental_AGREED.md`) — amending them is the more correct outcome
      and the grep-provable check still passes, but this is a real divergence from
      `design.md`'s literal D12 classification, reported per this phase's charter rather
      than silently accepted.
- [x] 6.2 Run the `ForgeVocabularyDerivedGuardTests` / lock family after the declarations
      have landed (vocabulary caution: `AGREED.md`, `Experimental_AGREED.md`, `"# Agreed"`,
      `"## Ladder"` are new literals in *skill* files, which Rule B/LockB scans for engine
      neutrality). Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k ForgeVocabularyDerivedGuardTests -v`
      — expect only the one known pre-existing failure
      (`test_rule_b_finds_no_target_vocabulary_in_the_forge`, dated 2026-09-24) — no new
      failures.
      **Result (2026-09-25):** 22 tests, 21 passed, 1 failed — exactly the one named
      pre-existing failure (`{'paper-writing/scripts/paper_tikz.py': ['plots']}`, unrelated
      to this change). No new vocabulary leak from `AGREED.md`, `Experimental_AGREED.md`,
      `# Agreed` or `## Ladder`. Re-confirmed after the 6.6 SKILL.md edits below.
- [x] 6.3 Verify all 10 doctrine-table rows (A1–A7, B1–B3, `design.md` D12) against shipped
      bytes, not intent, after all Phase 2–5 edits have landed. Verification: manual
      read-through checklist, one row at a time, against the D12 table.
      **Result (2026-09-25):** all 10 rows read against shipped bytes and confirmed to
      match their D12 verdict. A1 (`agreements_state:392-404`): "Found by shape, never by
      name" kept verbatim, new write-side paragraph added. A2 (`_chosen_holder:11992-12014`):
      dispatches off `holder_resolution`, docstring cross-reference repointed. A3/A4
      (`cmd_settle:14530-14548`, item 12 enumeration): amended, cites the same doctrine
      `_chosen_holder` states. A5/A6 (`SETTLE_HOLDER_ABSENT`/`POSITION_HOLDER_ABSENT`
      questions, `:19757-19760`/`:19822-19826`): re-authored for the narrowed "no product
      folder" case, not retired. A7 (`test_implementation_pair.py:477-485`): amended
      comment, fixture moved to `Fixture_AGREED.md` — that fixture's own declared name
      (from `tests/fixtures/two_documents/impl_profile.py`), not the literal
      `Experimental_AGREED.md` `design.md` named — correct, since this fixture is not the
      `experimental-implementation` skill itself. B1 (`position_state:767-782`): "found by
      shape... never a fixed filename" kept, gains a pointer to the declared-name lookup
      above it. B2 (`cmd_position:12412-12424`): sweep comment amended, glob-survives
      rationale preserved. B3 (`cmd_position:12302-12345`): docstring amended to describe
      the declared-name-first mechanism. All 4 fact-asserting docstrings (`main:575,
      12005, 18946, 18992`) confirmed to now name the declared leaf, not a literal
      filename (current sites: `:698`, `:12303`, `:19446`, `:19400-19401`). See 6.1 for the
      4-site leave-standing/amend deviation, reported there rather than duplicated here.
- [x] 6.4 Success-criteria closure check against `proposal.md`'s 14-item checklist — walk
      every box and confirm it is satisfied by a specific task above; do not check a box
      without the corresponding shipped test. Verification: manual cross-reference table
      (proposal checklist item → task ID → passing test).
      **Result (2026-09-25):** full 14-row table recorded in this phase's return report to
      the orchestrator (not duplicated here for length). 11 of 14 items have a direct
      automated test; items 8 ("all 7+3 doctrine restatements verified against shipped
      bytes"), 9 ("the four fact-asserting docstrings name the declared leaf") and 13
      (`references/usage.md` exists and matches shipped behavior) are satisfied only by
      this phase's manual read-through (6.3) and by tasks 5.1/5.3's own manual
      verification — no automated test exercises any of these three, confirmed by an
      exhaustive `rg` across `tests/` finding zero references to
      `experimental-implementation`'s `references/usage.md` at all. This is reported as a
      genuine, durable test-coverage gap, not closed by this phase (closing it would mean
      writing new tests, which is out of this phase's cross-cutting-verification charter).
- [x] 6.5 Final full-suite gate. Verification: `npm run test:all`. Acceptance: green except
      the 8 named pre-existing environmental failures from 1.8 (dated 2026-09-24);
      `tests/seal/digests.json` byte-identical to its pre-change state (hard zero-delta gate,
      confirmed via `git diff --stat tests/seal/digests.json` empty across the whole change);
      `tests/experiments_seal/digests.json` reflects exactly the 2.16/2.20-verified declared
      delta and nothing else.
      **Result (2026-09-25):** `npm run test:node`: 653/653 passed (run twice, before and
      after the 6.6 SKILL.md edits). `.venv/bin/python -m pytest` (hang test deselected):
      11 failed / 5077 passed / 3 skipped / 1 deselected — all 11 failures are exactly the
      8 named pre-existing tests from 1.8 (`GateInterpreterTests` ×3, `KitTests` ×3,
      `BridgesTests`×1, `ExecutorTests`×1, `GroundingThresholdObligationTests`×1,
      `test_repo_papersmith_yaml_parses`×1, `test_rule_b_finds_no_target_vocabulary_in_the_forge`×1
      — 11 test methods across those 8 named cases); zero unaccounted delta. Re-ran the
      full `tests/test_proposal_implementation.py` file a second time after the 6.6
      SKILL.md edits (1696 passed, 1 known failure) and both seal files together (73
      passed) to confirm the edits introduced no regression. `git diff main..HEAD --stat
      -- tests/seal/digests.json`: empty (confirmed across the whole change, not just this
      phase). `git diff main..HEAD -- tests/experiments_seal/digests.json`: exactly the 9
      keys `experiments-seal-delta.md` names (`__corpus_fingerprint__`, `position-e1`,
      `propose`, `verify-a`, `verify-a-declared`, `verify-b`, `verify-b-declared`,
      `verify-b-undeclared`, `verify-t`) — nothing else moved. `reachable_refusal_codes()`
      independently re-run (not just read from the pinned assertion): **121**, with
      `HOLDER_UNDECLARED`/`HOLDER_REPAIR_AMBIGUOUS`/`POSITION_REPAIR_CONFLICT` all present
      and classified (50 `INVOCATION_DEFECT` + 71 `WORK_STATE` = 121, independently
      recomputed and matching `proposal-implementation/SKILL.md`'s own stated split).
- [x] 6.6 Close the `HOLDER_UNDECLARED`/`HOLDER_REPAIR_AMBIGUOUS`/`POSITION_REPAIR_CONFLICT`
      gap in `proposal-implementation/SKILL.md`'s Command Roster table, left unassigned by
      Phases 4 and 5. **Result (2026-09-25):** added `--repair-header` to the `position`
      row's "What it writes" cell; added `POSITION_REPAIR_CONFLICT`, the narrowed
      `POSITION_HOLDER_ABSENT`, `HOLDER_UNDECLARED` and `HOLDER_REPAIR_AMBIGUOUS` to the
      `position` row's "Refuses on" cell; added the narrowed `SETTLE_HOLDER_ABSENT` and
      `HOLDER_UNDECLARED` to the `settle` row's "Refuses on" cell; corrected `settle`'s
      opening sentence, which still said "whichever holder file `agreements_state` already
      knows carries checklist items" (stale since D10 narrowed `settle`'s write set to the
      one `holder_resolution`-resolved file). No digest moved (`SKILL.md` is outside both
      seal corpora); no word-count lock exists on this file (checked: no test asserts a
      byte/word count on `proposal-implementation/SKILL.md`). Re-ran
      `tests/test_proposal_implementation.py` in full (1696 passed, 1 known failure) and
      both seal test files (73 passed, zero-delta held) after the edit to confirm.
      `experimental-implementation/SKILL.md` was left unchanged: it already documents
      `HOLDER_UNDECLARED` (`:281`) and explicitly delegates every other command's refusal
      documentation to the sibling's own doctrine ("every other published command runs
      exactly as `proposal-implementation`'s own doctrine describes it"), which now covers
      `--repair-header`/`HOLDER_REPAIR_AMBIGUOUS`/`POSITION_REPAIR_CONFLICT` by that same
      delegation — adding a second copy would duplicate, not close, the gap.

## Phase 7: Closing The CRITICAL Verify Defect (Operator-Authorized Extension)

`sdd-verify` found a CRITICAL defect after Phase 6 closed: `cmd_position` dispatched on
`holder_resolution_result["path"]` alone, never consulting `["action"]`/`["write"]`, so
the D3 middle row (a candidate found by shape but not by declared name) that ALREADY
carried a `<!-- position -->` block was silently adopted as "existing" by a fresh
`--sequence`/`--reconcile` write — the collision this whole change exists to close,
reachable through a path the 63 tasks above never tested. Full diagnosis: Engram
`sdd/the-holder-each-skill-declares/verify-critical` (obs 2139). The operator authorized
extending this change to close it. Spec: `implementation-declared-holder` — "Write
Refuses Into A Holder Not Found By The Declared Name, Naming Both Exits" (the sub-case
this phase's tasks close was untested, not unspecified — the requirement already covers
it).

- [x] 7.1 RED: reproduce the CRITICAL defect as a permanent regression test — real
      subprocesses throughout, `proposal-implementation` `discuss`+`settle`+`position
      --sequence` install a checklist item AND a position block into `Method/AGREED.md`
      (an item OUTSIDE the block is required so `agreements_state`'s `byShape` scan
      actually counts the file — a position block's own items are excluded from that
      scan by design, `implementation_engine.py:406-410`), then `experimental-
      implementation position --reconcile` and, separately, `position --sequence
      --replace`, against the SAME target, before `Experimental_AGREED.md` exists.
      Verification: `.venv/bin/python -m pytest
      tests/test_experimental_implementation.py -k "reconcile_never_writes_into_the_siblings
      or sequence_replace_never_overwrites_the_siblings" -v` — RED confirmed against the
      pre-fix commit (`git stash` of the engine file only): both reproduced the exact
      poisoning (`"status": "written"`, `"holder": "Method/AGREED.md"`, a `documents=`
      group added).
- [x] 7.2 GREEN: `skills/_core/implementation/engine/implementation_engine.py`'s
      `cmd_position` holder-sweep dispatch — add `elif holder_resolution_result["action"]
      == "undeclared":` ahead of the existing `else` (block-count ambiguity) branch,
      calling `_chosen_holder(target, name, product)` itself (which raises
      `HOLDER_UNDECLARED`, never returning) rather than re-deriving its message. No new
      refusal code — reuses `HOLDER_UNDECLARED` (D9). Deliberately scoped to exactly the
      `"undeclared"` action (not `"create"`/`"absent"`/`"ambiguous"` too — see 7.3).
      Acceptance: 7.1's two tests GREEN. Verification: same command as 7.1.
- [x] 7.3 Regression sweep against the WHOLE suite (not just the new tests) — a wider
      first attempt (also switching the `"declared"` branch's key from `["path"]` to
      `["write"]`, to close a related-looking `"create"`-action gap) reddened THREE
      already-shipped, unrelated tests in `tests/test_implementation_pair.py`
      (`TwoDocumentAmbiguousFamilyRefusesTests`, `AmbiguousFamilyMutationProvesReachabilityTests`
      ×2), because their OWN fixtures write a plain `AGREED.md` — not their OWN profile's
      declared `Fixture_AGREED.md` — under the two-document `pair_corpus.build` profile,
      relying (unknowingly) on the exact same silent-adoption defect this phase closes.
      Fixed the fixtures instead of widening the guard: `tests/test_implementation_pair.py`
      (`TwoDocumentAmbiguousFamilyRefusesTests.setUp`,
      `AmbiguousFamilyMutationProvesReachabilityTests.setUp`) now write
      `Fixture_AGREED.md`, matching their own profile's declaration
      (`tests/fixtures/two_documents/impl_profile.py`) — their actual test subject
      (document-family ambiguity / D5 mutation reachability) is unchanged. Verification:
      `.venv/bin/python -m pytest tests/test_implementation_pair.py -v` — 38 passed, 18
      subtests passed, zero failures.
- [x] 7.4 `HolderCollisionTests._load_engine()` isolation fix —
      `tests/test_experimental_implementation.py`: evict `sys.modules["impl_domain_profile"]`
      before AND after the fresh engine load, mirroring the sibling helper
      `_engine_with_documents`'s own documented discipline a few hundred lines up in the
      same file. Measured before the fix: `.venv/bin/python -m pytest
      tests/test_proposal_implementation.py tests/test_experimental_implementation.py -k
      HolderCollisionTests` read `engine.HOLDER_FILENAME == "AGREED.md"` (the PROPOSAL's
      own name, leaked in from the first file's own cached `impl_domain_profile` module)
      under this class's own EXPERIMENTAL-profile helper — two of its four tests failed
      outright in that combined order (a stronger, more visible symptom than the
      "silently passes wrong" the diagnosis described, but the same root cause: no
      eviction). Verification: same combined-file command — 4 passed, both file orders
      confirmed.
- [x] 7.5 Read-side investigation (scoped `MUST` — measure, implement only if no new key,
      report otherwise): `cmd_gate`'s launch-authorization inputs (`position_state`'s
      `sequence`/`status`/`unbacked`/etc.) can, in principle, come from the SAME by-shape
      read fallback (D3 — read-only, never write) that a foreign or arbitrarily-named
      holder satisfies. Compared `position_state`'s EXISTING `"holder"` key against
      `HOLDER_FILENAME` inside `cmd_gate` (no new key, folding a mismatch to the SAME
      shape `position_state`'s own `"absent"` branch returns, so the EXISTING
      `POSITION_ABSENT` refusal — not a new code — is what fires). Mechanically correct
      and closed the diagnosed gap in isolation (a dedicated RED/GREEN test proved it:
      `gate` recorded a real authorization against a `TASKS.md` read via the fallback
      before the fix; refused `POSITION_ABSENT` after). **Reverted — not shipped.**
      Applying it regressed an already-shipped, unrelated test,
      `tests/test_implementation_pair.py::TwoDocumentLifecycleTests
      ::test_the_full_lifecycle_reaches_every_named_gate` (`C4 gate`/`C2 close`
      sub-tests), whose OWN fixture writes its position block into a bare `AGREED.md`
      (not that profile's declared `Fixture_AGREED.md`) and depends on `gate`/`close`
      reading it back through the SAME by-shape fallback this fix would foreclose for
      authorization. Unlike 7.3's fixtures, that scenario is a file carrying ONLY a
      position-block item (no separate checklist line), which makes it `holder_resolution`
      action `"create"`, not `"undeclared"` — a DIFFERENT, pre-existing blind spot in
      `holder_resolution`'s own classification (`agreements_state`'s `byShape` excludes a
      position block's own items, so a block-only file is invisible to it) that this
      change does not touch. Given the fix could not be scoped narrowly enough to spare
      that fixture without inventing new machinery to distinguish "arbitrary undeclared
      name" from "another skill's own declared name" — exactly the ambiguity the original
      proposal's "The read-side gap" section already argued has no mandate here — the
      production edit and its test were reverted (net diff on
      `tests/test_proposal_implementation.py`: zero). Reported to the operator instead:
      the no-new-key comparison is implementable and does close the diagnosed gap, but
      not without a decision (fix the OTHER test's stale fixture too — a fourth,
      cross-feature test correction — or defer). Not decided in this phase.
- [x] 7.6 Mutation reachability proof for `cmd_position`'s own new guard (as distinct
      from `_chosen_holder`'s, already proven in task 2.14) —
      `tests/test_proposal_implementation.py::HolderUndeclaredMutationTests
      ::test_inverting_cmd_positions_own_undeclared_guard_lets_a_sequence_write_into_it`:
      a scratch-copied engine with the new `elif` disabled reaches `cmd_position`'s
      `else` branch and writes into the undeclared `TASKS.md` (`status: "written"`); the
      unmutated build, same target shape, refuses `HOLDER_UNDECLARED` and leaves it
      byte-identical. `--sequence --replace`, not `--reconcile`: reconcile discovery
      loads `remote_cli.py` by a `FORGE_ROOT`-relative path the scratch copy does not
      carry. Verification: `.venv/bin/python -m pytest tests/test_proposal_implementation.py
      -k HolderUndeclaredMutationTests -v` — 3 passed (both pre-existing mutation tests
      plus this one).
- [x] 7.7 `tests/test_implementation_domain_lock.py::DerivedDenylistTests::test_3`
      re-pin — a first full-suite run after 7.1-7.6 caught exactly the drift the
      operator's own briefing named as a standing risk ("Both moved from PROSE alone
      in Phases 2, 3 and 5"): the new `elif` branch's comment prose (7.2) moved 8
      already-pinned word counts by its own text alone, zero admissions, zero
      removals — `against` 196→197, `measured` 144→145, `rather` 378→380 (+2),
      `reported` 147→148, `resolves` 33→34, `sweep` 11→12, `whose` 155→157 (+2),
      `write` 151→152. Re-pinned `M5_PINNED_RESIDUE` to these MEASURED values (never
      predicted) and appended a Phase 7 changelog entry to the file's own convention,
      matching Phases 2/3/4's identical entries above it. Verification:
      `.venv/bin/python -m pytest tests/test_implementation_domain_lock.py -v` — 28
      passed, 134 subtests passed (`CampaignProposalExclusionTests::test_l1`'s own
      separate `\bproposal\b` pin unaffected).
- [x] 7.8 Full regression + seal + refusal-count gate, re-run after 7.7's re-pin.
      Verification: `npm run test:node` — 653/653 passed (unchanged from baseline);
      `.venv/bin/python -m pytest --deselect
      tests/test_proposal_implementation.py::StepCommandTests::test_a_step_killed_mid_run_leaves_a_started_line_with_no_partner
      -q` (clean, sequential run, no concurrent pytest) — **11 failed / 5083 passed / 3
      skipped / 1 deselected / 2674 subtests passed in 630.24s**; the 11 failures are
      EXACTLY the 8 named pre-existing cases (`GateInterpreterTests` ×3,
      `KitTests` ×3, `BridgesTests`×1, `ExecutorTests`×1,
      `GroundingThresholdObligationTests`×1, `test_repo_papersmith_yaml_parses`×1,
      `test_rule_b_finds_no_target_vocabulary_in_the_forge`×1) — zero unaccounted
      failure, zero `DerivedDenylistTests` subfail; passed count only rose (this phase
      added exactly 3 new test methods, confirmed by `git diff | rg '^\+.*def test_'`)
      and never fell. `.venv/bin/python -m pytest tests/test_implementation_seal.py
      tests/test_experiments_seal.py` — 73 passed, `git diff --stat --
      tests/seal/digests.json tests/experiments_seal/digests.json` empty (zero movement
      in EITHER seal — this phase touches no sealed case); `reachable_refusal_codes()`
      independently re-run via `tests/test_proposal_implementation.py`'s own derivation —
      **121**, unchanged (no refusal code added or retired by this phase);
      `git status --porcelain implementations/` — clean; `tests/seal_capture.py` — never
      invoked. **Concurrent-pytest incident, disclosed:** once, by mistake, mid-phase, a
      background full-suite run was still active when several targeted `pytest`
      invocations ran against it, corrupting THAT run's own result (19 failures,
      including 8 `DerivedDenylistTests::test_3` subtests that read the real engine
      file mid-mutation from an unrelated concurrent test writing it). That run's output
      was discarded entirely and never cited as evidence anywhere in this record; this
      task's own numbers, and the 7.7 re-pin they gated, come from clean, sequential
      re-runs only, confirmed by checking for a single `pytest` process before each.

## Phase 8: Closing The READ Face Of The CRITICAL Verify Defect (Operator-Authorized Extension)

Phase 7 closed the WRITE face of the CRITICAL defect (Engram obs 2139/2140): a
foreign or arbitrarily-named holder could no longer be silently adopted for a
write. Task 7.5 measured, tested, and then reverted a READ-side fix — the
regression was `tests/test_implementation_pair.py::TwoDocumentLifecycleTests`,
whose own fixture wrote its position block into a plain `AGREED.md` rather
than its own profile's declared `Fixture_AGREED.md`. The operator authorized
closing this gap. Spec: `implementation-declared-holder` — "Write Refuses Into
A Holder Not Found By The Declared Name, Naming Both Exits" (the read-side
authorization sub-case this phase closes was untested, and `cmd_gate`'s own
read was unguarded; the requirement's D3 read/write split already covers it).

- [x] 8.1 Fixed the enabling obstacle first, measured before any production
      change: `tests/test_implementation_pair.py::TwoDocumentLifecycleTests
      ::_build_box` wrote its hand-authored position block into a bare
      `AGREED.md` — a name the two-document fixture profile
      (`tests/fixtures/two_documents/impl_profile.py`) does NOT declare
      (`Fixture_AGREED.md` is). This is the third instance of the exact
      undeclared-name-in-its-own-fixture pattern task 7.3 already fixed in two
      sibling fixtures. Moved both sites (`_build_box`'s write, `C2 close`'s
      read-back assertion) to `Fixture_AGREED.md`. Verified in isolation,
      BEFORE touching any production code, that this alone keeps the lifecycle
      test green — confirming the KEY INSIGHT: the obstacle was the fixture,
      not a structural conflict with the read-side fix. Verification:
      `.venv/bin/python -m pytest tests/test_implementation_pair.py -k
      TwoDocumentLifecycleTests -v` — 1 passed, 10 subtests passed; full file
      `.venv/bin/python -m pytest tests/test_implementation_pair.py -q` — 38
      passed, 18 subtests passed.
- [x] 8.2 RED: reproduced the CRITICAL defect's READ face as a permanent
      regression test,
      `tests/test_experimental_implementation.py::HolderCollisionTests
      ::test_gate_never_authorizes_a_launch_against_the_siblings_position` —
      real subprocesses throughout: `proposal-implementation` installs a
      settled item plus a position block into `Method/AGREED.md`
      (`_install_siblings_holder`, already shipped by Phase 7), then
      `experimental-implementation gate` is called against the SAME target.
      Measured actual pre-fix output (not assumed): `gate` refused
      `NOT_READY` — it evaluated `job1`'s readiness against the SIBLING's own
      sequence — instead of the correct `POSITION_ABSENT`, since this skill's
      own declared holder (`Experimental_AGREED.md`) never existed on this
      target at all. Verification:
      `.venv/bin/python -m pytest tests/test_experimental_implementation.py -k
      test_gate_never_authorizes_a_launch_against_the_siblings_position -v`
      (RED — pasted actual failure: `AssertionError: 'NOT_READY' !=
      'POSITION_ABSENT'`).
- [x] 8.3 GREEN: `skills/_core/implementation/engine/implementation_engine.py`
      — extracted `position_state`'s own uniform "nothing to report" dict
      literal into a new module-level `_absent_position_state(multi: bool) ->
      dict`, called identically from `position_state`'s two `absent` branches
      (pure extraction, byte-identical output — no key added, no behaviour
      change; confirmed against the seal zero-delta gate immediately after).
      Then, in `cmd_gate` — after `position = position_state(...)`, before the
      launch verdict is computed — added a fold: when
      `position["holder"]` names a file whose basename is not
      `HOLDER_FILENAME`, `position` is replaced with
      `_absent_position_state(len(DOCUMENTS) > 1)`. No new refusal code: the
      EXISTING `POSITION_ABSENT` (`impl_availability.position_honest`) fires
      naturally once `status` reads `"absent"`. This is exactly task 7.5's own
      already-measured, already-RED/GREEN-tested mechanism, scoped
      identically (`cmd_gate` only — the launch-authorization consumer, never
      `verify`/`probe`/`discuss`/`offer`/`close`/`step`'s own reporting, which
      remains out of this phase's charter per the same reasoning
      `proposal.md`'s "The read-side gap" section already gives for a
      DIFFERENT read-side check). Acceptance: 8.2's RED test now GREEN.
      Verification: `.venv/bin/python -m pytest
      tests/test_experimental_implementation.py -k
      test_gate_never_authorizes_a_launch_against_the_siblings_position -v`
      (GREEN); full `HolderCollisionTests` class — 6 passed.
- [x] 8.4 RED: reproduced a SECOND, distinct blind spot on the WRITE side that
      Phase 7 diagnosed but explicitly deferred (task 7.5's own report,
      point 3): `agreements_state`'s `byShape` excludes a position block's
      own items, so a sibling's declared holder carrying ONLY a block (no
      checklist line outside it) resolves `holder_resolution`'s `"create"`
      action, not `"undeclared"` — invisible to Phase 7's `elif ... ==
      "undeclared":` guard. New test,
      `tests/test_experimental_implementation.py::HolderCollisionTests
      ::test_reconcile_never_writes_into_the_siblings_block_only_holder`, with
      a new helper `_install_siblings_block_only_holder` (a bare `position
      --sequence` install, no `settle`, so the sibling's `AGREED.md` carries
      ONLY a block). Measured actual pre-fix output: `experimental-
      implementation position --reconcile` against the same target wrote a
      `documents=` group straight into the sibling's `AGREED.md`
      (`payload["holder"] == "Method/AGREED.md"`), reproducing the exact
      poisoning task 7.5 named but did not test. Verification:
      `.venv/bin/python -m pytest tests/test_experimental_implementation.py -k
      test_reconcile_never_writes_into_the_siblings_block_only_holder -v` (RED
      — pasted actual failure: `AssertionError: 'Method/AGREED.md' !=
      'Method/Experimental_AGREED.md'`).
- [x] 8.5 GREEN, in two measured steps (the first attempt regressed two
      already-shipped tests and was corrected, not forced):
      (a) First attempt — widened `cmd_position`'s dispatch condition from
      `holder_resolution_result["path"] is not None` to
      `holder_resolution_result["write"] is not None"` (non-`None` for both
      `"declared"` and `"create"`, `None` only for `"absent"`/`"undeclared"`/
      `"ambiguous"`). This made 8.4's test GREEN, but running the wider
      `test_proposal_implementation.py -k "holder or position or repair or
      mutation"` sweep measured two regressions: `PositionCommandTests
      ::test_refuses_when_two_files_already_carry_a_position_block` and
      `PositionRepairHeaderTests
      ::test_repair_ambiguous_more_than_one_file_carrying_a_block_still_answers_holder_ambiguous`
      — both broke because the `else` branch's own `len(holders_with_block) >
      1` ambiguity check (a check independent of, and different from,
      `holder_resolution`'s own byShape-based `"ambiguous"` action) stopped
      running for `"create"`, letting an on-disk multi-block ambiguity route
      into create/repair instead of stopping for a human.
      (b) Corrected: re-shaped the dispatch to three explicit branches keyed
      on `holder_resolution_result["action"]` (`"declared"` /
      `"undeclared"` / else), keeping the `else` branch's block-count
      ambiguity check FIRST and unconditional, then — only for `"create"`,
      and only after that check has already passed — resetting
      `existing_path`/`existing_block` to `(None, None)` whenever a single
      block-carrying candidate was found, so `_chosen_holder` creates this
      skill's own declared holder instead of ever adopting the foreign one.
      Acceptance: 8.4's test GREEN, and both regressed tests GREEN again.
      Verification: `.venv/bin/python -m pytest
      tests/test_proposal_implementation.py -k
      "test_refuses_when_two_files_already_carry_a_position_block or
      test_repair_ambiguous_more_than_one_file_carrying_a_block_still_answers_holder_ambiguous"
      -v` (2 passed); `.venv/bin/python -m pytest
      tests/test_proposal_implementation.py -k "holder or HOLDER or position or
      Position or repair or Repair or mutation or Mutation" -q` (171 passed);
      `.venv/bin/python -m pytest tests/test_experimental_implementation.py -k
      HolderCollisionTests -v` (6 passed); `.venv/bin/python -m pytest
      tests/test_implementation_pair.py -q` (38 passed, 18 subtests passed).
- [x] 8.6 Mutation reachability proof for `cmd_gate`'s own fold guard (8.3), as
      distinct from `_chosen_holder`'s (task 2.14) and `cmd_position`'s own
      (task 7.6) — `tests/test_proposal_implementation.py
      ::HolderUndeclaredMutationTests
      ::test_inverting_cmd_gates_read_side_fold_lets_it_authorize_off_a_foreign_holder`:
      a scratch-copied engine with the fold guard's condition ANDed with
      `False` reaches `NOT_READY` against a foreign `TASKS.md` holder — the
      identical code the real cross-skill reproduction (8.2) measured; the
      unmutated build, same target shape, refuses `POSITION_ABSENT` and
      leaves the foreign holder byte-identical. Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k
      test_inverting_cmd_gates_read_side_fold_lets_it_authorize_off_a_foreign_holder
      -v` — 1 passed.
- [x] 8.7 `tests/test_implementation_domain_lock.py::DerivedDenylistTests
      ::test_3` re-pin — the new `_absent_position_state` docstring,
      `cmd_gate`'s fold-guard comment, and the widened three-way
      `cmd_position` dispatch's own prose moved 9 already-pinned word counts
      by their comment text alone, zero admissions, zero removals: `before`
      259→260, `beside` 109→110, `check` 158→161 (+3), `makes` 47→48,
      `rather` 380→382 (+2), `validated` 9→10, `write` 152→153 (grew); `sweep`
      12→11, `whose` 157→156 (SHRANK — the Phase 7 sweep-comment text was
      folded into the `else` branch's own comment once instead of twice, and
      the rewritten `elif`'s docstring reads differently from what it
      replaced). Re-pinned `M5_PINNED_RESIDUE` to these MEASURED values and
      appended a Phase 8 changelog entry matching the file's own convention.
      Verification: `.venv/bin/python -m pytest
      tests/test_implementation_domain_lock.py -v` — 28 passed, 134 subtests
      passed (`CampaignProposalExclusionTests::test_l1`'s own separate
      `\bproposal\b` pin unaffected).
- [x] 8.8 Full regression + seal + refusal-count gate. Verification: `npm run
      test:node` — 653/653 passed (unchanged from baseline); `.venv/bin/python
      -m pytest --deselect
      tests/test_proposal_implementation.py::StepCommandTests::test_a_step_killed_mid_run_leaves_a_started_line_with_no_partner
      -q` (clean, sequential run, no concurrent pytest) — see this phase's own
      apply-progress record for the exact counts; the failures are exactly
      the 8 named pre-existing cases from task 1.8, zero unaccounted failure,
      zero `DerivedDenylistTests` subfail; `.venv/bin/python -m pytest
      tests/test_implementation_seal.py tests/test_experiments_seal.py` — 73
      passed, `git diff --stat -- tests/seal/digests.json
      tests/experiments_seal/digests.json` empty (zero movement in EITHER
      seal — this phase touches no sealed case); `reachable_refusal_codes()`
      independently re-run (via the test module's own derivation, not merely
      read from the pinned assertion) — **121**, unchanged (no refusal code
      added or retired by this phase); `git status --porcelain
      implementations/` — clean; `tests/seal_capture.py` — never invoked; no
      concurrent pytest ever ran (each invocation checked to be the only one
      in flight before starting the next).

## Total: 79 tasks across 8 phases (Phase 1: 8, Phase 2: 25, Phase 3: 9, Phase 4: 12,
Phase 5: 3, Phase 6: 6, Phase 7: 8, Phase 8: 8 — 6.6 added during Phase 6 itself, closing
the SKILL.md roster gap Phases 4/5 both deliberately left unassigned; Phase 7 added
post-verify to close the WRITE face of a CRITICAL defect `sdd-verify` found after Phase 6,
operator-authorized; Phase 8 added to close the READ face of the same CRITICAL defect,
operator-authorized)
