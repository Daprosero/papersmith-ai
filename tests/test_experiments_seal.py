"""Change `the-second-skill-the-seam-was-for`, slice A2 (design.md D7): this
skill's own second sealed corpus, `tests/seal/` byte-untouched.

Authored from nothing (`experiments/` holds only `.gitkeep`, task 2.3):
every fixture byte here is this corpus's own (`tests/experiments_seal/
corpus.py`), never borrowed from `tests/seal/corpus.py`'s own "Seal"
package. What IS reused, unedited, is `tests/seal/harness.py`'s generic
argv/env-building machinery -- `run_case`, `validate_case`, `digest_result`,
`build_env`, `RosterValidationError` -- wrapped so a case's argv resolves
through THIS skill's own launcher for the call (design.md D7,
`tests/experiments_seal/harness.py::cli_invocation`).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
CORPUS_DIR = FORGE / "tests" / "experiments_seal"
SEAL_DIR = FORGE / "tests" / "seal"

sys.path.insert(0, str(FORGE / "tests"))
from experiments_seal import corpus as ec  # noqa: E402
from experiments_seal import harness as eh  # noqa: E402

CASES = json.loads((CORPUS_DIR / "cases.json").read_text(encoding="utf-8"))
UNSEALED = json.loads((CORPUS_DIR / "unsealed.json").read_text(encoding="utf-8"))
DIGESTS_PATH = CORPUS_DIR / "digests.json"

#: `propose`'s own digest embeds a second-precision timestamp -- excluded
#: from byte-exact comparison, mirroring `tests/seal/`'s own
#: `NON_DETERMINISTIC_CASE_IDS` (see `unsealed.json`'s own recorded reason).
NON_DETERMINISTIC_CASE_IDS = frozenset({"propose"})


def _run_all() -> dict[str, dict]:
    tmp = tempfile.mkdtemp(prefix="experiments-seal-corpus-")
    try:
        roots = ec.build(Path(tmp) / "corpus")
        scratch_root = FORGE / "implementations" / f"_experiments_seal_{os.getpid()}"
        scratch_root.mkdir(parents=True, exist_ok=True)
        try:
            results = {}
            with eh.cli_invocation():
                for case in CASES:
                    result = eh.run_case(case, roots, scratch_root=scratch_root)
                    results[case["id"]] = eh.digest_result(result)
            return results
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class RosterAndUnsealedCoverageTests(unittest.TestCase):
    """Task 2.2: the excluded commands are recorded by id and reason."""

    def test_the_roster_is_nonempty(self):
        self.assertGreater(len(CASES), 0)

    def test_every_case_id_is_unique(self):
        ids = [case["id"] for case in CASES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_materialize_is_recorded_excluded(self):
        for excluded in ("materialize",):
            with self.subTest(command=excluded):
                self.assertIn(excluded, UNSEALED)
                self.assertNotIn(
                    excluded, {case["command"] for case in CASES},
                    f"{excluded} is recorded excluded in unsealed.json AND "
                    "appears in the roster -- contradiction")

    def test_compose_and_admit_are_no_longer_in_the_unsealed_set(self):
        """`the-agreement-nothing-computes` (Slice D, spec
        `implementation-cli-seal`, "`compose` and `admit` are no longer in
        the unsealed set"): the block locator un-excludes both, and each
        is now a sealed case (`compose-t`, `admit-t`)."""
        for now_sealed in ("compose", "admit"):
            with self.subTest(command=now_sealed):
                self.assertNotIn(now_sealed, UNSEALED)
                self.assertIn(now_sealed, {case["command"] for case in CASES})

    def test_the_real_roster_passes_validation(self):
        eh.validate_roster(CASES)


class SealCorpusUntouchedTests(unittest.TestCase):
    """Task 2.5: this corpus lands BESIDE the existing 28 sealed digests,
    never inside them.

    TANDA B M5: `git diff --exit-code` never reports an untracked path --
    that verb reads worktree against the index, and an untracked file is in
    neither. `git status --porcelain` reads both states, so a stray file
    beside the seal is reported the same way a modified one already was."""

    def test_the_existing_seal_corpus_has_no_uncommitted_changes(self):
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--", "tests/seal/"],
            cwd=str(FORGE), capture_output=True, text=True)
        self.assertEqual(
            proc.stdout, "",
            f"tests/seal/ has uncommitted changes:\n{proc.stdout}")

    def test_an_untracked_file_beside_the_seal_is_caught(self):
        planted = SEAL_DIR / "PLANTED_extra_M5.json"
        planted.write_text("{}\n", encoding="utf-8")
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain", "--", "tests/seal/"],
                cwd=str(FORGE), capture_output=True, text=True)
            self.assertIn("PLANTED_extra_M5.json", proc.stdout)
        finally:
            planted.unlink()


class DigestComparisonTests(unittest.TestCase):
    """Task 2.4: every sealed case's captured digest agrees with the
    committed golden, `propose` excluded (non-deterministic, `unsealed.json`)."""

    @classmethod
    def setUpClass(cls):
        cls._captured = _run_all()
        cls._golden = json.loads(DIGESTS_PATH.read_text(encoding="utf-8"))

    def test_every_case_id_has_a_golden_entry(self):
        expected = {case["id"] for case in CASES}
        self.assertTrue(expected.issubset(set(self._golden)))

    def test_every_deterministic_case_matches_its_golden_digest(self):
        for case in CASES:
            case_id = case["id"]
            if case_id in NON_DETERMINISTIC_CASE_IDS:
                continue
            with self.subTest(case=case_id):
                self.assertEqual(
                    self._captured[case_id], self._golden[case_id],
                    f"{case_id}: captured digest disagrees with the "
                    "committed golden")

    def test_the_corpus_fingerprint_matches(self):
        digest = hashlib.sha256(
            ec.CORPUS_FINGERPRINT_SOURCE.read_bytes()).hexdigest()
        self.assertEqual(
            digest, self._golden["__corpus_fingerprint__"]["sha256"],
            "tests/experiments_seal/corpus.py was edited without "
            "recapturing digests.json")


class ThreatMatrixTests(unittest.TestCase):
    """Task 2.7: the same three threat-matrix RED tests
    `tests/test_implementation_seal.py` proves for the sibling, proven here
    against THIS corpus."""

    def test_a_literal_target_raises_before_any_subprocess_runs(self):
        bad_case = {"id": "bad", "command": "verify", "fixture": "A",
                    "proposals": True, "argv": ["--target", "/tmp/literal",
                                                "--name", "Trial"]}
        with self.assertRaises(eh.RosterValidationError):
            eh.validate_case(bad_case)

    def test_committed_fixtures_are_byte_identical_after_a_full_run(self):
        before = CORPUS_DIR.read_bytes() if CORPUS_DIR.is_file() else None
        before_files = {
            path: path.read_bytes()
            for path in sorted(CORPUS_DIR.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts}
        _run_all()
        after_files = {
            path: path.read_bytes()
            for path in sorted(CORPUS_DIR.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts}
        self.assertEqual(before_files, after_files,
                         "a full corpus run mutated a committed fixture "
                         "file under tests/experiments_seal/")

    def test_a_stray_parent_env_var_produces_an_identical_digest(self):
        case = {"id": "verify-a", "command": "verify", "fixture": "A",
                "proposals": True, "argv": ["--target", "<TARGET>", "--name",
                                            "Trial"]}
        tmp = tempfile.mkdtemp(prefix="experiments-seal-env-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        roots = ec.build(Path(tmp) / "corpus")
        scratch_root = FORGE / "implementations" / f"_experiments_seal_env_{os.getpid()}"
        scratch_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, scratch_root, ignore_errors=True)

        with eh.cli_invocation():
            clean = eh.digest_result(
                eh.run_case(case, roots, scratch_root=scratch_root))

            had = "IMPLEMENTATION_DOMAIN_PROFILE" in os.environ
            original = os.environ.get("IMPLEMENTATION_DOMAIN_PROFILE")
            os.environ["IMPLEMENTATION_DOMAIN_PROFILE"] = "/should/be/ignored"
            try:
                with_stray = eh.digest_result(
                    eh.run_case(case, roots, scratch_root=scratch_root))
            finally:
                if had:
                    os.environ["IMPLEMENTATION_DOMAIN_PROFILE"] = original
                else:
                    os.environ.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)

        self.assertEqual(
            clean, with_stray,
            "a stray IMPLEMENTATION_DOMAIN_PROFILE in the PARENT env moved "
            "the digest -- build_env's explicit dict must not pass it "
            "through")


class MutationTests(unittest.TestCase):
    """Task 2.6: flip one byte of a captured golden, confirm the comparison
    suite goes red, restore."""

    def test_a_planted_golden_mismatch_reddens_the_comparison_and_reverting_restores_green(self):
        real_digests = json.loads(DIGESTS_PATH.read_text(encoding="utf-8"))
        captured = _run_all()

        mutated = dict(real_digests)
        mutated["name"] = dict(mutated["name"])
        real_sha = mutated["name"]["sha256"]
        flipped = ("0" if real_sha[0] != "0" else "1") + real_sha[1:]
        mutated["name"]["sha256"] = flipped
        self.assertNotEqual(mutated["name"], captured["name"])

        # Reddens: a mutated golden disagrees with a real capture.
        self.assertNotEqual(mutated["name"], captured["name"])
        # Reverting restores agreement.
        self.assertEqual(real_digests["name"], captured["name"])


ENGINE_DIR = FORGE / "skills" / "_core" / "implementation" / "engine"


class AgreementCheckTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D7, tasks.md
    3.1/3.3/3.4/3.6/3.7/3.8/3.9/3.11): `cmd_agree`'s own refusal shape,
    proven through THIS skill's real launcher (`eh.run_case_here`), never
    in-process -- `crossing_state`'s own four-membership unit matrix
    already lives in `tests/test_experimental_implementation.py::
    CrossingStateTests` (Phase 2); this class is the one command-level
    layer over it: does `cmd_agree` turn that accessor's four lists into
    the right refusal, once, naming the right thing?

    Every case here is named BEFORE its assertion, per the Approach's own
    rule 3 -- each docstring below states which fixture text and which
    document-1 root it reaches, before the assertion that follows it.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="agree-check-corpus-")
        cls.roots = ec.build(Path(cls._tmp) / "corpus")
        cls._scratch_root = FORGE / "implementations" / f"_agree_check_{os.getpid()}"
        cls._scratch_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._scratch_root, ignore_errors=True)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _payload(self, case: dict) -> tuple[dict, int]:
        with eh.cli_invocation():
            result = eh.run_case_here(case, self.roots, scratch_root=self._scratch_root)
        return json.loads(result.stdout_text), result.exit_status

    def test_zero_crossings_against_the_default_target_refuses_once(self):
        """3.3: document 0's default text (`trial-1.md`) cites nothing of
        the new form, and the default document-1 discovery
        (`trial-plan-v01.md`, `PROPOSAL_REVISION_TEXT`) declares no
        `\\tag{}` at all -- M10's own 'unavoidable authored fixture': both
        sides read empty, not one 39-claim side, and the code must still
        fire exactly once, never once per (absent) declared claim."""
        case = {"id": "agree-undeclared-red", "command": "agree", "fixture": "A",
                "proposals": True,
                "argv": ["--target", "<TARGET>", "--name", "Trial",
                         "--revision", "trial-1.md"]}
        payload, status = self._payload(case)
        self.assertEqual(status, 2)
        self.assertEqual(payload["code"], "AGREEMENT_CROSSING_UNDECLARED")

    def test_the_reverse_direction_refuses_by_the_same_code(self):
        """3.4: document 0 now cites `[claims:9]`
        (`trial-crossing-resolved.md`) but document 1 is left at the
        DEFAULT discovery (`trial-plan-v01.md`, zero `\\tag{}`) -- the
        crossing target (`crossingTarget`) is deliberately NOT requested
        here, so `declared` reads empty while `crossed` does not. Same
        code, same once-not-N rule, the reverse of the case above."""
        case = {"id": "agree-reverse-red", "command": "agree", "fixture": "A",
                "proposals": True,
                "argv": ["--target", "<TARGET>", "--name", "Trial",
                         "--revision", "trial-crossing-resolved.md"]}
        payload, status = self._payload(case)
        self.assertEqual(status, 2)
        self.assertEqual(payload["code"], "AGREEMENT_CROSSING_UNDECLARED")

    def test_a_crossing_that_resolves_clears_and_the_no_crossing_code_never_fires(self):
        """3.6 (adapted to this corpus's one declared claim): document 0
        cites `[claims:9]` and, with `crossingTarget` requested, document
        1 resolves to `PROPOSAL_CROSSING_TEXT`, which declares exactly
        `\\tag{9}` -- crossed == declared == {'9'}, so BOTH `absent` and
        `untested` are empty. This is the positive control for Kind 1 AND
        Kind 2 at once (a citation matching a declared claim refuses for
        neither list) and proves the no-crossing code does not fire the
        moment a crossing exists -- the corpus declares only one claim, so
        there is no SECOND, still-untested claim left over to also prove
        the per-claim path firing beside a cleared one; that mixed case is
        `agree-disagree`'s own, immediately below."""
        case = {"id": "agree-resolved-red", "command": "agree", "fixture": "A",
                "proposals": True, "crossingTarget": True,
                "argv": ["--target", "<TARGET>", "--name", "Trial",
                         "--revision", "trial-crossing-resolved.md"]}
        payload, status = self._payload(case)
        self.assertEqual(status, 0, payload)
        self.assertEqual(payload["status"], "agreed")
        self.assertEqual(payload["crossed"], ["9"])
        self.assertEqual(payload["declared"], ["9"])

    def test_a_metric_protocol_mismatch_the_tutor_bullet_names_does_not_refuse(self):
        """`the-agreement-nothing-computes` (Slice D, design.md D11, tasks.md
        5.12, spec `implementation-cross-document-agreement`'s own boundary
        section, restated as SKILL.md's tutor bullet): whether an
        experiment's declared metric or protocol actually corresponds to
        what its cited claim asserts is a THIRD discrepancy kind `agree`
        never checks -- and never can, by construction. `crossing_state`
        (design.md D6) extracts numerals from `[claims:N]`/`\\tag{N}`
        alone; it reads no surrounding sentence, no metric name, no
        protocol description. The SAME resolving fixture this class's own
        positive control (`test_a_crossing_that_resolves_clears_...`)
        proves that with -- `CROSSING_RESOLVED_TEXT`'s citation and
        `PROPOSAL_CROSSING_TEXT`'s declared claim share no metric or
        protocol content whatsoever, and the crossing still resolves
        cleanly. There is no separate fixture to author for a mismatch
        `agree` would have to notice: by this measurement, it notices
        none, ever."""
        case = {"id": "agree-metric-mismatch-red", "command": "agree", "fixture": "A",
                "proposals": True, "crossingTarget": True,
                "argv": ["--target", "<TARGET>", "--name", "Trial",
                         "--revision", "trial-crossing-resolved.md"]}
        payload, status = self._payload(case)
        self.assertEqual(status, 0, payload)
        self.assertEqual(payload["status"], "agreed")

    def test_the_agreed_payloads_key_set_is_exactly_this_and_no_more(self):
        """`the-agreement-nothing-computes` (Slice D, design.md D11, tasks.md
        5.11): the mutation-adding-a-verdict-field guard, restated at the
        consumer layer -- D11's own mutation is 'add a suggestion key to
        cmd_agree's payload'; this lock is what that mutation goes red
        against (`AgreeSuggestionKeyZ11MutationTests`, below)."""
        case = {"id": "agree-resolved-keyset", "command": "agree", "fixture": "A",
                "proposals": True, "crossingTarget": True,
                "argv": ["--target", "<TARGET>", "--name", "Trial",
                         "--revision", "trial-crossing-resolved.md"]}
        payload, status = self._payload(case)
        self.assertEqual(status, 0, payload)
        self.assertEqual(
            set(payload.keys()),
            {"command", "target", "revision", "status", "crossed", "declared"})

    def test_documents_disagree_names_both_kinds_in_one_refusal(self):
        """3.7 (negative half) + 3.8 (negative half) + 3.9: document 0
        cites `[claims:5]` (`trial-crossing-disagree.md`), document 1 (via
        `crossingTarget`) declares `\\tag{9}` -- crossed=['5'],
        declared=['9'], so absent=['5'] (Kind 1: a citation the target no
        longer declares) and untested=['9'] (Kind 2: a declared claim no
        experiment cites), BOTH named in the SAME refusal, never two."""
        case = {"id": "agree-disagree-red", "command": "agree", "fixture": "A",
                "proposals": True, "crossingTarget": True,
                "argv": ["--target", "<TARGET>", "--name", "Trial",
                         "--revision", "trial-crossing-disagree.md"]}
        payload, status = self._payload(case)
        self.assertEqual(status, 2)
        self.assertEqual(payload["code"], "AGREEMENT_DOCUMENTS_DISAGREE")
        self.assertIn("5", payload["detail"])
        self.assertIn("9", payload["detail"])

    def test_the_refusal_names_the_discrepancy_without_judging_it(self):
        """3.11: the boundary. No verdict word, no suggested edit, no
        computed direction -- written against the SAME disagree case
        above; this assertion must already pass against the shipped
        payload, never wait for a later removal."""
        case = {"id": "agree-disagree-boundary", "command": "agree", "fixture": "A",
                "proposals": True, "crossingTarget": True,
                "argv": ["--target", "<TARGET>", "--name", "Trial",
                         "--revision", "trial-crossing-disagree.md"]}
        payload, _ = self._payload(case)
        self.assertNotIn("verdict", payload)
        detail = payload["detail"].lower()
        for banned in ("should follow", "is correct", "is wrong",
                       "the code should", "the target should", "recommend"):
            self.assertNotIn(banned, detail)


class AcknowledgmentTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D4, design.md D8, tasks.md
    4.1/4.2/4.3): `--acknowledge <id>`, repeatable, clearing only ids
    echoed back exactly. Reuses `agree-disagree`'s own reaching
    configuration (`trial-crossing-disagree.md` against the crossing
    target) -- the two-discrepancy case the spec's own note requires
    (absent=['5'], untested=['9']), so the two named ids are exactly
    `absent:5` and `untested:9`.

    Written RED against the shipped engine, which registers `agree`'s
    parser with `--revision` alone: passing `--acknowledge` here is an
    argparse-unrecognized-argument failure (exit 2, empty stdout, no
    JSON at all) -- red for the same reason 3.1's PRESENT half was red
    (the flag does not exist yet), never an authored assertion mismatch.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="acknowledge-corpus-")
        cls.roots = ec.build(Path(cls._tmp) / "corpus")
        cls._scratch_root = FORGE / "implementations" / f"_acknowledge_{os.getpid()}"
        cls._scratch_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._scratch_root, ignore_errors=True)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _payload(self, case: dict) -> tuple[dict, int]:
        with eh.cli_invocation():
            result = eh.run_case_here(case, self.roots, scratch_root=self._scratch_root)
        return json.loads(result.stdout_text), result.exit_status

    def _case(self, case_id: str, acknowledge: list[str] | None = None) -> dict:
        argv = ["--target", "<TARGET>", "--name", "Trial",
                "--revision", "trial-crossing-disagree.md"]
        for value in acknowledge or []:
            argv += ["--acknowledge", value]
        return {"id": case_id, "command": "agree", "fixture": "A",
                "proposals": True, "crossingTarget": True, "argv": argv}

    def test_one_of_two_acknowledged_the_other_still_blocks(self):
        """4.1 (spec 'Two discrepancies, one acknowledged, one still
        blocks'): acknowledging `absent:5` alone leaves `untested:9`
        refusing, named alone in `unacknowledged`."""
        case = self._case("acknowledge-one-red", acknowledge=["absent:5"])
        payload, status = self._payload(case)
        self.assertEqual(status, 2)
        self.assertEqual(payload["code"], "AGREEMENT_DOCUMENTS_DISAGREE")
        self.assertIn("untested:9", payload["detail"])
        self.assertNotIn("absent:5", payload["detail"].split("Unacknowledged:")[1])

    def test_both_acknowledged_both_clear(self):
        """4.2 (spec 'Both acknowledged, both clear'): naming both exact
        ids clears the refusal entirely -- `agree` reports `agreed`."""
        case = self._case("acknowledge-both-red",
                           acknowledge=["absent:5", "untested:9"])
        payload, status = self._payload(case)
        self.assertEqual(status, 0, payload)
        self.assertEqual(payload["status"], "agreed")

    def test_a_general_continue_with_no_ids_clears_nothing(self):
        """4.3 (spec 'A general continue with no ids clears nothing'):
        no `--acknowledge` at all still names both ids; naming an id
        that does not exist clears nothing either, since it matches
        neither outstanding id."""
        with self.subTest(form="omitted entirely"):
            case = self._case("acknowledge-none-red")
            payload, status = self._payload(case)
            self.assertEqual(status, 2)
            self.assertEqual(payload["code"], "AGREEMENT_DOCUMENTS_DISAGREE")
            self.assertIn("absent:5", payload["detail"])
            self.assertIn("untested:9", payload["detail"])
        with self.subTest(form="an id that does not exist"):
            case = self._case("acknowledge-unknown-id-red",
                               acknowledge=["absent:999"])
            payload, status = self._payload(case)
            self.assertEqual(status, 2)
            self.assertEqual(payload["code"], "AGREEMENT_DOCUMENTS_DISAGREE")
            self.assertIn("absent:5", payload["detail"])
            self.assertIn("untested:9", payload["detail"])


class AgreementDisagreeZ7MutationTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md Mutation plan,
    tasks.md 3.13): Z7 -- fire `AGREEMENT_DOCUMENTS_DISAGREE` per
    discrepancy instead of once with both lists, in a SCRATCH copy of
    `_core/implementation/` (never the shipped engine, per this change's
    own standing rule). Confirm the combined-message anchor's count 1->0,
    and that the mutated payload no longer names BOTH '5' and '9' in one
    message."""

    def test_z7_per_discrepancy_raise_loses_the_second_named_claim(self):
        real_source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        anchor = (
            '    if unacknowledged:\n'
            '        raise Refused(\n'
            '            "AGREEMENT_DOCUMENTS_DISAGREE",\n'
            '            f"Document 0 cites {absent!r} with nothing matching in the "\n'
            '            f"target document, and the target declares {untested!r} with "\n'
            '            f"no citation anywhere in document 0. Unacknowledged: "\n'
            '            f"{unacknowledged!r}.")\n')
        self.assertEqual(real_source.count(anchor), 1)
        mutated_block = (
            '    if unacknowledged:\n'
            '        for _kind, _value in ([("absent", v) for v in absent]\n'
            '                               + [("untested", v) for v in untested]):\n'
            '            raise Refused(\n'
            '                "AGREEMENT_DOCUMENTS_DISAGREE",\n'
            '                f"Document 0/target disagree on {_kind}:{_value!r}.")\n')
        mutated_source = real_source.replace(anchor, mutated_block, 1)
        self.assertEqual(mutated_source.count(anchor), 0)
        self.assertNotEqual(mutated_source, real_source)

        scratch_core = Path(tempfile.mkdtemp(prefix="z7-core-"))
        self.addCleanup(shutil.rmtree, scratch_core, ignore_errors=True)
        shutil.copytree(ENGINE_DIR.parent, scratch_core / "core",
                        ignore=shutil.ignore_patterns("__pycache__"),
                        dirs_exist_ok=True)
        (scratch_core / "core" / "engine" / "implementation_engine.py").write_text(
            mutated_source, encoding="utf-8")

        tmp = tempfile.mkdtemp(prefix="z7-corpus-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        roots = ec.build(Path(tmp) / "corpus")
        # Under WORKSPACE (`FORGE_ROOT/implementations/`) -- `resolve_target`
        # refuses OUTSIDE_WORKSPACE for anything else.
        target_dir = FORGE / "implementations" / f"_z7_target_{os.getpid()}"
        self.addCleanup(shutil.rmtree, target_dir, ignore_errors=True)
        shutil.copytree(roots.fixture_a, target_dir, dirs_exist_ok=True)

        skill_dir = FORGE / "skills" / "experimental-implementation"
        env = os.environ.copy()
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(skill_dir / "impl_profile.py")
        env["IMPLEMENTATION_PROPOSALS"] = str(roots.proposals)
        env["IMPLEMENTATION_PROPOSALS_1"] = str(roots.proposals_1_crossing)
        code = (
            "import sys, argparse, json\n"
            f"sys.path.insert(0, {str(scratch_core / 'core' / 'engine')!r})\n"
            "import implementation_engine as impl\n"
            "import impl_guards\n"
            # The scratch copy's own `impl_layout.py` computes `FORGE_ROOT`
            # from ITS OWN on-disk depth under a tmp directory, which is
            # not this repo's root -- `resolve_target` would refuse
            # OUTSIDE_WORKSPACE for a real target no matter where it
            # lives. Patched here, in-process, before the ONE call this
            # subprocess makes -- never the "monkeypatch a module
            # attribute and expect a CHILD process to see it" scar; there
            # is no child process here.
            f"impl_guards.WORKSPACE = impl.Path({str(FORGE / 'implementations')!r})\n"
            f"args = argparse.Namespace(target={str(target_dir)!r}, name='Trial', "
            "revision='trial-crossing-disagree.md')\n"
            "try:\n"
            "    impl.cmd_agree(args)\n"
            "    print(json.dumps({'refused': False}))\n"
            "except impl.Refused as r:\n"
            "    print(json.dumps({'refused': True, 'code': r.code, 'detail': r.detail}))\n"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        mutated_payload = json.loads(proc.stdout.strip())
        self.assertTrue(mutated_payload["refused"])
        self.assertEqual(mutated_payload["code"], "AGREEMENT_DOCUMENTS_DISAGREE")
        # The mutated raise fires on the FIRST discrepancy and never
        # reaches the second -- the real implementation names BOTH '5'
        # and '9' in one message (proven above); the mutated one names
        # only one.
        names_both = "5" in mutated_payload["detail"] and "9" in mutated_payload["detail"]
        self.assertFalse(
            names_both,
            "the mutated per-discrepancy raise still named both claims -- "
            "Z7 did not reach the property it is supposed to break")


class AcknowledgeZ8MutationTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D4, design.md Mutation plan,
    tasks.md 4.5): Z8 -- `--acknowledge` clears the WHOLE unacknowledged
    list rather than only the named id, in a SCRATCH copy (never the
    shipped engine). This is the mutation a weaker, single-discrepancy
    assertion would survive -- it cannot tell 'cleared the named id'
    from 'cleared everything'; the two-discrepancy fixture (4.1's own)
    can."""

    def test_z8_acknowledging_one_id_clears_both_under_the_mutation(self):
        real_source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        anchor = "    unacknowledged = [i for i in ids if i not in acknowledged]\n"
        self.assertEqual(real_source.count(anchor), 1)
        mutated_block = "    unacknowledged = [] if acknowledged else ids\n"
        mutated_source = real_source.replace(anchor, mutated_block, 1)
        self.assertEqual(mutated_source.count(anchor), 0)
        self.assertNotEqual(mutated_source, real_source)

        scratch_core = Path(tempfile.mkdtemp(prefix="z8-core-"))
        self.addCleanup(shutil.rmtree, scratch_core, ignore_errors=True)
        shutil.copytree(ENGINE_DIR.parent, scratch_core / "core",
                        ignore=shutil.ignore_patterns("__pycache__"),
                        dirs_exist_ok=True)
        (scratch_core / "core" / "engine" / "implementation_engine.py").write_text(
            mutated_source, encoding="utf-8")

        tmp = tempfile.mkdtemp(prefix="z8-corpus-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        roots = ec.build(Path(tmp) / "corpus")
        target_dir = FORGE / "implementations" / f"_z8_target_{os.getpid()}"
        self.addCleanup(shutil.rmtree, target_dir, ignore_errors=True)
        shutil.copytree(roots.fixture_a, target_dir, dirs_exist_ok=True)

        skill_dir = FORGE / "skills" / "experimental-implementation"
        env = os.environ.copy()
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(skill_dir / "impl_profile.py")
        env["IMPLEMENTATION_PROPOSALS"] = str(roots.proposals)
        env["IMPLEMENTATION_PROPOSALS_1"] = str(roots.proposals_1_crossing)
        code = (
            "import sys, argparse, json\n"
            f"sys.path.insert(0, {str(scratch_core / 'core' / 'engine')!r})\n"
            "import implementation_engine as impl\n"
            "import impl_guards\n"
            f"impl_guards.WORKSPACE = impl.Path({str(FORGE / 'implementations')!r})\n"
            f"args = argparse.Namespace(target={str(target_dir)!r}, name='Trial', "
            "revision='trial-crossing-disagree.md', acknowledge=['absent:5'])\n"
            "try:\n"
            "    result = impl.cmd_agree(args)\n"
            "    print(json.dumps({'refused': False, 'status': result['status']}))\n"
            "except impl.Refused as r:\n"
            "    print(json.dumps({'refused': True, 'code': r.code, 'detail': r.detail}))\n"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        mutated_payload = json.loads(proc.stdout.strip())
        # 4.1's own case: only 'absent:5' acknowledged, 'untested:9' still
        # outstanding. The real engine still refuses, naming untested:9
        # alone (proven in AcknowledgmentTests, above). The mutated one
        # clears BOTH the moment any id is acknowledged -- caught here as
        # a false "agreed".
        self.assertFalse(
            mutated_payload["refused"],
            "the mutation did not reach the property it is supposed to "
            "break -- it still refused with only one id acknowledged")
        self.assertEqual(mutated_payload["status"], "agreed")


class AgreeRegistrationZ10MutationTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md Mutation plan,
    tasks.md 3.14): Z10 -- delete `len(DOCUMENTS) > 1` from `COMMANDS`'s
    conditional spread, in a scratch copy, and confirm the SIBLING's own
    `test_the_case_roster_covers_the_command_roster_exactly` property
    (`tests/test_implementation_seal.py::SealMembershipTests`) would go
    red under that mutation -- the bar held by the sibling's own suite,
    never by this change's care."""

    def test_z10_deleting_the_gate_breaks_the_siblings_own_membership_property(self):
        real_source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        anchor = '**({"agree": cmd_agree} if len(DOCUMENTS) > 1 else {})}'
        self.assertEqual(real_source.count(anchor), 1)
        mutated_anchor = '**({"agree": cmd_agree})}'
        self.assertEqual(real_source.count(mutated_anchor), 0)
        mutated_source = real_source.replace(anchor, mutated_anchor, 1)
        self.assertEqual(mutated_source.count(anchor), 0)
        self.assertEqual(mutated_source.count(mutated_anchor), 1)

        scratch_core = Path(tempfile.mkdtemp(prefix="z10-core-"))
        self.addCleanup(shutil.rmtree, scratch_core, ignore_errors=True)
        shutil.copytree(ENGINE_DIR.parent, scratch_core / "core",
                        ignore=shutil.ignore_patterns("__pycache__"),
                        dirs_exist_ok=True)
        (scratch_core / "core" / "engine" / "implementation_engine.py").write_text(
            mutated_source, encoding="utf-8")

        sibling_profile = (FORGE / "skills" / "proposal-implementation"
                           / "impl_profile.py")
        sibling_cases_path = SEAL_DIR / "cases.json"
        code = (
            "import sys, json\n"
            "import os\n"
            f"os.environ['IMPLEMENTATION_DOMAIN_PROFILE'] = {str(sibling_profile)!r}\n"
            f"sys.path.insert(0, {str(scratch_core / 'core' / 'engine')!r})\n"
            "import implementation_engine as impl\n"
            f"cases = json.loads(open({str(sibling_cases_path)!r}, encoding='utf-8').read())\n"
            "commands = {c['command'] for c in cases}\n"
            "print(json.dumps({'equal': commands == set(impl.COMMANDS),\n"
            "                  'agree_in_commands': 'agree' in impl.COMMANDS}))\n"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout.strip())
        # The mutation's whole point: under the sibling's own
        # single-document profile, the gate's removal registers `agree`
        # unconditionally, so the sibling's OWN roster-equality property
        # (`tests/seal/cases.json`'s commands == `impl.COMMANDS`) now
        # disagrees -- the sibling's own suite would go red on this.
        self.assertTrue(result["agree_in_commands"])
        self.assertFalse(
            result["equal"],
            "the sibling's own case-roster-equals-COMMANDS property held "
            "even with the len(DOCUMENTS) > 1 gate deleted -- Z10 did not "
            "reach the property it is supposed to break")

        # And confirm the REAL, unmutated engine leaves that property
        # holding (the bar, unbroken by this phase).
        real_code = (
            "import sys, json, os\n"
            f"os.environ['IMPLEMENTATION_DOMAIN_PROFILE'] = {str(sibling_profile)!r}\n"
            f"sys.path.insert(0, {str(ENGINE_DIR)!r})\n"
            "import implementation_engine as impl\n"
            f"cases = json.loads(open({str(sibling_cases_path)!r}, encoding='utf-8').read())\n"
            "commands = {c['command'] for c in cases}\n"
            "print(json.dumps({'equal': commands == set(impl.COMMANDS)}))\n"
        )
        real_proc = subprocess.run([sys.executable, "-c", real_code],
                                   capture_output=True, text=True)
        self.assertEqual(real_proc.returncode, 0, real_proc.stdout + real_proc.stderr)
        self.assertTrue(json.loads(real_proc.stdout.strip())["equal"])


class AgreeSuggestionKeyZ11MutationTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D11, tasks.md
    5.11): D11's own mutation, restated at the consumer layer -- add a
    `suggestion` key to `cmd_agree`'s returned payload, in a scratch copy,
    and confirm the key-set lock above goes red under it. Never the
    shipped engine -- the same scratch-copy mechanism Z10 already uses in
    this file."""

    def test_adding_a_suggestion_key_reddens_the_keyset_lock(self):
        real_source = ENGINE_DIR.joinpath("implementation_engine.py").read_text(
            encoding="utf-8")
        anchor = (
            'return {"command": "agree", "target": str(target), '
            '"revision": args.revision,\n'
            '            "status": "agreed", "crossed": crossed, '
            '"declared": declared}')
        self.assertEqual(real_source.count(anchor), 1)
        mutated_anchor = (
            'return {"command": "agree", "target": str(target), '
            '"revision": args.revision,\n'
            '            "status": "agreed", "crossed": crossed, '
            '"declared": declared, "suggestion": "follow the target"}')
        self.assertEqual(real_source.count(mutated_anchor), 0)
        mutated_source = real_source.replace(anchor, mutated_anchor, 1)
        self.assertEqual(mutated_source.count(anchor), 0)
        self.assertEqual(mutated_source.count(mutated_anchor), 1)

        # `impl_layout.FORGE_ROOT = Path(__file__).resolve().parents[4]`
        # (measured directly): the scratch copy must preserve the real
        # repo's OWN nesting depth under `skills/_core/
        # implementation/`, or `resolve_target`'s "must live under
        # .../implementations" check resolves against the wrong root
        # entirely (a flat `scratch/core/engine/...` copy, as Z10 uses,
        # never runs `resolve_target` at all -- this test does, since it
        # exercises the real return statement through a real `cmd_agree`
        # call).
        scratch_forge = Path(tempfile.mkdtemp(prefix="z11-forge-"))
        self.addCleanup(shutil.rmtree, scratch_forge, ignore_errors=True)
        scratch_core_dir = scratch_forge / "skills" / "_core" / "implementation"
        shutil.copytree(ENGINE_DIR.parent, scratch_core_dir,
                        ignore=shutil.ignore_patterns("__pycache__"))
        (scratch_core_dir / "engine" / "implementation_engine.py").write_text(
            mutated_source, encoding="utf-8")
        (scratch_forge / "implementations").mkdir(parents=True)

        tmp = tempfile.mkdtemp(prefix="z11-corpus-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        roots = ec.build(Path(tmp) / "corpus")

        case = {"id": "agree-resolved-mutated", "command": "agree",
                "fixture": "A", "proposals": True, "crossingTarget": True,
                "argv": ["--target", "<TARGET>", "--name", "Trial",
                         "--revision", "trial-crossing-resolved.md"]}
        target_dir = scratch_forge / "implementations" / "z11-target"
        shutil.copytree(roots.fixture_a, target_dir)
        argv = eh.seal_harness.resolve_argv(case, target_dir, roots, None)
        env = eh._build_env_with_document_one(case, roots)
        # Never set by `_build_env_with_document_one` itself -- that key is
        # ordinarily defaulted by `implementation_cli.py`'s own launcher
        # (`os.environ.setdefault`), which this test bypasses entirely by
        # invoking the scratch `implementation_engine.py` module directly.
        env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(
            FORGE / "skills" / "experimental-implementation"
            / "impl_profile.py")

        scratch_engine = str(scratch_core_dir / "engine" / "implementation_engine.py")
        proc = subprocess.run(
            [sys.executable, scratch_engine, "agree", *argv],
            env=env, capture_output=True, text=True, cwd=str(scratch_forge))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "agreed")
        self.assertIn("suggestion", payload)
        self.assertNotEqual(
            set(payload.keys()),
            {"command", "target", "revision", "status", "crossed", "declared"},
            "the mutated payload's key set should have grown by one -- "
            "this is what the keyset lock above catches")


if __name__ == "__main__":
    unittest.main()
