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

- [ ] 5.1 Create `skills/experimental-implementation/references/usage.md` (no
      `references/` directory exists today for this skill). Document this skill's holder
      obligations **only**: the declared filename (`Experimental_AGREED.md`), the
      create-on-absent behavior, and the write-refusal-into-an-undeclared-holder behavior —
      mirroring the holder section of `skills/proposal-implementation/references/usage.md`
      without mirroring its unrelated sections (e.g. kit assets this skill does not ship).
      Verification: `ls skills/experimental-implementation/references/usage.md` confirms the
      file now exists.
- [ ] 5.2 Update `skills/proposal-implementation/SKILL.md` and
      `skills/experimental-implementation/SKILL.md` so holder naming follows each skill's own
      declaration. Verification: `grep -n "AGREED" skills/proposal-implementation/SKILL.md
      skills/experimental-implementation/SKILL.md` — confirm each names only its own declared
      holder.
- [ ] 5.3 Verify `references/usage.md`'s stated obligations match shipped behavior
      (documentation-only capability, no executable scenario): cross-check the stated
      filename, create-on-absent behavior, and write-refusal behavior against the actually
      enforced `cmd_settle`/`cmd_position` behavior for `experimental-implementation` from
      Phases 2–4. Verification: manual read-through cross-check; record the result in this
      change's own verification notes (N/A for an automated command — this is a documentation
      fidelity check).

## Phase 6: Cross-Cutting Verification And Final Gate

Spec: `implementation-declared-holder` ("The Engine Uses No Default Or Fallback Holder
Filename Of Its Own", "The Never-Invents-A-File Doctrine Is Narrowed To The Read Path, Not
Retired"), `implementation-cli-seal` ("The Proposal Seal's 28 Digests Stay Byte-Identical").

- [ ] 6.1 Grep-provable check: no engine-side default/fallback holder filename literal
      remains. Verification: `grep -n "AGREED"
      skills/_core/implementation/engine/implementation_engine.py
      skills/_core/implementation/impl_position.py` — every remaining hit must be one of the
      9 (+3 in `impl_position.py`) "leave standing" dated/target-specific quotations from
      task 2.12, never a Python default value or fallback expression.
- [ ] 6.2 Run the `ForgeVocabularyDerivedGuardTests` / lock family after the declarations
      have landed (vocabulary caution: `AGREED.md`, `Experimental_AGREED.md`, `"# Agreed"`,
      `"## Ladder"` are new literals in *skill* files, which Rule B/LockB scans for engine
      neutrality). Verification:
      `.venv/bin/python -m pytest tests/test_proposal_implementation.py -k ForgeVocabularyDerivedGuardTests -v`
      — expect only the one known pre-existing failure
      (`test_rule_b_finds_no_target_vocabulary_in_the_forge`, dated 2026-09-24) — no new
      failures.
- [ ] 6.3 Verify all 10 doctrine-table rows (A1–A7, B1–B3, `design.md` D12) against shipped
      bytes, not intent, after all Phase 2–5 edits have landed. Verification: manual
      read-through checklist, one row at a time, against the D12 table.
- [ ] 6.4 Success-criteria closure check against `proposal.md`'s 14-item checklist — walk
      every box and confirm it is satisfied by a specific task above; do not check a box
      without the corresponding shipped test. Verification: manual cross-reference table
      (proposal checklist item → task ID → passing test).
- [ ] 6.5 Final full-suite gate. Verification: `npm run test:all`. Acceptance: green except
      the 8 named pre-existing environmental failures from 1.8 (dated 2026-09-24);
      `tests/seal/digests.json` byte-identical to its pre-change state (hard zero-delta gate,
      confirmed via `git diff --stat tests/seal/digests.json` empty across the whole change);
      `tests/experiments_seal/digests.json` reflects exactly the 2.16/2.20-verified declared
      delta and nothing else.

## Total: 62 tasks across 6 phases (Phase 1: 8, Phase 2: 25, Phase 3: 9, Phase 4: 12,
Phase 5: 3, Phase 6: 5)
