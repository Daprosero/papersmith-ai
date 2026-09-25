"""This skill's own second sealed corpus (design.md D7, change
`the-second-skill-the-seam-was-for`, slice A2). Mirrors `tests/seal/corpus.py`'s
own idiom -- a package fixture with and without a `Data/` directory, a
findings module, a documents root -- rewritten with THIS domain's own
vocabulary (`claim_key`/`locus_key`/`remedy_locus_key` = `experiments`,
never `equations`). `tests/seal/` itself is never imported by this module
for its FIXTURE CONTENT (only `tests/seal/harness.py`'s generic
argv/env-building machinery is reused, per design.md D7) -- this corpus
authors its own bytes from nothing, exactly as `proposals/`/`experiments/`
hold only `.gitkeep` on disk.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
from pathlib import Path

_GIT_AUTHOR_DATE = "2026-01-01T00:00:00"
_GIT_COMMITTER_DATE = "2026-01-01T00:00:00"
_GIT_IDENTITY_NAME = "experiments-seal-corpus"
_GIT_IDENTITY_EMAIL = "experiments-seal-corpus@example.invalid"

#: `MANAGED_ARTIFACT_MARKER`, read back exactly as `tests/seal/corpus.py`
#: reads it.
_MANAGED_ARTIFACT_MARKER = b"<!-- proposal-workspace:artifact:v1 -->\n"

#: This domain's own revision text -- no `\tag{}` blocks at all: TAG_RE is a
#: fixed engine-wide LaTeX pattern this domain's own documents never carry
#: (design.md D11 -- `compose`/`admit`/the audit block, the only readers
#: that need it, are excluded from this domain's available surface, D8).
REVISION_TEXT = (
    "## 1\n"
    "\n"
    "The protocol runs step one against a fixed seed.\n"
    "\n"
    "## 2\n"
    "\n"
    "The protocol runs step two and records the outcome.\n"
    "\n"
    "## 3\n"
    "\n"
    "The protocol runs step three and reports.\n"
    "\n"
    "Throughout, the recorded outcome is written E[x].\n"
    "\n"
    "The corrected form now reads g = h + k.\n"
    "\n"
    "This document's own citation syntax cites Exp.(9) once, and again "
    "Exp.(9) a second time.\n"
)

#: `a-data-directory-somebody-can-owe` (B2, design.md D9): document 0's
#: second axis -- a dataset declaration, or its absence. `dataset-0.md`/
#: `dataset-1.md` sit outside the discovered `trial-(\d+)\.md` family
#: (M7's own naming), so neither existing case's discovery changes and
#: no existing revision's bytes change; only these two files are new.
#: Byte-identical except for the ONE trailing `**Dataset:**` line
#: `dataset-1.md` carries and `dataset-0.md` does not -- the smallest
#: difference that could move `with_data` and nothing else.
_DATASET_AXIS_BASE_TEXT = (
    "## 1\n"
    "\n"
    "This revision names no dataset at all.\n"
)
DATASET_UNDECLARED_TEXT = _DATASET_AXIS_BASE_TEXT
DATASET_DECLARED_TEXT = (
    _DATASET_AXIS_BASE_TEXT
    + "\n"
    "**Dataset:** a synthetic corpus authored for this case\n"
)

#: Document 1's own revision text (Slice C, design.md task 4.6) --
#: `documents[1]`'s own root, cited in its OWN citation syntax ("Ec."/
#: "Eq."), never document 0's ("Exp."). Cites the SAME locus
#: (`"9"`, `both-documents-citation`'s own `remedy_experiments`) three
#: times, so the captured `impact.class` genuinely differs from what
#: document 0's own two citations would produce if cross-applied.
PROPOSAL_REVISION_TEXT = (
    "## 1\n"
    "\n"
    "The mathematical proposal states its own identity.\n"
    "\n"
    "This document's own citation syntax cites Ec.(9) once, Eq.(9) again, "
    "and Ecuaciones(9) a third time.\n"
)

#: `the-agreement-nothing-computes` (Slice D, design.md D5/D6, tasks.md
#: 2.10): the corpus's crossing axis -- document 0 citing the
#: `[claims:N]` form, and document 1 (proposal-shaped) declaring the
#: matching `\tag{N}`. Named outside the `trial-(\d+)\.md` family (M7's
#: own naming, like `dataset-0.md`/`trial-t.md`), so no existing case's
#: discovery changes and no existing revision's bytes move.
#:
#: Both directions share ONE target (`PROPOSAL_CROSSING_TEXT`, declaring
#: `\tag{9}` alone) rather than one target per module: `crossing_state`'s
#: own `absent`/`untested` set differences are what tell resolved from
#: disagreeing apart, not two differently-shaped targets (M10's own
#: instruction -- the fixture supplies both directions, and the negative
#: one is the acceptance condition, never a fixture that could only ever
#: satisfy the check).
CROSSING_RESOLVED_TEXT = (
    "## 1\n"
    "\n"
    "This experiment sustains the proposal's own claim, citing [claims:9].\n"
)
CROSSING_DISAGREEMENT_TEXT = (
    "## 1\n"
    "\n"
    "This experiment cites a claim the proposal does not declare: "
    "[claims:5].\n"
)
PROPOSAL_CROSSING_TEXT = (
    "## 1\n"
    "\n"
    "The mathematical proposal declares its own claim as $$a = b \\tag{9}$$.\n"
)

#: `tests/findings.py`'s content: `experiments`/`remedy_experiments` --
#: THIS domain's own `locus_key`/`remedy_locus_key`, never `equations`/
#: `remedy_equations`. Slice C (`the-second-document-verified-on-its-own-
#: terms`, design.md task 4.6): every finding now carries a `document`
#: field -- REQUIRED once `documents[1]` exists (`read_findings`'s own
#: `require_document` gate, unchanged from Cut 3). The first three keep
#: their original text and `document: "experiments"` (document 0 alone);
#: a fourth, `both-documents-citation`, names BOTH documents and is the
#: one this task exists for -- spec `implementation-cli-seal`
#: Requirement "A Declared Second Document's Own Vocabulary Is Exercised,
#: Not Only Its Directory And Label": its locus (`"9"`) is cited multiple
#: times in EACH document's own revision text, in EACH document's own
#: citation syntax ("Exp.(9)" for document 0, "Ec.(9)" for document 1) --
#: proving the captured `impact.class` mapping reads each document's own
#: `citation_pattern`, not one shared across both.
FINDINGS_SOURCE = '''FINDINGS = [
    {
        "id": "adopted-run",
        "kind": "inconsistency",
        "status": "measured",
        "rate": "always",
        "statement": "Step one's outcome omits a correction term.",
        "remedy": "Re-run step one with the corrected seed.",
        "document": "experiments",
        "experiments": ["T1"],
        "remedy_experiments": ["T1"],
        "uses": ["E[x]"],
        "introduces": [],
        "adoption": {"absent": "UNPATCHED_ARTIFACT_MARKER_1",
                      "expect": ["g = h + k"]},
        "becomes_invariant": "identity_one_holds",
    },
    {
        "id": "inline-run",
        "kind": "gap",
        "status": "measured",
        "rate": "always",
        "statement": "Step two's outcome is recorded without its correction.",
        "remedy": "Re-run step two with the corrected form.",
        "document": "experiments",
        "experiments": ["T2"],
        "remedy_experiments": ["T2"],
        "uses": ["E[x]"],
        "introduces": [],
        "adoption": {"absent": "c = d", "expect": ["c = D_corrected"]},
    },
    {
        "id": "structural-run",
        "kind": "gap",
        "status": "measured",
        "rate": "always",
        "statement": "Step three needs a measurement this protocol has never defined.",
        "remedy": "Introduce a new measurement and re-run step three.",
        "document": "experiments",
        "experiments": ["T3"],
        "remedy_experiments": ["T3"],
        "uses": ["E[x]"],
        "introduces": ["Theta-op"],
        "adoption": {"absent": "e = f", "expect": ["e = Theta-op"]},
    },
    {
        "id": "both-documents-citation",
        "kind": "gap",
        "status": "measured",
        "rate": "always",
        "statement": "Both declared documents cite the same locus, each in "
                      "its own notation.",
        "remedy": "No change to either document; this finding exists only "
                   "to prove per-document citation matching against the "
                   "shipped two-document profile.",
        "document": ["experiments", "proposal"],
        "experiments": ["T1"],
        "remedy_experiments": ["9"],
        "uses": [],
        "introduces": [],
    },
]
'''

#: `the-agreement-nothing-computes` (Slice D, design.md D13, tasks.md
#: 1.21): fixture T's OWN revision text, spelled in this domain's own
#: heading form -- a NEW file under the shared documents root
#: (`trial-t.md`), never an edit to `REVISION_TEXT`/`_DATASET_AXIS_BASE_
#: TEXT`/`PROPOSAL_REVISION_TEXT` above, which is what keeps M3's
#: zero-movement prediction for the 24 pre-existing cases true.
FIXTURE_T_REVISION_TEXT = (
    "## 1\n"
    "\n"
    "The protocol's first step currently yields h = k.\n"
)

#: Fixture T's own `tests/findings.py` (design.md D13): its own package,
#: never `fixture_b`'s aliased one. One finding whose locus (`"1"`) IS
#: declared in `FIXTURE_T_REVISION_TEXT` above -- the first case in this
#: corpus where a locus is NOT unknown -- and whose `remedy_block` is
#: written in this domain's own heading block form (`"## 1\n\n..."`),
#: substitutable by `compose`.
FIXTURE_T_FINDINGS_SOURCE = '''FINDINGS = [
    {
        "id": "heading-fix",
        "kind": "inconsistency",
        "status": "measured",
        "rate": "always",
        "statement": "The first step's outcome still carries its "
                      "uncorrected value.",
        "remedy": "Replace the first entry with its corrected form.",
        "document": "experiments",
        "experiments": ["1"],
        "remedy_experiments": ["1"],
        "uses": ["h = k"],
        "introduces": [],
        "adoption": {"absent": "h = k", "expect": ["h = corrected"]},
        "remedy_block": "## 1\\n\\nThe corrected first entry: h = corrected.\\n",
    },
]
'''

_MODULE_SOURCE = (
    '__provenance__ = {\n'
    '    "revision": "trial-1.md", "sections": ["1", "2", "3"],\n'
    '    "experiments": ["T1", "T2", "T3"], "invariants": ["identity_one_holds"],\n'
    '}\n\n\n'
    'def run_once():\n'
    '    return True\n'
)

_BENCHMARK_INIT_SOURCE = (
    "__benchmark__ = {\n"
    "    'arms': {'floor': {'sections': ['1']}, 'full': {'sections': ['1', '2', '3']}},\n"
    "    'search': {},\n"
    "    'report': {},\n"
    "    'distribution': {},\n"
    "    'entry': {'module': 'Trial_Benchmark.steps', 'function': 'run'},\n"
    "}\n"
)

#: `src/Trial/__init__.py`'s content: `__all__` beside `__implementation__`
#: and `__steps__` (design D1/D2, moved off `__benchmark__`).
_IMPLEMENTATION_INIT_SOURCE = (
    "__all__ = []\n"
    "__implementation__ = {\n"
    "    'revision': 'trial-1.md',\n"
    "    'premises': {},\n"
    "}\n"
    "__steps__ = {\n"
    "    'measure': {'module': 'Trial_Benchmark.steps', 'function': 'run'},\n"
    "}\n"
)

_STEPS_MODULE_SOURCE = "def run(*a, **k):\n    return {}\n"

_AGREED_SOURCE = "# Agreed\n\n## Ladder\n\n- [ ] First measurable claim.\n"


@dataclasses.dataclass(frozen=True)
class Roots:
    """Duck-typed against `seal.corpus.Roots` (design.md D7): `run_case`/
    `resolve_argv`/`build_env` reach `.proposals` unconditionally -- the
    engine-wide override variable is literally `IMPLEMENTATION_PROPOSALS`
    for every domain (Cut 2/3 never parameterised its name), so this
    attribute is named `proposals` even though it holds THIS domain's own
    `experiments`-labelled documents root."""

    root: Path
    fixture_a: Path
    fixture_b: Path
    #: `the-agreement-nothing-computes` (Slice D, design.md D13): its own
    #: real package, carrying its own `tests/findings.py`
    #: (`FIXTURE_T_FINDINGS_SOURCE`) -- no longer aliased to `fixture_b`
    #: now that `compose-t`/`admit-t`/`verify-t` name it.
    fixture_t: Path
    proposals: Path
    #: Slice C (design.md task 4.6): `documents[1]`'s own root -- the
    #: mathematical proposal's revision text, never document 0's. Named
    #: `proposals_1` to match `IMPLEMENTATION_PROPOSALS_1`, the env
    #: variable `proposals_root(1)` reads.
    proposals_1: Path
    #: `the-agreement-nothing-computes` (Slice D, corrected this phase):
    #: the crossing axis's own isolated target root (`_build_crossing_
    #: target`) -- never `proposals_1` itself, which stays the default
    #: `trial-plan-v01.md` discovery every OTHER two-document case relies
    #: on unmoved.
    proposals_1_crossing: Path
    plan_template: dict


def _git_env() -> dict:
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = _GIT_IDENTITY_NAME
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = _GIT_IDENTITY_EMAIL
    env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = _GIT_AUTHOR_DATE
    env["GIT_CONFIG_GLOBAL"] = env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return env


def _git_commit(target: Path) -> None:
    env = _git_env()
    subprocess.run(["git", "init", "-q", str(target)], check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=target, env=env, check=True,
                   capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=target, env=env,
                   check=True, capture_output=True)


def _write_common_package(target: Path, *, with_data: bool,
                          findings_source: str = FINDINGS_SOURCE) -> None:
    (target / "src" / "Trial").mkdir(parents=True)
    (target / "src" / "Trial_Benchmark").mkdir(parents=True)
    (target / "tests").mkdir(parents=True)
    (target / "Trial" / "Notebooks").mkdir(parents=True)
    (target / "Trial" / "Results").mkdir(parents=True)
    (target / "Trial" / "Models").mkdir(parents=True)
    if with_data:
        (target / "Trial" / "Data").mkdir(parents=True)

    (target / "src" / "Trial" / "__init__.py").write_text(
        _IMPLEMENTATION_INIT_SOURCE, encoding="utf-8")
    (target / "src" / "Trial" / "kernels.py").write_text(_MODULE_SOURCE, encoding="utf-8")
    (target / "src" / "Trial_Benchmark" / "__init__.py").write_text(
        _BENCHMARK_INIT_SOURCE, encoding="utf-8")
    (target / "src" / "Trial_Benchmark" / "steps.py").write_text(
        _STEPS_MODULE_SOURCE, encoding="utf-8")
    (target / "tests" / "findings.py").write_text(findings_source, encoding="utf-8")
    (target / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (target / "Trial" / "Experimental_AGREED.md").write_text(
        _AGREED_SOURCE, encoding="utf-8")
    _git_commit(target)


def _build_documents(root: Path) -> Path:
    """This domain's own documents root -- unmarked, hand-authored files,
    never `tests/seal/`'s own `proposals/` fixture (this corpus authors its
    own bytes from nothing, design.md D7/tasks.md 2.3)."""
    documents = root / "E"
    documents.mkdir(parents=True)
    (documents / "trial-1.md").write_bytes(
        _MANAGED_ARTIFACT_MARKER + REVISION_TEXT.encode("utf-8"))
    (documents / "trial-2.md").write_bytes(
        _MANAGED_ARTIFACT_MARKER + REVISION_TEXT.encode("utf-8"))
    # B2 (design.md D9): the dataset-declaration axis, named outside the
    # `trial-(\d+)\.md` family on purpose (M7) -- neither file is a
    # candidate for this corpus's own seedless/family discovery, so
    # every existing case's discovered name is unaffected.
    (documents / "dataset-0.md").write_bytes(
        _MANAGED_ARTIFACT_MARKER + DATASET_UNDECLARED_TEXT.encode("utf-8"))
    (documents / "dataset-1.md").write_bytes(
        _MANAGED_ARTIFACT_MARKER + DATASET_DECLARED_TEXT.encode("utf-8"))
    # `the-agreement-nothing-computes` (Slice D, design.md D13): fixture
    # T's own revision -- a NEW file, named outside the `trial-(\d+)\.md`
    # family the same way `dataset-0.md`/`dataset-1.md` are (M7's own
    # naming), so no existing case's discovery changes.
    (documents / "trial-t.md").write_bytes(
        _MANAGED_ARTIFACT_MARKER + FIXTURE_T_REVISION_TEXT.encode("utf-8"))
    # `the-agreement-nothing-computes` (Slice D, design.md D5/D6, tasks.md
    # 2.10): the crossing axis's own document-0 half -- named outside the
    # `trial-(\d+)\.md` family, same reasoning as `dataset-0.md`/
    # `trial-t.md` above.
    (documents / "trial-crossing-resolved.md").write_bytes(
        _MANAGED_ARTIFACT_MARKER + CROSSING_RESOLVED_TEXT.encode("utf-8"))
    (documents / "trial-crossing-disagree.md").write_bytes(
        _MANAGED_ARTIFACT_MARKER + CROSSING_DISAGREEMENT_TEXT.encode("utf-8"))
    return documents


def _build_document_one(root: Path) -> Path:
    """Slice C (design.md task 4.6): `documents[1]`'s own root -- the
    mathematical proposal, hand-authored, never document 0's own
    `_build_documents` fixture."""
    documents = root / "P"
    documents.mkdir(parents=True)
    (documents / "trial-plan-v01.md").write_bytes(
        _MANAGED_ARTIFACT_MARKER + PROPOSAL_REVISION_TEXT.encode("utf-8"))
    return documents


def _build_crossing_target(root: Path) -> Path:
    """`the-agreement-nothing-computes` (Slice D, design.md D5/D6, tasks.md
    2.10 -- corrected this phase): the crossing axis's own target,
    ISOLATED from `_build_document_one`'s shared root.

    Measured this phase, not assumed: the file this fixture originally
    wrote alongside `trial-plan-v01.md` (`trial-plan-crossing.md`) carries
    no digit in its own name, so `discover_document_revision`'s own
    candidate filter (`re.search(r"\\d", candidate.name)`) never selected
    it as a candidate at all -- a fixture the corpus committed but no
    command could ever reach; `crossing_state(0, "trial-crossing-
    resolved.md")` measured `declared: []` against it directly. Naming it
    WITH a digit inside the SAME shared root would not have fixed this:
    two digit-bearing names in one directory become two families
    (`re.sub(r"\\d+", "#", name)` differs for `trial-plan-v#.md` and a
    hypothetical `trial-plan-crossing-#.md`), and `discover_document_
    revision` refuses ambiguity across GATE-e1/OFFER-e1/CLOSE-e1/HANDOFF-
    e1/ADMIT-t -- every one of which discovers document 1 for its own
    unrelated reason and would start refusing `DOCUMENT_REVISION_
    UNREADABLE`. So the crossing target gets its OWN root, its own
    digit-bearing name, resolved only when a case asks for it
    (`crossingTarget`, `harness.py`) -- never the default a bare
    `--revision` on document 0 discovers.
    """
    documents = root / "Pc"
    documents.mkdir(parents=True)
    (documents / "trial-plan-9.md").write_bytes(
        _MANAGED_ARTIFACT_MARKER + PROPOSAL_CROSSING_TEXT.encode("utf-8"))
    return documents


def build(root: Path) -> Roots:
    root.mkdir(parents=True, exist_ok=True)
    fixture_a = root / "A"
    fixture_b = root / "B"
    fixture_t = root / "T"
    fixture_a.mkdir(parents=True)
    fixture_b.mkdir(parents=True)
    fixture_t.mkdir(parents=True)

    _write_common_package(fixture_a, with_data=True)
    _write_common_package(fixture_b, with_data=False)
    # `the-agreement-nothing-computes` (Slice D, design.md D13, task 1.21):
    # fixture T's own `findings.py`, never `fixture_b`'s aliased one -- the
    # aliasing comment named the reason ("no case names it"); that changes
    # here.
    _write_common_package(
        fixture_t, with_data=False, findings_source=FIXTURE_T_FINDINGS_SOURCE)
    documents = _build_documents(root)
    document_one = _build_document_one(root)
    crossing_target = _build_crossing_target(root)

    plan_template = {
        "name": "Trial", "renames": [], "moves": [], "createDirs": [],
        "referenceUpdates": [],
    }

    return Roots(root=root, fixture_a=fixture_a, fixture_b=fixture_b,
                fixture_t=fixture_t, proposals=documents,
                proposals_1=document_one,
                proposals_1_crossing=crossing_target,
                plan_template=plan_template)


#: Digested into `digests.json` under `"__corpus_fingerprint__"`, the same
#: anti-trim guard `tests/seal/`'s own corpus uses.
CORPUS_FINGERPRINT_SOURCE = Path(__file__)
