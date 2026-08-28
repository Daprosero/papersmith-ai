"""Name normalization and reorganization scale — the two v2 gates that are code.

The rest of the v2 flow is orchestration and lives in SKILL.md, where a test cannot
reach it. These two are decisions the CLI makes on its own, so they are pinned here:
what the user types becomes a directory/package pair deterministically, and a plan
declares whether the user can still review it.
"""

import argparse
import ast
import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import unittest.mock
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
CLI = FORGE / ".claude/skills/proposal-implementation/scripts/implementation_cli.py"
sys.path.insert(0, str(CLI.parent))
import implementation_cli as impl  # noqa: E402  (path set above)
# `implementation_cli`'s own import of `impl_layout` etc. already put
# `_core/implementation` on `sys.path`; this reaches the same module the CLI
# reads its position grammar through, never a second copy.
import impl_position  # noqa: E402
import impl_steps  # noqa: E402

SKILL_ROOT = CLI.parent.parent
KIT = SKILL_ROOT / "assets" / "kit"
PYPROJECT_TEMPLATE = SKILL_ROOT / "assets" / "pyproject.template.toml"

SCAFFOLD_TOKENS = ("{{NAME}}", "{{NAME_LOWER}}", "{{PKG}}", "{{SEED}}", "{{REVISION}}")

#: A placeholder as every template spells one. Two classes already carried a copy
#: of this pattern and a third now needs it, so it is stated once and they alias
#: it: three spellings of the same rule is how a token stops being one.
TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

SKILL_MD = SKILL_ROOT / "SKILL.md"
USAGE_MD = SKILL_ROOT / "references" / "usage.md"

#: The remote-execution seam table's header, held in one place so the roster
#: test and the flags/stale-pin test below read the identical table rather
#: than two headers drifting apart from each other.
SEAM_TABLE_HEADER = ("| Subcommand | The reported state that routes here "
                     "| Applicable flags | Where the flags are documented |")

STAGE_ONE_HEADER = "| Gap `plan` and `verify` report | Written from |"
STAGE_TWO_HEADER = "| Written into | Written from |"

ASSET_RE = re.compile(r"`(assets/[^`]+)`")

# The register's domain, and `kit_tokens()`'s, from one definition so the two can
# never drift. Generated artifacts are not assets: `.pytest_cache/` and
# `__pycache__/` appear under `assets/kit/nb/` on any machine that has run the kit
# there. Measured: all six such files are untracked, so there is nothing to
# delete — only a domain to state, so they are never mistaken for unplaced assets.
CACHES = ("__pycache__", ".pytest_cache", ".ipynb_checkpoints")
BINARY_SUFFIXES = (".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".pdf",
                   ".pth", ".npz", ".npy", ".zip", ".ico")

#: Words a target owns that the forge is forbidden to borrow — the floor the
#: derived guard stands on. Being a fixed list, it can only ever hold leaks
#: somebody already found; that is why the derived rules exist beside it rather
#: than instead of it, and why a word here may never be admitted to
#: `FORGE_LEXICON`. Stated once, because two spellings of a floor is how a floor
#: drifts.
FORGE_VOCABULARY_FLOOR = ("kaggle", "t4", "ceiling", "ramp", "transfer",
                          "creda", "milcreda", "latent")


def write_fixture_interpreter(bin_dir):
    """Put an interpreter equivalent to THIS one at `bin_dir/python`.

    A fixture that wants "a venv whose interpreter can import what these
    tests can import" cannot get one from `os.symlink(sys.executable, ...)`.
    CPython resolves the launched path through the WHOLE symlink chain
    before it looks for `pyvenv.cfg`, so a link to a venv's own `python`
    lands on the base interpreter and the venv is silently lost. Measured
    on 2026-08-24, launching through each shape:

        symlink -> sys.prefix = /opt/homebrew/.../python@3.12   (no torch)
        shim    -> sys.prefix = <this venv>                     (torch ok)

    While the suite ran under a system interpreter that happened to carry
    the fixtures' imports ambiently, the symlink was indistinguishable from
    the real thing. It stopped being so the moment the suite moved into a
    virtualenv of its own -- and four tests went red for a reason that had
    nothing to do with what they assert.

    A shim that `exec`s the real path keeps `sys.executable` and
    `sys.prefix` exactly as this process has them, which is the whole
    point of the fixture.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        # `.exe` cannot be shimmed with a shell script; a link is the only
        # shape available, and Windows has no venv-through-symlink problem
        # to work around because it copies rather than links.
        target = bin_dir / "python.exe"
        os.symlink(sys.executable, target)
        return target
    target = bin_dir / "python"
    # `shlex.quote`, not an f-string inside double quotes: POSIX double
    # quotes still expand `$(...)` and backticks. Nothing hostile reaches
    # `sys.executable` here, but a quoting rule that only holds while the
    # input stays friendly is not a quoting rule.
    target.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n",
                      encoding="utf-8")
    target.chmod(0o755)
    return target


def kit_assets(root=None):
    """Every text file under `assets/**` the register has to account for.

    `root` is overridable so the domain rule can be proven against a tree built
    for the purpose, rather than against whatever caches this checkout happens
    to be carrying.
    """
    base = SKILL_ROOT if root is None else Path(root)
    return sorted(
        str(path.relative_to(base))
        for path in (base / "assets").rglob("*")
        if path.is_file()
        and not any(part in CACHES for part in path.parts)
        and path.suffix.lower() not in BINARY_SUFFIXES)


def markdown_table_rows(text, header):
    """Every row of every table introduced by exactly this header line.

    One shape, read one way, wherever doctrine states a placement. Prose cannot
    be held to code — SKILL.md is what an agent reads, not a rendered artifact —
    so the instruction has to be written in something a test can parse.
    """
    lines = [line.strip() for line in text.splitlines()]
    tables = []
    for index, line in enumerate(lines):
        if line != header:
            continue
        rows = []
        for row in lines[index + 2:]:
            if not row.startswith("|"):
                break
            rows.append([cell.strip() for cell in row.strip("|").split("|")])
        tables.append(rows)
    return tables


def returned_keys(source: Path, function: str) -> list[str]:
    """The top-level keys a function's dict returns are built from.

    A command's reported statuses are doctrine's subject and the code's return
    value, and holding one to the other needs the second read from the code
    rather than restated beside it. `ast` rather than calling the function,
    because a command needs a target on disk to run and this needs to be
    answerable about a command nobody invoked.

    **Every** dict return is read, not the first, and they are required to agree.
    That second half is not decoration: a function whose early branches return a
    smaller dict than its late ones makes a key vanish for exactly the callers
    that took the early branch, and nothing else in this suite would notice.

    Returns whose value is not a dict literal are invisible here — a function
    that builds its dict in a variable and returns the name reports nothing, and
    that limitation is stated rather than guessed at.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    definition = next(
        (node for node in ast.walk(tree)
         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
         and node.name == function), None)
    if definition is None:
        raise AssertionError(f"{source.name} defines no {function}")

    # Nested definitions are not descended into: a helper written inside the
    # function returns for itself, and counting its returns here would report
    # somebody else's key set as this function's.
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    returns: list[ast.Return] = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, nested):
                continue
            if isinstance(child, ast.Return):
                returns.append(child)
            visit(child)

    visit(definition)

    key_sets = []
    for node in returns:
        if not isinstance(node.value, ast.Dict):
            continue
        key_sets.append(sorted(
            key.value for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)))
    if not key_sets:
        raise AssertionError(f"{function} returns no dict literal to read")
    if any(keys != key_sets[0] for keys in key_sets):
        raise AssertionError(
            f"{function}'s dict returns do not agree on their keys, so the key "
            "set a caller gets depends on which branch answered: "
            + " vs ".join(str(keys) for keys in key_sets))
    return key_sets[0]


def declared_assets(cell):
    """The kit assets a `Written from` cell names.

    A cell beginning `authored:` names none — the scaffold writes those files
    from what the target already has rather than from a template. Reading such a
    cell's backticks blindly would lift whatever path its sentence happens to
    mention into the register and treat it as an asset that ships.
    """
    if cell.startswith("authored:"):
        return []
    return ASSET_RE.findall(cell)


def scaffold_substitute(text, name="Example-Method", seed="7",
                        revision="research-concept-r01.md"):
    """A template as the scaffold can write it: the five scaffold-time tokens
    answered, and no others.

    One definition, because every caller has to answer them the same way. A
    template whose remaining tokens are stage-2 answers still parses when they
    sit inside a string or a literal, which is exactly the property the stage
    discriminator reads.
    """
    for token, value in zip(SCAFFOLD_TOKENS,
                            (name, name.lower(), name.replace("-", "_"),
                             seed, revision)):
        text = text.replace(token, value)
    return text


def kit_notebook_cells(notebook, name="Example-Method"):
    """Every non-empty code cell of a kit notebook, as the scaffold writes it.

    The tokens are answered first because `{{PKG}}_Benchmark` in an import is
    not Python and would fail to parse for a reason that has nothing to do with
    what is being asserted. The stage-2 tokens are left standing; they sit
    inside strings and literals and parse as they are.
    """
    loaded = json.loads((KIT / "nb" / notebook).read_text(encoding="utf-8"))
    return [(index, scaffold_substitute("".join(cell["source"]), name))
            for index, cell in enumerate(loaded["cells"])
            if cell["cell_type"] == "code" and "".join(cell["source"]).strip()]


def cells_calling(notebook, function, name="Example-Method"):
    """Every code cell of a kit notebook that calls the named function.

    Read as a call and never as a substring: a marker, a path or an exit code
    written in a comment reads exactly like one written in an expression, and a
    cell is what it executes rather than what it mentions. Two classes select
    their subject this way, so the selection is defined once.
    """
    found = []
    for index, source in kit_notebook_cells(notebook, name):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and ast.unparse(node.func).endswith(function)):
                found.append((index, source, tree))
                break
    return found


def gap_path(gap):
    """The path a gap string names.

    Two gaps carry a computed tail — which ignore entries are missing, and which
    anchor the pyproject lacks — so they are matched by the thing they name
    rather than by the sentence they name it in.
    """
    for prefix in (".gitignore", "pyproject.toml"):
        if gap.startswith(prefix):
            return prefix
    return gap


def doctrine_scaffold(case, name="Example-Method", seed="7",
                      revision="research-concept-r01.md", box=None):
    """A target holding exactly the paths `scaffold_gaps` reports as wanted.

    Written gap by gap, the way an agent reading step 5 writes them — never by
    shelling `materialize.py`, which writes a different tree, and whose standing
    in for the doctrine is what let the two drift apart unobserved.

    Each gap resolves to its template by basename under `assets/kit/`, which is
    the mapping step 5's table states file by file. The two authored gaps are
    the exceptions the table itself marks as authored.

    `box` is overridable because `verify` refuses any target outside
    `<forge>/implementations`, so a scaffold the CLI has to read cannot live in
    the system temporary directory the default picks.
    """
    package = name.replace("-", "_")
    if box is None:
        box = Path(tempfile.mkdtemp())
        case.addCleanup(shutil.rmtree, box, ignore_errors=True)
    box = Path(box)

    def substitute(text):
        return scaffold_substitute(text, name, seed, revision)

    templates = {path.name: path for path in sorted(KIT.rglob("*"))
                 if path.is_file() and path.name != "__init__.py"}
    templates["__init__.py"] = KIT / "src_benchmark" / "__init__.py"

    for gap in impl.scaffold_gaps(box, name):
        if gap.startswith(".gitignore"):
            (box / ".gitignore").write_text(
                "".join(f"{entry}\n" for entry in impl.IGNORE_ENTRIES),
                encoding="utf-8")
            continue
        if gap.startswith("pyproject.toml"):
            (box / "pyproject.toml").write_text(
                substitute(PYPROJECT_TEMPLATE.read_text(encoding="utf-8")),
                encoding="utf-8")
            continue
        destination = box / gap
        destination.parent.mkdir(parents=True, exist_ok=True)
        if gap == f"src/{package}/__init__.py":
            # Authored, as the table says: the target's own modules, and step 9
            # has not written any of them yet.
            destination.write_text(
                f'"""Reference implementation of the {name} formulation."""\n\n'
                "__all__ = []\n", encoding="utf-8")
            continue
        destination.write_text(
            substitute(templates[destination.name].read_text(encoding="utf-8")),
            encoding="utf-8")
    return box


class NormalizeNameTests(unittest.TestCase):
    def assertPair(self, raw, directory, package):
        resolved = impl.normalize_name(raw)
        self.assertEqual(resolved["directory"], directory, raw)
        self.assertEqual(resolved["package"], package, raw)

    def test_spaces_become_the_separator_pair(self):
        self.assertPair("mil creda", "Mil-Creda", "Mil_Creda")

    def test_an_acronym_survives_untouched(self):
        # Lowercasing MIL-CREDA renames the method, not the folder.
        self.assertPair("MIL-CREDA", "MIL-CREDA", "MIL_CREDA")

    def test_a_mixed_acronym_keeps_only_the_acronym_uppercase(self):
        self.assertPair("MIL creda", "MIL-Creda", "MIL_Creda")

    def test_camel_case_is_split_at_the_boundary(self):
        self.assertPair("milCreda", "Mil-Creda", "Mil_Creda")

    def test_underscores_and_hyphens_are_the_same_separator(self):
        self.assertPair("mil_creda", "Mil-Creda", "Mil_Creda")
        self.assertPair("mil-creda", "Mil-Creda", "Mil_Creda")

    def test_surrounding_and_repeated_whitespace_is_absorbed(self):
        self.assertPair("  mil   creda  ", "Mil-Creda", "Mil_Creda")

    def test_a_single_word_still_produces_both_forms(self):
        self.assertPair("creda", "Creda", "Creda")

    def test_digits_inside_a_word_are_kept(self):
        self.assertPair("creda v2", "Creda-V2", "Creda_V2")

    def test_a_leading_digit_is_refused_because_no_package_may_start_with_one(self):
        with self.assertRaises(impl.NameRefused):
            impl.normalize_name("2creda")

    def test_an_empty_name_is_refused(self):
        for raw in ("", "   ", None):
            with self.assertRaises(impl.NameRefused):
                impl.normalize_name(raw)

    def test_a_name_with_nothing_but_separators_is_refused(self):
        with self.assertRaises(impl.NameRefused):
            impl.normalize_name("-_-")

    def test_the_package_is_always_importable(self):
        for raw in ("mil creda", "MIL-CREDA", "milCreda", "creda v2", "Creda"):
            package = impl.normalize_name(raw)["package"]
            self.assertTrue(package.isidentifier(), f"{raw} -> {package}")

    def test_normalization_is_idempotent(self):
        # Feeding a normalized name back must not drift it.
        for raw in ("mil creda", "MIL-CREDA", "milCreda"):
            once = impl.normalize_name(raw)
            twice = impl.normalize_name(once["directory"])
            self.assertEqual(once["directory"], twice["directory"], raw)
            self.assertEqual(once["package"], twice["package"], raw)


class NameCommandTests(unittest.TestCase):
    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, cwd=FORGE)
        return json.loads(proc.stdout or "{}"), proc.returncode

    def test_the_command_needs_no_repository_because_it_runs_before_one_exists(self):
        result, code = self.run_cli("name", "--name", "mil creda")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["directory"], "Mil-Creda")
        self.assertEqual(result["package"], "Mil_Creda")

    def test_an_unusable_name_is_refused_with_a_code_not_a_traceback(self):
        result, code = self.run_cli("name", "--name", "2creda")
        self.assertEqual(code, 2, result)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["code"], "NAME_STARTS_WITH_DIGIT")


class PlanScaleTests(unittest.TestCase):
    """`plan` must say whether its own output is still readable before approval."""

    def scale(self, plan, tracked=()):
        with tempfile.TemporaryDirectory() as box:
            original = impl.tracked_files
            impl.tracked_files = lambda _target: list(tracked)
            try:
                return impl.plan_scale(plan, Path(box))
            finally:
                impl.tracked_files = original

    def test_a_short_list_is_reviewable(self):
        result = self.scale({"moves": [{"from": f"f{n}.py", "to": "src/x.py"} for n in range(4)],
                             "renames": [], "referenceUpdates": []})
        self.assertEqual(result["scale"], "reviewable")
        self.assertEqual(result["decisionCount"], 4)

    def test_crossing_the_decision_limit_makes_it_large(self):
        result = self.scale({"moves": [{"from": f"f{n}.py", "to": "src/x.py"} for n in range(16)],
                             "renames": [], "referenceUpdates": []})
        self.assertEqual(result["scale"], "large")

    def test_a_rename_carrying_many_files_is_still_one_decision(self):
        # The whole point: renaming a folder of 200 files is one line the user reads,
        # not 200. Counting the carried files measures blast radius, not reviewability,
        # and would force a separate session for a trivial change.
        tracked = [f"Images/Results/plot{n}.png" for n in range(200)]
        result = self.scale({"moves": [], "renames": [{"from": "Images", "to": "Creda"}],
                             "referenceUpdates": []}, tracked=tracked)
        self.assertEqual(result["decisionCount"], 1)
        self.assertEqual(result["carriedFiles"], 200)
        self.assertEqual(result["scale"], "reviewable")

    def test_reference_rewrites_are_decisions_because_each_edits_a_file(self):
        # These are what a rename really costs: each one can be wrong on its own.
        result = self.scale({"moves": [], "renames": [{"from": "Images", "to": "Creda"}],
                             "referenceUpdates": [{"file": f"src/m{n}.py"} for n in range(20)]})
        self.assertEqual(result["decisionCount"], 21)
        self.assertEqual(result["scale"], "large")

    def test_the_real_repository_shape_stays_reviewable(self):
        # One rename of a product folder plus six reference rewrites: seven lines.
        tracked = [f"Images/Results/plot{n}.png" for n in range(37)]
        result = self.scale({"moves": [], "renames": [{"from": "Images", "to": "Neutral-Method"}],
                             "referenceUpdates": [{"file": f"src/m{n}.py"} for n in range(6)]},
                            tracked=tracked)
        self.assertEqual(result["decisionCount"], 7)
        self.assertEqual(result["carriedFiles"], 37)
        self.assertEqual(result["scale"], "reviewable")

    def test_the_breakdown_and_limit_travel_with_the_answer(self):
        result = self.scale({"moves": [], "renames": [], "referenceUpdates": []})
        self.assertEqual(result["limit"], impl.LARGE_PLAN_DECISIONS)
        self.assertEqual(result["breakdown"], {"moves": 0, "renames": 0, "referenceUpdates": 0})


if __name__ == "__main__":
    unittest.main()


class ProbeStateTests(unittest.TestCase):
    """The probe reads its own state from the repository, and stores nothing else."""

    def repo(self, packages=(), results=None, name="Creda"):
        box = Path(tempfile.mkdtemp(prefix="pp-probe-"))
        for package in packages:
            (box / "src" / package).mkdir(parents=True)
            (box / "src" / package / "mod.py").write_text("x = 1\n")
        if results is not None:
            out = box / name / "Results"
            out.mkdir(parents=True)
            (out / impl.PROBE_RESULTS).write_text(json.dumps(results))
        return box

    def test_a_run_below_the_declared_scale_is_a_pilot_and_not_a_finished_campaign(self):
        # The reduction was always read and returned here; nothing looked at it, so a
        # point estimate from one repetition reported as a completed benchmark.
        box = self.repo(results={
            "revision": "r05.md", "comparison": [{"dimension": "accuracy"}],
            "reduction": {"epochs": 3, "seeds": [0]},
            "targetScale": {"epochs": 20, "seeds": list(range(30))},
        })
        state = impl.probe_state(box, "Creda", "r05.md")
        self.assertEqual(state["status"], "piloted")
        self.assertEqual(state["belowTargetScale"]["seeds"], {"ran": 1, "declared": 30})

    def test_a_run_at_the_declared_scale_is_finished(self):
        box = self.repo(results={
            "revision": "r05.md", "comparison": [{"dimension": "accuracy"}],
            "reduction": {"epochs": 20, "seeds": list(range(30))},
            "targetScale": {"epochs": 20, "seeds": list(range(30))},
        })
        self.assertEqual(impl.probe_state(box, "Creda", "r05.md")["status"], "current")

    def test_a_record_the_checker_wrote_itself_proves_only_half_the_path(self):
        # The join, crossed. Every test above hands `probe_state` a record this file
        # authored, which verifies the reader and says nothing about whether anything
        # produces one — and that is exactly how a repository ended up with a correct
        # summary at a path nobody opens. So: the contract says where the record goes,
        # and the harness the skill ships has to name that same place.
        root = Path(impl.SKILL_ROOT)
        self.assertIn(impl.PROBE_RESULTS, (root / "SKILL.md").read_text(encoding="utf-8"),
                      "the contract must name the file the probe opens")
        harness = (root / "assets/kit/nb" / impl.BENCHMARK_MODULE).read_text(
            encoding="utf-8")
        self.assertIn("--out", harness,
                      "the harness must write the record, not only compute it")

    def test_a_repository_of_placeholders_is_told_apart_from_a_complete_one(self):
        # A clone that skipped the smudge filter looks finished: the paths are all
        # there and every one of them is a few hundred bytes of text. Whatever opens
        # one fails with an error about the file format, nowhere near the reason.
        box = Path(tempfile.mkdtemp(prefix="pp-lfs-"))
        (box / ".gitattributes").write_text("*.pth filter=lfs diff=lfs merge=lfs -text\n")
        (box / "Models").mkdir()
        (box / "Models" / "placeholder.pth").write_bytes(
            impl.LFS_POINTER_PREFIX + b"v1\noid sha256:abc\nsize 1073741824\n")
        (box / "Models" / "real.pth").write_bytes(b"\x80\x02\x8a\nreal weights")

        state = impl.lfs_state(box)
        self.assertEqual(state["status"], "pointers")
        self.assertEqual(state["pointerCount"], 1)
        self.assertEqual(state["materializedCount"], 1)
        self.assertEqual([p["path"] for p in state["pointers"]], ["Models/placeholder.pth"])
        self.assertIn("git lfs pull", state["fetchCommand"])
        # The pointer declares the real size, so the cost is a number rather than a
        # warning. Fetching this one would spend the whole free monthly allowance.
        self.assertEqual(state["bytesToFetch"], 1073741824)
        self.assertIn("1.00 GiB", state["humanBytesToFetch"])
        # And the tempting workaround must be named as not existing: every route
        # costs the same, the browser's download button included.
        self.assertIn("download button", state["quota"])

    def test_a_repository_with_no_lfs_says_so_rather_than_guessing(self):
        box = Path(tempfile.mkdtemp(prefix="pp-lfs-"))
        self.assertEqual(impl.lfs_state(box)["status"], "none")
        (box / ".gitattributes").write_text("*.md text\n")
        self.assertEqual(impl.lfs_state(box)["status"], "none")

    def test_what_exists_is_inspected_even_before_anybody_commits_it(self):
        # The index is the wrong enumerator: a misplaced module invisible until it is
        # committed gets reported after it has entered the history, which is the
        # opposite of useful. Two questions, two sources — does this exist is the
        # disk's to answer, is this part of the record is the ignore rules'.
        box = Path(tempfile.mkdtemp(prefix="pp-present-"))
        subprocess.run(["git", "init", "-q", str(box)], check=True)
        (box / "src" / "Creda").mkdir(parents=True)
        (box / "Creda" / "Notebooks").mkdir(parents=True)
        stray = box / "Creda" / "Notebooks" / "helper.py"
        stray.write_text("x = 1\n")

        self.assertNotIn("Creda/Notebooks/helper.py", impl.tracked_files(box),
                         "nothing has been committed, so the index cannot know")
        self.assertIn("Creda/Notebooks/helper.py", impl.present_files(box),
                      "but it is on disk and nobody said to ignore it")

        (box / ".gitignore").write_text("Creda/Notebooks/helper.py\n")
        self.assertNotIn("Creda/Notebooks/helper.py", impl.present_files(box),
                         "deliberately ignored is not the same as not yet added")

    def test_a_leftover_package_is_the_baseline_a_probe_compares_against(self):
        box = self.repo(packages=["Creda", "legacy"])
        self.assertEqual(impl.previous_implementations(box, "Creda"), ["legacy"])

    def test_our_own_package_is_never_its_own_baseline(self):
        box = self.repo(packages=["Creda"])
        self.assertEqual(impl.previous_implementations(box, "Creda"), [])

    def test_the_hyphen_form_still_resolves_to_our_package(self):
        # <Name>/ is Mil-Creda, src/<Package>/ is Mil_Creda: the pair must not
        # make the implementation look like somebody else's leftover.
        box = self.repo(packages=["Mil_Creda", "legacy"])
        self.assertEqual(impl.previous_implementations(box, "Mil-Creda"), ["legacy"])

    def test_a_directory_with_no_source_is_not_an_implementation(self):
        box = Path(tempfile.mkdtemp(prefix="pp-probe-"))
        (box / "src" / "assets").mkdir(parents=True)
        (box / "src" / "assets" / "notes.md").write_text("nothing here\n")
        self.assertEqual(impl.previous_implementations(box, "Creda"), [])

    def test_our_own_package_is_not_a_baseline_even_spelled_differently(self):
        # macOS folds case, so src/Creda and src/CREDA are one directory: an exact
        # comparison hands our own package back as somebody else's prior work. On a
        # case-sensitive filesystem they are two, but a package differing from ours
        # only in case is a naming accident, not a baseline.
        box = Path(tempfile.mkdtemp(prefix="pp-probe-"))
        (box / "src" / "CREDA").mkdir(parents=True)
        (box / "src" / "CREDA" / "m.py").write_text("x = 1\n")
        self.assertEqual(impl.previous_implementations(box, "Creda"), [])

    def test_a_baseline_that_is_not_python_is_still_a_baseline(self):
        # Prior work arrives in whatever shape it was written in. Requiring .py
        # would make a notebook or MATLAB baseline invisible to the comparison.
        box = Path(tempfile.mkdtemp(prefix="pp-probe-"))
        for package, filename in (("Creda", "m.py"), ("old_matlab", "run.m"),
                                  ("old_notebooks", "study.ipynb")):
            (box / "src" / package).mkdir(parents=True)
            (box / "src" / package / filename).write_text("x\n")
        self.assertEqual(impl.previous_implementations(box, "Creda"),
                         ["old_matlab", "old_notebooks"])

    def test_no_summary_means_no_probe_has_run(self):
        box = self.repo(packages=["Creda"])
        self.assertEqual(impl.probe_state(box, "Creda", "r16.md")["status"], "absent")

    def test_a_summary_naming_the_current_revision_is_current(self):
        box = self.repo(results={"revision": "r16.md", "reduction": {}, "comparison": []})
        self.assertEqual(impl.probe_state(box, "Creda", "r16.md")["status"], "current")

    def test_without_a_revision_to_compare_it_says_unknown_not_stale(self):
        # Reporting "stale" here would assert a state nobody established.
        box = self.repo(results={"revision": "r16.md", "comparison": []})
        self.assertEqual(impl.probe_state(box, "Creda", None)["status"], "unknown")

    def test_a_malformed_comparison_refuses_instead_of_raising(self):
        # The same defect read_findings carried: malformed input must produce a
        # typed refusal, never a traceback.
        box = self.repo(results={"revision": "r16.md", "comparison": "not a list"})
        self.assertEqual(impl.probe_state(box, "Creda", "r16.md")["status"], "unreadable")

    def test_a_summary_naming_an_older_revision_is_stale_by_inspection(self):
        # Nothing is stored to know this: the artifact carries the revision it
        # was obtained under, so staleness is read, not remembered.
        state = impl.probe_state(
            self.repo(results={"revision": "r13.md", "reduction": {}, "comparison": []}),
            "Creda", "r16.md")
        self.assertEqual(state["status"], "stale")
        self.assertEqual(state["revision"], "r13.md")
        self.assertEqual(state["expectedRevision"], "r16.md")

    def test_an_unreadable_summary_refuses_instead_of_reading_as_absent(self):
        box = self.repo(results={"revision": "r16.md"})
        (box / "Creda" / "Results" / impl.PROBE_RESULTS).write_text("{not json")
        self.assertEqual(impl.probe_state(box, "Creda", "r16.md")["status"], "unreadable")

    def test_the_shipped_notebook_template_carries_its_placeholders(self):
        template = (Path(impl.SKILL_ROOT) / "assets/kit/nb" / impl.PROBE_NOTEBOOK)
        self.assertTrue(template.exists(), "the probe notebook must ship with the kit")
        text = template.read_text(encoding="utf-8")
        for token in ("{{NAME}}", "{{BASELINE}}", "{{REVISION}}", "{{PROBE_RESULTS}}",
                      "{{DATASET}}", "{{SEEDS}}"):
            self.assertIn(token, text, token)
        self.assertIn("screening", text, "the notebook must say it is not a benchmark")
        self.assertIn("stratified", text, "the slice must be stratified, and say why")
        # The notebook must RUN the harness. A notebook that only describes a
        # comparison is a form, and handing back a form is not the capability.
        self.assertIn(impl.BENCHMARK_MODULE, text,
                      "the notebook must drive the benchmark, not describe it")
        self.assertIn("subprocess", text, "it has to actually execute something")
        self.assertIn("parents[1]", text,
                      "the output path must be anchored to the repository, never a "
                      "bare ../ that resolves outside it")


class BackendStateTests(unittest.TestCase):
    """numpy cannot be trained, so the backend decides whether a benchmark can run."""

    def repo(self, package_files=(), test_files=(), name="Creda"):
        box = Path(tempfile.mkdtemp(prefix="pp-backend-"))
        pkg = box / "src" / impl.package_name(name)
        pkg.mkdir(parents=True)
        (box / "tests").mkdir()
        for filename, source in package_files:
            (pkg / filename).write_text(source)
        for filename, source in test_files:
            (box / "tests" / filename).write_text(source)
        return box

    def test_numpy_only_is_not_trainable(self):
        state = impl.backend_state(
            self.repo([("kernel.py", "import numpy as np\n")]), "Creda")
        self.assertEqual(state["state"], "numpy")
        self.assertFalse(state["trainable"])

    def test_torch_is_trainable(self):
        state = impl.backend_state(
            self.repo([("kernel.py", "import torch\n")]), "Creda")
        self.assertEqual(state["state"], "tensor")
        self.assertTrue(state["trainable"])

    def test_a_half_converted_repository_is_mixed_and_not_trainable(self):
        # The dangerous state: modules train while the tests still assert over
        # numpy, so the suite passes while measuring what the model never touched.
        state = impl.backend_state(
            self.repo([("kernel.py", "import torch\n")],
                      [("test_kernel.py", "import numpy as np\n")]), "Creda")
        self.assertEqual(state["state"], "mixed")
        self.assertFalse(state["trainable"])
        self.assertTrue(state["numpyFiles"] and state["tensorFiles"])

    def test_an_unparsable_file_does_not_crash_the_reading(self):
        state = impl.backend_state(
            self.repo([("broken.py", "def (:\n")]), "Creda")
        self.assertEqual(state["state"], "unknown")

    def test_the_benchmark_harness_ships_with_the_kit_and_compiles(self):
        import ast
        harness = Path(impl.SKILL_ROOT) / "assets/kit/nb" / impl.BENCHMARK_MODULE
        self.assertTrue(harness.exists(), "the benchmark must ship with the kit")
        source = harness.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("stratified_indices", source, "the slice must be stratified")
        self.assertIn("stdev", source, "a bare mean over seeds hides what seeds reveal")
        # This test used to require the harness to name resnet18, CIFAR10, CIFAR100
        # and MNIST. It was asserting the defect: a catalogue here dictates the
        # experiment instead of serving it. The opposite is now pinned in
        # InterpreterGuardTests.test_the_harness_names_no_dataset_and_no_backbone_of_its_own.


sys.path.insert(0, str(CLI.parent.parent / "assets/kit/nb"))
import verdict as vd  # noqa: E402


class VerdictTests(unittest.TestCase):
    """Values are not an answer. These rules turn them into one, or refuse to."""

    def spread(self, mean, stdev=0.0, n=10):
        return {"mean": mean, "stdev": stdev, "n": n}

    def test_a_clear_gap_names_the_winner(self):
        result = vd.decide(self.spread(0.60, 0.01), self.spread(0.80, 0.01), vd.HIGHER)
        self.assertEqual(result["winner"], "new")

    def test_direction_decides_who_wins_not_the_larger_number(self):
        # Lower is better for time: the smaller side wins.
        result = vd.decide(self.spread(120.0, 1.0), self.spread(40.0, 1.0), vd.LOWER)
        self.assertEqual(result["winner"], "new")
        result = vd.decide(self.spread(40.0, 1.0), self.spread(120.0, 1.0), vd.LOWER)
        self.assertEqual(result["winner"], "baseline")

    def test_overlapping_means_are_indistinguishable_not_a_win(self):
        # The whole reason several seeds are run. Two bare means always differ at
        # enough decimal places, and calling that a result is reading noise aloud.
        result = vd.decide(self.spread(0.700, 0.05), self.spread(0.702, 0.05), vd.HIGHER)
        self.assertEqual(result["winner"], vd.TIE)

    def test_more_seeds_can_turn_a_tie_into_a_verdict(self):
        # Same means and spread, more repetitions: the standard error shrinks.
        loose = vd.decide(self.spread(0.70, 0.06, n=3), self.spread(0.76, 0.06, n=3), vd.HIGHER)
        tight = vd.decide(self.spread(0.70, 0.06, n=200), self.spread(0.76, 0.06, n=200), vd.HIGHER)
        self.assertEqual(loose["winner"], vd.TIE)
        self.assertEqual(tight["winner"], "new")

    def test_below_the_floor_the_threshold_inverts_so_no_verdict_is_granted(self):
        # One repetition gives a dispersion of zero, hence a threshold of zero, hence
        # a winner on every row from a bare difference — the rule turning into its
        # own opposite exactly where the protection matters most.
        alone = vd.decide(self.spread(0.72, 0.0, n=1), self.spread(0.78, 0.0, n=1), vd.HIGHER)
        self.assertEqual(alone["winner"], vd.UNRESOLVED)
        self.assertAlmostEqual(alone["margin"], 0.06)
        self.assertIn("point estimate", alone["reason"])

    def test_the_measurement_is_still_reported_when_the_verdict_is_withheld(self):
        # Suppressing the table would make the pilot a different program from the
        # campaign, which is the one thing the pilot may not be.
        rows = [{"dimension": "accuracy", "better": vd.HIGHER,
                 "baseline": self.spread(0.72, 0.0, n=1),
                 "new": self.spread(0.78, 0.0, n=1)}]
        rendered = vd.render(vd.judge(rows), {"seeds": 1})
        self.assertIn("0.72", rendered)
        self.assertIn("0.78", rendered)
        self.assertIn("point estimates, not verdicts", rendered)

    def test_a_missing_side_is_not_applicable_never_a_walkover(self):
        self.assertEqual(vd.decide(None, self.spread(0.9), vd.HIGHER)["winner"],
                         vd.NOT_APPLICABLE)
        self.assertEqual(vd.decide(self.spread(0.9), None, vd.HIGHER)["winner"],
                         vd.NOT_APPLICABLE)

    def test_a_descriptive_dimension_is_reported_and_not_contested(self):
        result = vd.decide(self.spread(11_000_000), self.spread(240_000), vd.DESCRIPTIVE)
        self.assertIsNone(result["winner"])

    def test_the_tally_says_where_each_side_wins(self):
        rows = [
            {"dimension": "accuracy", "better": vd.HIGHER,
             "baseline": self.spread(0.60, 0.01), "new": self.spread(0.80, 0.01)},
            {"dimension": "seconds", "better": vd.LOWER,
             "baseline": self.spread(10.0, 0.1), "new": self.spread(40.0, 0.1)},
            {"dimension": "peakMiB", "better": vd.LOWER,
             "baseline": self.spread(100.0, 20.0), "new": self.spread(101.0, 20.0)},
        ]
        counts = vd.tally(vd.judge(rows))
        self.assertEqual(counts["new"], ["accuracy"])
        self.assertEqual(counts["baseline"], ["seconds"])
        self.assertEqual(counts[vd.TIE], ["peakMiB"])

    def test_the_table_carries_the_reduction_and_a_winner_column(self):
        rows = [{"dimension": "accuracy", "better": vd.HIGHER,
                 "baseline": self.spread(0.60, 0.01), "new": self.spread(0.80, 0.01)}]
        text = vd.render(vd.judge(rows), {"setting": "trained", "backbone": "resnet18",
                                          "dataset": "CIFAR10", "seeds": 5,
                                          "revision": "r16.md"})
        for token in ("trained", "resnet18", "CIFAR10", "r16.md", "winner", "new"):
            self.assertIn(token, text, token)

    def test_both_settings_share_these_rules(self):
        # A synthetic sweep and a trained run measure different instruments and
        # answer the same question, so they share one shape and one verdict rule.
        synthetic = {"dimension": "separation d", "better": vd.HIGHER,
                     "baseline": self.spread(4.36, 0.10), "new": self.spread(3.29, 0.10)}
        trained = {"dimension": "accuracy", "better": vd.HIGHER,
                   "baseline": self.spread(0.60, 0.01), "new": self.spread(0.80, 0.01)}
        judged = vd.judge([synthetic, trained])
        self.assertEqual(judged[0]["verdict"]["winner"], "baseline")
        self.assertEqual(judged[1]["verdict"]["winner"], "new")


class WiringProposalTests(unittest.TestCase):
    """The gap where a comparison belongs is a proposal, not a placeholder."""

    def repo(self, modules=(), baseline_files=(), name="Creda"):
        box = Path(tempfile.mkdtemp(prefix="pp-wiring-"))
        pkg = box / "src" / impl.package_name(name)
        pkg.mkdir(parents=True)
        for filename, source in modules:
            (pkg / filename).write_text(source)
        for path in baseline_files:
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("x = 1\n")
        return box

    MODULE = ('__provenance__ = {"revision": "r16.md", "sections": ["5"],\n'
              '                  "equations": ["32", "33"], "invariants": ["bounded"]}\n')

    def test_the_draft_is_assembled_from_provenance_not_guessed(self):
        box = self.repo(modules=[("global_term.py", self.MODULE)],
                        baseline_files=["src/CREDA/models.py"])
        draft = impl.wiring_proposal(box, "Creda", ["CREDA"])
        module = draft["new"]["modules"][0]
        self.assertEqual(module["sections"], ["5"])
        self.assertEqual(module["equations"], ["32", "33"])
        self.assertEqual(module["invariants"], ["bounded"])

    def test_it_says_what_it_needs_from_the_user_rather_than_deciding(self):
        draft = impl.wiring_proposal(self.repo(), "Creda", [])
        self.assertEqual(draft["status"], "draft")
        needs = " ".join(draft["new"]["needs"] + draft["baseline"]["needs"]).lower()
        for asked in ("trainable terms", "backbone", "head", "entry point"):
            self.assertIn(asked, needs, asked)

    def test_the_offer_starts_from_what_the_baseline_already_trains_on(self):
        # Not a list somebody guessed about the field: what this repository does.
        box = self.repo(baseline_files=["src/CREDA/models.py"])
        (box / "src/CREDA/models.py").write_text(
            "from torchvision import models\n"
            "def build():\n"
            "    return models.resnet50(weights=None)\n")
        draft = impl.wiring_proposal(box, "Creda", ["CREDA"])
        found = [b["name"] for b in draft["offer"]["fromBaseline"]["backbones"]]
        self.assertEqual(found, ["resnet50"])
        # Nothing is suggested from a list: a forge for papers cannot know which
        # models are reasonable for a field it has not read.
        self.assertNotIn("lighterAlternatives", draft["offer"])

    def test_the_baseline_is_offered_as_a_candidate_never_as_editable(self):
        box = self.repo(baseline_files=["src/CREDA/models.py", "src/CREDA/train.py"])
        draft = impl.wiring_proposal(box, "Creda", ["CREDA"])
        candidate = draft["baseline"]["candidates"][0]
        self.assertEqual(candidate["package"], "CREDA")
        self.assertEqual(len(candidate["files"]), 2)
        self.assertIn("never modified", " ".join(draft["baseline"]["needs"]))

    def test_the_harness_refuses_without_wiring_instead_of_training_a_bare_backbone(self):
        # The defect this replaces: a placeholder that trained a generic backbone,
        # reported the baseline as not applicable, and produced a table about nothing.
        harness = (Path(impl.SKILL_ROOT) / "assets/kit/nb" / impl.BENCHMARK_MODULE)
        source = harness.read_text(encoding="utf-8")
        self.assertIn("wiring.py is missing", source)
        self.assertIn("SystemExit", source, "a missing wiring must stop the run")
        self.assertNotIn('"baseline": None,', source,
                         "the baseline must never be hardcoded as not applicable")


class BaselineEnvironmentTests(unittest.TestCase):
    """Read the environment the prior results were obtained in, do not assume one."""

    def repo(self, files):
        box = Path(tempfile.mkdtemp(prefix="pp-env-"))
        for path, source in files.items():
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(source)
        return box

    def test_a_called_module_attribute_is_a_backbone(self):
        box = self.repo({"src/CREDA/models.py":
                         "from torchvision import models\n"
                         "net = models.resnet50(weights=None)\n"})
        found = [b["name"] for b in impl.baseline_environment(box, ["CREDA"])["backbones"]]
        self.assertEqual(found, ["resnet50"])

    def test_a_method_call_on_an_instance_is_not_a_backbone(self):
        # The distinction that decides whether the reading is useful at all: matching
        # on the holder alone buries the real names under every .eval() and .to().
        box = self.repo({"src/CREDA/train.py":
                         "def run(model, device):\n"
                         "    model.eval()\n"
                         "    model.to(device)\n"
                         "    model.parameters()\n"})
        self.assertEqual(impl.baseline_environment(box, ["CREDA"])["backbones"], [])

    def test_dataset_names_are_read_from_the_baselines_own_vocabulary(self):
        box = self.repo({"src/CREDA/artifacts.py":
                         'DATASETS = ["MNIST-USPS-SVHN", "Office-Caltech", "ImageCLEF"]\n'})
        found = [d["name"] for d in impl.baseline_environment(box, ["CREDA"])["datasets"]]
        self.assertEqual(found, ["ImageCLEF", "MNIST-USPS-SVHN", "Office-Caltech"])

    def test_ordinary_words_near_a_dataset_variable_are_not_datasets(self):
        box = self.repo({"src/CREDA/train.py":
                         'dataset_keys = ["classes", "labels", "domain", "loader"]\n'})
        self.assertEqual(impl.baseline_environment(box, ["CREDA"])["datasets"], [])

    def test_the_data_entry_points_are_found_because_a_name_is_not_a_loader(self):
        # Naming Office-Caltech says what was measured; load_office_caltech() says
        # how to measure it again. The wiring needs the second one.
        box = self.repo({"src/CREDA/pipeline.py":
                         "def split_stratified(dataset, val_ratio):\n    return dataset\n"
                         "def load_dataset_results(backbone, dataset):\n    return None\n"
                         "def train_model(x):\n    return x\n"})
        found = impl.baseline_environment(box, ["CREDA"])["dataEntryPoints"]
        names = sorted(e["function"] for e in found)
        self.assertEqual(names, ["load_dataset_results", "split_stratified"])
        self.assertIn("dataset", found[0]["args"] + found[1]["args"])

    def test_notebooks_outside_the_proposal_are_prior_experiments(self):
        box = self.repo({"src/CREDA/m.py": "x = 1\n",
                         "CREDA/Notebooks/Results_Generator.ipynb": "{}",
                         "MIL-CREDA/Notebooks/probe.ipynb": "{}"})
        found = impl.baseline_environment(box, ["CREDA"], "MIL-CREDA")["notebooks"]
        self.assertEqual(found, ["CREDA/Notebooks/Results_Generator.ipynb"],
                         "the proposal's own notebooks are not prior work")

    def test_trained_weights_left_behind_are_reported(self):
        box = self.repo({"src/CREDA/m.py": "x = 1\n",
                         "Creda/Models/resnet50/resnet50_ADDA.pth": "binary"})
        self.assertEqual(impl.baseline_environment(box, ["CREDA"])["weights"],
                         ["resnet50_ADDA.pth"])

    def test_an_empty_baseline_says_it_discovered_nothing(self):
        box = self.repo({"src/CREDA/m.py": "x = 1\n"})
        self.assertFalse(impl.baseline_environment(box, ["CREDA"])["discovered"])


class InterpreterGuardTests(unittest.TestCase):
    """The benchmark must run under the repository's own interpreter, or not at all."""

    KIT = None  # set in setUp

    def setUp(self):
        self.KIT = Path(impl.SKILL_ROOT) / "assets/kit/nb"

    def stage(self, root_name="repo"):
        """Lay the harness out where doctrine puts it: <repo>/src/<Package>_Benchmark/.

        `environment()` says that address in prose and then derives the repository
        as `parents[2]`, which is exactly this depth. It reached a repository root
        from `<Name>/Notebooks/` too, and that coincidence is the whole reason the
        two placements could disagree without anything going red.
        """
        box = Path(tempfile.mkdtemp(prefix="pp-interp-"))
        bench = box / root_name / "src" / "Example_Method_Benchmark"
        bench.mkdir(parents=True)
        for asset in (impl.BENCHMARK_MODULE, "verdict.py"):
            shutil.copy(self.KIT / asset, bench / asset)
        (bench / "config.json").write_text("{}")
        return box / root_name, bench

    def run_harness(self, bench, executable=sys.executable):
        return subprocess.run(
            [executable, impl.BENCHMARK_MODULE, "--config", "config.json",
             "--out", "out.json"],
            cwd=str(bench), capture_output=True, text=True)

    def test_a_foreign_interpreter_is_refused_before_anything_is_measured(self):
        # Not hygiene: wall time and peak memory ARE the measurement, so another
        # interpreter measures a different environment correctly and the summary
        # would attribute it to this repository.
        repository, bench = self.stage()
        proc = self.run_harness(bench)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("refusing to run under", proc.stdout + proc.stderr)
        self.assertFalse((bench / "out.json").exists(),
                         "a refused run must not leave a summary behind")

    def test_the_refusal_names_the_interpreter_the_user_should_use(self):
        """The refusal is built from `parents[2]`, so it also pins that the new
        depth still resolves to the repository and not to `src/`."""
        repository, bench = self.stage()
        output = "".join([self.run_harness(bench).stdout,
                          self.run_harness(bench).stderr])
        self.assertIn(str(repository / ".venv"), output,
                      "a refusal that does not say what to run instead is a dead end")

    def test_the_guard_runs_before_the_missing_wiring_is_reported(self):
        # Order matters: under a foreign interpreter the wiring question is not yet
        # the user's problem, and reporting it first would send them to fix the
        # wrong thing.
        repository, bench = self.stage()
        output = self.run_harness(bench).stdout + self.run_harness(bench).stderr
        self.assertIn("refusing to run under", output)
        self.assertNotIn("wiring.py is missing", output)

    def test_the_contract_and_the_harness_agree_that_it_is_enforced(self):
        source = (self.KIT / impl.BENCHMARK_MODULE).read_text(encoding="utf-8")
        self.assertIn("def environment(", source)
        self.assertIn("sys.prefix", source, "the check must look at the running prefix")
        # The relaxation for notebook services must be a positive test for one, never
        # an inference from a missing virtualenv: a repository where nobody has made
        # one yet also lacks it, and there the guard is exactly right to refuse.
        self.assertIn("def hosted_runtime(", source)
        self.assertNotIn('".venv").is_dir()', source)

    def test_the_harness_names_no_dataset_and_no_backbone_of_its_own(self):
        # A catalogue here would dictate the experiment: the wiring would be forced
        # to pick whichever well-known set the baseline happens to touch, and the
        # "common environment" would be an intersection with somebody's list rather
        # than the environment the prior results came from.
        source = (self.KIT / impl.BENCHMARK_MODULE).read_text(encoding="utf-8")
        for name in ("CIFAR10", "CIFAR100", "MNIST", "torchvision", "resnet18"):
            self.assertNotIn(name, source,
                             f"{name} is named by the harness: the data and the model "
                             f"must come from the wiring")
        self.assertIn("build_data", source, "the data has to arrive from the wiring")


class DiscoveryHonestyTests(unittest.TestCase):
    """An empty reading must announce itself as a miss, never as a clean result."""

    def repo(self, files):
        box = Path(tempfile.mkdtemp(prefix="pp-honest-"))
        for path, source in files.items():
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(source)
        return box

    def test_paths_and_names_are_discovered_not_assumed(self):
        # A different field, a different package, different file names: the reading
        # is over structure, so none of it is anchored to any one repository.
        box = self.repo({"src/LegacyTransformer/corpus_io.py":
                         "from torchvision import models\n"
                         "def load_corpus(name):\n    return None\n"
                         "def prepare_splits(corpus):\n    return corpus\n"
                         "def build():\n    return models.vgg16(weights=None)\n",
                         "LegacyTransformer/Notebooks/Experiments.ipynb": "{}",
                         "Method/Notebooks/mine.ipynb": "{}"})
        env = impl.baseline_environment(box, ["LegacyTransformer"], "Method")
        self.assertEqual([b["name"] for b in env["backbones"]], ["vgg16"])
        self.assertEqual(sorted(e["function"] for e in env["dataEntryPoints"]),
                         ["load_corpus", "prepare_splits"])
        self.assertEqual(env["notebooks"], ["LegacyTransformer/Notebooks/Experiments.ipynb"])

    def test_what_it_could_not_read_is_named_rather_than_returned_empty(self):
        # `CORPORA` misses the stem `corpus`, and a Spanish name misses everything.
        # Returning [] would read as "this baseline has no data layer", which is a
        # conclusion the reading never established.
        box = self.repo({"src/Legacy/io.py":
                         'CORPORA = ["WikiText-103"]\n'
                         "def cargar_datos(x):\n    return x\n"})
        env = impl.baseline_environment(box, ["Legacy"], "Method")
        self.assertIn("datasets", env["foundNothingFor"])
        self.assertIn("dataEntryPoints", env["foundNothingFor"])
        self.assertTrue(env["note"], "a miss with no explanation is indistinguishable "
                                     "from an absence")
        self.assertIn("another language", env["note"])

    def test_it_says_how_it_looked_so_the_user_can_point_at_what_it_missed(self):
        box = self.repo({"src/Legacy/io.py": "x = 1\n"})
        env = impl.baseline_environment(box, ["Legacy"], "Method")
        for kind in ("backbones", "datasets", "dataEntryPoints", "notebooks"):
            self.assertIn(kind, env["readBy"], kind)

    def test_a_full_reading_leaves_the_note_empty(self):
        box = self.repo({"src/Legacy/io.py":
                         "from torchvision import models\n"
                         'DATASETS = ["Some-Task"]\n'
                         "def load_data(x):\n    return x\n"
                         'SOURCE = "https://example.org/corpus.zip"\n'
                         "def build():\n    return models.vgg16()\n",
                         "Legacy/Notebooks/e.ipynb": "{}"})
        env = impl.baseline_environment(box, ["Legacy"], "Method")
        self.assertEqual(env["foundNothingFor"], [])
        self.assertEqual(env["note"], "")


class BackendIsAStageTests(unittest.TestCase):
    """numpy is where the mathematics is proved, not a defect to be fixed."""

    def repo(self, backend="numpy", baseline=False, name="Method"):
        box = Path(tempfile.mkdtemp(prefix="pp-stage-"))
        pkg = box / "src" / impl.package_name(name)
        pkg.mkdir(parents=True)
        (box / "tests").mkdir()
        source = "import torch\n" if backend == "tensor" else "import numpy as np\n"
        (pkg / "k.py").write_text(source)
        (box / "tests" / "test_k.py").write_text(source)
        if baseline:
            (box / "src" / "Prior").mkdir()
            (box / "src" / "Prior" / "m.py").write_text("x = 1\n")
        return box

    def step(self, box, name="Method", revision="r16.md"):
        backend = impl.backend_state(box, name)
        baselines = impl.previous_implementations(box, name)
        state = impl.probe_state(box, name, revision)
        if not baselines:
            return "nothing-to-compare"
        if not backend["trainable"]:
            return "convert"
        return "already-benchmarked" if state["status"] == "current" else "benchmark"

    def test_numpy_without_a_baseline_is_finished_not_unconverted(self):
        # Asking for a conversion here would demand work with no purpose and read as
        # though the implementation were unfinished when it is done.
        self.assertEqual(self.step(self.repo("numpy", baseline=False)),
                         "nothing-to-compare")

    def test_numpy_with_a_baseline_needs_converting_because_it_cannot_train(self):
        self.assertEqual(self.step(self.repo("numpy", baseline=True)), "convert")

    def test_torch_without_a_baseline_is_still_nothing_to_compare(self):
        self.assertEqual(self.step(self.repo("tensor", baseline=False)),
                         "nothing-to-compare")

    def test_the_reading_itself_does_not_care_which_backend_it_finds(self):
        # verify is static: provenance, invariant ids, trivial assertions. Only
        # backend_state looks at numpy or torch, and that is its whole job.
        for backend in ("numpy", "tensor"):
            state = impl.backend_state(self.repo(backend), "Method")
            self.assertEqual(state["state"], backend)
            self.assertEqual(state["trainable"], backend == "tensor")


class AcquisitionTests(unittest.TestCase):
    """Absent until something runs is not the same as impossible to obtain."""

    def repo(self, files):
        box = Path(tempfile.mkdtemp(prefix="pp-acq-"))
        for path, source in files.items():
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(source)
        return box

    def notebook(self, *cells):
        return json.dumps({"cells": [{"cell_type": "code", "source": [c]} for c in cells],
                           "nbformat": 4, "nbformat_minor": 5, "metadata": {}})

    def test_a_notebook_is_read_not_merely_listed(self):
        # The package resolves a directory it never creates; what creates it is here.
        box = self.repo({"src/Prior/paths.py":
                         'def resolve_root():\n    return "/mounted/somewhere"\n',
                         "Prior/Notebooks/Bootstrap.ipynb": self.notebook(
                             'run_command("git", "clone", REPO, str(CACHE))\n'
                             'import gdown\n')})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        how = {a["how"] for a in env["acquisition"]}
        self.assertIn("cloned from a repository", how)
        self.assertIn("fetched with gdown", how)

    def test_a_self_downloading_source_is_recognized_as_obtainable(self):
        box = self.repo({"src/Prior/m.py": "x = 1\n",
                         "Prior/Notebooks/Run.ipynb": self.notebook(
                             'sets = datasets.MNIST(root=R, download=True)\n')})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertIn("downloads itself", {a["how"] for a in env["acquisition"]})

    def test_a_path_outside_the_repository_is_reported_as_what_it_is(self):
        # Reading from somewhere else is a real constraint, and a different one from
        # unobtainable — it says where it runs, not that it cannot.
        box = self.repo({"src/Prior/paths.py": 'P = "/kaggle/input/some-set/images"\n'})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertIn("read from a path outside the repository",
                      {a["how"] for a in env["acquisition"]})

    def test_definitions_inside_a_notebook_count_as_entry_points(self):
        box = self.repo({"src/Prior/m.py": "x = 1\n",
                         "Prior/Notebooks/Run.ipynb": self.notebook(
                             "def load_everything(root):\n    return root\n")})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertEqual([e["function"] for e in env["dataEntryPoints"]],
                         ["load_everything"])

    def test_a_cell_that_cannot_be_parsed_does_not_stop_the_reading(self):
        # Shell magics are ordinary in notebooks and must not silence the rest.
        box = self.repo({"src/Prior/m.py": "x = 1\n",
                         "Prior/Notebooks/Run.ipynb": self.notebook(
                             "!pip install torch\n",
                             'sets = datasets.MNIST(root=R, download=True)\n')})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertIn("downloads itself", {a["how"] for a in env["acquisition"]})


class AcquisitionHonestyTests(unittest.TestCase):
    """The pattern list is fixed, so its silence must never read as an absence."""

    def repo(self, files):
        box = Path(tempfile.mkdtemp(prefix="pp-acqh-"))
        for path, source in files.items():
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(source)
        return box

    def test_a_mechanism_the_list_does_not_know_is_reported_as_a_miss(self):
        # A cloud SDK, a data-versioning tool, a hosting client: none are in the list,
        # and returning [] silently is how "we could not read it" becomes "it cannot
        # be obtained" — the mistake this whole reading exists to prevent.
        box = self.repo({"src/Prior/m.py":
                         "import dvc.api\n"
                         'def load():\n    return dvc.api.read("data.csv")\n'})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertEqual(env["acquisition"], [])
        self.assertIn("acquisition", env["foundNothingFor"])

    def test_the_reading_says_it_is_partial_so_the_user_can_point(self):
        box = self.repo({"src/Prior/m.py": "x = 1\n"})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertIn("partial", env["readBy"]["acquisition"])

    def test_an_absolute_path_outside_the_repository_is_recognized_anywhere(self):
        # Not the two hosted runtimes this was written against: any of them, plus a
        # cluster scratch or a mounted share.
        for path in ("/kaggle/input/some-set/images", "/content/Data/images",
                     "/mnt/shared/corpus", "/gpfs/scratch/experiment"):
            box = self.repo({"src/Prior/paths.py": f'ROOT = "{path}"\n'})
            how = {a["how"] for a in impl.baseline_environment(box, ["Prior"], "M")["acquisition"]}
            self.assertIn("read from a path outside the repository", how, path)

    def test_an_ordinary_relative_path_is_not_mistaken_for_a_mount(self):
        box = self.repo({"src/Prior/paths.py": 'ROOT = "data/images"\n'})
        how = {a["how"] for a in impl.baseline_environment(box, ["Prior"], "M")["acquisition"]}
        self.assertNotIn("read from a path outside the repository", how)


# --------------------------------------------------------------------- el sello

import importlib.util  # noqa: E402

_digest_spec = importlib.util.spec_from_file_location(
    "report_digest",
    FORGE / ".claude/skills/proposal-implementation/assets/kit/nb/report_digest.py",
)
report_digest = importlib.util.module_from_spec(_digest_spec)
_digest_spec.loader.exec_module(report_digest)


class ReportDigestJoinTests(unittest.TestCase):
    """Las dos mitades del sello, corridas sobre el mismo árbol.

    Una la escribe el destino y la otra la recomputa la verificación. Probar cada
    una contra un fixture propio verificaría las dos mitades y nunca la unión, que
    es lo único que el sello es: si dan números distintos, todo informe queda
    marcado como reliquia y nadie sabe por qué.
    """

    def build(self, root: Path) -> None:
        for relative, body in (
            ("src/Method/kernels.py", "K = 1\n"),
            ("src/Method_Benchmark/tables.py", "def render():\n    return 'x'\n"),
            ("src/Method_Benchmark/__init__.py", "__benchmark__ = {}\n"),
            ("tests/test_smoke.py", "def test_ok():\n    assert True\n"),
            ("Method/Notebooks/.gitkeep", ""),
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

    def test_both_halves_agree_on_the_same_tree(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            self.assertEqual(report_digest.source_digest(root, "Method"),
                             impl.source_digest(root, "Method"))

    def test_the_benchmark_package_is_inside_what_the_stamp_covers(self):
        """El módulo que escribe las conclusiones cuenta como fuente del informe.

        Dejarlo afuera permitía corregir una conclusión y que el registro siguiera
        afirmando la vieja con la verificación en verde. Rojo alcanzable: si el
        digest ignorara el paquete del banco, este test no distinguiría los dos
        árboles y fallaría.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            before = impl.source_digest(root, "Method")
            (root / "src/Method_Benchmark/tables.py").write_text(
                "def render():\n    return 'y'\n", encoding="utf-8")
            after = impl.source_digest(root, "Method")
            self.assertNotEqual(before, after)
            self.assertNotEqual(report_digest.source_digest(root, "Method"), before)

    def test_prior_work_the_benchmark_imports_is_inside_what_the_stamp_covers(self):
        """Mover lo que computa un brazo tiene que marcar rancio el informe.

        El banco importa del trabajo previo — es lo que lo hace una comparación —
        así que un cambio ahí cambia los números de esos brazos. Nombrando los
        paquetes uno por uno esto quedaba afuera: los cuadernos seguían diciendo
        `executed` sobre resultados viejos, y la sesión aparte que arregla el
        trabajo previo y vuelve es justo la que lo dispara.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            baseline = root / "src/PriorWork/models.py"
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text("LOSS = 1\n", encoding="utf-8")
            before = impl.source_digest(root, "Method")
            baseline.write_text("LOSS = 2\n", encoding="utf-8")
            after = impl.source_digest(root, "Method")
            self.assertNotEqual(before, after)
            self.assertEqual(after, report_digest.source_digest(root, "Method"))

    def test_adding_a_test_does_not_mark_every_report_in_the_repository_stale(self):
        """`tests/` no es de lo que depende un informe: ningún cuaderno lo importa.

        Cubrirlo hacía que agregar cualquier prueba — incluso una sobre el
        trabajo previo, que ningún cuaderno toca — pidiera re-ejecutar la campaña
        entera para re-estampar un hash.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            before = impl.source_digest(root, "Method")
            (root / "tests/test_added_later.py").write_text(
                "def test_new():\n    assert True\n", encoding="utf-8")
            self.assertEqual(impl.source_digest(root, "Method"), before)
            self.assertEqual(report_digest.source_digest(root, "Method"), before)

    def test_the_marker_is_the_one_the_verification_looks_for(self):
        """Otra unión: el destino imprime un prefijo y la verificación lo busca."""
        self.assertEqual(report_digest.MARKER, impl.DIGEST_MARKER)

    def test_the_stamp_needs_no_context_from_the_notebook_that_prints_it(self):
        """Cualquier cuaderno lo llama sin argumentos, incluso el que no comparte
        el molde de los demás.

        La primera versión los pedía, y el primer cuaderno que no definía las
        mismas variables que el resto falló al estampar y quedó informado como
        rancio — el sello dejaba afuera justo al que se salía del molde, que es el
        que más falta hace vigilar.
        """
        import inspect

        signature = inspect.signature(report_digest.stamp)
        for parameter in signature.parameters.values():
            self.assertIsNot(parameter.default, inspect.Parameter.empty,
                             f"stamp() exige {parameter.name} a quien lo llame")

    def test_the_stamp_line_parses_the_way_the_verification_reads_it(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            line = report_digest.stamp(root, "Method")
            recovered = line.split(impl.DIGEST_MARKER, 1)[1].strip().split()[0]
            self.assertEqual(recovered, impl.source_digest(root, "Method"))


# ------------------------------------------------------- el contrato de informe

def _stream(text="salida\n"):
    return {"output_type": "stream", "name": "stdout", "text": [text]}


def _shown(mime, payload="x"):
    return {"output_type": "display_data", "data": {mime: payload}, "metadata": {}}


def _cell(kind, text, outputs=None, executed=True):
    """Una celda, y para las de código lo que dejó al correr.

    El default de una celda de código es haber impreso algo, porque es lo que hace
    un `print`. Una celda ejecutada con la lista de salidas vacía no es un fixture
    neutro: es exactamente el defecto de haber computado una medición y no haberla
    mostrado, y dejarlo como default haría que cada prueba de este archivo lo
    disparara sin querer.
    """
    cell = {"cell_type": kind, "metadata": {}, "source": [text]}
    if kind == "code":
        cell |= {"execution_count": 1 if executed else None,
                 "outputs": [_stream()] if outputs is None else list(outputs)}
    return cell


class PriorWorkTests(unittest.TestCase):
    """"El baseline se usa como está" era la regla más fuerte sin verificar.

    El trabajo previo vive bajo `src/` junto al método y su banco, y todos los
    chequeos pasaban de largo. Se podía editar en cualquier sesión y la siguiente
    abría un repositorio que no decía nada.

    Lo que hace útil el aviso es la segunda pregunta. "Cambió" a secas queda rojo
    para siempre en un repositorio que evoluciona y se deja de leer; "cambió esto,
    que tus brazos importan" es accionable.
    """

    def build(self, root: Path) -> None:
        for relative, body in (
            ("src/Method/kernels.py", "K = 1\n"),
            ("src/Method_Benchmark/__init__.py", "__benchmark__ = {}\n"),
            ("src/Method_Benchmark/wiring.py",
             "from PriorWork.models import Loss\nimport PriorWork.helpers\n"),
            ("src/PriorWork/__init__.py", ""),
            ("src/PriorWork/models.py", "class Loss:\n    scale = 1\n"),
            ("src/PriorWork/helpers.py", "def helper():\n    return 1\n"),
            ("src/PriorWork/training_loop.py", "def train():\n    return 'own'\n"),
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "base"], cwd=root, check=True)

    def state(self, root: Path) -> dict:
        return impl.prior_work_state(root, "Method")

    def test_an_untouched_baseline_is_reported_as_present_and_clean(self):
        """El hecho se informa aunque la respuesta sea que no pasó nada."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            state = self.state(root)
            self.assertEqual(state["status"], "clean")
            self.assertEqual(state["packages"], ["PriorWork"])
            self.assertEqual(state["modified"], [])

    def test_a_change_the_benchmark_imports_is_reported_as_reaching_the_run(self):
        """Mueve lo que computa un brazo: los resultados dejaron de valer."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            (root / "src/PriorWork/models.py").write_text(
                "class Loss:\n    scale = 2\n", encoding="utf-8")
            state = self.state(root)
            self.assertEqual(state["status"], "reaching")
            self.assertEqual(state["reaching"], ["src/PriorWork/models.py"])

    def test_a_change_the_benchmark_never_imports_is_reported_without_alarm(self):
        """Rojo alcanzable: si `reaching` ignorara los imports, esto sería `reaching`.

        El loop de entrenamiento propio del trabajo previo no lo llama el banco.
        Importa para los cuadernos del trabajo previo y no para esta comparación,
        y confundir los dos casos es lo que vuelve el aviso ruido.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            (root / "src/PriorWork/training_loop.py").write_text(
                "def train():\n    return 'changed'\n", encoding="utf-8")
            state = self.state(root)
            self.assertEqual(state["status"], "modified")
            self.assertEqual(state["modified"], ["src/PriorWork/training_loop.py"])
            self.assertEqual(state["reaching"], [])

    def test_a_module_the_ignore_rules_hide_is_still_seen_on_the_disk(self):
        """El caso que obliga a enumerar desde el disco y no desde el índice.

        Git no dice nada de una ruta ignorada. Preguntándole a él *qué hay*, un
        módulo de trabajo previo ignorado pero importado y ejecutado desaparece
        del reporte y todo vuelve `clean` — con un brazo computando con él.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            (root / ".gitignore").write_text("src/PriorWork/secret.py\n", encoding="utf-8")
            (root / "src/PriorWork/secret.py").write_text("SCALE = 3\n", encoding="utf-8")
            (root / "src/Method_Benchmark/wiring.py").write_text(
                "from PriorWork.models import Loss\n"
                "from PriorWork.secret import SCALE\n", encoding="utf-8")

            state = self.state(root)
            self.assertIn("src/PriorWork/secret.py", state["modules"])
            self.assertIn("src/PriorWork/secret.py", state["imported"])
            self.assertEqual(state["untrackedImported"], ["src/PriorWork/secret.py"])
            # Rojo alcanzable: preguntándole al índice esto sería `clean`.
            self.assertEqual(state["status"], "reaching")

    def test_an_unreadable_record_is_unknown_and_never_clean(self):
        """El silencio de git no puede leerse como "no cambió nada"."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for relative in ("src/Method/kernels.py", "src/PriorWork/models.py"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("X = 1\n", encoding="utf-8")
            # Sin `git init`: no hay registro que consultar.
            state = self.state(root)
            self.assertEqual(state["recordStatus"], "unavailable")
            self.assertEqual(state["status"], "unknown")
            self.assertEqual(state["modules"], ["src/PriorWork/models.py"])

    def test_what_an_arm_imports_is_reported_without_anything_having_changed(self):
        """`imported` es un hecho del árbol, no la consecuencia de un diff.

        El `__init__.py` del paquete cuenta: importar `PriorWork.models` lo
        ejecuta, así que un cambio ahí alcanza al brazo igual que uno en el
        módulo nombrado. El loop de entrenamiento propio del trabajo previo no,
        y esa es la distinción entera.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            state = self.state(root)
            self.assertEqual(state["status"], "clean")
            self.assertIn("src/PriorWork/models.py", state["imported"])
            self.assertIn("src/PriorWork/__init__.py", state["imported"])
            self.assertNotIn("src/PriorWork/training_loop.py", state["imported"])

    def test_the_stamp_moves_even_when_the_change_reaches_no_arm(self):
        """El par que hay que declarar, no descubrir.

        El sello cubre `src/` entero a propósito: se computa dos veces, una en el
        cuaderno y otra en la verificación, y cualquier regla más sutil que un
        directorio es una regla en la que dos implementaciones se desincronizan —
        y un sello cuyas mitades no coinciden no protege nada.

        Así que las dos cosas pasan juntas: ningún brazo cambió de número y el
        informe queda obsoleto igual. Sin decirlo, alguien re-corre una campaña
        por un comentario en trabajo previo que el banco nunca importa.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            before = impl.source_digest(root, "Method")
            (root / "src/PriorWork/training_loop.py").write_text(
                "def train():\n    return 'changed'\n", encoding="utf-8")
            self.assertEqual(self.state(root)["reaching"], [])
            self.assertNotEqual(impl.source_digest(root, "Method"), before)

    def test_a_repository_with_no_prior_work_reports_none_rather_than_clean(self):
        """Sin baseline no hay nada que vigilar, y decir `clean` lo insinuaría."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for relative in ("src/Method/kernels.py", "src/Method_Benchmark/__init__.py"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("X = 1\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            self.assertEqual(self.state(root)["status"], "none")


class ReportContractTests(unittest.TestCase):
    """Los cinco chequeos estáticos del informe, cada uno con su rojo alcanzable.

    Un chequeo que no puede fallar es el defecto que fue escrito para atrapar, así
    que ninguno se da por bueno sin construir el árbol que lo dispara.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'renderers': ['tables.render'],\n"
        "        'conclusions': ['tables.conclusion'],\n"
        "        'objectiveEntry': 'tables.objective',\n"
        "        'components': {'terms': ['fit'], 'share': None},\n"
        "        'dimensions': {'accuracy': 'higher', 'seconds': 'lower', 'fit': None},\n"
        "    },\n"
        "    'entry': {'module': 'Method_Benchmark.benchmark', 'function': 'run'},\n"
        "}\n"
    )

    def build(self, root: Path, cells, declaration=None):
        (root / "src/Method_Benchmark").mkdir(parents=True, exist_ok=True)
        (root / "src/Method_Benchmark/__init__.py").write_text(
            self.DECLARATION if declaration is None else declaration, encoding="utf-8")
        notebooks = root / "Method/Notebooks"
        notebooks.mkdir(parents=True, exist_ok=True)
        (notebooks / "Report.ipynb").write_text(
            json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                        "nbformat_minor": 5}), encoding="utf-8")

    def state(self, cells, declaration=None):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, cells, declaration)
            return impl.report_state(root, "Method", "Method")

    WELL_FORMED = [
        _cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
        # La mitad calculada del encuadre: contra qué valor se compara lo de abajo.
        _cell("code", "print(tables.objective('accuracy'))"),
        _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                      "print(tables.conclusion(runs, 'accuracy', reduction))"),
    ]

    def test_a_well_formed_report_passes_every_static_check(self):
        state = self.state(self.WELL_FORMED)
        for finding in ("proseNumbers", "duplicated", "unframed", "unconcluded"):
            self.assertEqual(state[finding], [], f"{finding}: {state[finding]}")

    def test_a_section_that_never_says_what_value_it_seeks_is_caught(self):
        """Una dirección no es un objetivo.

        «Más alto es mejor» dice para qué lado mirar y nada sobre dónde termina lo
        bueno. Quien no conoce la métrica no aprende nada de eso: le falta el hito
        contra el que se compara — un azar, una cota, un acuerdo entre corridas.
        """
        cells = [_cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                               "print(tables.conclusion(runs, 'accuracy', reduction))")]
        found = self.state(cells)["unaimed"]
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["reason"], "la sección no dice qué valor se busca")

    def test_declaring_no_objective_at_all_is_the_reason_and_not_a_pass(self):
        """La lección de `figures: []`, aplicada antes de repetirla.

        Un hallazgo que solo puede dispararse cuando alguien escribió una clave
        opcional se apaga justo en el paquete que nunca la escribió, y ahí el
        informe sale limpio sin decir en ningún lado qué se busca. La ausencia de
        la declaración es el motivo del hallazgo, no su excusa.
        """
        silent = self.DECLARATION.replace(
            "        'objectiveEntry': 'tables.objective',\n", "")
        found = self.state(self.WELL_FORMED, silent)["unaimed"]
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["reason"], "el contrato no declara objectiveEntry")

    def test_the_objective_is_computed_and_counts_as_framing(self):
        """El valor que se busca no puede ir tipeado: envejece igual que una
        medición tipeada, y el día que cambie una constante la frase va a seguir
        nombrando el hito viejo. Va calculado, y por eso ocupa una celda de código
        entre el párrafo y la tabla — que el chequeo tiene que leer como parte del
        encuadre y no como trabajo ajeno."""
        state = self.state(self.WELL_FORMED)
        self.assertEqual(state["unaimed"], [])
        self.assertEqual(state["unframed"], [])
        self.assertEqual(state["unconcluded"], [])

    def test_the_skill_never_asks_what_the_objective_says(self):
        """El límite que impide que esto aprenda un campo.

        Cualquier texto sirve: si la comprobación distinguiera un azar de una cota
        habría aprendido de qué se trata el experimento, y se apagaría en el
        próximo que mida otra cosa. Solo pregunta si la sección lo dice.
        """
        for texto in ("hacia cero", "por encima del azar", "adentro de sus cotas"):
            with self.subTest(texto=texto):
                cells = [_cell("markdown", "Qué mide: la exactitud."),
                         _cell("code", f"print(tables.objective({texto!r}))"),
                         _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                                       "print(tables.conclusion(runs, 'accuracy', reduction))")]
                self.assertEqual(self.state(cells)["unaimed"], [])

    def test_a_number_typed_into_prose_is_caught(self):
        cells = [_cell("markdown", "La exactitud sube 2,78 puntos."),
                 *self.WELL_FORMED]
        found = self.state(cells)["proseNumbers"]
        self.assertEqual([f["value"] for f in found], ["2,78"])

    def test_one_decimal_place_is_not_treated_as_a_measurement(self):
        """Un entero o un decimal corto suele ser estructura — un número de sección,
        una cantidad de paneles — y marcarlos entrenaría al lector a ignorar el
        chequeo entero."""
        cells = [_cell("markdown", "Son 3 paneles y la seccion 5.1."), *self.WELL_FORMED]
        self.assertEqual(self.state(cells)["proseNumbers"], [])

    def test_the_same_measurement_rendered_twice_is_caught(self):
        cells = [*self.WELL_FORMED,
                 _cell("markdown", "otra vez"),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                               "print(tables.conclusion(runs, 'accuracy', reduction))")]
        self.assertTrue(self.state(cells)["duplicated"])

    def test_two_measurements_in_one_cell_are_caught(self):
        cells = [_cell("markdown", "dos juntas"),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                               "print(harness.render_panorama(summary))\n"
                               "print(tables.conclusion(runs, 'accuracy', reduction))")]
        state = self.state(cells, self.DECLARATION.replace(
            "'renderers': ['tables.render']",
            "'renderers': ['tables.render', 'harness.render_panorama']"))
        self.assertTrue(state["duplicated"])

    def test_the_same_renderer_called_twice_in_one_cell_is_caught(self):
        """El hueco que dejaba pasar el caso más común de todos.

        La comprobación de arriba usa dos renderizadores DISTINTOS, y con eso el
        conteo se hacía sobre el conjunto de llamadas. Dos tablas producidas por
        la misma función colapsaban en una sola entrada y la celda salía limpia —
        que es justo la forma que «una celda, una medición» viene a atajar, y la
        que más aparece: dos lecturas hermanas impresas juntas porque se leen
        juntas.
        """
        cells = [_cell("markdown", "las dos distancias"),
                 _cell("code",
                       "print(tables.render(runs, 'accuracy', reduction))\n"
                       "print(tables.render(runs, 'seconds', reduction))\n"
                       "print(tables.conclusion(runs, 'accuracy', reduction))")]
        found = self.state(cells)["duplicated"]
        self.assertTrue(found, "una celda con dos tablas salió limpia")
        self.assertTrue(any(f.get("reason") == "más de una medición en una celda"
                            for f in found), found)

    def test_one_renderer_called_once_is_not_a_duplicate(self):
        """El verde tiene que seguir siendo alcanzable, o el conteo por
        repeticiones convierte cualquier tabla en un hallazgo."""
        cells = [_cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))")]
        self.assertEqual(self.state(cells)["duplicated"], [])

    def test_a_complementary_pair_shares_one_framing_and_one_conclusion(self):
        """Dos tablas que no se pueden concluir por separado.

        El numerador y el denominador de una razón son el caso claro: una
        distancia que baja puede ser alineación o colapso, y solo el par lo
        distingue. Ponerlas en una celda es el hallazgo de arriba; darle una
        conclusión a cada una sería concluir sobre media lectura. Queda una sola
        forma legítima — dos celdas bajo un encuadre, con una conclusión que lee
        las dos — y el chequeo tiene que admitirla.
        """
        cells = [_cell("markdown", "Las dos distancias, que se leen juntas."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.render(runs, 'seconds', reduction))"),
                 _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))")]
        state = self.state(cells)
        self.assertEqual(state["unframed"], [])
        self.assertEqual(state["unconcluded"], [])
        self.assertEqual(state["duplicated"], [])

    def test_a_section_that_never_concludes_is_still_caught(self):
        """La garantía no se aflojó: mirar la sección en vez de la celda de al lado
        no puede convertir en verde a una sección que nunca concluye."""
        cells = [_cell("markdown", "dos tablas y ninguna conclusión"),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.render(runs, 'seconds', reduction))"),
                 _cell("markdown", "otra sección"),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))")]
        found = self.state(cells)["unconcluded"]
        self.assertEqual(sorted(f["cell"] for f in found), [1, 2], found)

    def test_a_table_with_nothing_explaining_it_is_caught(self):
        cells = [_cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                               "print(tables.conclusion(runs, 'accuracy', reduction))")]
        self.assertTrue(self.state(cells)["unframed"])

    def test_a_table_with_no_computed_conclusion_is_caught(self):
        cells = [_cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))")]
        self.assertTrue(self.state(cells)["unconcluded"])

    def test_a_conclusion_in_the_following_cell_still_counts(self):
        cells = [_cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))")]
        self.assertEqual(self.state(cells)["unconcluded"], [])

    def test_the_cell_that_writes_the_record_may_render_everything_again(self):
        """El registro tiene que contener todo lo que el cuaderno mostró. Contarlo
        como segunda lectura haría que el único archivo del que depende una sesión
        posterior sea el defecto, y la forma de aprobar sería dejar de escribirlo."""
        cells = [*self.WELL_FORMED,
                 _cell("markdown", "el registro"),
                 _cell("code", "(root / 'report.txt').write_text("
                               "tables.render(runs, 'accuracy', reduction))")]
        self.assertEqual(self.state(cells)["duplicated"], [])

    def test_without_a_declaration_nothing_is_reported_as_fine(self):
        """No poder buscar algo no es lo mismo que no encontrarlo."""
        state = self.state(self.WELL_FORMED, declaration="__benchmark__ = {}\n")
        self.assertEqual(state["status"], "undeclared")

    def test_no_benchmark_package_at_all_is_absent_not_undeclared(self):
        """A directory that was never created is a different fact than one
        that exists and names nothing — `report_contract` alone cannot tell
        them apart (both read as `{}`), so this reaches for the resolver
        directly rather than reporting the same `"undeclared"` for both."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method" / "Notebooks").mkdir(parents=True, exist_ok=True)
            state = impl.report_state(root, "Method", "Method")
        self.assertEqual(state["status"], "absent")

    def test_an_unavailable_live_check_never_reports_ok(self):
        """Sin intérprete del destino, dos de los chequeos no pudieron correr, y
        decir `ok` informaría su ausencia como su respuesta."""
        state = self.state(self.WELL_FORMED)
        self.assertEqual(state["live"], "unavailable")
        self.assertEqual(state["status"], "incomplete")


# --------------------------------------------- run/report coupling detection

_COUPLING_DECLARATION = (
    "__benchmark__ = {\n"
    "    'revision': 'r01.md',\n"
    "    'arms': {},\n"
    "    'report': {\n"
    "        'renderers': ['tables.render'],\n"
    "        'record': 'latent.json',\n"
    "    },\n"
    "}\n"
)

# The one shape the whole check exists to catch: a call the report never
# named, whose arguments are not literals, bound in a cell that renders
# nothing — exactly what costs a re-run when a reporting cell reads it back.
_COUPLED_CELLS = [
    _cell("code", "from Method_Benchmark import tables, harness"),
    _cell("code", "runs = harness.campaign(config=CONFIG, seeds=SEEDS)"),
    _cell("code", "print(tables.render(runs))"),
]

_CLEAN_CELLS = [
    _cell("code", "from Method_Benchmark import tables"),
    _cell("code", "print(tables.render(1))"),
]


class CouplingTests(unittest.TestCase):
    """`notebook_coupling`'s five-step criterion (design #744 section 8).

    Step 5, the reconstructibility guard, is the point of every test here —
    it is the real criterion and not a heuristic about "setup cells": what
    costs a re-run is a binding that cannot be rebuilt without executing a
    call the report itself never named.
    """

    CONTRACT = {"renderers": ["tables.render"], "conclusions": [], "figures": [],
                "record": "latent.json"}

    def couple(self, cells, contract=None):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "Report.ipynb"
            path.write_text(json.dumps({"cells": cells, "metadata": {},
                                        "nbformat": 4, "nbformat_minor": 5}),
                            encoding="utf-8")
            return impl.notebook_coupling(path, contract or self.CONTRACT)

    def test_an_imported_module_alias_never_couples(self):
        """`import numpy as np` — reconstructible by definition: nothing runs
        to redo an import, so a reporting cell reading `np` is never coupled."""
        cells = [
            _cell("code", "import numpy as np\nfrom Method_Benchmark import tables"),
            _cell("code", "print(tables.render(np.array([1, 2, 3])))"),
        ]
        self.assertEqual(self.couple(cells), {"coupled": False, "couplings": []})

    def test_a_literal_constructor_call_never_couples(self):
        """`RESULTS = Path("Results")` — a call, but every argument is a
        constant: retyping the line reproduces it, so it passes even though
        `Path` is nowhere in the declared vocabulary — the whitelist is by
        reconstructibility, never by a list of blessed names."""
        cells = [
            _cell("code", "from pathlib import Path\n"
                          "from Method_Benchmark import tables"),
            _cell("code", "RESULTS = Path('Results')"),
            _cell("code", "print(tables.render(RESULTS))"),
        ]
        self.assertEqual(self.couple(cells), {"coupled": False, "couplings": []})

    def test_a_function_definition_never_couples(self):
        """`def fmt(x): ...` binds a name with nothing to execute at
        definition time — whatever the body calls is irrelevant, because
        defining a function is always reconstructible from its own text."""
        cells = [
            _cell("code", "from Method_Benchmark import tables"),
            _cell("code", "def fmt(x):\n    return round(x, 2)"),
            _cell("code", "print(tables.render(fmt(1.234)))"),
        ]
        self.assertEqual(self.couple(cells), {"coupled": False, "couplings": []})

    def test_a_call_outside_the_vocabulary_with_non_constant_args_couples(self):
        """`runs = harness.campaign(...)` — the one that costs GPU hours: a
        call the report never named, with arguments that are not literals, so
        it cannot be rebuilt without running it again."""
        state = self.couple(_COUPLED_CELLS)
        self.assertTrue(state["coupled"], state)
        self.assertEqual(state["couplings"],
                         [{"name": "runs", "boundIn": 1, "readIn": 2}])

    def test_a_binding_by_a_reporting_cell_is_never_the_finding(self):
        """A name last bound inside another reporting cell is not what this
        check exists for — the false-positive guard is about a setup cell
        that renders nothing, not about the report's own pipeline."""
        cells = [
            _cell("code", "from Method_Benchmark import tables, harness"),
            _cell("code", "runs = tables.render(harness.campaign(config=CONFIG))"),
            _cell("code", "print(tables.render(runs))"),
        ]
        self.assertEqual(self.couple(cells)["couplings"], [])

    def test_a_clean_notebook_reports_no_coupling(self):
        self.assertEqual(self.couple(_CLEAN_CELLS), {"coupled": False, "couplings": []})

    def test_reading_a_persisted_json_record_never_couples(self):
        """`runs = [json.loads(line) for line in (RESULTS / "runs.jsonl")
        .read_text().splitlines() if line.strip()]` — the exact shape of a
        correctly split report notebook reading back what the run already
        wrote (T12b, correcting the false positive T12's real-notebook
        validation exposed on `Benchmark_Phase1_Report.ipynb`).

        `.read_text()` takes no argument of its own, so retyping the call
        reproduces it; `line` is manufactured and consumed entirely inside
        the same comprehension, never read from anywhere outside it. Neither
        is a dependency on a call the report never named — both are the
        report's own record, read back rather than recomputed.
        """
        cells = [
            _cell("code", "from pathlib import Path\n"
                          "import json\n"
                          "from Method_Benchmark import tables\n"
                          "RESULTS = Path('Results')"),
            _cell("code",
                  "runs = [json.loads(line) for line in "
                  "(RESULTS / 'runs.jsonl').read_text().splitlines() "
                  "if line.strip()]\n"
                  "summary = json.loads((RESULTS / 'summary.json').read_text())"),
            _cell("code", "print(tables.render(runs))\n"
                          "print(tables.render(summary))"),
        ]
        self.assertEqual(self.couple(cells), {"coupled": False, "couplings": []})

    def test_reconstructing_an_object_from_already_read_data_still_couples(self):
        """`Reduction(**summary['reduction'])` reconstructs a dataclass from
        data that was itself read back cleanly — but the constructor call is
        not one of the read primitives this guard recognizes, so it stays
        flagged. The exemption is narrow by design: it does not widen to
        make every coupling on a report notebook vanish (T12b)."""
        cells = [
            _cell("code", "import json\nfrom pathlib import Path\n"
                          "from Method_Benchmark import tables, harness\n"
                          "RESULTS = Path('Results')"),
            _cell("code",
                  "summary = json.loads((RESULTS / 'summary.json').read_text())\n"
                  "reduction = harness.Reduction(**summary['reduction'])"),
            _cell("code", "print(tables.render(reduction))"),
        ]
        state = self.couple(cells)
        self.assertTrue(state["coupled"], state)
        self.assertEqual(state["couplings"],
                         [{"name": "reduction", "boundIn": 1, "readIn": 2}])


class CouplingSurfacingTests(unittest.TestCase):
    """`notebook_coupling` reaches `notebooks_state()`, `verify` and `probe` —
    never as a gate, only as a fact next to the ones that already are."""

    def _write_notebook(self, root, cells, notebook_name="Report.ipynb"):
        notebooks = root / "Method" / "Notebooks"
        notebooks.mkdir(parents=True, exist_ok=True)
        (notebooks / notebook_name).write_text(
            json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                        "nbformat_minor": 5}), encoding="utf-8")

    def test_notebooks_state_surfaces_a_coupling_per_notebook(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "src" / "Method_Benchmark").mkdir(parents=True)
            (root / "src" / "Method_Benchmark" / "__init__.py").write_text(
                _COUPLING_DECLARATION, encoding="utf-8")
            self._write_notebook(root, _COUPLED_CELLS)
            state = impl.notebooks_state(root, "Method", "Method")
        self.assertEqual(len(state["reports"]), 1)
        self.assertTrue(state["reports"][0]["coupling"]["coupled"], state)

    def test_verify_and_probe_report_coupling_end_to_end(self):
        box = FORGE / "implementations" / f"_e2e_coupling_{os.getpid()}"
        try:
            (box / "src" / "Method").mkdir(parents=True)
            (box / "src" / "Method_Benchmark").mkdir(parents=True)
            (box / "tests").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
            (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
                _COUPLING_DECLARATION, encoding="utf-8")
            self._write_notebook(box, _COUPLED_CELLS)
            verify = subprocess.run(
                [sys.executable, str(CLI), "verify", "--target", str(box),
                 "--name", "Method"],
                capture_output=True, text=True, cwd=FORGE)
            probe = subprocess.run(
                [sys.executable, str(CLI), "probe", "--target", str(box),
                 "--name", "Method"],
                capture_output=True, text=True, cwd=FORGE)
        finally:
            shutil.rmtree(box, ignore_errors=True)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        verify_json = json.loads(verify.stdout or "{}")
        probe_json = json.loads(probe.stdout or "{}")
        self.assertTrue(verify_json["coupling"]["coupled"], verify_json)
        self.assertTrue(probe_json["coupling"]["coupled"], probe_json)


class CouplingNeverGatesTests(unittest.TestCase):
    """The one rule that makes coupling detection safe to ship: no command's
    exit status may ever be conditioned on it. A static approximation of how
    someone organized their notebook has no authority to stop their work; it
    may only tell them what it sees (design #744 section 8, mandated RED)."""

    def _run(self, cells, command, suffix):
        box = FORGE / "implementations" / f"_e2e_coupling_gate_{os.getpid()}_{suffix}"
        try:
            (box / "src" / "Method").mkdir(parents=True)
            (box / "src" / "Method_Benchmark").mkdir(parents=True)
            (box / "tests").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
            (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
                _COUPLING_DECLARATION, encoding="utf-8")
            notebooks = box / "Method" / "Notebooks"
            notebooks.mkdir(parents=True)
            (notebooks / "Report.ipynb").write_text(
                json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                            "nbformat_minor": 5}), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), command, "--target", str(box),
                 "--name", "Method"],
                capture_output=True, text=True, cwd=FORGE)
        finally:
            shutil.rmtree(box, ignore_errors=True)
        return proc

    def test_verify_exit_status_is_byte_identical_coupled_or_not(self):
        coupled = self._run(_COUPLED_CELLS, "verify", "v_coupled")
        clean = self._run(_CLEAN_CELLS, "verify", "v_clean")
        self.assertEqual(coupled.returncode, clean.returncode)
        self.assertEqual(coupled.returncode, 0, coupled.stderr)
        self.assertTrue(json.loads(coupled.stdout)["coupling"]["coupled"])
        self.assertFalse(json.loads(clean.stdout)["coupling"]["coupled"])

    def test_probe_exit_status_is_byte_identical_coupled_or_not(self):
        coupled = self._run(_COUPLED_CELLS, "probe", "p_coupled")
        clean = self._run(_CLEAN_CELLS, "probe", "p_clean")
        self.assertEqual(coupled.returncode, clean.returncode)
        self.assertEqual(coupled.returncode, 0, coupled.stderr)
        self.assertTrue(json.loads(coupled.stdout)["coupling"]["coupled"])
        self.assertFalse(json.loads(clean.stdout)["coupling"]["coupled"])


# ------------------------------------- lo que una celda produjo, no lo que dice

class AgreementsTests(unittest.TestCase):
    """La regla de escribir los acuerdos existía en prosa y sin nada que la sostenga
    — la misma forma que el defecto que describe.

    Un acuerdo se toma en una compuerta, no vive en ningún archivo, y cuando se
    escribe el código el único registro es una memoria que re-decide sola.
    """

    def write(self, root: Path, body: str) -> dict:
        (root / "Method").mkdir(parents=True, exist_ok=True)
        (root / "Method/AGREEMENTS.md").write_text(body, encoding="utf-8")
        return impl.agreements_state(root, "Method")

    def test_no_file_is_a_state_and_says_what_it_would_have_held(self):
        with tempfile.TemporaryDirectory() as raw:
            state = impl.agreements_state(Path(raw), "Method")
            self.assertEqual(state["status"], "absent")
            self.assertEqual(state["searched"], "Method/*.md")

    def test_an_unticked_item_is_an_agreement_that_never_reached_the_code(self):
        with tempfile.TemporaryDirectory() as raw:
            state = self.write(Path(raw), (
                "# Acuerdos\n\n"
                "- [x] el techo queda en 1 y compartido\n"
                "- [ ] la figura muestra la imagen, no la ruta\n"))
            self.assertEqual(state["status"], "open")
            self.assertEqual(state["open"], ["la figura muestra la imagen, no la ruta"])
            self.assertEqual(state["settled"], 1)

    def test_everything_ticked_settles(self):
        """Rojo alcanzable: si no leyera la marca, esto seguiría `open`."""
        with tempfile.TemporaryDirectory() as raw:
            state = self.write(Path(raw), "- [x] uno\n- [X] dos\n")
            self.assertEqual(state["status"], "settled")
            self.assertEqual(state["settled"], 2)
            self.assertEqual(state["open"], [])

    def test_a_checklist_under_any_name_is_found(self):
        """El caso que motivó esto, y que no probé la primera vez.

        Un repositorio ya tenía su checklist bajo otro nombre, con 159 ítems
        acordados a mano. Con el nombre fijo el chequeo reportaba `absent` encima
        de ella e inventaba una segunda al lado. Eso no es un archivo faltante:
        es una ausencia que nadie fue a buscar, vestida de hallazgo.

        Rojo alcanzable: con `AGREEMENTS.md` fijo, esto da `absent`.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method/AGREED.md").write_text(
                "# Acordado\n\n- [x] el techo queda en uno\n- [ ] la figura inline\n",
                encoding="utf-8")
            state = impl.agreements_state(root, "Method")
            self.assertEqual(state["status"], "open")
            self.assertEqual(state["holders"], ["Method/AGREED.md"])
            self.assertEqual(state["settled"], 1)

    def test_every_checklist_in_the_product_folder_is_counted(self):
        """Dos archivos con acuerdos son dos mitades de un contrato, no uno."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method/AGREED.md").write_text("- [x] uno\n", encoding="utf-8")
            (root / "Method/AGREEMENTS.md").write_text("- [ ] dos\n", encoding="utf-8")
            state = impl.agreements_state(root, "Method")
            self.assertEqual(state["holders"],
                             ["Method/AGREED.md", "Method/AGREEMENTS.md"])
            self.assertEqual(state["settled"], 1)
            self.assertEqual(state["open"], ["dos"])

    def test_a_markdown_file_with_no_items_is_a_document_and_not_a_checklist(self):
        """Un README en la carpeta del producto no es un contrato incumplido."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method/README.md").write_text(
                "# El método\n\n- una viñeta cualquiera\n- otra\n", encoding="utf-8")
            state = impl.agreements_state(root, "Method")
            self.assertEqual(state["status"], "absent")
            self.assertEqual(state["unparsed"], [])

    def test_prose_is_not_mistaken_for_a_malformed_agreement(self):
        """Un párrafo en negrita no es una viñeta.

        Probando solo el primer carácter, cada `**negrita**` se leía como un
        acuerdo mal escrito. Un archivo que registra un acuerdo revertido lo
        explica en prosa, y esa prosa es justo la que este archivo necesita
        permitir — un chequeo que grita por markdown se deja de leer, que cuesta
        más que el caso que vigilaba.
        """
        with tempfile.TemporaryDirectory() as raw:
            state = self.write(Path(raw), (
                "# Acuerdos\n\n- [x] el techo queda en uno\n\n"
                "## Revertidos\n\n"
                "**\"El techo se fija sin mirar resultados.\"** Revertido al "
                "decidir que cada familia busca el suyo.\n\n"
                "*Una línea en cursiva tampoco es una viñeta.*\n"))
            self.assertEqual(state["unparsed"], [])
            self.assertEqual(state["status"], "settled")
            self.assertEqual(state["settled"], 1)

    def test_a_bullet_that_is_not_a_checklist_item_is_never_counted_as_settled(self):
        """Un acuerdo escrito con el formato equivocado no es un acuerdo cumplido.

        Es la misma falla que el archivo previene, un nivel más abajo: quedaría
        escrito, nadie lo contaría, y el reporte diría que no falta nada.
        """
        with tempfile.TemporaryDirectory() as raw:
            state = self.write(Path(raw), "- [x] uno\n- dos, sin casilla\n")
            self.assertEqual(state["unparsed"], ["AGREEMENTS.md: - dos, sin casilla"])
            self.assertEqual(state["status"], "open")


class SearchIsAnExperimentTests(unittest.TestCase):
    """Una búsqueda es un experimento y se declara como tal.

    Tres cosas que se vuelven invisibles hasta que alguien se choca con ellas:
    escala propia, rol de material propio, y una regla de desempate escrita en vez
    de heredada de `max`. Nada acá sabe qué se busca ni nombra herramienta alguna.
    """

    COMPLETE = {
        "what": "el techo del coeficiente de adaptación, por familia",
        "requiredScale": {"epochs": 20, "seeds": 3},
        "role": "valid",
        "tieRule": "el techo más chico entre los empatados",
        "record": "Results/ceilings.json",
    }

    def test_a_repository_that_searches_nothing_has_nothing_to_declare(self):
        """Ausencia es un estado, no una falla: casi ningún repo busca algo."""
        state = impl.search_state({}, [])
        self.assertEqual(state["status"], "none")
        self.assertIn("undeclaredRecords", state["note"])

    def test_absent_and_undeclared_propagate_over_none(self):
        """The tri-state `resolve_benchmark_declaration` computes must survive
        into this reader instead of collapsing into the same `"none"` a
        repository that legitimately searches nothing also reports."""
        for status in ("absent", "undeclared"):
            with self.subTest(status=status):
                state = impl.search_state({}, [], declaration_status=status)
                self.assertEqual(state["status"], status)

    def test_declared_but_no_search_block_still_reads_none(self):
        """A real declaration that simply names no search is the case `none`
        exists for, and `declaration_status="declared"` must not disturb it."""
        state = impl.search_state({"arms": {}}, [], declaration_status="declared")
        self.assertEqual(state["status"], "none")
        self.assertIn("undeclaredRecords", state["note"])

    def test_each_missing_piece_is_named_with_why_it_matters(self):
        for field in ("what", "requiredScale", "role", "tieRule"):
            partial = {k: v for k, v in self.COMPLETE.items() if k != field}
            state = impl.search_state({"search": partial}, ["Results/ceilings.json"])
            self.assertEqual(state["status"], "incomplete", field)
            self.assertEqual([m["field"] for m in state["missing"]], [field])
            self.assertTrue(state["missing"][0]["reason"], field)

    def test_a_search_that_writes_a_record_has_to_name_it_among_the_records(self):
        """La junta entre las dos declaraciones.

        Una búsqueda que escribe un archivo y no lo nombra donde se nombran los
        registros es un segundo experimento llegando sin contabilizar, que es
        justamente para lo que existe `records`.
        """
        state = impl.search_state({"search": self.COMPLETE}, ["Results/summary.json"])
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual(state["recordNotDeclared"], "Results/ceilings.json")

    def test_a_directory_among_the_records_covers_the_search_record(self):
        state = impl.search_state({"search": self.COMPLETE}, ["Results"])
        self.assertEqual(state["recordNotDeclared"], None)
        self.assertEqual(state["status"], "ok")

    def test_a_complete_declaration_passes(self):
        """Rojo alcanzable: si no leyera la declaración, esto seguiría incompleto."""
        state = impl.search_state({"search": self.COMPLETE}, ["Results/ceilings.json"])
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["missing"], [])
        self.assertEqual(state["declared"]["role"], "valid")

    def test_the_declared_record_is_checked_against_the_disk(self):
        """Comparar las dos declaraciones verifica que alguien escribió el mismo
        texto dos veces, y no dice nada de dónde escribe la búsqueda."""
        with tempfile.TemporaryDirectory() as raw:
            product = Path(raw) / "Method"
            (product / "Results").mkdir(parents=True, exist_ok=True)
            state = impl.search_state({"search": self.COMPLETE},
                                      ["Results/ceilings.json"], product)
            self.assertIs(state["recordFound"], False)
            self.assertEqual(state["status"], "incomplete")

            (product / "Results/ceilings.json").write_text("{}", encoding="utf-8")
            state = impl.search_state({"search": self.COMPLETE},
                                      ["Results/ceilings.json"], product)
            self.assertIs(state["recordFound"], True)
            self.assertEqual(state["status"], "ok")

    def test_a_record_written_one_level_deeper_is_found_and_named(self):
        """El caso que motivó esto, y que las dos declaraciones no podían ver.

        Una ruta con un directorio duplicado satisfacía las dos declaraciones y
        dejaba el registro un nivel por debajo de donde nadie lo iba a buscar. Se
        descubrió después de que la búsqueda ya hubiera escrito ahí.
        """
        with tempfile.TemporaryDirectory() as raw:
            product = Path(raw) / "Method"
            deeper = product / "Results/Benchmark/Benchmark"
            deeper.mkdir(parents=True, exist_ok=True)
            (deeper / "ceilings.json").write_text("{}", encoding="utf-8")

            declaration = {**self.COMPLETE,
                           "record": "Results/Benchmark/ceilings.json"}
            state = impl.search_state({"search": declaration},
                                      ["Results/Benchmark"], product)
            self.assertIs(state["recordFound"], False)
            self.assertEqual(state["strayRecords"],
                             ["Results/Benchmark/Benchmark/ceilings.json"])

    def test_nothing_to_check_is_none_and_never_a_failure(self):
        """Sin carpeta de producto no hay pregunta que hacerle al disco, y `False`
        ahí sería inventar un hallazgo."""
        state = impl.search_state({"search": self.COMPLETE},
                                  ["Results/ceilings.json"])
        self.assertIsNone(state["recordFound"])
        self.assertEqual(state["status"], "ok")

    def test_it_names_no_tool(self):
        """La skill no recomienda con qué buscar: eso depende del problema.

        Un muestreo adaptativo entrega puntos desigualmente muestreados, y la
        skill exige después el paisaje completo para sostener una afirmación de
        escala. Recomendar la herramienta sería empujar una salida que contradice
        sus propias reglas de reporte.
        """
        source = (impl.SEARCH_DECLARATION, impl.search_state.__doc__)
        for tool in ("optuna", "hyperopt", "ray", "skopt", "grid", "bayesian"):
            self.assertNotIn(tool, json.dumps(source[0]).lower())
            self.assertNotIn(tool, (source[1] or "").lower())


class SearchRecordScaleAgreementTests(unittest.TestCase):
    """The declaration is the fact: `search_state` reads the record's own
    recorded scale along exactly the axis names `requiredScale` declares, and
    reports a tri-state `scaleSatisfied` — `true`/`false`/`null` — never a
    plain boolean. `null` is what an unprovable precondition looks like: the
    record names none of the declared axes, the same doctrine
    `_verify_commit_reachable` already applies to a question that could not
    be asked.

    No axis vocabulary is forge-known: whichever names `requiredScale` uses
    are exactly the names looked up in the record, so a record naming its
    scale under any other key reads as answering none of them.
    """

    COMPLETE = {
        "what": "el techo del coeficiente de adaptación, por familia",
        "requiredScale": {"epochs": 20, "seeds": 3},
        "role": "valid",
        "tieRule": "el techo más chico entre los empatados",
        "record": "Results/ceilings.json",
    }

    def _state(self, record_payload):
        with tempfile.TemporaryDirectory() as raw:
            product = Path(raw) / "Method"
            results = product / "Results"
            results.mkdir(parents=True, exist_ok=True)
            (results / "ceilings.json").write_text(
                json.dumps(record_payload), encoding="utf-8")
            return impl.search_state({"search": self.COMPLETE},
                                     ["Results/ceilings.json"], product)

    def test_a_record_naming_none_of_the_declared_axes_is_null_not_false(self):
        """The tri-state's whole point: a record that answers nothing about
        scale is not the same fact as a record that answers it and falls
        short. Collapsing this to `False` would read an unasked question as
        a failed one."""
        state = self._state({"someOtherField": 1})
        self.assertEqual(state["recordScale"], {})
        self.assertIsNone(state["scaleSatisfied"])

    def test_a_record_meeting_every_declared_axis_is_true(self):
        state = self._state({"epochs": 20, "seeds": 5})
        self.assertEqual(state["recordScale"], {"epochs": 20, "seeds": 5})
        self.assertIs(state["scaleSatisfied"], True)

    def test_a_record_short_on_one_declared_axis_is_false(self):
        state = self._state({"epochs": 20, "seeds": 1})
        self.assertIs(state["scaleSatisfied"], False)

    def test_a_record_naming_only_some_of_the_declared_axes_is_false(self):
        """Naming `epochs` and staying silent on `seeds` is not the same fact
        as naming neither — a partial answer is not an unasked question."""
        state = self._state({"epochs": 20})
        self.assertEqual(state["recordScale"], {"epochs": 20})
        self.assertIs(state["scaleSatisfied"], False)

    def test_an_empty_record_reads_as_null(self):
        state = self._state({})
        self.assertEqual(state["recordScale"], {})
        self.assertIsNone(state["scaleSatisfied"])

    def test_no_required_scale_leaves_scale_satisfied_null_and_gap_computed_lazily(self):
        """A search that never declared `requiredScale` has nothing to
        satisfy — `scaleSatisfied` stays `None` rather than manufacturing a
        verdict from a requirement that was never named."""
        incomplete = {k: v for k, v in self.COMPLETE.items() if k != "requiredScale"}
        with tempfile.TemporaryDirectory() as raw:
            product = Path(raw) / "Method"
            results = product / "Results"
            results.mkdir(parents=True, exist_ok=True)
            (results / "ceilings.json").write_text(
                json.dumps({"epochs": 20, "seeds": 5}), encoding="utf-8")
            state = impl.search_state({"search": incomplete},
                                      ["Results/ceilings.json"], product)
        self.assertIsNone(state["scaleSatisfied"])

    def test_a_list_valued_axis_is_measured_by_length(self):
        """`_scale_of` already treats a list as the count of what it holds —
        `seeds: [0, 1, 2, 3, 4]` is a scale of five, the same rule the pilot
        comparison already applies."""
        state = self._state({"epochs": 25, "seeds": [0, 1, 2, 3, 4]})
        self.assertIs(state["scaleSatisfied"], True)

    def test_absence_of_a_record_on_disk_reports_recordscale_empty_not_an_error(self):
        state = impl.search_state({"search": self.COMPLETE},
                                  ["Results/ceilings.json"])
        self.assertEqual(state["recordScale"], {})
        self.assertIsNone(state["scaleSatisfied"])


class SearchRecordScaleNestedFieldShapedRecordTests(unittest.TestCase):
    """The declaration declares axis *names*; it never declared a depth.

    A record written by a real run groups its result by whatever the run was
    comparing — one group per family — and puts the scale axes inside each
    group. Read only at the top level, such a record answers none of the
    declared axes and `scaleSatisfied` goes `null`: a search that ran at full
    declared scale is reported back as one that has not run.

    The fixture below is field-shaped, not reader-shaped: its keys are the
    keys of a `ceilings.json` left behind by a completed 74-minute GPU run,
    including the ones this reader has no use for. Tests that write the
    fixture the reader expects never cross the seam that this defect lived
    in.
    """

    COMPLETE = {
        "what": "el techo del coeficiente de adaptación, por familia",
        "requiredScale": {"epochs": 20, "seeds": 3},
        "role": "valid",
        "tieRule": "el techo más chico entre los empatados",
        "record": "Results/ceilings.json",
    }

    @staticmethod
    def _field_group(epochs=20, seeds=(0, 1, 2)):
        """One family's entry, carrying every key the real record carries.

        The scale axes sit among fifteen others that mean nothing to this
        reader — which is the point: the reader must find `epochs` and
        `seeds` in there without being told where to look.
        """
        return {
            "arm": "full",
            "ceiling": 0.62,
            "criterion": "target accuracy at the ceiling",
            "grid": [0.25, 0.5, 0.75, 1.0],
            "tied": False,
            "decidedByTieBreak": False,
            "tieRule": "el techo más chico entre los empatados",
            "comparison": {"baseline": 0.51},
            "perSeedPick": {"0": 0.62, "1": 0.62, "2": 0.62},
            "seedsAgree": True,
            "role": "valid",
            "epochs": epochs,
            "seeds": list(seeds),
            "atRequiredScale": True,
            "requiredScale": {"epochs": 20, "seeds": 3},
            "transfers": ["U-S", "S-M"],
            "neutral": 1.0,
        }

    def _state(self, record_payload):
        with tempfile.TemporaryDirectory() as raw:
            product = Path(raw) / "Method"
            results = product / "Results"
            results.mkdir(parents=True, exist_ok=True)
            (results / "ceilings.json").write_text(
                json.dumps(record_payload), encoding="utf-8")
            return impl.search_state({"search": self.COMPLETE},
                                     ["Results/ceilings.json"], product)

    def test_a_flat_record_still_reads_exactly_as_it_did(self):
        """The regression lock on today's path. Accepting a second shape may
        not change what the first one answers, or every existing record
        starts reading differently to buy a shape none of them use."""
        state = self._state({"epochs": 20, "seeds": [0, 1, 2]})
        self.assertEqual(state["recordScale"], {"epochs": 20, "seeds": [0, 1, 2]})
        self.assertIs(state["scaleSatisfied"], True)

    def test_the_field_shaped_record_of_a_completed_run_reads_its_axes(self):
        """The defect, reproduced from the shape that exposed it: two family
        groups, the declared axes inside each. Read at the top level this
        record answers nothing; read uniformly it answers everything, and a
        search that ran at full declared scale stops reporting as unrun."""
        state = self._state({"creda": self._field_group(),
                             "milcreda": self._field_group()})
        self.assertEqual(state["recordScale"],
                         {"epochs": 20, "seeds": [0, 1, 2]})
        self.assertIs(state["scaleSatisfied"], True)

    def test_groups_disagreeing_on_an_axis_report_the_weakest_of_each(self):
        """A record satisfies a requirement only if every part of it does, so
        the minimum is the honest reading — taken per axis, not per group.
        The two groups here are each weaker than the other on a different
        axis, so an implementation picking the first group, the last group,
        or the weakest group wholesale reports something else."""
        state = self._state({
            "creda": self._field_group(epochs=20, seeds=(0, 1)),
            "milcreda": self._field_group(epochs=12, seeds=(0, 1, 2, 3)),
        })
        self.assertEqual(state["recordScale"],
                         {"epochs": 12, "seeds": [0, 1]})
        self.assertIs(state["scaleSatisfied"], False)

    def test_an_axis_no_scale_can_be_read_from_is_weaker_than_one_that_can(self):
        """Weakest includes unmeasurable. A group naming `epochs` as prose
        proves nothing about how large that group ran, so reporting the
        sibling's number instead would hand `_scale_satisfied` a figure no
        group vouched for and let half a record answer for the whole."""
        state = self._state({
            "creda": self._field_group(epochs="veinte"),
            "milcreda": self._field_group(epochs=20),
        })
        self.assertEqual(state["recordScale"],
                         {"epochs": "veinte", "seeds": [0, 1, 2]})
        self.assertIs(state["scaleSatisfied"], False)

    def test_a_group_missing_one_declared_axis_answers_nothing(self):
        """Not every axis in every group is not a uniform nesting, and a
        reader that filled the gap from the group that has it would be
        guessing at what the silent group ran. `{}` and `null`: unprovable,
        the same answer a record naming no axis at all gets."""
        partial = self._field_group()
        del partial["seeds"]
        state = self._state({"creda": self._field_group(), "milcreda": partial})
        self.assertEqual(state["recordScale"], {})
        self.assertIsNone(state["scaleSatisfied"])

    def test_a_top_level_value_that_is_not_a_group_answers_nothing(self):
        """The nesting is accepted only when it is structurally unambiguous.
        One scalar beside the groups and there is no longer a rule that says
        which level the record is written at, so the reader declines rather
        than picking one."""
        state = self._state({"creda": self._field_group(),
                             "milcreda": self._field_group(),
                             "generatedAt": "2026-08-24T03:44:00Z"})
        self.assertEqual(state["recordScale"], {})
        self.assertIsNone(state["scaleSatisfied"])


class UndeclaredRecordsTests(unittest.TestCase):
    """Lo que la corrida deja escrito donde viven sus registros, o está declarado
    o se reporta.

    Todos los demás chequeos solo pueden dispararse sobre algo que alguien
    escribió, así que el repositorio corriendo un experimento que nadie contabilizó
    es justamente aquel donde todos se quedan callados. Es la misma red que
    `undeclaredDrawings` tiende sobre las figuras, tendida sobre lo que una
    corrida escribe.
    """

    def build(self, root: Path, declared: str) -> dict:
        (root / "src/Method_Benchmark").mkdir(parents=True, exist_ok=True)
        (root / "src/Method_Benchmark/__init__.py").write_text(
            "__benchmark__ = {\n"
            "    'revision': 'r01.md',\n"
            "    'arms': {},\n"
            "    'report': {\n"
            "        'renderers': ['tables.render'],\n"
            "        'conclusions': ['tables.conclusion'],\n"
            "        'objectiveEntry': 'tables.objective',\n"
            "        'components': {'terms': ['fit'], 'share': None},\n"
            "        'dimensions': {'accuracy': 'higher', 'fit': None},\n"
            f"{declared}"
            "    },\n"
            "}\n", encoding="utf-8")
        (root / "Method/Notebooks").mkdir(parents=True, exist_ok=True)
        return impl.report_state(root, "Method", "Method")

    def results(self, root: Path, *relatives: str) -> None:
        for relative in relatives:
            path = root / "Method/Results" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")

    def test_a_record_nobody_declared_is_named(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.results(root, "summary.json", "Benchmark/ceilings.json")
            state = self.build(root, "        'records': ['Results/summary.json'],\n")
            self.assertEqual(state["undeclaredRecords"],
                             ["Results/Benchmark/ceilings.json"])

    def test_it_does_not_filter_by_format(self):
        """Filtrar por `.json` daría un pase mudo a quien registre en otra cosa.

        Rojo alcanzable: con un filtro de extensión, ninguno de estos tres
        aparecería y el chequeo se quedaría callado justo donde hace falta.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.results(root, "runs.csv", "grid.parquet", "latents.npz")
            state = self.build(root, "        'records': [],\n")
            self.assertEqual(state["undeclaredRecords"],
                             ["Results/grid.parquet", "Results/latents.npz",
                              "Results/runs.csv"])

    def test_declaring_a_directory_covers_it_and_shows_in_the_echo(self):
        """Permitido, y visible: renunciar a la cuenta archivo por archivo es una
        decisión que se ve, no un silencio."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.results(root, "figures/curve.pdf", "figures/grid.pdf",
                         "Benchmark/ceilings.json")
            state = self.build(root, "        'records': ['Results/figures'],\n")
            self.assertEqual(state["undeclaredRecords"],
                             ["Results/Benchmark/ceilings.json"])
            self.assertEqual(state["declared"]["records"], ["Results/figures"])

    def test_the_per_checkpoint_artefacts_of_models_are_never_reported(self):
        """`Models/` guarda uno por checkpoint por diseño del layout.

        Reportar sesenta manifiestos sería un hallazgo que nadie lee, en cualquier
        repositorio — no solo en el que lo motivó.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            models = root / "Method/Models/Benchmark"
            models.mkdir(parents=True, exist_ok=True)
            for i in range(5):
                (models / f"A_M-U_seed{i}.manifest.json").write_text("{}", encoding="utf-8")
            self.results(root, "summary.json")
            state = self.build(root, "        'records': ['Results/summary.json'],\n")
            self.assertEqual(state["undeclaredRecords"], [])

    def test_declaring_everything_leaves_nothing_to_report(self):
        """Rojo alcanzable: si no leyera `records`, esto seguiría reportando."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.results(root, "summary.json", "Benchmark/latent.json")
            state = self.build(
                root,
                "        'records': ['Results/summary.json',\n"
                "                    'Results/Benchmark/latent.json'],\n")
            self.assertEqual(state["undeclaredRecords"], [])


class DistributionTests(unittest.TestCase):
    """A run split across machines, checked without knowing what any of it means.

    Three obligations, and each one's prohibition is the reason it is general:
    the axis must not be a comparison, the partition must be exhaustive, and
    shards must agree on what they said had to agree.
    """

    COMPLETE = {
        "axis": "seed",
        "poolable": ["accuracy"],
        "perEnvironment": ["cost"],
        "perRun": [],
        "identicalAcrossShards": ["revision"],
    }
    DIMENSIONS = {"accuracy": "higher", "cost": "lower"}

    def test_a_repository_that_distributes_nothing_has_nothing_to_declare(self):
        state = impl.distribution_state({}, self.DIMENSIONS)
        self.assertEqual(state["status"], "none")

    def test_absent_and_undeclared_propagate_over_none(self):
        """Same escape `search_state` needed from the same collapse: a
        Benchmark package that is absent, or one that declares nothing yet,
        must not read like a repository that legitimately runs on one
        machine."""
        for status in ("absent", "undeclared"):
            with self.subTest(status=status):
                state = impl.distribution_state(
                    {}, self.DIMENSIONS, declaration_status=status)
                self.assertEqual(state["status"], status)

    def test_declared_but_no_distribution_block_still_reads_none(self):
        state = impl.distribution_state(
            {"arms": {}}, self.DIMENSIONS, declaration_status="declared")
        self.assertEqual(state["status"], "none")

    def test_sharding_along_a_comparison_is_refused(self):
        """The one axis that is never allowed, because the ladder subtracts along it.

        Every rung compares two arms, so splitting by arm puts that subtraction
        across a hardware boundary and credits a mechanism with what the machine
        did.
        """
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "axis": "arm"}}, self.DIMENSIONS)
        self.assertEqual(state["status"], "incomplete")
        self.assertTrue(state["axisIsAComparison"])

    def test_any_other_axis_is_the_repository_s_business(self):
        """Reachable red: requiring `"seed"` would make this a forge for one paper.

        Another repository shards by subject, by fold, by episode, by patient.
        The skill has no notion of a seed and must not acquire one.
        """
        for axis in ("seed", "subject", "fold", "episode", "patient"):
            state = impl.distribution_state(
                {"distribution": {**self.COMPLETE, "axis": axis}}, self.DIMENSIONS)
            self.assertEqual(state["status"], "ok", axis)

    def test_a_dimension_in_neither_half_is_named(self):
        """Silently dropped, it becomes a column nobody notices is gone."""
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "perEnvironment": []}},
            self.DIMENSIONS)
        self.assertEqual(state["unpartitioned"], ["cost"])
        self.assertEqual(state["status"], "incomplete")

    def test_a_dimension_in_both_halves_is_named(self):
        """Pooled and grouped at once is two answers to one question."""
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "poolable": ["accuracy", "cost"]}},
            self.DIMENSIONS)
        self.assertEqual(state["inBothHalves"], ["cost"])
        self.assertEqual(state["status"], "incomplete")

    def test_a_declared_dimension_that_does_not_exist_is_named(self):
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "poolable": ["accuracy", "ghost"]}},
            self.DIMENSIONS)
        self.assertEqual(state["notADimension"], ["ghost"])

    def test_it_names_no_dimension_of_its_own(self):
        """The offending names are echoed from the repository, never written here.

        A skill that knew `seconds` describes a machine would be a skill that had
        learned one benchmark's vocabulary.
        """
        import json as _json
        source = _json.dumps([impl.DISTRIBUTION_DECLARATION,
                              impl.distribution_state.__doc__]).lower()
        for leaked in ("seconds", "peakmib", "accuracy", "seed", "kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)

    def test_shards_that_disagree_on_what_must_match_are_reported(self):
        """Refused rather than averaged: a difference there is a different
        experiment, not different hardware."""
        merged = {"shardsArrived": ["a", "b"],
                  "disagreements": [{"field": "revision", "values": {}}]}
        state = impl.distribution_state(
            {"distribution": self.COMPLETE}, self.DIMENSIONS, merged)
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual(state["shardsDisagree"], ["revision"])

    def test_the_forecast_scales_what_the_pilot_measured(self):
        """A projection from data, not an estimate from memory."""
        cost = impl._projected_cost(
            {"seconds": 600, "epochs": 3, "seeds": [0]},
            {"epochs": 20, "seeds": list(range(30))})
        self.assertEqual(cost["factor"], 200.0)
        self.assertEqual(cost["projectedSeconds"], 120000)

    def test_a_forecast_it_cannot_make_says_why(self):
        """A silent `None` reads as "the cost is fine" to anyone skimming.

        It means the record never wrote down how long it took, and the whole
        point of projecting from a measurement is that somebody kept one.
        """
        cost = impl._projected_cost({"epochs": 3}, {"epochs": 20})
        self.assertIsNone(cost["projectedSeconds"])
        self.assertIn("no duration", cost["reason"])

    def test_a_complete_declaration_with_agreeing_shards_passes(self):
        merged = {"shardsArrived": ["a", "b"], "disagreements": []}
        state = impl.distribution_state(
            {"distribution": self.COMPLETE}, self.DIMENSIONS, merged)
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["missing"], [])

    def test_per_run_dimensions_are_recognized_as_declared(self):
        """A replication measured that nothing here is stable across machines
        or across runs; `perRun` is the third way a dimension may be spoken for,
        not a gap `unpartitioned` should keep naming."""
        dist = {**self.COMPLETE, "poolable": [], "perRun": ["accuracy"]}
        state = impl.distribution_state({"distribution": dist}, self.DIMENSIONS)
        self.assertEqual(state["unpartitioned"], [])
        self.assertEqual(state["status"], "ok")

    def test_a_measured_empty_field_is_not_reported_missing(self):
        """Someone measured and the answer was `[]`; that is not silence."""
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "perEnvironment": []}},
            self.DIMENSIONS)
        self.assertNotIn(
            "perEnvironment", [row["field"] for row in state["missing"]])

    def test_a_field_never_answered_is_reported_missing(self):
        """The key was never set at all — nobody answered."""
        incomplete = dict(self.COMPLETE)
        del incomplete["perEnvironment"]
        state = impl.distribution_state(
            {"distribution": incomplete}, self.DIMENSIONS)
        self.assertIn(
            "perEnvironment", [row["field"] for row in state["missing"]])

    def test_a_field_of_the_wrong_shape_is_malformed_not_missing_or_answered(self):
        """A string typo'd where a list belongs is a third thing, not silently
        read as either present-and-answered or plainly missing."""
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "poolable": "accuracy"}},
            self.DIMENSIONS)
        self.assertNotIn(
            "poolable", [row["field"] for row in state["missing"]])
        self.assertIn(
            "poolable", [row["field"] for row in state["malformed"]])
        self.assertEqual(state["status"], "incomplete")

    def test_a_malformed_field_is_never_smuggled_into_the_partition(self):
        """`list("accuracy")` would read three letters as three dimensions;
        a malformed value must contribute nothing to the partition instead."""
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "poolable": "accuracy"}},
            self.DIMENSIONS)
        self.assertEqual(state["unpartitioned"], ["accuracy"])


class DeclaredDimensionNamesTests(unittest.TestCase):
    """The shard-level dimension universe, read the same way a target keeps it.

    `distribution_state` needs names, never directions, so this reads only
    `ast.Dict.keys` — the values are frequently bare names (`HIGHER`, `LOWER`)
    that `ast.literal_eval` cannot evaluate at all.
    """

    def bench(self, root: Path) -> Path:
        path = root / "src" / "Method_Benchmark"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_reads_keys_even_when_values_are_bare_names(self):
        """The real shape: directions are module constants, not literals."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "config.py").write_text(
                "HIGHER, LOWER, DESCRIPTIVE = 'higher', 'lower', None\n"
                "DIMENSIONS = {\n"
                "    'targetAccuracy': HIGHER,\n"
                "    'seconds': LOWER,\n"
                "    'contribution': DESCRIPTIVE,\n"
                "}\n", encoding="utf-8")
            names = impl.declared_dimension_names(root, "Method")
            self.assertEqual(names, ["targetAccuracy", "seconds", "contribution"])

    def test_config_py_takes_precedence_over_benchmark_py(self):
        """A materialized target keeps its own shard contract in config.py."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bench = self.bench(root)
            (bench / "config.py").write_text(
                "DIMENSIONS = {'fromConfig': None}\n", encoding="utf-8")
            (bench / "benchmark.py").write_text(
                "DIMENSIONS = {'fromKit': None}\n", encoding="utf-8")
            names = impl.declared_dimension_names(root, "Method")
            self.assertEqual(names, ["fromConfig"])

    def test_falls_back_to_benchmark_py_when_config_py_has_none(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bench = self.bench(root)
            (bench / "config.py").write_text("REDUCTION = {}\n", encoding="utf-8")
            (bench / "benchmark.py").write_text(
                "DIMENSIONS = {'fromKit': None}\n", encoding="utf-8")
            names = impl.declared_dimension_names(root, "Method")
            self.assertEqual(names, ["fromKit"])

    def test_absent_universe_is_none_not_an_empty_list(self):
        """`[]` reads as "declares zero dimensions" — trivially exhaustive.

        Reachable red: returning `[]` here instead of `None` would make this
        pass while silently emptying `unpartitioned` for every caller.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.bench(root)
            names = impl.declared_dimension_names(root, "Method")
            self.assertIsNone(names)

    def test_a_non_dict_dimensions_is_not_read_as_no_dimensions(self):
        """A name bound to something else is not a declaration of zero.

        Reachable red: treating any non-dict as `[]` would make this pass
        for the wrong reason — the assertion has to be `None`, not falsy.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "config.py").write_text(
                "DIMENSIONS = ['targetAccuracy', 'seconds']\n", encoding="utf-8")
            names = impl.declared_dimension_names(root, "Method")
            self.assertIsNone(names)

    def test_a_non_dict_in_config_py_falls_through_to_benchmark_py(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bench = self.bench(root)
            (bench / "config.py").write_text(
                "DIMENSIONS = compute_dimensions()\n", encoding="utf-8")
            (bench / "benchmark.py").write_text(
                "DIMENSIONS = {'fromKit': None}\n", encoding="utf-8")
            names = impl.declared_dimension_names(root, "Method")
            self.assertEqual(names, ["fromKit"])

    def test_an_unparsable_file_does_not_raise_and_falls_through(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bench = self.bench(root)
            (bench / "config.py").write_text("DIMENSIONS = {\n", encoding="utf-8")
            (bench / "benchmark.py").write_text(
                "DIMENSIONS = {'fromKit': None}\n", encoding="utf-8")
            names = impl.declared_dimension_names(root, "Method")
            self.assertEqual(names, ["fromKit"])

    def test_a_key_that_is_not_a_constant_string_is_skipped_not_raised(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "config.py").write_text(
                "OTHER = {'ghost': None}\n"
                "DIMENSIONS = {**OTHER, 'real': None}\n", encoding="utf-8")
            names = impl.declared_dimension_names(root, "Method")
            self.assertEqual(names, ["real"])


class VerifyDistributionUniverseTests(unittest.TestCase):
    """`verify` classifies a shard's dimensions, not the report's.

    A report can render latent-analysis quantities no shard ever carries —
    a class-separation figure, an attention diagnostic — and none of those
    belong in the partition a machine split has to be exhaustive over.
    Demanding a classification for them is a category error, not a missing
    declaration, and this is the seam where that used to leak in.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'dimensions': {'shardOnly': 'higher', 'latentOnly': None},\n"
        "    },\n"
        "    'distribution': {\n"
        "        'axis': 'seed',\n"
        "        'poolable': ['shardOnly'],\n"
        "        'perEnvironment': [],\n"
        "        'perRun': [],\n"
        "        'identicalAcrossShards': [],\n"
        "    },\n"
        "}\n"
    )

    def _box(self, tag: str) -> Path:
        box = FORGE / "implementations" / f"_dist_universe_{tag}_{os.getpid()}"
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        return box

    def test_a_dimension_the_report_renders_but_no_shard_carries_is_never_demanded(self):
        """Reachable red: sourcing this from the report's dimensions instead
        of `config.DIMENSIONS` would put `latentOnly` in `unpartitioned` and
        report `incomplete` for a declaration that classified everything a
        shard actually has."""
        box = self._box("universe")
        try:
            (box / "src" / "Method_Benchmark" / "config.py").write_text(
                "DIMENSIONS = {'shardOnly': None}\n", encoding="utf-8")
            result = impl.cmd_verify(
                argparse.Namespace(target=str(box), name="Method", revision=None))
        finally:
            shutil.rmtree(box, ignore_errors=True)

        distribution = result["distribution"]
        self.assertEqual(distribution["unpartitioned"], [])
        self.assertEqual(distribution["status"], "ok")
        self.assertEqual(distribution["dimensionSource"], ["shardOnly"])

    def test_an_undetermined_universe_never_silently_reads_as_exhaustive(self):
        """No `config.py`, no `benchmark.py`: the universe is unknown, and
        that has to say so rather than pass by having nothing to check."""
        box = self._box("unknown")
        try:
            result = impl.cmd_verify(
                argparse.Namespace(target=str(box), name="Method", revision=None))
        finally:
            shutil.rmtree(box, ignore_errors=True)

        distribution = result["distribution"]
        self.assertIsNone(distribution["dimensionSource"])
        self.assertEqual(distribution["unpartitioned"], [])
        self.assertIn("note", distribution)


class ResolveBenchmarkDeclarationTests(unittest.TestCase):
    """The one place every reader gets `__benchmark__` from.

    Before this resolver, four call sites checked `__init__.py` only while two
    checked both `__init__.py` and `config.py` — so a declaration written in
    `config.py` alone passed for two readers and read as absent for the rest.
    These pin the resolver's own contract; `ResolverCrossReaderAgreementTests`
    below proves the split verdict itself is closed.
    """

    def bench(self, root: Path) -> Path:
        path = root / "src" / "Method_Benchmark"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_no_benchmark_directory_is_absent(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            resolved = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(resolved["status"], "absent")
        self.assertIsNone(resolved["path"])
        self.assertIsNone(resolved["detail"])
        self.assertEqual(resolved["contract"], {})

    def test_directory_with_neither_file_declaring_is_undeclared(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.bench(root)
            resolved = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(resolved["status"], "undeclared")
        self.assertIsNone(resolved["path"])
        self.assertIn("__benchmark__", resolved["detail"])
        self.assertEqual(resolved["contract"], {})

    def test_declared_in_init_py_is_found(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "__init__.py").write_text(
                "__benchmark__ = {'revision': 'r01.md'}\n", encoding="utf-8")
            resolved = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(resolved["status"], "declared")
        self.assertEqual(resolved["path"], "src/Method_Benchmark/__init__.py")
        self.assertEqual(resolved["contract"], {"revision": "r01.md"})

    def test_declared_in_config_py_alone_is_found(self):
        """The defect this resolver closes: a declaration living only in
        `config.py` used to read as absent everywhere but two call sites."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "config.py").write_text(
                "__benchmark__ = {'revision': 'r01.md'}\n", encoding="utf-8")
            resolved = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(resolved["status"], "declared")
        self.assertEqual(resolved["path"], "src/Method_Benchmark/config.py")
        self.assertEqual(resolved["contract"], {"revision": "r01.md"})

    def test_init_py_takes_precedence_over_config_py(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bench = self.bench(root)
            (bench / "__init__.py").write_text(
                "__benchmark__ = {'revision': 'fromInit'}\n", encoding="utf-8")
            (bench / "config.py").write_text(
                "__benchmark__ = {'revision': 'fromConfig'}\n", encoding="utf-8")
            resolved = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(resolved["contract"]["revision"], "fromInit")

    def test_an_unparsable_declaration_is_undeclared_with_the_parse_error(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "__init__.py").write_text(
                "__benchmark__ = {\n", encoding="utf-8")
            resolved = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(resolved["status"], "undeclared")
        self.assertEqual(resolved["path"], "src/Method_Benchmark/__init__.py")
        self.assertIn("unparsable", resolved["detail"])
        self.assertEqual(resolved["contract"], {})

    def test_a_declaration_that_parses_with_every_block_blank_is_undeclared(self):
        """The companion decision: a scaffold that parses is not a scaffold
        that has said anything. Every block at its empty value must read the
        same as no `__benchmark__` at all, or a fresh Flow A scaffold would
        pass for a finished declaration on the day it is written."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "__init__.py").write_text(
                "__benchmark__ = {'revision': '', 'premises': {}, 'arms': {}, "
                "'search': {}, 'report': {}, 'distribution': {}}\n",
                encoding="utf-8")
            resolved = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(resolved["status"], "undeclared")
        self.assertIn("empty", resolved["detail"])
        self.assertEqual(resolved["contract"], {})

    def test_one_answered_block_among_five_blank_ones_is_declared(self):
        """The other pole: a single answer anywhere is enough to leave
        `undeclared` behind, because `arms`/`search`/`report`/`distribution`
        each report their own state once the whole declaration is `declared`."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "__init__.py").write_text(
                "__benchmark__ = {'revision': 'r01.md', 'premises': {}, "
                "'arms': {}, 'search': {}, 'report': {}, 'distribution': {}}\n",
                encoding="utf-8")
            resolved = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(resolved["status"], "declared")
        self.assertEqual(resolved["contract"]["revision"], "r01.md")


class ResolverCrossReaderAgreementTests(unittest.TestCase):
    """A declaration living only in `config.py` must not be a split verdict.

    Before the resolver, `unreached_mathematics`'s caller and `verify`'s
    `benchmark` block saw a `config.py`-only declaration while
    `report_contract`, `search_state` and `distribution_state` did not — the
    same declaration, four different answers. This walks `cmd_verify` end to
    end and confirms every reader now agrees it is present.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'search': {'material': 'validation split'},\n"
        "    'report': {'renderers': ['tables.render']},\n"
        "    'premises': '',\n"
        "    'distribution': {\n"
        "        'axis': 'seed',\n"
        "        'poolable': [],\n"
        "        'perEnvironment': [],\n"
        "        'perRun': [],\n"
        "        'identicalAcrossShards': [],\n"
        "    },\n"
        "}\n"
    )

    def _box(self) -> Path:
        box = FORGE / "implementations" / f"_resolver_agreement_{os.getpid()}"
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        # Declared only in config.py, never in __init__.py — the shape that
        # used to split the verdict.
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text("", encoding="utf-8")
        (box / "src" / "Method_Benchmark" / "config.py").write_text(
            self.DECLARATION, encoding="utf-8")
        return box

    def test_every_reader_sees_a_declaration_that_lives_only_in_config_py(self):
        box = self._box()
        try:
            result = impl.cmd_verify(
                argparse.Namespace(target=str(box), name="Method", revision=None))
            contract = impl.report_contract(box, "Method")
        finally:
            shutil.rmtree(box, ignore_errors=True)

        benchmark = result["fidelity"]["benchmark"]
        self.assertNotIn(benchmark["status"], ("absent", "undeclared"), benchmark)
        self.assertNotEqual(result["search"]["status"], "none", result["search"])
        self.assertNotEqual(result["distribution"]["status"], "none",
                            result["distribution"])
        self.assertEqual(contract, {"renderers": ["tables.render"]})


class DoctrineAmendmentTests(unittest.TestCase):
    """The record's clause and the launcher's clause governed different things.

    Only the launcher's ever moved. Asserting sentence-one survival alone would
    already pass before the amendment, since that sentence is untouched today —
    the reachable red is the second assertion, so both live in one test.
    """

    SKILL_MD = CLI.parent.parent / "SKILL.md"

    def test_amendment_preserves_sentence_and_revokes_launcher_clause(self):
        text = self.SKILL_MD.read_text(encoding="utf-8")
        self.assertIn(
            "No service is named here, and none should be.", text,
            "the sentence governing what the RECORD names must survive verbatim")
        collapsed = " ".join(text.split())
        self.assertNotIn(
            "belongs in `tools/` for the reasons that section gives", collapsed,
            "the clause governing where the launcher's CODE lives must be revoked")


class ToolsRootTests(unittest.TestCase):
    """`tools/` is where a launcher lives, and it needed a home.

    The same shape of problem the sibling-package rule already solved: a script
    that operates a run cannot sit in the method's package, because it implements
    no equation and could only be there by declaring a `__provenance__` it has no
    right to; it cannot sit in the benchmark's package, because it neither trains
    nor measures; and it cannot stay untracked, because then the configuration of
    a multi-hour campaign lives on one disk and no later session can reproduce
    how it was launched. No place existed, and that absence is the argument.
    """

    def build(self, root: Path, *relatives: str) -> list:
        for relative in ("src/Method/kernels.py", "tests/test_smoke.py", *relatives):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("X = 1\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "base"], cwd=root, check=True)
        paths = impl.present_files(root)
        return [p for p in paths
                if p.endswith(".py")
                and not p.startswith(impl.SOURCE_ROOTS)
                and Path(p).parts[0] not in impl.IGNORED_DIRS
                and Path(p).name != "setup.py"]

    def test_a_launcher_under_tools_is_not_a_stray_module(self):
        """Reachable red: without `tools/` among the roots, this is a stray."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertEqual(self.build(root, "tools/distribute.py"), [])

    def test_a_script_loose_at_the_top_is_still_a_stray_module(self):
        """The permission is a named place, not an amnesty."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertEqual(self.build(root, "run_it.py"), ["run_it.py"])

    def test_a_launcher_is_never_asked_for_a_provenance(self):
        """A launcher implements no equation, so it must never be asked for one.

        Safe by construction rather than by a guard: the provenance scan only
        recurses into `src/<Package>/`. Pinned end to end so a later widening of
        that walk cannot quietly start demanding a stamp `tools/` cannot honestly
        give — the falsified provenance the sibling-package rule exists to prevent.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for relative, body in (
                ("src/Method/kernels.py",
                 '__provenance__ = {"revision": "r01.md", "sections": ["1"],\n'
                 '                  "equations": ["1"], "invariants": ["holds"]}\n'),
                ("tests/test_invariants.py", "def test_holds():\n    assert True\n"),
                ("tools/distribute.py", "ACCELERATOR = 'X'\n"),
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")

            missing = [str(f.relative_to(root))
                       for f in sorted((root / "src" / "Method").rglob("*.py"))
                       if impl.read_declaration(f, "__provenance__") is None]
            self.assertEqual(missing, [])
            self.assertTrue((root / "tools/distribute.py").exists(),
                            "el lanzador existe y aun asi nadie le pide procedencia")


class ProseTests(unittest.TestCase):
    """Claims in prose that stopped being true, where nothing else would notice.

    Every other check reads a declaration or a file. These read sentences, and a
    sentence ages without anything failing: a rename leaves the old symbol named
    in the paragraph beside it, a new revision leaves the old one in a heading.
    """

    def build(self, root: Path, **files: str) -> None:
        for relative, body in files.items():
            path = root / relative.replace("__", "/")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

    def test_a_revision_named_in_prose_that_is_not_the_current_one(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py":
                    '"""Verified against research-concept-r16.md."""\nK = 1\n',
            })
            state = impl.prose_state(root, "research-concept-r17.md")
            self.assertEqual(len(state["staleRevisions"]), 1)
            self.assertEqual(state["staleRevisions"][0]["named"],
                             "research-concept-r16.md")

    def test_the_current_revision_in_prose_is_not_reported(self):
        """Rojo alcanzable: reportarlas todas haría el hallazgo inútil."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py":
                    '"""Verified against research-concept-r17.md."""\nK = 1\n',
            })
            self.assertEqual(
                impl.prose_state(root, "research-concept-r17.md")["staleRevisions"], [])

    def test_the_pattern_comes_from_the_revision_handed_in(self):
        """Nada acá conoce una convención de nombres: se deriva del argumento."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py": '"""Bound to paper-v3.md."""\nK = 1\n',
            })
            state = impl.prose_state(root, "paper-v9.md")
            self.assertEqual(state["staleRevisions"][0]["named"], "paper-v3.md")

    def test_a_symbol_named_in_prose_that_resolves_to_nothing(self):
        """Lo que deja un rename: el párrafo sigue nombrando la constante vieja."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__config.py": "RAMP_CEILING = 1.0\n",
                "src__Method__figures.py":
                    '"""The coefficient is fixed at `LAMBDA_CONST` for every arm."""\n',
            })
            found = impl.prose_state(root, None)["unresolvedSymbols"]
            self.assertEqual([f["symbol"] for f in found], ["LAMBDA_CONST"])

    def test_a_symbol_that_exists_is_not_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__config.py": "RAMP_CEILING = 1.0\n",
                "src__Method__figures.py":
                    '"""Fixed at `RAMP_CEILING` for every arm."""\n',
            })
            self.assertEqual(impl.prose_state(root, None)["unresolvedSymbols"], [])

    def test_a_filename_is_not_mistaken_for_a_symbol(self):
        """Dotted y con guion bajo es exactamente lo que parece un archivo, y la
        prosa nombra archivos todo el tiempo."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py":
                    '"""See `Results_Generator.ipynb` and `requirements.txt`."""\nK = 1\n',
            })
            self.assertEqual(impl.prose_state(root, None)["unresolvedSymbols"], [])

    def test_code_is_not_read_as_prose(self):
        """Una revisión dentro de un literal es código y se chequea en otro lado;
        reportarla acá sería ruido sobre algo que ya tiene su verificación."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py":
                    '__provenance__ = {"revision": "research-concept-r16.md"}\n',
            })
            self.assertEqual(
                impl.prose_state(root, "research-concept-r17.md")["staleRevisions"], [])


class StaleFindingTests(unittest.TestCase):
    """Un hallazgo del reporte se lee de lo que un cuaderno **emitió**.

    Sobre un cuaderno obsoleto describe la corrida que pasó, no el código que hay
    ahora. Las dos mitades ya se reportaban —el hallazgo y el estado del
    cuaderno— en dos lugares distintos de la misma salida, y nadie las cruzaba.
    Un lector que lo toma por defecto vivo va y arregla algo ya arreglado, o lo
    arregla de una segunda manera.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'renderers': ['tables.render'],\n"
        "        'conclusions': ['tables.conclusion'],\n"
        "        'objectiveEntry': 'tables.objective',\n"
        "        'components': {'terms': ['fit'], 'share': None},\n"
        "        'dimensions': {'accuracy': 'higher', 'fit': None},\n"
        "    },\n"
        "}\n")

    def build(self, root: Path, digest_matches: bool,
              unexecuted: bool = False, errored: bool = False) -> dict:
        (root / "src/Method_Benchmark").mkdir(parents=True, exist_ok=True)
        (root / "src/Method_Benchmark/__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        (root / "src/Method").mkdir(parents=True, exist_ok=True)
        (root / "src/Method/kernels.py").write_text("K = 1\n", encoding="utf-8")

        digest = (impl.source_digest(root, "Method") if digest_matches
                  else "0" * 64)
        cells = [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["tables.render()"],
             "outputs": [{"output_type": "stream", "name": "stdout",
                          "text": ["acc 81.5  peor 67.1  piso 0.0\n"]}]},
            {"cell_type": "code", "execution_count": 2, "metadata": {},
             "source": ["tables.conclusion()"],
             "outputs": [{"output_type": "stream", "name": "stdout",
                          "text": ["mejor 81.5, peor 67.1, piso 0.0\n"]}]},
            {"cell_type": "code", "execution_count": 3, "metadata": {},
             "source": [f'print("{impl.DIGEST_MARKER} {digest}")'],
             "outputs": [{"output_type": "stream", "name": "stdout",
                          "text": [f"{impl.DIGEST_MARKER} {digest}\n"]}]},
        ]
        if unexecuted:
            cells.append({"cell_type": "code", "execution_count": None,
                          "metadata": {}, "source": ["tables.render()"],
                          "outputs": []})
        if errored:
            cells.append({"cell_type": "code", "execution_count": 4,
                          "metadata": {}, "source": ["tables.render()"],
                          "outputs": [{"output_type": "error",
                                       "ename": "NameError", "evalue": "tables",
                                       "traceback": []}]})
        nb = root / "Method/Notebooks/report.ipynb"
        nb.parent.mkdir(parents=True, exist_ok=True)
        nb.write_text(json.dumps({"cells": cells, "metadata": {},
                                  "nbformat": 4, "nbformat_minor": 5}),
                      encoding="utf-8")
        return impl.report_state(root, "Method", "Method")

    def test_a_finding_from_a_stale_notebook_says_so(self):
        with tempfile.TemporaryDirectory() as raw:
            state = self.build(Path(raw), digest_matches=False)
            found = state["restated"]
            self.assertTrue(found, "el fixture tiene que producir el hallazgo")
            self.assertTrue(found[0]["fromStaleNotebook"])

    def test_a_finding_from_a_current_notebook_carries_no_flag(self):
        """Rojo alcanzable: marcarlos todos haría la bandera inútil."""
        with tempfile.TemporaryDirectory() as raw:
            state = self.build(Path(raw), digest_matches=True)
            found = state["restated"]
            self.assertTrue(found, "el fixture tiene que producir el hallazgo")
            self.assertNotIn("fromStaleNotebook", found[0])

    def test_a_notebook_too_stale_to_be_called_stale_sources_still_says_so(self):
        """La escalera de estados es excluyente, y esta bandera leía un peldaño.

        Un cuaderno con celdas sin correr se llama `stale` y ahí se queda: nunca
        llega a la comparación de digest, así que sus fuentes pueden diferir en
        todo y el estado no cambia. Filtrar por `stale-sources` entonces pierde la
        marca justo cuando el cuaderno está más desactualizado y no menos —
        corrió a medias *y* contra otro código— que es la única dirección en la
        que este error podía ser peligroso.
        """
        with tempfile.TemporaryDirectory() as raw:
            state = self.build(Path(raw), digest_matches=False, unexecuted=True)
            found = state["restated"]
            self.assertTrue(found, "el fixture tiene que producir el hallazgo")
            self.assertTrue(found[0].get("fromStaleNotebook"))

    def test_a_finding_read_off_a_notebook_that_failed_says_so(self):
        """Un cuaderno con un error corrió parte de sus celdas y abandonó el
        resto, así que lo que emitió describe una corrida que no terminó."""
        with tempfile.TemporaryDirectory() as raw:
            state = self.build(Path(raw), digest_matches=True, errored=True)
            found = state["restated"]
            self.assertTrue(found, "el fixture tiene que producir el hallazgo")
            self.assertTrue(found[0].get("fromStaleNotebook"))


class ComponentShareTests(unittest.TestCase):
    """Un término bien implementado y multiplicado por algo minúsculo da una
    columna de casi-ceros que se lee como resultado.

    `contribution` sola — el numerador, sin denominador al lado — no distingue
    "el término no comandó nada" de "el término fue escalado a nada", y las dos
    imprimen chico. La regla existía en prosa y un repositorio entregó el
    numerador solo con la verificación en verde.

    Lo que se chequea es la declaración, nunca el significado: nada acá puede
    aprender cómo se llama un término del objetivo de alguien.
    """

    BASE = ("__benchmark__ = {\n"
            "    'revision': 'r01.md',\n"
            "    'arms': {},\n"
            "    'report': {\n"
            "        'renderers': ['tables.render'],\n"
            "        'conclusions': ['tables.conclusion'],\n"
            "        'objectiveEntry': 'tables.objective',\n"
            "%s"
            "        'dimensions': %s,\n"
            "    },\n"
            "}\n")

    def state(self, root: Path, components: str, dimensions: str) -> dict:
        (root / "src/Method_Benchmark").mkdir(parents=True, exist_ok=True)
        (root / "src/Method_Benchmark/__init__.py").write_text(
            self.BASE % (components, dimensions), encoding="utf-8")
        (root / "Method/Notebooks").mkdir(parents=True, exist_ok=True)
        return impl.report_state(root, "Method", "Method")

    def test_a_package_that_declares_no_components_is_told_why_that_matters(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            found = self.state(root, "", "{'accuracy': 'higher'}")["componentsWithoutShare"]
            self.assertEqual(len(found), 1)
            self.assertIn("no declara `components`", found[0]["reason"])

    def test_more_than_one_term_and_no_share_is_the_gap_the_rule_is_about(self):
        """Dos términos que se suman y ninguna forma de leer la parte de cada uno."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            found = self.state(
                root,
                "        'components': {'terms': ['fit', 'align'], 'share': None},\n",
                "{'accuracy': 'higher', 'fit': None, 'align': None}",
            )["componentsWithoutShare"]
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["terms"], ["fit", "align"])

    def test_a_declared_term_the_record_never_carries_is_named(self):
        """Declararlo y no registrarlo deja la parte sin poder computarse igual."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = self.state(
                root,
                "        'components': {'terms': ['fit', 'align'], 'share': 'alignShare'},\n",
                "{'accuracy': 'higher', 'fit': None}",
            )
            self.assertEqual(state["componentsNotRecorded"], ["align", "alignShare"])

    def test_terms_and_share_both_recorded_raise_nothing(self):
        """Rojo alcanzable: si el chequeo no leyera `dimensions`, esto fallaría."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = self.state(
                root,
                "        'components': {'terms': ['fit', 'align'], 'share': 'alignShare'},\n",
                "{'accuracy': 'higher', 'fit': None, 'align': None, 'alignShare': None}",
            )
            self.assertEqual(state["componentsNotRecorded"], [])
            self.assertEqual(state["componentsWithoutShare"], [])


class CellOutputTests(unittest.TestCase):
    """Los dos chequeos que leen la salida de una celda y no su código.

    Todo lo demás en `report_state` se contesta desde las fuentes. Estos dos no:
    una celda puede correr, no levantar nada, emitir una salida, y no haber
    mostrado nada. `execution_count` dice que corrió y la lista de errores está
    vacía, así que cualquier chequeo que lea solo esas dos la aprueba.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'renderers': ['tables.render'],\n"
        "        'conclusions': ['tables.conclusion'],\n"
        "        'objectiveEntry': 'tables.objective',\n"
        "        'figures': ['figures.curves'],\n"
        "        'components': {'terms': ['fit'], 'share': None},\n"
        "        'dimensions': {'accuracy': 'higher', 'fit': None},\n"
        "    },\n"
        "}\n"
    )

    FRAME = _cell("markdown", "Qué mide: la exactitud. Más alto es mejor.")
    AIM = _cell("code", "print(tables.objective('accuracy'))")
    TABLE = _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                          "print(tables.conclusion(runs, 'accuracy', reduction))")

    def state(self, cells, declaration=None):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "src/Method_Benchmark").mkdir(parents=True)
            (root / "src/Method_Benchmark/__init__.py").write_text(
                declaration or self.DECLARATION, encoding="utf-8")
            notebooks = root / "Method/Notebooks"
            notebooks.mkdir(parents=True)
            (notebooks / "Report.ipynb").write_text(
                json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                            "nbformat_minor": 5}), encoding="utf-8")
            return impl.report_state(root, "Method", "Method")

    def drawing(self, outputs):
        return [_cell("markdown", "La figura muestra las curvas."),
                _cell("code", "figures.curves(path)", outputs=outputs)]

    def test_a_figure_that_came_out_as_a_description_is_caught(self):
        """El defecto real: `display(fig)` sin el formateador registrado emite
        `<Figure size ...>` como texto. La celda corrió, no levantó nada, produjo
        una salida — y le muestra al lector una línea de prosa donde va el dibujo.
        """
        found = self.state(self.drawing([_shown("text/plain", "<Figure size 640x480>")]))
        self.assertEqual(len(found["describedNotShown"]), 1, found["describedNotShown"])
        self.assertEqual(found["describedNotShown"][0]["drawing"], "figures.curves")
        self.assertEqual(found["describedNotShown"][0]["emitted"], ["text/plain"])

    def test_a_figure_that_printed_its_filename_is_caught(self):
        """Guardar y anunciar la ruta es la misma falla con otra ropa: la celda
        informa un nombre de archivo donde debería haber un resultado."""
        found = self.state(self.drawing([_stream("escrita: curves.pdf\n")]))
        self.assertEqual(len(found["describedNotShown"]), 1)
        self.assertEqual(found["describedNotShown"][0]["emitted"], ["texto"])

    def test_a_figure_that_actually_rendered_passes(self):
        """El verde tiene que ser alcanzable, o el rojo de arriba no prueba nada."""
        self.assertEqual(self.state(self.drawing([_shown("image/png")]))["describedNotShown"], [])

    def test_any_image_mime_counts_as_shown(self):
        """Nada acá puede saber en qué formato dibuja alguien. Un SVG es una
        figura mostrada tanto como un PNG, y exigir uno sería aprender la cadena
        de herramientas de un repositorio."""
        for mime in ("image/png", "image/svg+xml", "image/jpeg"):
            with self.subTest(mime=mime):
                self.assertEqual(
                    self.state(self.drawing([_shown(mime)]))["describedNotShown"], [])

    def test_a_measurement_computed_and_never_shown_is_caught(self):
        cells = [self.FRAME,
                 _cell("code", "tabla = tables.render(runs, 'accuracy', reduction)\n"
                               "conclusion = tables.conclusion(runs, 'accuracy', reduction)",
                       outputs=[])]
        found = self.state(cells)["unrendered"]
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["rendering"], "tables.render")

    def test_a_table_that_printed_is_not_reported_as_unrendered(self):
        self.assertEqual(self.state([self.FRAME, self.TABLE])["unrendered"], [])

    def test_the_cell_that_writes_the_record_may_show_nothing(self):
        """Escribir el registro es su trabajo entero. Exigirle una salida visible
        haría que la forma de aprobar sea imprimir el archivo."""
        cells = [self.FRAME, self.TABLE,
                 _cell("markdown", "el registro"),
                 _cell("code", "(root / 'r.txt').write_text("
                               "tables.render(runs, 'accuracy', reduction))",
                       outputs=[])]
        self.assertEqual(self.state(cells)["unrendered"], [])

    def test_an_unexecuted_cell_is_not_a_report_defect(self):
        """Un cuaderno sin ejecutar ya es un hallazgo de `validation`. Repetirlo
        acá como un defecto de informe por celda enterraría a los que sí lo son.
        """
        cells = [self.FRAME,
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))",
                       outputs=[], executed=False),
                 _cell("markdown", "la figura"),
                 _cell("code", "figures.curves(path)", outputs=[], executed=False)]
        state = self.state(cells)
        self.assertEqual(state["unrendered"], [])
        self.assertEqual(state["describedNotShown"], [])

    def test_a_cell_that_raised_is_reported_once_and_not_twice(self):
        """El error lo informa `notebook_execution`. Sin marcarlo, esta celda
        también leería como una que no mostró nada, y un defecto saldría dos
        veces con dos nombres distintos."""
        error = {"output_type": "error", "ename": "ValueError",
                 "evalue": "x", "traceback": []}
        state = self.state(self.drawing([error]))
        self.assertEqual(state["describedNotShown"], [])

    SILENT = DECLARATION.replace("        'figures': ['figures.curves'],\n", "")

    def test_a_description_is_caught_with_no_declaration_at_all(self):
        """El hallazgo del e2e sobre el repositorio real, convertido en prueba.

        Ese paquete declaraba `renderers` y `conclusions` y ninguna llamada de
        dibujo, así que la comprobación quedaba inerte justo en el repositorio
        cuyo defecto la motivó. Una red que solo se activa cuando alguien escribió
        una clave opcional no es una red. La forma de la salida alcanza: un
        `text/plain` que es el repr de un objeto es una descripción-de-figura la
        haya dibujado quien la haya dibujado, y ahí no se nombra ninguna librería.
        """
        state = self.state(self.drawing([_shown("text/plain", "<Figure size 640x480>")]),
                           self.SILENT)
        self.assertEqual(len(state["describedNotShown"]), 1, state["describedNotShown"])
        found = state["describedNotShown"][0]
        self.assertEqual(found["drawing"], "<sin declarar>")
        self.assertEqual(found["description"], "<Figure size 640x480>")
        self.assertEqual(state["status"], "drift")

    def test_the_repr_of_any_object_reads_as_a_description(self):
        """No hay una lista de librerías acá, y no puede haberla. Lo que delata al
        defecto es que la celda mostró el repr de algo en vez de la cosa."""
        for repr_text in ("<Figure size 640x480 with 6 Axes>",
                          "<matplotlib.axes._axes.Axes object at 0x10a3f>",
                          "[<Line2D object at 0x7fa1>]"):
            with self.subTest(repr_text=repr_text):
                state = self.state(self.drawing([_shown("text/plain", repr_text)]),
                                   self.SILENT)
                self.assertEqual(len(state["describedNotShown"]), 1, repr_text)

    def test_a_rich_rendering_carries_a_repr_beside_it_and_that_is_not_a_defect(self):
        """El falso positivo que el e2e sacó a la luz, y que la suite no cubría.

        Una salida rica guarda su repr de respaldo AL LADO: un Markdown mostrado
        deja `<IPython.core.display.Markdown object>` en `text/plain` junto a su
        `text/markdown`. Esa celda mostró lo que tenía que mostrar. Leer la celda
        entera en vez de cada salida marcaba las once celdas de encabezado del
        repositorio real como figuras que nunca se dibujaron — y once hallazgos
        falsos entierran al verdadero, que es peor que no tener el hallazgo.
        """
        rich = {"output_type": "display_data",
                "data": {"text/markdown": "## Qué mide",
                         "text/plain": "<IPython.core.display.Markdown object>"},
                "metadata": {}}
        state = self.state([self.FRAME, _cell("code", "display(Markdown(texto))",
                                              outputs=[rich])], self.SILENT)
        self.assertEqual(state["describedNotShown"], [])

    def test_ordinary_printed_output_is_not_a_description(self):
        """El rojo de arriba no sirve de nada si una tabla impresa también lo
        dispara: un informe que grita en cada celda se lee salteando."""
        for text in ("accuracy  0.81", "escrita: curves.pdf", "a < b > c"):
            with self.subTest(text=text):
                state = self.state([self.FRAME, _cell("code", "print(resumen)",
                                                      outputs=[_shown("text/plain", text)])],
                                   self.SILENT)
                self.assertEqual(state["describedNotShown"], [], text)

    def test_a_picture_no_declared_call_could_have_drawn_is_a_finding(self):
        """Lo que impide que las dos comprobaciones de arriba sean una cortesía.
        Sin esto, un paquete que no declara `figures` es indistinguible de uno
        cuyas figuras están todas bien — y el informe sale limpio."""
        state = self.state(self.drawing([_shown("image/png")]), self.SILENT)
        self.assertEqual(len(state["undeclaredDrawings"]), 1, state["undeclaredDrawings"])
        self.assertIn("figures.curves", state["undeclaredDrawings"][0]["calls"])
        self.assertEqual(state["status"], "drift")

    def test_a_declared_drawing_that_showed_its_picture_is_not_undeclared(self):
        """El verde tiene que seguir siendo alcanzable declarando, o el hallazgo
        de arriba no pide una declaración: pide que nadie dibuje."""
        state = self.state(self.drawing([_shown("image/png")]))
        self.assertEqual(state["undeclaredDrawings"], [])
        # No `ok`: sin intérprete del target la sonda `live` no corre y el estado
        # queda `incomplete`, que es una limitación del banco y no del hallazgo.
        # Lo que esta prueba defiende es que declarar y mostrar no produce deriva.
        self.assertNotEqual(state["status"], "drift")

    def _table_then_conclusion(self, table_out, conclusion_out):
        return [self.FRAME,
                _cell("code", "print(tables.render(runs, 'accuracy', reduction))",
                      outputs=[_shown("text/plain", table_out)]),
                _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))",
                      outputs=[_shown("text/plain", conclusion_out)])]

    def test_a_conclusion_that_restates_its_own_table_is_caught(self):
        """Encontrado leyendo un informe real, no razonando sobre el código.

        `duplicated` compara un renderizado con otro y no puede ver este caso: la
        segunda copia no es un renderizado, es una frase. Y el número no está en
        ninguna de las dos fuentes — está en lo que las dos celdas emitieron, así
        que solo se ve leyendo las salidas.
        """
        state = self.state(self._table_then_conclusion(
            "A 0.81 · B 0.74 · C 0.69 · D 0.55",
            "Los aciertos: A 0.81, B 0.74, C 0.69, D 0.55."))
        self.assertEqual(len(state["restated"]), 1, state["restated"])
        found = state["restated"][0]
        self.assertEqual(found["table"], 1)
        self.assertEqual(found["count"], 4)
        self.assertEqual(state["status"], "drift")

    def test_a_conclusion_may_name_the_value_it_rests_on(self):
        """El verde tiene que quedar alcanzable, o el hallazgo no pide una
        conclusión: pide una conclusión sin evidencia. Nombrar quién va adelante y
        con cuánto es el trabajo de la conclusión, no una segunda tabla."""
        state = self.state(self._table_then_conclusion(
            "A 0.81 · B 0.74 · C 0.69 · D 0.55",
            "Mejor: **A** con 0.81; peor: D con 0.55."))
        self.assertEqual(state["restated"], [])

    def test_a_conclusion_is_never_matched_against_another_notebook_table(self):
        """El emparejamiento se reinicia por cuaderno. Sin eso, la primera
        conclusión de un cuaderno se compararía contra la última tabla del
        anterior, y el hallazgo señalaría dos celdas que nunca se vieron."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "src/Method_Benchmark").mkdir(parents=True)
            (root / "src/Method_Benchmark/__init__.py").write_text(
                self.DECLARATION, encoding="utf-8")
            notebooks = root / "Method/Notebooks"
            notebooks.mkdir(parents=True)
            (notebooks / "A_tabla.ipynb").write_text(json.dumps({
                "cells": [self.FRAME,
                          _cell("code", "print(tables.render(runs, 'accuracy', reduction))",
                                outputs=[_shown("text/plain", "A 0.81 B 0.74 C 0.69")])],
                "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
            (notebooks / "B_conclusion.ipynb").write_text(json.dumps({
                "cells": [self.FRAME,
                          _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))",
                                outputs=[_shown("text/plain", "A 0.81 B 0.74 C 0.69")])],
                "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
            state = impl.report_state(root, "Method", "Method")
        self.assertEqual(state["restated"], [])

    def test_the_echo_still_shows_the_key_when_nothing_was_declared(self):
        """Declarar ninguna llamada no es lo mismo que no dibujar, y el eco lo
        tiene que dejar ver en vez de callar."""
        state = self.state([self.FRAME, self.TABLE], self.SILENT)
        self.assertEqual(state["declared"]["figures"], [])

    def test_a_figure_defect_puts_the_whole_report_in_drift(self):
        """Sin esto el hallazgo existiría y no frenaría nada: es el estado del
        informe lo que hace que `probe` conteste `report-first` en vez de ofrecer
        la campaña."""
        state = self.state(self.drawing([_shown("text/plain", "<Figure ...>")]))
        self.assertEqual(state["status"], "drift")


class CellOutputEndToEndTests(unittest.TestCase):
    """El chequeo, desde `argv` hasta el JSON que lee una persona.

    Las pruebas de arriba llaman a `report_state` directo, así que verifican las
    dos mitades y nunca la unión. Esta cruza la junta: arma un repositorio de
    juguete, corre el CLI como proceso, y le pregunta a la herramienta qué ve.

    El objetivo vive bajo `implementations/` porque el guardia lo exige, con un
    nombre que no puede chocar con nada, y se borra pase lo que pase.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'renderers': ['tables.render'],\n"
        "        'conclusions': ['tables.conclusion'],\n"
        "        'objectiveEntry': 'tables.objective',\n"
        "        'figures': ['figures.curves'],\n"
        "        'components': {'terms': ['fit'], 'share': None},\n"
        "        'dimensions': {'accuracy': 'higher', 'fit': None},\n"
        "    },\n"
        "}\n"
    )

    def verify_with(self, outputs):
        box = FORGE / "implementations" / f"_e2e_cell_outputs_{os.getpid()}"
        try:
            (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "Method/Notebooks").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method_Benchmark/__init__.py").write_text(
                self.DECLARATION, encoding="utf-8")
            cells = [_cell("markdown", "La figura muestra las curvas."),
                     _cell("code", "figures.curves(path)", outputs=outputs)]
            (box / "Method/Notebooks/Report.ipynb").write_text(
                json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                            "nbformat_minor": 5}), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "verify", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
            return json.loads(proc.stdout or "{}")
        finally:
            shutil.rmtree(box, ignore_errors=True)

    def test_the_defect_reaches_the_reported_json(self):
        report = self.verify_with(
            [_shown("text/plain", "<Figure size 640x480 with 6 Axes>")])["report"]
        self.assertEqual(report["status"], "drift")
        self.assertEqual([f["drawing"] for f in report["describedNotShown"]],
                         ["figures.curves"])

    def test_a_shown_figure_clears_it(self):
        report = self.verify_with([_shown("image/png")])["report"]
        self.assertEqual(report["describedNotShown"], [])

    def test_the_toy_target_left_nothing_behind(self):
        self.verify_with([_shown("image/png")])
        leftover = list((FORGE / "implementations").glob("_e2e_cell_outputs_*"))
        self.assertEqual(leftover, [], leftover)


# ------------------------------- la junta entre el método y el arnés que lo mide

def _module(revision, sections, equations, imports=""):
    return (f"{imports}"
            f"__provenance__ = {{\n"
            f"    'revision': {revision!r},\n"
            f"    'sections': {sections!r},\n"
            f"    'equations': {equations!r},\n"
            f"    'invariants': [],\n"
            f"}}\n")


class UnreachedMathematicsEndToEndTests(unittest.TestCase):
    """El brazo declara que ejercita una sección y nunca llama a lo que la implementa.

    Es la única junta que ninguna otra comprobación cruzaba. `verify` leía la
    procedencia del método y la declaración del banco como dos documentos separados,
    y los dos pueden estar impecables mientras el brazo reimplementa la ecuación en
    vez de llamarla: el módulo declara sus secciones, el brazo declara las mismas, y
    nunca se encuentran.

    No es hipotético. Así corrió una campaña entera con un brazo calculando una forma
    simplificada del término que declaraba, con todos los chequeos en verde.

    Los módulos del juguete se llaman por su ROL en la prueba y no por ninguna
    matemática. El chequeo es estructural: no sabe qué es una sección ni qué implementa
    un módulo, y un fixture con nombres de un método real sugeriría que sí.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {\n"
        "        'floor': {'sections': ['3']},\n"
        "        'full': {'sections': ['3', '5']},\n"
        "    },\n"
        "}\n"
    )

    def verify_with(self, wiring):
        box = FORGE / "implementations" / f"_e2e_unreached_{os.getpid()}"
        try:
            (box / "src/Method").mkdir(parents=True)
            (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "tests").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
            # Imported by the harness, and the only way the next one is reached.
            (box / "src/Method/called.py").write_text(
                _module("r01.md", ["3"], ["11"],
                        imports="from Method.reached_through import reached_through\n"),
                encoding="utf-8")
            # Reached only through `called`: a direct-import check would call this
            # missing on every faithful repository, so it is pinned here.
            (box / "src/Method/reached_through.py").write_text(
                _module("r01.md", ["3"], ["21"]), encoding="utf-8")
            # The defect: the arms declare sections 3 and 5, and nobody calls it.
            (box / "src/Method/never_called.py").write_text(
                _module("r01.md", ["3", "5"], ["12", "13"]), encoding="utf-8")
            # Mathematics no arm claims. Unreached, and correctly silent.
            (box / "src/Method/unclaimed.py").write_text(
                _module("r01.md", ["9"], ["31"]), encoding="utf-8")

            (box / "src/Method_Benchmark/__init__.py").write_text(
                self.DECLARATION, encoding="utf-8")
            (box / "src/Method_Benchmark/wiring.py").write_text(wiring,
                                                                encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "verify", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
            return json.loads(proc.stdout or "{}")
        finally:
            shutil.rmtree(box, ignore_errors=True)

    WITHOUT = "from Method.called import called\n"
    WITH = "from Method.called import called\nfrom Method.never_called import total\n"

    def test_a_module_no_arm_calls_is_named_with_its_equations(self):
        fidelity = self.verify_with(self.WITHOUT)["fidelity"]
        unreached = fidelity["benchmark"]["unreachedModules"]
        self.assertEqual([u["module"] for u in unreached], ["src/Method/never_called.py"])
        # The equation, not the section it lives in: that is what a reader acts on.
        self.assertEqual(unreached[0]["equations"], ["12", "13"])
        self.assertEqual(unreached[0]["declaredBy"], ["floor", "full"])

    def test_the_defect_is_not_left_inside_a_headline_that_reads_ok(self):
        """Un defecto que solo vive dentro de `benchmark` mientras `fidelity` dice
        `ok` es exactamente el silencio que este chequeo viene a romper."""
        fidelity = self.verify_with(self.WITHOUT)["fidelity"]
        self.assertEqual(fidelity["benchmark"]["status"], "unfaithful")
        self.assertEqual(fidelity["status"], "drift")

    def test_calling_it_clears_the_finding(self):
        """El otro polo. Sin esto, un chequeo que siempre marca rojo no distingue
        un arnés infiel de uno fiel, y aprobar sería imposible."""
        fidelity = self.verify_with(self.WITH)["fidelity"]
        self.assertEqual(fidelity["benchmark"]["unreachedModules"], [])
        self.assertEqual(fidelity["benchmark"]["status"], "ok")
        self.assertEqual(fidelity["status"], "ok")

    def test_a_module_reached_through_another_is_not_reported(self):
        """`called` importa `reached_through`, así que el arnés la ejercita sin nombrarla.
        Marcarla haría que el hallazgo se ignore en todo repositorio real."""
        unreached = self.verify_with(self.WITHOUT)["fidelity"]["benchmark"]
        self.assertNotIn("src/Method/reached_through.py",
                         [u["module"] for u in unreached["unreachedModules"]])

    def test_mathematics_no_arm_claims_stays_silent(self):
        """Un método puede cargar más de lo que una comparación ejercita. Exigir que
        todo módulo se llame dispararía sobre eso y enseñaría a saltear el hallazgo.

        Se mide sobre el caso que SÍ marca: con `WITH` la lista queda vacía por el
        control y `unclaimed` pasaría aunque nada lo estuviera silenciando.
        """
        unreached = self.verify_with(self.WITHOUT)["fidelity"]["benchmark"]
        reported = [u["module"] for u in unreached["unreachedModules"]]
        self.assertNotIn("src/Method/unclaimed.py", reported)
        self.assertIn("src/Method/never_called.py", reported)

    def probe_with(self, wiring):
        """Un juguete que llega hasta donde se ofrece la corrida.

        Hace falta lo mismo que en cualquier repositorio real para que la pregunta
        exista: algo contra qué comparar, y un backend entrenable. Sin las dos cosas
        `probe` contesta otra cosa mucho antes y la compuerta no se ejercita nunca.
        """
        box = FORGE / "implementations" / f"_e2e_unreached_probe_{os.getpid()}"
        try:
            (box / "src/Method").mkdir(parents=True)
            (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "src/Prior").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
            (box / "src/Method/called.py").write_text(
                _module("r01.md", ["3"], ["11"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Method/never_called.py").write_text(
                _module("r01.md", ["3", "5"], ["12", "13"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Prior/model.py").write_text("import torch\n", encoding="utf-8")
            (box / "src/Method_Benchmark/__init__.py").write_text(
                self.DECLARATION, encoding="utf-8")
            (box / "src/Method_Benchmark/wiring.py").write_text(wiring, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "probe", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
            return json.loads(proc.stdout or "{}")
        finally:
            shutil.rmtree(box, ignore_errors=True)

    def test_the_run_is_not_offered_while_an_arm_does_not_call_what_it_declares(self):
        """El hallazgo tiene que frenar la campaña, no solo figurar: cada número
        vendría de un brazo que no computa lo que la tabla dice que computó."""
        probe = self.probe_with(self.WITHOUT)
        self.assertEqual(probe["nextStep"], "wiring-first")
        self.assertEqual([u["module"] for u in probe["unreachedModules"]],
                         ["src/Method/never_called.py"])

    def test_the_offer_comes_back_once_the_arm_calls_it(self):
        """El polo de control de la compuerta. Sin él, `wiring-first` podría estar
        frenando por cualquier motivo y la prueba de arriba no lo notaría."""
        probe = self.probe_with(self.WITH)
        self.assertEqual(probe["unreachedModules"], [])
        self.assertNotEqual(probe["nextStep"], "wiring-first")

    def test_the_toy_target_left_nothing_behind(self):
        self.verify_with(self.WITH)
        leftover = list((FORGE / "implementations").glob("_e2e_unreached_*"))
        self.assertEqual(leftover, [], leftover)


class DeclareFirstBeforeTheRunTests(unittest.TestCase):
    """A benchmark declaration that has said nothing yet blocks the run ahead
    of every other rung the ladder can reach, because each of them reads that
    same declaration and finds nothing wrong with a target that has not
    started declaring — `wiring-first` reads `arms`, `search-first` reads
    `search`, `report-first` reads `report`, and all three are empty in
    exactly the same way a real defect in one of them would not be.

    Fixtures reuse the toy shape `UnreachedMathematicsEndToEndTests`
    established: a module reached through an import, and a `Prior` package to
    compare against — enough to make `nextStep` reach `"benchmark"` before the
    declaration is read at all.
    """

    def probe_with(self, *, benchmark_dir=True, declaration=None, suffix=""):
        box = FORGE / "implementations" / f"_e2e_declare_first_{suffix}_{os.getpid()}"
        try:
            (box / "src/Method").mkdir(parents=True)
            if benchmark_dir:
                (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "src/Prior").mkdir(parents=True)
            (box / "Method").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
            (box / "src/Method/called.py").write_text(
                _module("r01.md", ["3"], ["11"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Prior/model.py").write_text("import torch\n", encoding="utf-8")
            if declaration is not None:
                (box / "src/Method_Benchmark/__init__.py").write_text(
                    declaration, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "probe", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout or "{}")
        finally:
            shutil.rmtree(box, ignore_errors=True)

    BLANK = ("__benchmark__ = {'revision': '', 'premises': {}, 'arms': {}, "
             "'search': {}, 'report': {}, 'distribution': {}}\n")

    def test_no_benchmark_package_at_all_yields_declare_first(self):
        probe = self.probe_with(benchmark_dir=False, suffix="absent")
        self.assertEqual(probe["nextStep"], "declare-first")

    def test_a_scaffold_with_every_block_blank_yields_declare_first(self):
        """The companion decision, proved end to end: the exact template
        `materialize.py` writes must not be mistaken for a finished
        declaration the day it is created."""
        probe = self.probe_with(declaration=self.BLANK, suffix="blank")
        self.assertEqual(probe["nextStep"], "declare-first")
        self.assertNotEqual(probe["nextStep"], "benchmark")

    def test_declare_first_does_not_change_the_process_exit_status(self):
        """`probe` is read-only advisory guidance, never a gate on exit
        status — declaring nothing yet is a state, not a failure."""
        box = FORGE / "implementations" / f"_e2e_declare_first_exit_{os.getpid()}"
        try:
            (box / "src/Method").mkdir(parents=True)
            (box / "src/Prior").mkdir(parents=True)
            (box / "Method").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
            (box / "src/Method/called.py").write_text(
                _module("r01.md", ["3"], ["11"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Prior/model.py").write_text("import torch\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "probe", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
        finally:
            shutil.rmtree(box, ignore_errors=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout or "{}")
        self.assertEqual(result["nextStep"], "declare-first")
        self.assertEqual(result["kind"], "read-only")

    def test_the_toy_targets_left_nothing_behind(self):
        self.probe_with(benchmark_dir=False, suffix="cleanup")
        leftover = list((FORGE / "implementations").glob("_e2e_declare_first_*"))
        self.assertEqual(leftover, [], leftover)


class SearchDeclaredBeforeTheRunTests(unittest.TestCase):
    """A run whose governing scalar has not yet been chosen has no
    configuration at all — narrower than a wrong report and cheaper to catch
    before any machine time is spent on it. `probe`'s ladder now asks about a
    declared search between asking about a faithful arm and asking about a
    sound report.

    Fixtures reuse the toy shape `UnreachedMathematicsEndToEndTests` already
    established: a module reached through an import (faithful) or not
    (unfaithful), a `Prior` package to compare against, and a
    `Method_Benchmark` package that carries the harness's own contract.
    """

    SEARCH = {
        "what": "which free scalar this chooses",
        "requiredScale": {"epochs": 20, "seeds": 3},
        "role": "valid",
        "tieRule": "the smallest value among the tied candidates",
        "record": "Results/ceilings.json",
    }

    def _declaration(self, search):
        search_line = f"    'search': {search!r},\n" if search is not None else ""
        return ("__benchmark__ = {\n"
                "    'revision': 'r01.md',\n"
                "    'arms': {'floor': {'sections': ['3']}, "
                "'full': {'sections': ['3']}},\n"
                f"{search_line}"
                "}\n")

    def probe_with(self, wiring, *, search=None, record_present=False,
                   record_scale=None, pilot=False, suffix=""):
        box = FORGE / "implementations" / f"_e2e_search_first_{suffix}_{os.getpid()}"
        try:
            (box / "src/Method").mkdir(parents=True)
            (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "src/Prior").mkdir(parents=True)
            # The product folder, distinct from `src/Method`: `search_state`
            # answers the filesystem's own question about it, and without it
            # the question has nothing to be asked of.
            (box / "Method").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
            (box / "src/Method/called.py").write_text(
                _module("r01.md", ["3"], ["11"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Method/never_called.py").write_text(
                _module("r01.md", ["3"], ["12"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Prior/model.py").write_text("import torch\n", encoding="utf-8")
            (box / "src/Method_Benchmark/__init__.py").write_text(
                self._declaration(search), encoding="utf-8")
            (box / "src/Method_Benchmark/wiring.py").write_text(wiring,
                                                                encoding="utf-8")
            if record_present:
                results = box / "Method" / "Results"
                results.mkdir(parents=True, exist_ok=True)
                (results / "ceilings.json").write_text(
                    json.dumps(record_scale or {}), encoding="utf-8")
            if pilot:
                results = box / "Method" / "Results"
                results.mkdir(parents=True, exist_ok=True)
                (results / impl.PROBE_RESULTS).write_text(json.dumps({
                    "revision": "r01.md",
                    "comparison": {"metric": 1},
                    "reduction": {"epochs": 1, "wallSeconds": 60},
                    "targetScale": {"epochs": 5},
                }), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "probe", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
            return json.loads(proc.stdout or "{}")
        finally:
            shutil.rmtree(box, ignore_errors=True)

    WITH = "from Method.called import called\nfrom Method.never_called import total\n"
    WITHOUT = "from Method.called import called\n"

    def test_a_missing_record_yields_search_first_from_what_would_be_benchmark(self):
        """Reachable red: before this change `probe` never read `search` at
        all, so this exact fixture answered `benchmark` — the offer a
        repository whose free scalar was never chosen has no business
        receiving."""
        probe = self.probe_with(self.WITH, search=self.SEARCH, suffix="benchmark")
        self.assertIs(probe["search"]["recordFound"], False)
        self.assertEqual(probe["nextStep"], "search-first")

    def test_a_missing_record_yields_search_first_from_piloted_too(self):
        """The same defect, reachable from the other state the ladder offers
        a run from: a below-scale pilot is still an offer to run, and a
        search with nothing chosen yet still has to come first."""
        probe = self.probe_with(self.WITH, search=self.SEARCH, pilot=True,
                                suffix="piloted")
        self.assertEqual(probe["nextStep"], "search-first")

    def test_a_record_on_disk_does_not_trigger_search_first(self):
        """The other pole: without it, a search that is declared and already
        satisfied would still block every run behind a step it has already
        passed. `record_scale` names every declared axis and meets it — the
        accepted cost of Decision 11 is that an empty or below-scale record
        no longer passes silently, so this fixture now has to earn `ok`
        rather than assume it from mere presence on disk."""
        probe = self.probe_with(self.WITH, search=self.SEARCH,
                                record_present=True,
                                record_scale={"epochs": 20, "seeds": 3},
                                suffix="satisfied")
        self.assertIs(probe["search"]["recordFound"], True)
        self.assertIs(probe["search"]["scaleSatisfied"], True)
        self.assertNotEqual(probe["nextStep"], "search-first")

    def test_a_record_naming_none_of_the_declared_axes_yields_search_first(self):
        """Decision 11's accepted cost, measured directly: a record present
        on disk but silent about scale used to pass — `recordFound` alone
        cannot tell a run at scale from a record that answers nothing about
        it. `scaleSatisfied: null` now refuses to advance either, the same
        doctrine an unprovable precondition already gets elsewhere."""
        probe = self.probe_with(self.WITH, search=self.SEARCH,
                                record_present=True, record_scale={},
                                suffix="null_scale")
        self.assertIs(probe["search"]["recordFound"], True)
        self.assertIsNone(probe["search"]["scaleSatisfied"])
        self.assertEqual(probe["nextStep"], "search-first")

    def test_a_record_below_the_declared_scale_yields_search_first(self):
        """The other half of the tri-state: a record that does name the
        declared axes but falls short of them is `false`, not `null`, and
        still refuses to advance — the disagreement Finding 8 exists to
        close, closed on the forge's own side of it."""
        probe = self.probe_with(self.WITH, search=self.SEARCH,
                                record_present=True,
                                record_scale={"epochs": 20, "seeds": 1},
                                suffix="below_scale")
        self.assertIs(probe["search"]["recordFound"], True)
        self.assertIs(probe["search"]["scaleSatisfied"], False)
        self.assertEqual(probe["nextStep"], "search-first")

    def test_no_declared_search_is_unaffected(self):
        """Absence of a declaration is not a finding: most repositories
        search nothing, and this rung has to stay silent for every one of
        them."""
        probe = self.probe_with(self.WITH, search=None, suffix="undeclared")
        self.assertEqual(probe["search"]["status"], "none")
        self.assertNotEqual(probe["nextStep"], "search-first")

    def test_wiring_first_still_wins_over_search_first(self):
        """The ordering test that matters most. Correcting a fork changes
        what an arm computes, which changes what a search over that arm
        would find — so the wired defect is settled first, or a search-first
        report would spend itself on a configuration about to change out
        from under it."""
        probe = self.probe_with(self.WITHOUT, search=self.SEARCH,
                                suffix="ordering")
        self.assertEqual(probe["nextStep"], "wiring-first")

    def test_search_first_wins_over_report_first(self):
        """A missing configuration is worse than a report in drift and
        cheaper to prevent, so it is asked about first even here, where both
        conditions hold: the report is undeclared and the search's record is
        absent."""
        probe = self.probe_with(self.WITH, search=self.SEARCH,
                                suffix="over_report")
        self.assertNotEqual(probe["report"]["status"], "ok")
        self.assertEqual(probe["nextStep"], "search-first")

    def test_the_toy_targets_left_nothing_behind(self):
        self.probe_with(self.WITH, search=self.SEARCH, suffix="cleanup")
        leftover = list((FORGE / "implementations").glob("_e2e_search_first_*"))
        self.assertEqual(leftover, [], leftover)


class RemoteExecutionPendingBeforeTheRunTests(unittest.TestCase):
    """A session that submits work to a remote worker and then ends leaves
    the next session's `probe` saying "run the benchmark" while results are
    still in flight — inviting a duplicate run that spends real quota and
    produces a second answer to a question already being answered.
    `remote_execution_state()` already computes this (`status: "pending"`);
    the ladder now asks it, reusing that one call rather than re-folding the
    ledger a second time.

    Fixtures reuse the toy shape `SearchDeclaredBeforeTheRunTests` already
    established, plus a `.remote-execution/ledger.jsonl` under the product
    folder — the one path `remote_execution_state()` reads.
    """

    def _declaration(self, search=None):
        search_line = f"    'search': {search!r},\n" if search is not None else ""
        return ("__benchmark__ = {\n"
                "    'revision': 'r01.md',\n"
                "    'arms': {'floor': {'sections': ['3']}, "
                "'full': {'sections': ['3']}},\n"
                f"{search_line}"
                "}\n")

    def probe_with(self, wiring, *, pending=False, digest="live", search=None,
                   record_present=False, extra_ledger_lines=None, pilot=False,
                   suffix=""):
        box = FORGE / "implementations" / f"_e2e_poll_first_{suffix}_{os.getpid()}"
        try:
            (box / "src/Method").mkdir(parents=True)
            (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "src/Prior").mkdir(parents=True)
            # The product folder, distinct from `src/Method`: the ledger the
            # pending fixture writes lives under it, exactly where
            # `remote_execution_state()` looks.
            (box / "Method").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
            (box / "src/Method/called.py").write_text(
                _module("r01.md", ["3"], ["11"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Method/never_called.py").write_text(
                _module("r01.md", ["3"], ["12"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Prior/model.py").write_text("import torch\n", encoding="utf-8")
            (box / "src/Method_Benchmark/__init__.py").write_text(
                self._declaration(search), encoding="utf-8")
            (box / "src/Method_Benchmark/wiring.py").write_text(wiring,
                                                                encoding="utf-8")
            if record_present and search is not None:
                results = box / "Method" / "Results"
                results.mkdir(parents=True, exist_ok=True)
                (results / "ceilings.json").write_text("{}", encoding="utf-8")
            if pilot:
                results = box / "Method" / "Results"
                results.mkdir(parents=True, exist_ok=True)
                (results / impl.PROBE_RESULTS).write_text(json.dumps({
                    "revision": "r01.md",
                    "comparison": {"metric": 1},
                    "reduction": {"epochs": 1, "wallSeconds": 60},
                    "targetScale": {"epochs": 5},
                }), encoding="utf-8")
            if pending or extra_ledger_lines:
                lines = []
                if pending:
                    source_digest = (impl.source_digest(box, "Method")
                                     if digest == "live" else "0" * 64)
                    lines.append(json.dumps({
                        "kind": "submitted", "ts": "2026-08-19T00:00:00Z",
                        "entrypoint": "Method/Notebooks/probe.ipynb",
                        "sourceDigest": source_digest, "submissionId": "s1",
                        "worker": "w1", "requestedCapacity": 1,
                        "grantedCapacity": 1,
                    }))
                if extra_ledger_lines:
                    lines.extend(extra_ledger_lines)
                ledger_dir = box / "Method" / ".remote-execution"
                ledger_dir.mkdir(parents=True, exist_ok=True)
                (ledger_dir / "ledger.jsonl").write_text(
                    "\n".join(lines) + "\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "probe", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
            return json.loads(proc.stdout or "{}")
        finally:
            shutil.rmtree(box, ignore_errors=True)

    WITH = "from Method.called import called\nfrom Method.never_called import total\n"
    WITHOUT = "from Method.called import called\n"

    def test_a_pending_submission_yields_poll_first_from_what_would_be_benchmark(self):
        """Reachable red: before this change `probe` never read
        `remoteExecution` at all when choosing `nextStep`, so this exact
        fixture answered `benchmark` — the offer a repository with an
        answer already on its way to a remote worker has no business
        receiving."""
        probe = self.probe_with(self.WITH, pending=True, suffix="benchmark")
        self.assertEqual(probe["remoteExecution"]["status"], "pending")
        self.assertEqual(probe["nextStep"], "poll-first")

    def test_a_pending_submission_yields_poll_first_from_piloted_too(self):
        """The same defect, reachable from the other state the ladder offers
        a run from: a below-scale pilot is still an offer to run, and a
        submission already out still means the answer may already be on its
        way."""
        probe = self.probe_with(self.WITH, pending=True, pilot=True,
                                suffix="piloted")
        self.assertEqual(probe["nextStep"], "poll-first")

    def test_no_pending_submission_is_unaffected(self):
        """The pole. Without it, `poll-first` could be firing on anything at
        all and none of the tests above would notice."""
        probe = self.probe_with(self.WITH, pending=False, suffix="clean")
        self.assertEqual(probe["remoteExecution"]["status"], "absent")
        self.assertNotEqual(probe["nextStep"], "poll-first")

    def test_wiring_first_still_wins_over_poll_first(self):
        """A submission that went out under broken wiring is already
        answering the wrong question, and no amount of waiting fixes that —
        so the wired defect is still settled first, regardless of what is
        already in flight."""
        probe = self.probe_with(self.WITHOUT, pending=True, suffix="ordering")
        self.assertEqual(probe["remoteExecution"]["status"], "pending")
        self.assertEqual(probe["nextStep"], "wiring-first")

    def test_poll_first_wins_over_search_first(self):
        """The scenario this rung exists to catch: a search's own record is
        absent because the search itself is the thing pending. Answering
        `search-first` here would ask the reader to resubmit exactly what is
        already in flight — the duplicate the gap describes."""
        probe = self.probe_with(
            self.WITH, pending=True,
            search=SearchDeclaredBeforeTheRunTests.SEARCH, suffix="over_search")
        self.assertIs(probe["search"]["recordFound"], False)
        self.assertEqual(probe["nextStep"], "poll-first")

    def test_poll_first_wins_over_report_first(self):
        """Waiting on quota already spent outranks a document that merely
        does not yet agree with the run — fixing a sentence never had to
        compete with a submission still in flight."""
        probe = self.probe_with(self.WITH, pending=True, suffix="over_report")
        self.assertNotEqual(probe["report"]["status"], "ok")
        self.assertEqual(probe["nextStep"], "poll-first")

    def test_drift_does_not_trigger_poll_first(self):
        """`drift` means a submission's source moved out from under it while
        it was in flight — waiting does not repair that, so this rung leaves
        it alone rather than telling the reader to poll for something a poll
        cannot resolve."""
        probe = self.probe_with(self.WITH, pending=True, digest="stale",
                                suffix="drift")
        self.assertEqual(probe["remoteExecution"]["status"], "drift")
        self.assertNotEqual(probe["nextStep"], "poll-first")

    def test_unreliable_does_not_trigger_poll_first(self):
        """`unreliable` means a line of the log could not be read, so
        nothing about what is or is not out there can be trusted yet —
        polling would be asking a question of a record that cannot
        currently answer it."""
        probe = self.probe_with(self.WITH, pending=True,
                                extra_ledger_lines=["{not valid json"],
                                suffix="unreliable")
        self.assertEqual(probe["remoteExecution"]["status"], "unreliable")
        self.assertNotEqual(probe["nextStep"], "poll-first")

    def test_the_toy_targets_left_nothing_behind(self):
        self.probe_with(self.WITH, pending=True, suffix="cleanup")
        leftover = list((FORGE / "implementations").glob("_e2e_poll_first_*"))
        self.assertEqual(leftover, [], leftover)


class SearchCostForecastTests(unittest.TestCase):
    """What a declared search costs, forecast from what was actually
    measured rather than from whatever the pilot happens to be running at.

    The trap this closes: a search declares its own scale, and it is not
    the pilot's. Reading a low pilot scale and concluding the whole flow is
    a short one misses that the run about to go first — the search — has
    just declared a configuration nobody has measured anything at.
    """

    def test_it_projects_from_a_measured_duration(self):
        forecast = impl.search_cost_forecast(
            {"seconds": 600, "epochs": 3}, {"epochs": 30})
        self.assertEqual(forecast["factor"], 10.0)
        self.assertEqual(forecast["projectedSeconds"], 6000)

    def test_it_explains_itself_when_it_cannot_project(self):
        """A silent `None` reads as "the cost is fine" to anyone skimming."""
        forecast = impl.search_cost_forecast({"epochs": 3}, {"epochs": 30})
        self.assertIsNone(forecast["projectedSeconds"])
        self.assertIn("no duration", forecast["reason"])

        forecast = impl.search_cost_forecast({"seconds": 600}, {})
        self.assertIsNone(forecast["projectedSeconds"])
        self.assertIn("no required scale", forecast["reason"])

    def test_it_names_the_gap_when_the_declared_scale_exceeds_what_ran(self):
        """The whole trap, stated as a finding rather than left to
        arithmetic nobody reads closely enough to notice."""
        forecast = impl.search_cost_forecast(
            {"seconds": 600, "epochs": 3}, {"epochs": 20})
        self.assertEqual(forecast["aboveMeasuredScale"],
                         {"epochs": {"declared": 20, "measuredAt": 3}})

    def test_no_gap_is_named_when_the_declared_scale_does_not_exceed_it(self):
        forecast = impl.search_cost_forecast(
            {"seconds": 600, "epochs": 30}, {"epochs": 20})
        self.assertNotIn("aboveMeasuredScale", forecast)

    def test_the_new_code_names_no_dimension_of_its_own(self):
        """Mirrors `test_it_names_no_dimension_of_its_own`, over what this
        change adds instead of over `DISTRIBUTION_DECLARATION`.

        Word boundaries, not bare substrings: a previous version of that
        check had to be tightened because `arm` fired on `warm` and `harm`,
        and nothing here has learned that lesson yet on its own account.
        """
        source = "\n".join(filter(None, [
            inspect.getsource(impl.search_cost_forecast),
            inspect.getsource(impl.cmd_probe),
        ])).lower()
        for leaked in ("kaggle", "t4", "seconds", "peakmib", "accuracy",
                      "seed", "ceiling", "ramp"):
            self.assertIsNone(re.search(rf"\b{leaked}\b", source), leaked)


class RemoteExecutionLedgerSectionTests(unittest.TestCase):
    """`verify`'s ledger section, read service-blind through `ledger.py` alone.

    A guard you have to go looking for is a guard nobody looks at — that is
    why this section lives inside `verify` rather than a command of its own,
    and it is what these tests hold it to: it reports what was sent, what
    came back, and what changed since, and it never resolves anything and
    never names a worker.
    """

    def _write_ledger(self, target: Path, name: str, lines: list) -> Path:
        ledger_path = target / name / ".remote-execution" / "ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(
            "\n".join(lines) + "\n" if lines else "", encoding="utf-8")
        return ledger_path

    def _minimal_source(self, target: Path) -> None:
        """Enough of `src/` for `source_digest()` to compute over something
        real, so a "stale" fixture is stale against an actual hash and not
        an accident of an empty tree."""
        module = target / "src" / "Method" / "module.py"
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text("VALUE = 1\n", encoding="utf-8")

    def test_absent_when_no_remote_execution_skill_present(self):
        """The one state every target predates this section in, and the one
        `verify` must stay safe on without anyone touching a target at all."""
        from unittest import mock

        box = FORGE / "implementations" / f"_re_absent_{os.getpid()}"
        try:
            (box / "src" / "Method").mkdir(parents=True)
            (box / "src" / "Method_Benchmark").mkdir(parents=True)
            (box / "tests").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
            (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
                "__benchmark__ = {}\n", encoding="utf-8")

            missing_script = box / "no-such-skill" / "ledger.py"
            with mock.patch.object(impl, "REMOTE_EXECUTION_LEDGER_SCRIPT", missing_script):
                result = impl.cmd_verify(
                    argparse.Namespace(target=str(box), name="Method", revision=None))
        finally:
            shutil.rmtree(box, ignore_errors=True)

        # The whole of verify, not just the new key: this is the case every
        # existing target is in today, so it is the one that must never crash it.
        self.assertEqual(result["command"], "verify")
        self.assertEqual(result["remoteExecution"], {"status": "absent"})

    def test_absent_when_the_skill_is_present_but_nothing_was_ever_sent(self):
        """Absence of data reads the same as absence of the capability: an
        installed skill with no ledger file for this target has nothing to
        report either, and reporting it as `ok` would claim a fact — that a
        run completed cleanly — nobody has any evidence for."""
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            state = impl.remote_execution_state(target, "Method", "Method")
            self.assertEqual(state, {"status": "absent"})

    def test_drift_when_a_pending_submission_s_source_has_moved(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            self._write_ledger(target, "Method", [json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:00:00Z",
                "entrypoint": "Method/Notebooks/verification.ipynb",
                "sourceDigest": "0" * 64, "submissionId": "s1", "worker": "w1",
                "requestedCapacity": 1, "grantedCapacity": 1,
            })])
            state = impl.remote_execution_state(target, "Method", "Method")
            self.assertEqual(state["status"], "drift")
            self.assertEqual(state["staleInFlight"],
                            ["Method/Notebooks/verification.ipynb"])
            self.assertEqual(state["fromStaleSubmission"], [])
            self.assertEqual(state["pending"], 1)
            self.assertEqual(state["sent"], 1)

    def test_unreliable_when_a_line_cannot_be_read(self):
        """Reachable only against a log that is otherwise clean: if
        `unreadableLines` did not override an otherwise-`ok` verdict, this
        would read `ok` with the corrupted line silently dropped."""
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            live = impl.source_digest(target, "Method")
            lines = [json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:00:00Z",
                "entrypoint": "Method/Notebooks/verification.ipynb",
                "sourceDigest": live, "submissionId": "s1", "worker": "w1",
                "requestedCapacity": 1, "grantedCapacity": 1,
            }), json.dumps({
                "kind": "returned", "ts": "2026-08-17T00:05:00Z",
                "submissionId": "s1", "artifactPath": "out/s1", "observedConcurrency": 1,
            }), "{not valid json"]
            self._write_ledger(target, "Method", lines)
            state = impl.remote_execution_state(target, "Method", "Method")
            self.assertEqual(state["unreadableLines"], 1)
            # Otherwise-clean and still `unreliable`: an unread line must
            # outrank a report that would read `ok` without it.
            self.assertEqual(state["returned"], 1)
            self.assertEqual(state["status"], "unreliable")

    def test_a_quarantined_result_is_reported_and_never_treated_as_merged(self):
        """The result from a superseded submission arrives, is named, and
        never promotes its entrypoint's current state to `returned`."""
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            live = impl.source_digest(target, "Method")
            entrypoint = "Method/Notebooks/verification.ipynb"
            lines = [json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:00:00Z",
                "entrypoint": entrypoint, "sourceDigest": live,
                "submissionId": "s1", "worker": "w1",
                "requestedCapacity": 1, "grantedCapacity": 1,
            }), json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:10:00Z",
                "entrypoint": entrypoint, "sourceDigest": live,
                "submissionId": "s2", "worker": "w1",
                "requestedCapacity": 1, "grantedCapacity": 1,
            }), json.dumps({
                # Arrives late, for the superseded submission s1.
                "kind": "returned", "ts": "2026-08-17T00:20:00Z",
                "submissionId": "s1", "artifactPath": "out/s1", "observedConcurrency": 1,
            })]
            self._write_ledger(target, "Method", lines)
            state = impl.remote_execution_state(target, "Method", "Method")
            self.assertEqual(state["quarantined"], 1)
            self.assertEqual(state["fromStaleSubmission"], [entrypoint])
            # s2, the entrypoint's LATEST submission, has no terminal event of
            # its own yet: the quarantined result for s1 must not count here.
            self.assertEqual(state["returned"], 0)
            self.assertEqual(state["pending"], 1)
            self.assertEqual(state["status"], "drift")

    def test_the_section_names_no_service(self):
        """The test the user cares most about: a ledger whose workers carry
        service-shaped usernames must never leak one into the section's JSON,
        and `workers` must be a count. Assert this over the section's full
        JSON dump — asserting field-by-field would let a leak hide in a key
        this test forgot to check."""
        service_shaped_workers = ("kaggle-svc-worker-42", "prod-training-bot-07")
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            live = impl.source_digest(target, "Method")
            lines = [json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:00:00Z",
                "entrypoint": f"Method/Notebooks/n{i}.ipynb",
                "sourceDigest": live, "submissionId": f"s{i}", "worker": worker,
                "requestedCapacity": 1, "grantedCapacity": 1,
            }) for i, worker in enumerate(service_shaped_workers)]
            self._write_ledger(target, "Method", lines)
            state = impl.remote_execution_state(target, "Method", "Method")

            dumped = json.dumps(state)
            for worker in service_shaped_workers:
                self.assertNotIn(worker, dumped, worker)
            self.assertIsInstance(state["workers"], int)
            self.assertEqual(state["workers"], len(service_shaped_workers))


class RemoteExecutionJobsSectionTests(unittest.TestCase):
    """`probe`'s own `remoteExecution` fact (design #744 section 9): unlike
    `verify`'s ledger-only section above, `probe` reports what job folders
    exist on disk right now — reused via `remote_execution_jobs_state()`,
    merged beside `remote_execution_state()`'s own ledger fields under the
    same `remoteExecution` key. States the fact; issues no submission.
    """

    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "probe-jobs-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "probe-jobs-tests@example.invalid"
        return subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check)

    def _init_repo(self, target: Path, packages=("Method",)) -> str:
        target.mkdir(parents=True, exist_ok=True)
        self._git(target, "init", "-q")
        for package in packages:
            module = target / "src" / package / "module.py"
            module.parent.mkdir(parents=True, exist_ok=True)
            module.write_text("VALUE = 1\n", encoding="utf-8")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", "initial")
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _write_job_folder(self, target: Path, *, service: str, job_name: str,
                           product: str, commit: str, clone_paths=("src/Method",)) -> Path:
        job_dir = target / "tools" / service / job_name
        job_dir.mkdir(parents=True, exist_ok=True)
        run_config = {
            "schemaVersion": 1, "product": product, "service": service,
            "jobName": job_name, "commit": commit,
            "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
            "clonePaths": list(clone_paths),
            "run": {"module": f"{product}.module", "function": "run", "kwargs": {}},
            "runnerTemplate": [
                {"path": "assets/runner_bootstrap.py", "sha256": "0" * 64},
                {"path": "assets/runner_invoke.py", "sha256": "0" * 64},
            ],
        }
        (job_dir / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
        return job_dir

    def _write_smoke_record(self, target: Path, *, product: str, job_name: str,
                             result: str, commit: str, worker: str) -> Path:
        smoke_path = target / product / ".remote-execution" / "smoke.jsonl"
        smoke_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"kind": "smokeResult", "ts": "2026-08-18T00:00:00Z",
                  "jobName": job_name, "result": result, "commit": commit,
                  "worker": worker, "missing": []}
        with smoke_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        return smoke_path

    def test_absent_when_no_job_folder_exists_at_all(self):
        """No `tools/` directory: nothing to discover, and the shape stays
        the same one `remote_execution_state()` already uses for absence."""
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            state = impl.remote_execution_jobs_state(target)
        self.assertEqual(state, {"jobs": [], "services": 0, "smokeReady": {}})

    def test_two_jobs_across_two_services_one_stale(self):
        """The runtime harness this task is scored against: two generated
        job folders, one stale — proven with different declared clone paths
        so only the one whose declared path actually changed reports drift,
        the same declared-vs-undeclared contrast `StalenessTests` uses."""
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            commit = self._init_repo(target, packages=("MethodA", "MethodB"))
            self._write_job_folder(target, service="svc-a", job_name="job-fresh",
                                    product="Method", commit=commit,
                                    clone_paths=("src/MethodA",))
            self._write_job_folder(target, service="svc-b", job_name="job-stale",
                                    product="Method", commit=commit,
                                    clone_paths=("src/MethodB",))
            (target / "src" / "MethodB" / "module.py").write_text(
                "VALUE = 2\n", encoding="utf-8")
            self._git(target, "add", "-A")
            self._git(target, "commit", "-q", "-m", "declared change")

            state = impl.remote_execution_jobs_state(target)

        self.assertEqual(state["services"], 2)
        by_job = {j["job"]: j for j in state["jobs"]}
        self.assertEqual(by_job["job-fresh"]["staleness"]["status"], "fresh")
        self.assertEqual(by_job["job-stale"]["staleness"]["status"], "drift")
        for job in state["jobs"]:
            self.assertEqual(set(job.keys()), {"job", "product", "staleness"})

    def test_services_is_a_count_never_a_name(self):
        """Mirrors `test_the_section_names_no_service` above, over the
        `<service>` path segment this new fact walks to discover jobs."""
        service_shaped = "kaggle-svc-worker-42"
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            commit = self._init_repo(target)
            self._write_job_folder(target, service=service_shaped, job_name="job1",
                                    product="Method", commit=commit)
            state = impl.remote_execution_jobs_state(target)

        dumped = json.dumps(state)
        self.assertNotIn(service_shaped, dumped)
        self.assertIsInstance(state["services"], int)
        self.assertEqual(state["services"], 1)

    def test_smoke_ready_true_when_the_latest_record_passes_at_the_pinned_commit(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            commit = self._init_repo(target)
            self._write_job_folder(target, service="svc", job_name="job1",
                                    product="Method", commit=commit)
            self._write_smoke_record(target, product="Method", job_name="job1",
                                      result="pass", commit=commit, worker="w1")
            state = impl.remote_execution_jobs_state(target)
        self.assertEqual(state["smokeReady"], {"job1": True})

    def test_smoke_ready_false_when_no_smoke_record_exists(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            commit = self._init_repo(target)
            self._write_job_folder(target, service="svc", job_name="job1",
                                    product="Method", commit=commit)
            state = impl.remote_execution_jobs_state(target)
        self.assertEqual(state["smokeReady"], {"job1": False})

    def test_an_unreadable_run_config_is_reported_not_silently_dropped(self):
        """The conflation design #744 leaves open: `remote_cli.py`'s own
        `_job_folder_staleness()` returns `None` both for "no job folder"
        (correct — nothing to report) and for a `run-config.json`
        `jobfolder.read()` cannot parse (a real defect). This job's
        directory was already found BY its `run-config.json` existing, so
        a `JobFolderError` here can only mean the second case — it must
        never read as a blank cell."""
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            job_dir = target / "tools" / "svc" / "broken-job"
            job_dir.mkdir(parents=True)
            (job_dir / "run-config.json").write_text("{not valid json", encoding="utf-8")

            state = impl.remote_execution_jobs_state(target)

        self.assertEqual(len(state["jobs"]), 1)
        job = state["jobs"][0]
        self.assertEqual(job["job"], "broken-job")
        self.assertEqual(job["staleness"]["status"], "unreadable")
        self.assertIsNotNone(job["staleness"]["reason"])
        self.assertNotEqual(job["staleness"]["status"], "unknown")

    def test_reading_the_fact_issues_no_submission(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            commit = self._init_repo(target)
            self._write_job_folder(target, service="svc", job_name="job1",
                                    product="Method", commit=commit)
            impl.remote_execution_jobs_state(target)
            impl.remote_execution_jobs_state(target)
            ledger_exists = (target / "Method" / ".remote-execution" / "ledger.jsonl").exists()
            smoke_exists = (target / "Method" / ".remote-execution" / "smoke.jsonl").exists()
        self.assertFalse(ledger_exists)
        self.assertFalse(smoke_exists)

    def test_probe_end_to_end_reports_two_jobs_one_stale(self):
        """The mandated runtime harness: a real CLI subprocess call against
        a target with two generated job folders, one stale."""
        box = FORGE / "implementations" / f"_e2e_remote_jobs_{os.getpid()}"
        try:
            (box / "src" / "Method").mkdir(parents=True)
            (box / "src" / "Method_Benchmark").mkdir(parents=True)
            (box / "tests").mkdir(parents=True)
            (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
            (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
                "__benchmark__ = {}\n", encoding="utf-8")
            (box / "src" / "MethodA").mkdir(parents=True)
            (box / "src" / "MethodA" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            (box / "src" / "MethodB").mkdir(parents=True)
            (box / "src" / "MethodB" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            self._git(box, "init", "-q")
            self._git(box, "add", "-A")
            self._git(box, "commit", "-q", "-m", "initial")
            commit = self._git(box, "rev-parse", "HEAD").stdout.strip()

            self._write_job_folder(box, service="svc-a", job_name="job-fresh",
                                    product="Method", commit=commit,
                                    clone_paths=("src/MethodA",))
            self._write_job_folder(box, service="svc-b", job_name="job-stale",
                                    product="Method", commit=commit,
                                    clone_paths=("src/MethodB",))
            (box / "src" / "MethodB" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
            self._git(box, "add", "-A")
            self._git(box, "commit", "-q", "-m", "declared change")

            probe = subprocess.run(
                [sys.executable, str(CLI), "probe", "--target", str(box),
                 "--name", "Method"],
                capture_output=True, text=True, cwd=FORGE)
            ledger_exists = (box / "Method" / ".remote-execution" / "ledger.jsonl").exists()
        finally:
            shutil.rmtree(box, ignore_errors=True)

        self.assertEqual(probe.returncode, 0, probe.stderr)
        probe_json = json.loads(probe.stdout or "{}")
        remote = probe_json["remoteExecution"]
        self.assertEqual(remote["services"], 2)
        by_job = {j["job"]: j for j in remote["jobs"]}
        self.assertEqual(by_job["job-fresh"]["staleness"]["status"], "fresh")
        self.assertEqual(by_job["job-stale"]["staleness"]["status"], "drift")
        self.assertIn("smokeReady", remote)
        # `probe` states the fact and issues no submission.
        self.assertFalse(ledger_exists)


class NextStepSectionCoverageTests(unittest.TestCase):
    """`probe` returns eight `nextStep` values; SKILL.md must define a
    `### nextStep: "..."` section for exactly the ones that prescribe work.

    The reachable red here is `test_no_next_step_is_named_without_a_definition`:
    before `report-first` had its own section, `search-first`'s section already
    named it by name, in prose, to explain the ordering — a reader arriving at
    `report-first` from `probe` found nothing. Commenting out the `report-first`
    section this suite pins turns that test red again.
    """

    SKILL_MD = CLI.parent.parent / "SKILL.md"

    # The three `nextStep` values that prescribe no work, and therefore must
    # never get a `### nextStep: "..."` section of their own. This split cannot
    # be read off the CLI source — the source only says which strings
    # `next_step` can hold, never which of them call for a procedure and which
    # call for silence — so it is named here once, with the reason attached,
    # rather than inferred from the shape of the list.
    #
    # `nothing-to-compare` and `already-benchmarked`: Flow B already says to ask
    # the user and invent no work for either, so a section prescribing steps
    # would be inventing exactly the work Flow B refuses to do.
    #
    # `piloted`: stronger than the other two, and on purpose. Its own rule in
    # SKILL.md requires the question to stay open and calls out "not a menu" by
    # name — the pilot is where somebody looks, adds a test, moves a proportion
    # and runs it short again, and a list of steps closes exactly the door that
    # rule exists to hold open. Giving `piloted` a section would not be filling
    # a gap; it would violate the rule the section would be explaining. This is
    # the assertion that stops a future contributor from "fixing the asymmetry"
    # by handing `piloted` the menu its own text forbids.
    NO_SECTION = frozenset({
        "nothing-to-compare",
        "already-benchmarked",
        "piloted",
    })

    HEADING_RE = re.compile(r'^### `nextStep: "([a-z0-9-]+)"`', re.MULTILINE)

    @classmethod
    def all_next_steps(cls):
        """Every literal `probe` can assign to `next_step`, read from the source.

        Not hardcoded: every rung of the ladder in `cmd_probe` assigns the same
        variable a string literal and nothing else, so scraping every
        `next_step = "..."` assignment out of the function's own source recovers
        the complete set without this test carrying a second copy of the list
        that could drift out of sync with the code.
        """
        source = inspect.getsource(impl.cmd_probe)
        return set(re.findall(r'next_step\s*=\s*"([a-z0-9-]+)"', source))

    @classmethod
    def headings(cls):
        text = cls.SKILL_MD.read_text(encoding="utf-8")
        return set(cls.HEADING_RE.findall(text))

    def test_every_value_the_cli_can_return_is_accounted_for(self):
        """Sanity check on the derivation itself, not on SKILL.md: a change to
        `cmd_probe` that adds, removes or renames a rung should move this test,
        not a typo in the scraping regex above."""
        self.assertEqual(
            self.all_next_steps(),
            {"nothing-to-compare", "convert", "piloted", "already-benchmarked",
             "benchmark", "declare-first", "env-first", "wiring-first",
             "poll-first", "search-first", "report-first"})

    def test_every_prescriptive_next_step_has_its_own_section(self):
        prescriptive = self.all_next_steps() - self.NO_SECTION
        missing = sorted(prescriptive - self.headings())
        self.assertEqual(missing, [], f"no `### nextStep` heading for: {missing}")

    def test_the_three_that_prescribe_no_work_have_no_section(self):
        """See `NO_SECTION` above for why these three are withheld on purpose
        rather than by oversight."""
        present = sorted(self.NO_SECTION & self.headings())
        self.assertEqual(present, [], f"unexpected `### nextStep` heading for: {present}")

    def test_no_next_step_is_named_without_a_definition(self):
        """A value mentioned in backticks anywhere in the document must either
        have its own heading or be one of the three deliberately left unheaded
        (`NO_SECTION`); anything else is a dangling reference — the exact shape
        of the defect this change fixes."""
        text = self.SKILL_MD.read_text(encoding="utf-8")
        found_headings = self.headings()
        dangling = []
        for value in self.all_next_steps():
            pattern = re.compile(r'`[^`]*\b' + re.escape(value) + r'\b[^`]*`')
            mentioned = bool(pattern.search(text))
            if mentioned and value not in found_headings and value not in self.NO_SECTION:
                dangling.append(value)
        self.assertEqual(dangling, [], f"referenced but never defined: {dangling}")


class ReportFirstSectionProseTests(unittest.TestCase):
    """The `report-first` section's own examples must stay generic: this is a
    forge for papers, not for one benchmark.

    Word boundaries, not bare substrings — mirroring
    `test_the_new_code_names_no_dimension_of_its_own` — because `arm` is
    legitimate vocabulary in this section and must not be treated as a leak
    just because it is a substring of `warm` or `harm`.
    """

    SKILL_ROOT = CLI.parent.parent
    SKILL_MD = SKILL_ROOT / "SKILL.md"
    SECTION_RE = re.compile(
        r'### `nextStep: "report-first"`.*?(?=\n### |\n## |\Z)', re.DOTALL)

    #: Directories a checkout accumulates and nobody writes prose into.
    CACHES = ("__pycache__", ".pytest_cache", ".ipynb_checkpoints")
    #: Suffixes that are not text, so scanning them for words says nothing.
    BINARY_SUFFIXES = (".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".pdf",
                       ".pth", ".npz", ".npy", ".zip", ".ico")

    def guarded_documents(self, root=None):
        """Every surface of the forge a target's vocabulary could leak into.

        `SKILL.md` is what an agent reads, but it is not the only thing a
        target copies: `references/usage.md` is the worked walkthrough, and
        `assets/` is the kit a scaffold is literally made of. A leak in a
        template ships into every repository materialized from it.

        `scripts/` is here for a different reason. Nothing copies it, but it is
        the forge's own code, it is read by anyone extending the skill, and it
        is edited by every change that touches the checker or the materializer —
        including this one. A guard whose surface stops at the documents leaves
        the surface that changes most often unscanned.

        `root` is overridable so the rule can be proven against a tree built for
        the purpose rather than only against a checkout that happens to be clean.
        """
        base = self.SKILL_ROOT if root is None else Path(root)
        documents = [base / "SKILL.md", base / "references" / "usage.md"]
        for directory in ("assets", "scripts"):
            for path in sorted((base / directory).rglob("*")):
                if not path.is_file():
                    continue
                if any(part in self.CACHES for part in path.parts):
                    continue
                if path.suffix.lower() in self.BINARY_SUFFIXES:
                    continue
                documents.append(path)
        return [path for path in documents if path.is_file()]

    def scannable_text(self, document: Path) -> str:
        """The document, minus the one place a service name is a fact.

        Detecting which hosted notebook service you are running on requires
        naming them, and the kit's `hosted_runtime()` names four of them
        symmetrically rather than defaulting to any one — the same shape the
        forge already uses for `remote-execution/scripts/adapters/`, where a
        single designated module names a service and every seam around it
        names none. That function is exempted here and nothing else is: the
        same word two lines below it still fails this test.
        """
        text = document.read_text(encoding="utf-8", errors="replace")
        if document.suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                return text.lower()
            lines = text.splitlines()
            for node in ast.walk(tree):
                if (isinstance(node, ast.FunctionDef)
                        and node.name == "hosted_runtime"):
                    for index in range(node.lineno - 1, node.end_lineno):
                        lines[index] = ""
            text = "\n".join(lines)
        return text.lower()

    def section_text(self):
        text = self.SKILL_MD.read_text(encoding="utf-8")
        match = self.SECTION_RE.search(text)
        self.assertIsNotNone(match, "the report-first section itself is missing")
        return match.group(0).lower()

    def test_it_names_no_service_or_method_of_its_own(self):
        section = self.section_text()
        for leaked in ("kaggle", "t4", "ceiling", "ramp", "transfer", "creda"):
            self.assertIsNone(re.search(rf"\b{leaked}\b", section), leaked)

    def test_the_whole_forge_borrows_no_repository_s_vocabulary(self):
        """The guard covers every surface, not the paragraph written last.

        Scoped to one section it protects only whatever somebody just added,
        which is the half least likely to have drifted. It was scoped that way
        because the file already held one leak: the worked example of a
        checklist carried a real agreement from a real target, copied in as if
        it were neutral illustration. That is worse than clutter — a reader
        takes an example for a general practice, so the forge would have been
        teaching one repository's decision as everybody's default.

        Widened from `SKILL.md` alone to the usage reference and the kit,
        because those are the surfaces a target copies from verbatim and
        neither had ever been scanned.
        """
        for document in self.guarded_documents():
            with self.subTest(document=str(document.relative_to(self.SKILL_ROOT))):
                text = self.scannable_text(document)
                for leaked in FORGE_VOCABULARY_FLOOR:
                    self.assertIsNone(
                        re.search(rf"\b{leaked}\b", text),
                        f"{leaked!r} is some target's vocabulary, not the forge's")

    def test_the_guard_scans_the_scripts_this_forge_ships(self):
        """The surface that changes most often was the one never scanned.

        Nothing copies `scripts/`, which is why it was left out, but that is the
        wrong test: it is the forge's own code, read by anyone extending the
        skill and edited by every change that touches the checker or the
        materializer. It had exactly one leak when it was first scanned.
        """
        scanned = {str(path.relative_to(self.SKILL_ROOT))
                   for path in self.guarded_documents()}
        expected = {str(path.relative_to(self.SKILL_ROOT))
                    for path in sorted((self.SKILL_ROOT / "scripts").rglob("*"))
                    if path.is_file()
                    and not any(part in self.CACHES for part in path.parts)
                    and path.suffix.lower() not in self.BINARY_SUFFIXES}
        self.assertTrue(expected, "the forge ships no scripts, which cannot be")
        self.assertEqual(sorted(expected - scanned), [])

    def test_a_leak_into_a_script_is_caught(self):
        """Proven against a tree built for it, not against a clean checkout.

        A guard that passes because nothing is wrong today has not been shown to
        do anything. This builds the forge's shape, plants one leak in a script
        and one in a comment, and reads what the guard would scan.
        """
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        (base / "references").mkdir()
        (base / "assets").mkdir()
        (base / "scripts").mkdir()
        (base / "SKILL.md").write_text("Generic doctrine.\n", encoding="utf-8")
        (base / "references" / "usage.md").write_text("Generic.\n", encoding="utf-8")
        (base / "scripts" / "leaky.py").write_text(
            "# reached only by the ramp\nVALUE = 1\n", encoding="utf-8")
        (base / "scripts" / "clean.py").write_text("VALUE = 2\n", encoding="utf-8")

        caught = {}
        for document in self.guarded_documents(base):
            text = self.scannable_text(document)
            hits = [word for word in FORGE_VOCABULARY_FLOOR
                    if re.search(rf"\b{word}\b", text)]
            if hits:
                caught[str(document.relative_to(base))] = hits
        self.assertEqual(caught, {"scripts/leaky.py": ["ramp"]})

    def test_the_tests_stay_unguarded_and_it_is_measured(self):
        """Why the widening stops at `scripts/`.

        `remote-execution` ships an adapter for one hosted service, so the suite
        that tests it names that service constantly and legitimately. Guarding
        `tests/` would mean exempting the file that most needs its vocabulary,
        which is not a guard. Measured rather than asserted, so the day the
        number goes to zero somebody can reconsider.
        """
        suite_root = FORGE / "tests"
        self.assertEqual(
            [str(path) for path in self.guarded_documents()
             if suite_root in path.parents], [],
            "the forge's own suite is not a guarded surface")

        suite = suite_root / "test_remote_execution.py"
        self.assertTrue(suite.is_file())
        occurrences = len(re.findall(
            r"\bkaggle\b", suite.read_text(encoding="utf-8").lower()))
        self.assertGreater(
            occurrences, 100,
            "one test file names the service hundreds of times because the "
            "skill under test ships an adapter for it")


class MaterializeBenchmarkDeclarationTests(unittest.TestCase):
    """Before this, `materialize.py` never created `src/<Package>_Benchmark/`
    at all, so `scaffold_gaps` — the one check whose job is reporting what a
    scaffold left out — checked five paths and none of them was the
    declaration. These pin the fix: a fresh scaffold writes the declaration,
    it parses empty, and `scaffold_gaps` can both see it present and see it
    missing.
    """

    KIT = FORGE / ".claude/skills/proposal-implementation/assets/kit"

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(CLI.parent))
        import materialize  # local import: path to scripts/ set above
        cls.materialize = materialize

    def _box(self):
        box = FORGE / "implementations" / f"_materialize_{os.getpid()}_{id(self)}"
        box.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        return box

    def _declared(self, box):
        self.materialize.main(str(box), "Method", "1", str(self.KIT))
        return box / "src" / "Method_Benchmark" / "__init__.py"

    def test_a_fresh_scaffold_writes_a_declaration_that_parses_empty(self):
        box = self._box()
        declared = self._declared(box)
        self.assertTrue(declared.exists())

        tree = ast.parse(declared.read_text(encoding="utf-8"))
        value = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__benchmark__"
                for t in node.targets
            ):
                value = ast.literal_eval(node.value)
        self.assertIsNotNone(value, "no literal __benchmark__ assignment found")
        self.assertEqual(
            set(value),
            {"revision", "premises", "arms", "search", "report", "distribution",
             "entry"})
        for key, field in value.items():
            if key == "entry":
                # The seventh block's own blank shape: a dict of two blank
                # scalars, not an empty container like the other six.
                self.assertEqual(field, {"module": "", "function": ""},
                                 f"{key!r} is not empty: {field!r}")
                continue
            self.assertIn(field, ("", {}, []), f"{key!r} is not empty: {field!r}")

    def test_scaffold_gaps_no_longer_reports_it_missing_once_written(self):
        box = self._box()
        self._declared(box)
        gaps = impl.scaffold_gaps(box, "Method")
        self.assertNotIn("src/Method_Benchmark/__init__.py", gaps)

    def test_scaffold_gaps_reports_it_missing_when_absent(self):
        with tempfile.TemporaryDirectory() as raw:
            gaps = impl.scaffold_gaps(Path(raw), "Method")
        self.assertIn("src/Method_Benchmark/__init__.py", gaps)


class LatestRevisionDiscoveryTests(unittest.TestCase):
    """El campo se llamaba `latestRevision` y era el eco del argumento.

    `verify` comparaba el banco contra la revisión que alguien escribiera en la
    línea de comandos. Ese chequeo solo estaba armado si el que llamaba acertaba a
    escribir la correcta: pasándole la revisión a la que el banco ya está atado, el
    chequeo se da la razón a sí mismo por más que en `proposals/` haya aterrizado
    algo más nuevo. Y sin argumento, `fidelity` contestaba `unknown` y ni lo
    intentaba.

    Los nombres del fixture son neutros a propósito. El patrón de familia se deriva
    de un nombre que llega como dato, nunca de una convención que este código
    conozca, así que una forja cuyas revisiones se llamen `draft-N.md` está servida
    por el mismo código — y eso es exactamente lo que se pinea acá.
    """

    def _proposals(self, *names):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for revision in names:
            (root / revision).write_text("## 1\ntexto\n", encoding="utf-8")
        return root

    def _with_root(self, root):
        previous = os.environ.get("IMPLEMENTATION_PROPOSALS")
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(root)

        def restore():
            if previous is None:
                os.environ.pop("IMPLEMENTATION_PROPOSALS", None)
            else:
                os.environ["IMPLEMENTATION_PROPOSALS"] = previous

        self.addCleanup(restore)

    def test_the_newest_of_the_family_is_found(self):
        self._with_root(self._proposals("draft-1.md", "draft-2.md", "draft-3.md"))
        self.assertEqual(impl.latest_revision("draft-1.md"), "draft-3.md")

    def test_ten_outranks_nine(self):
        """El orden es sobre los dígitos como enteros. Sobre la cadena, `draft-9`
        gana y el chequeo reporta la más nueva como más vieja: en silencio, y para
        el lado que aprueba."""
        self._with_root(self._proposals("draft-9.md", "draft-10.md"))
        self.assertEqual(impl.latest_revision("draft-9.md"), "draft-10.md")

    def test_another_family_is_not_a_successor(self):
        self._with_root(self._proposals("draft-2.md", "otra-cosa-7.md"))
        self.assertEqual(impl.latest_revision("draft-2.md"), "draft-2.md")

    def test_a_name_without_digits_has_no_family(self):
        self._with_root(self._proposals("draft-2.md"))
        self.assertIsNone(impl.latest_revision("sin-numero.md"))

    def test_nothing_to_derive_from_is_not_a_guess(self):
        self._with_root(self._proposals("draft-2.md"))
        self.assertIsNone(impl.latest_revision(None))


class VerifyDiscoversTheNewestRevisionTests(unittest.TestCase):
    """La costura, de punta a punta: el banco atado a una revisión vieja mientras
    en `proposals/` ya vive una más nueva, y nadie pasa `--revision`.

    Antes esto contestaba `unknown` y `latestRevision: null`. El banco podía estar
    atado a cualquier cosa y el flujo no tenía nada que decir.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'draft-1.md',\n"
        "    'arms': {'floor': {'sections': ['3']}},\n"
        "}\n"
    )

    def verify_in(self, *proposals, revision=None):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for name in proposals:
            (root / name).write_text("## 3\ntexto\n", encoding="utf-8")

        box = FORGE / "implementations" / f"_e2e_latest_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src/Method").mkdir(parents=True)
        (box / "src/Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "src/Method_Benchmark/__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")

        argv = [sys.executable, str(CLI), "verify", "--target", str(box),
                "--name", "Method"]
        if revision:
            argv += ["--revision", revision]
        environment = dict(os.environ, IMPLEMENTATION_PROPOSALS=str(root))
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=FORGE,
                              env=environment)
        return json.loads(proc.stdout or "{}")["fidelity"]

    def test_a_bench_bound_to_an_older_revision_is_caught_without_being_told(self):
        fidelity = self.verify_in("draft-1.md", "draft-2.md")
        self.assertEqual(fidelity["latestRevision"], "draft-2.md")
        self.assertEqual(fidelity["revisionSource"], "discovered")
        self.assertTrue(fidelity["benchmark"]["staleRevision"])
        self.assertEqual(fidelity["benchmark"]["status"], "stale")

    def test_the_newest_being_the_bound_one_is_the_other_pole(self):
        """Sin esto, un chequeo que siempre marca viejo no distingue un banco al
        día de uno atrasado, y aprobar sería imposible."""
        fidelity = self.verify_in("draft-1.md")
        self.assertEqual(fidelity["latestRevision"], "draft-1.md")
        self.assertFalse(fidelity["benchmark"]["staleRevision"])
        self.assertEqual(fidelity["benchmark"]["status"], "ok")

    def test_an_explicit_argument_still_wins(self):
        """Quien fija una revisión está contestando la pregunta, no haciéndola."""
        fidelity = self.verify_in("draft-1.md", "draft-2.md", revision="draft-1.md")
        self.assertEqual(fidelity["latestRevision"], "draft-1.md")
        self.assertEqual(fidelity["revisionSource"], "argument")
        self.assertFalse(fidelity["benchmark"]["staleRevision"])

    def test_nothing_on_disk_reports_itself_unable(self):
        fidelity = self.verify_in()
        self.assertIsNone(fidelity["latestRevision"])
        self.assertEqual(fidelity["revisionSource"], "none")
        self.assertEqual(fidelity["status"], "unknown")


class EquationTagRecognitionTests(unittest.TestCase):
    """One `\\tag{...}` reader, because three of them disagreed.

    `compose` and `handoff` read a tag as anything between the braces, which is
    what a paper actually writes: `3.1`, `A.2`, `B.10`. `admit` and the
    compatibility audit each carried their own digits-only copy, so the same
    document that `compose` reads happily made `admit` rule a finding
    inadmissible for "citing equations absent from the revision" — equations
    that are right there — and made `verify`'s audit report the revision
    incompatible. The reason given was false in both cases.

    The fixture is neutral on purpose: a two-section draft whose equations are
    labelled the way a numbered paper labels them.
    """

    REVISION = (
        "## 3\n"
        "\n"
        "$$\n"
        "a = b \\tag{3.1}\n"
        "$$\n"
        "\n"
        "## A\n"
        "\n"
        "$$\n"
        "c = d \\tag{A.2}\n"
        "$$\n"
        "\n"
        "Throughout, the estimator is written E[x].\n"
    )

    ENTRY = "$$\nc = d \\tag{A.2}\n$$"
    REMEDY_BLOCK = "$$\nc = e + f \\tag{A.2}\n$$"

    FINDINGS = (
        "FINDINGS = [\n"
        "    {\n"
        "        'id': 'lettered-tags',\n"
        "        'equations': ['3.1'],\n"
        "        'remedy_equations': ['A.2'],\n"
        "        'uses': ['E[x]'],\n"
        "        'introduces': [],\n"
        "        'adoption': {'absent': 'c = d', 'expect': ['c = e + f']},\n"
        "        'remedy_block': '$$\\nc = e + f \\\\tag{A.2}\\n$$',\n"
        "    },\n"
        "]\n"
    )

    ABSENT_CITATION_FINDINGS = (
        "FINDINGS = [\n"
        "    {\n"
        "        'id': 'cites-nothing-real',\n"
        "        'equations': ['9.9'],\n"
        "        'remedy_equations': [],\n"
        "        'uses': ['E[x]'],\n"
        "        'introduces': [],\n"
        "        'adoption': {'absent': 'c = d', 'expect': ['c = e + f']},\n"
        "    },\n"
        "]\n"
    )

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'draft-1.md',\n"
        "    'arms': {'floor': {'sections': ['3']}},\n"
        "}\n"
    )

    def _proposals(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "draft-1.md").write_text(self.REVISION, encoding="utf-8")
        previous = os.environ.get("IMPLEMENTATION_PROPOSALS")
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(root)

        def restore():
            if previous is None:
                os.environ.pop("IMPLEMENTATION_PROPOSALS", None)
            else:
                os.environ["IMPLEMENTATION_PROPOSALS"] = previous

        self.addCleanup(restore)
        return root

    def _box(self, tag: str, findings: str) -> Path:
        box = FORGE / "implementations" / f"_tags_{tag}_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        (box / "tests" / "findings.py").write_text(findings, encoding="utf-8")
        return box

    def test_a_dotted_or_lettered_citation_is_admissible(self):
        """The equations are in the document. Ruling the finding inadmissible
        for their absence states something about the revision that is false."""
        self._proposals()
        box = self._box("admit", self.FINDINGS)
        result = impl.cmd_admit(
            argparse.Namespace(target=str(box), name="Method", revision="draft-1.md"))

        self.assertEqual(result["inadmissible"], {})
        self.assertEqual(result["admitted"], ["lettered-tags"])
        self.assertEqual(result["status"], "admitted")

    def test_the_compatibility_audit_reads_the_same_tags(self):
        """The second copy of the narrow pattern: it drove
        `audit.compatibility` to `incompatible` on a revision nothing is wrong
        with."""
        self._proposals()
        box = self._box("audit", self.FINDINGS)
        result = impl.cmd_verify(
            argparse.Namespace(target=str(box), name="Method", revision="draft-1.md"))

        compatibility = result["audit"]["compatibility"]
        self.assertEqual(compatibility["unknownEquations"], [])
        self.assertNotEqual(compatibility["status"], "incompatible")

    def test_compose_and_admit_agree_on_one_tag_set(self):
        """The whole defect in one assertion: `compose` locates `A.2` in this
        document while `admit` used to answer that `A.2` is not in it."""
        self._proposals()
        box = self._box("agree", self.FINDINGS)
        composed = impl.cmd_compose(
            argparse.Namespace(target=str(box), finding="lettered-tags",
                               entry_text=self.ENTRY))
        admitted = impl.cmd_admit(
            argparse.Namespace(target=str(box), name="Method", revision="draft-1.md"))

        self.assertEqual(composed["equation"], "A.2")
        self.assertIn("lettered-tags", admitted["admitted"])

    def test_a_citation_the_revision_does_not_carry_is_still_refused(self):
        """The lock on the widening: recognizing more tags must not turn into
        recognizing every tag. `9.9` is nowhere in the document."""
        self._proposals()
        box = self._box("absent", self.ABSENT_CITATION_FINDINGS)
        result = impl.cmd_admit(
            argparse.Namespace(target=str(box), name="Method", revision="draft-1.md"))

        self.assertEqual(result["status"], "inadmissible")
        self.assertIn("cites-nothing-real", result["inadmissible"])
        self.assertTrue(
            any("absent from the revision" in reason
                for reason in result["inadmissible"]["cites-nothing-real"]),
            result["inadmissible"])


class SearchDeclarationShapeTests(unittest.TestCase):
    """The `search` declaration had no shape table, and the published example
    was a scalar every consumer iterated as a mapping.

    `distribution` has been guarded by `DISTRIBUTION_SHAPE` since it was
    written: a key of the wrong type is a third thing, neither answered nor
    missing. `search` had nothing of the kind, so `search_state` accepted
    `requiredScale: 30` as answered on bare truthiness — and then
    `_projected_cost` iterated `.items()` on it and `probe` died with a
    traceback, emitting no JSON at all. The value came from the kit's own
    template, so the first target to copy the example it was handed hit it.
    """

    KIT_DECLARATION = (FORGE / ".claude/skills/proposal-implementation"
                       / "assets/kit/src_benchmark/__init__.py")
    DOCTRINE = FORGE / ".claude/skills/proposal-implementation/SKILL.md"

    MAPPING_SEARCH = {
        "what": "which free scalar this chooses",
        "requiredScale": {"epochs": 20, "seeds": 3},
        "role": "valid",
        "tieRule": "the smallest value among the tied candidates",
    }
    SCALAR_SEARCH = {**MAPPING_SEARCH, "requiredScale": 30}

    def _published_search_example(self, path: Path) -> dict:
        """The `search` example a target is invited to copy, read from where it
        is published rather than restated here.

        Restating it would let the two drift, which is exactly how a scalar
        stayed in both places long enough for a target to adopt it.
        """
        body: list[str] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip().lstrip("#").strip()
            if body:
                body.append(line)
                if line in ("}", "},"):
                    break
            elif line == '"search": {':
                body.append(line)
        self.assertTrue(body, f"no published search example found in {path}")
        return ast.literal_eval("{" + "\n".join(body).rstrip(",") + "}")["search"]

    def _declaration(self, search) -> str:
        return ("__benchmark__ = {\n"
                "    'revision': 'r01.md',\n"
                "    'arms': {'floor': {'sections': ['3']}},\n"
                f"    'search': {search!r},\n"
                "}\n")

    def _probe(self, search, *, suffix):
        box = FORGE / "implementations" / f"_search_shape_{suffix}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src/Method").mkdir(parents=True)
        (box / "src/Method_Benchmark").mkdir(parents=True)
        # The product folder, distinct from `src/Method`: the pilot record the
        # forecast is projected from lives under it.
        (box / "Method" / "Results").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "src/Method_Benchmark/__init__.py").write_text(
            self._declaration(search), encoding="utf-8")
        (box / "Method" / "Results" / impl.PROBE_RESULTS).write_text(json.dumps({
            "revision": "r01.md",
            "comparison": {"metric": 1},
            "reduction": {"epochs": 1, "wallSeconds": 60},
            "targetScale": {"epochs": 5},
        }), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(CLI), "probe", "--target", str(box),
             "--name", "Method", "--revision", "r01.md"],
            capture_output=True, text=True, cwd=FORGE)

    def test_a_scalar_required_scale_is_reported_and_never_crashed_on(self):
        """The live reproduction: `AttributeError: 'int' object has no
        attribute 'items'`, raised where the forecast is projected. `main`
        catches only `Refused`, so the process ended on a traceback and
        whoever called `probe` got no JSON to read at all."""
        proc = self._probe(self.SCALAR_SEARCH, suffix="scalar")

        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout or "{}")
        self.assertEqual(result["search"]["status"], "incomplete")
        self.assertEqual([m["field"] for m in result["search"]["malformed"]],
                         ["requiredScale"])

    def test_a_scalar_required_scale_reads_as_malformed_not_as_answered(self):
        """Bare truthiness accepted `30` as an answer. A declaration nobody
        type-checked is the producer half of the same defect, and guarding
        only the arithmetic downstream would have left it in place."""
        state = impl.search_state({"search": self.SCALAR_SEARCH}, [])

        self.assertEqual([m["field"] for m in state["malformed"]], ["requiredScale"])
        self.assertEqual(state["malformed"][0]["expected"], "dict")
        self.assertEqual(state["malformed"][0]["found"], "int")
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual([m["field"] for m in state["missing"]], [])

    def test_every_published_example_is_one_a_target_can_run(self):
        """The regression test that makes the doc and the code one contract:
        the example is read from the two places it is published and run
        through `probe` exactly as a target would copy it."""
        for path in (self.KIT_DECLARATION, self.DOCTRINE):
            with self.subTest(published=path.name):
                example = self._published_search_example(path)
                self.assertIsInstance(example["requiredScale"], dict)
                proc = self._probe(example, suffix=f"published_{path.suffix.strip('.')}")
                self.assertNotIn("Traceback", proc.stderr)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                search = json.loads(proc.stdout or "{}")["search"]
                self.assertEqual(search["malformed"], [])

    def test_a_mapping_required_scale_still_projects_the_forecast(self):
        """Characterization: the arithmetic the guard sits in front of is not
        touched. 60 measured seconds at one epoch, twenty declared, so twenty
        times the measurement — and `seeds`, which the pilot never recorded,
        scales nothing rather than being guessed at."""
        proc = self._probe(self.MAPPING_SEARCH, suffix="mapping")
        forecast = json.loads(proc.stdout or "{}")["search"]["costForecast"]

        self.assertEqual(forecast["measuredSeconds"], 60)
        self.assertEqual(forecast["factor"], 20.0)
        self.assertEqual(forecast["projectedSeconds"], 1200)
        self.assertEqual(forecast["aboveMeasuredScale"],
                         {"epochs": {"declared": 20, "measuredAt": 1}})

    def test_the_toy_targets_left_nothing_behind(self):
        self._probe(self.MAPPING_SEARCH, suffix="cleanup")
        for box in (FORGE / "implementations").glob("_search_shape_cleanup_*"):
            shutil.rmtree(box, ignore_errors=True)
        self.assertEqual(list((FORGE / "implementations").glob("_search_shape_*")), [])


class ScaffoldInstructionsAgreementTests(unittest.TestCase):
    """The producer instructions and the gap checker were two lists, and only
    one of them was executable.

    Step 5 told the agent to write four files "from `assets/`"; `scaffold_gaps`
    required thirteen, from `assets/kit/`. An agent that followed the instruction
    exactly produced a target `verify` then reported incomplete, and the
    quickest reading of that is that the checker is wrong. Prose cannot be
    generated from code here — SKILL.md is what an agent reads, not a rendered
    artifact — so it is held to the code by tests that go red the moment either
    side moves alone.

    `Example-Method` is the name the usage reference already works its
    examples in, so the substituted placeholders land on paths a reader of
    that document recognizes.
    """

    SKILL_ROOT = CLI.parent.parent
    SKILL_MD = SKILL_ROOT / "SKILL.md"
    USAGE = SKILL_ROOT / "references" / "usage.md"
    ASSETS = SKILL_ROOT / "assets"

    EXAMPLE_NAME = "Example-Method"
    EXAMPLE_PACKAGE = "Example_Method"

    TABLE_HEADER = "| Gap `plan` and `verify` report | Written from |"
    TOKEN_RE = TOKEN_RE  # the module-level pattern; call sites are unchanged
    CACHES = CACHES
    BINARY_SUFFIXES = BINARY_SUFFIXES

    def required_gaps(self):
        """What the checker demands of a repository holding none of it."""
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        return impl.scaffold_gaps(empty, self.EXAMPLE_NAME)

    gap_class = staticmethod(gap_path)

    def documented_gaps(self):
        lines = self.SKILL_MD.read_text(encoding="utf-8").splitlines()
        stripped = [line.strip() for line in lines]
        self.assertIn(self.TABLE_HEADER, stripped,
                      "step 5 carries no gap → template table")
        start = stripped.index(self.TABLE_HEADER)
        documented = []
        for line in stripped[start + 2:]:
            if not line.startswith("|"):
                break
            cell = line.split("|")[1].strip().strip("`")
            documented.append(cell.replace("<Name>", self.EXAMPLE_NAME)
                                  .replace("<Package>", self.EXAMPLE_PACKAGE))
        return documented

    def kit_tokens(self):
        found = set()
        for path in sorted(self.ASSETS.rglob("*")):
            if not path.is_file():
                continue
            if any(part in self.CACHES for part in path.parts):
                continue
            if path.suffix.lower() in self.BINARY_SUFFIXES:
                continue
            found.update(self.TOKEN_RE.findall(
                path.read_text(encoding="utf-8", errors="replace")))
        return found

    def test_the_documented_file_list_equals_the_gap_checker(self):
        """Reachable red: step 5 named four files while `scaffold_gaps`
        required thirteen, and the four did not include the benchmark
        declaration — the one file the whole declaration contract is read
        from."""
        documented = self.documented_gaps()
        self.assertEqual(
            sorted(self.gap_class(gap) for gap in documented),
            sorted(self.gap_class(gap) for gap in self.required_gaps()))

    def test_the_documented_tokens_cover_every_kit_template_token(self):
        """Both directions. A token the kit uses and the doc omits is a
        substitution nobody performs, which ships `{{PKG}}` into a target's
        source; a token the doc lists and no template carries is an
        instruction to substitute nothing."""
        documented = set(self.TOKEN_RE.findall(
            self.USAGE.read_text(encoding="utf-8")))
        self.assertEqual(documented, self.kit_tokens())

    def test_the_worked_scaffold_file_example_is_the_whole_list(self):
        """The example is what a reader copies. Showing four of thirteen teaches
        a scaffold that `verify` reports incomplete."""
        text = self.USAGE.read_text(encoding="utf-8")
        blocks = re.findall(r"```json\n(.*?)```", text, re.DOTALL)
        worked = [json.loads(block) for block in blocks
                  if '"scaffoldFiles"' in block]
        self.assertTrue(worked, "the usage reference works no plan example")
        self.assertEqual(sorted(worked[0]["scaffoldFiles"]),
                         sorted(self.required_gaps()))

    def test_the_template_root_is_the_one_the_templates_live_in(self):
        """`../assets/` resolves to the forge root's own `assets/`, which does
        not exist. Every template lives under the skill's `assets/kit/`."""
        lines = self.USAGE.read_text(encoding="utf-8").splitlines()
        self.assertEqual([line for line in lines if "../assets/" in line], [])
        self.assertTrue([line for line in lines if "assets/kit/" in line],
                        "the usage reference names no template root at all")


class ScaffoldImportClosureTests(unittest.TestCase):
    """A scaffold built from exactly the paths doctrine names could not import.

    Two of the files step 5 sends into `tests/` open with an absolute import of
    a sibling the same table never names: `test_audit.py` imports `sweep`, and
    `test_remedies.py` imports `admissibility` and `sweep`. Neither sibling is
    among the gaps `scaffold_gaps` requires, so an agent that followed the
    instruction exactly wrote every file it was asked for and got a tree pytest
    refuses to collect — while `verify` reported `scaffoldGaps: []` and exited
    `0`, because a checker only ever asks for what doctrine already names.

    The count is the mechanism, not the defect. Closure is what keeps it
    closed: a stage-1 test may only import siblings that are themselves stage 1,
    so the next file added to `kit/tests/` cannot repeat this quietly.

    `conftest.py` is deliberately outside closure's reach and is named here so
    nobody looks for it: pytest loads it by convention, nothing in the kit
    imports it, and its `rng`/`TOL` are used by no shipped template. Only the
    coverage register can hold it. Closure and coverage are complements.
    """

    SKILL_ROOT = CLI.parent.parent
    KIT_TESTS = SKILL_ROOT / "assets" / "kit" / "tests"
    KIT_NB = SKILL_ROOT / "assets" / "kit" / "nb"
    KIT_BENCH = SKILL_ROOT / "assets" / "kit" / "src_benchmark"
    TEMPLATE = SKILL_ROOT / "assets" / "pyproject.template.toml"

    NAME = "Example-Method"
    PACKAGE = "Example_Method"
    SEED = "7"

    def required_gaps(self):
        """What the checker demands of a repository holding none of it."""
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        return impl.scaffold_gaps(empty, self.NAME)

    def stage_one_test_stems(self):
        """The kit tests doctrine actually places, by module name."""
        gaps = self.required_gaps()
        return {Path(gap).stem for gap in gaps if gap.startswith("tests/")}

    @staticmethod
    def absolute_import_roots(source: str) -> set:
        """Every top-level name this module imports from outside a package.

        `level == 0` excludes explicit relative imports, which resolve inside a
        package and can never name a flat sibling on `sys.path`.
        """
        roots = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        return roots

    def test_every_stage_one_kit_test_imports_only_stage_one_siblings(self):
        """Reachable red: `test_audit.py` and `test_remedies.py` are both gaps
        `scaffold_gaps` requires, and both import siblings it does not."""
        siblings = {path.stem for path in self.KIT_TESTS.glob("*.py")}
        placed = self.stage_one_test_stems()
        unplaced = {}
        for stem in sorted(placed):
            template = self.KIT_TESTS / f"{stem}.py"
            if not template.exists():
                continue
            for root in sorted(self.absolute_import_roots(
                    template.read_text(encoding="utf-8"))):
                if root in siblings and root not in placed:
                    unplaced.setdefault(f"{stem}.py", []).append(root)
        self.assertEqual(
            unplaced, {},
            "a stage-1 kit test imports a sibling the scaffold never places: "
            f"{unplaced}")

    def scaffold(self):
        return doctrine_scaffold(self, self.NAME, self.SEED)

    def test_a_doctrine_faithful_scaffold_is_collected_without_error(self):
        """Reachable red, and the one that was measured rather than argued:

            tests/test_audit.py:11: in <module>
                from sweep import SWEEP_SIZE, sweep
            E   ModuleNotFoundError: No module named 'sweep'
            2 tests collected, 2 errors

        Collection, not passing, is the bar. `test_smoke.py` must still fail at
        run time — `MODULES` names a module step 9 has not written — and that
        red is protected, not repaired.
        """
        box = self.scaffold()
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=str(box), capture_output=True, text=True)
        self.assertNotIn("ModuleNotFoundError", proc.stdout + proc.stderr,
                         proc.stdout[-3000:])
        self.assertNotIn("error", proc.stdout.splitlines()[-1].lower(),
                         proc.stdout[-3000:])


class ReportSealPlacementTests(unittest.TestCase):
    """The seal that binds a report to its code shipped with no instruction
    naming where it goes.

    `assets/kit/nb/report_digest.py` is the one implementation of the source
    digest: it agrees with `implementation_cli.source_digest` line for line, and
    it is what a notebook is supposed to import instead of hashing a tree of its
    own. No table, no `wanted` entry and no worked example ever named a
    destination for it, so a target scaffolded exactly as doctrine instructs
    does not contain it — and every notebook that would import it cannot.

    `assets/kit/nb/` is a staging folder, not a mirror of where its contents
    end up: `benchmark.py` and `verdict.py` already ship out of it into
    `src/<Package>_Benchmark/`. So the repair is a row, and the file does not
    move.
    """

    NAME = "Example-Method"
    PACKAGE = "Example_Method"
    SEED = "7"
    DESTINATION = "src/Example_Method_Benchmark/report_digest.py"

    def test_the_seal_is_placed_where_a_notebook_can_import_it(self):
        """Reachable red: a scaffold built from exactly the gaps `scaffold_gaps`
        reports holds no `report_digest.py` anywhere."""
        box = doctrine_scaffold(self, self.NAME, self.SEED)
        self.assertTrue(
            (box / self.DESTINATION).is_file(),
            "a doctrine-faithful scaffold does not carry the report seal; "
            f"it holds {sorted(str(p.relative_to(box)) for p in box.rglob('*.py'))}")

    def test_the_placed_seal_agrees_with_the_digest_verify_recomputes(self):
        """Why the row exists, stated as behaviour rather than as a row.

        The seal is only worth placing if the string it stamps is the string
        `verify` recomputes. Loading it from where the scaffold puts it also
        proves the placement itself: `_here()` resolves the repository as
        `parents[1]` of its own directory, which is only the target's root when
        the file sits in `src/<Package>_Benchmark/`.
        """
        import importlib.util

        box = doctrine_scaffold(self, self.NAME, self.SEED)
        placed = box / self.DESTINATION
        self.assertTrue(placed.is_file(), "the seal was never placed")
        spec = importlib.util.spec_from_file_location("placed_report_digest", placed)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.stamp(),
                         f"{module.MARKER} {impl.source_digest(box, self.PACKAGE)}")

    def test_the_materializer_places_the_seal_too(self):
        """A destination nothing honours is a destination in name only, so the
        commit that declares it is the commit that teaches the producer."""
        box = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/materialize.py"),
             str(box), self.NAME, self.SEED], check=True, capture_output=True)
        self.assertTrue((box / self.DESTINATION).is_file(),
                        "`materialize.py` writes no report seal")


class NotebookSealAgreementTests(unittest.TestCase):
    """The kit notebook stamped a digest over a tree the verifier never reads.

    Three implementations of one source digest shipped together.
    `implementation_cli.source_digest` covers all of `src/` and no `tests/`;
    `assets/kit/nb/report_digest.py` is byte-for-byte the same algorithm; and
    `verification.ipynb` inlined a third one over `src/<Pkg>` union `tests/`.

    The third one can never agree with the first. A report executed one second
    ago stamps a string `verify` recomputes differently, so `notebooks.status`
    reads `drift` and `validation.status` reads `incomplete` — permanently, and
    for no reason a reader of either file could see. The repair is deleting the
    copy that disagrees, not reconciling two formulas: the kit already carries
    the one implementation, and the notebook only has to import it.
    """

    NAME = "Example-Method"
    PACKAGE = "Example_Method"
    SEED = "7"

    @classmethod
    def code_cells(cls, notebook):
        """Every non-empty code cell of a kit notebook, as the scaffold writes
        it. The reading moved to module level once a second class needed it; the
        name stays because this class's tests read better through it."""
        return kit_notebook_cells(notebook, cls.NAME)

    def stamping_cell(self, notebook):
        """The cell that stamps the seal, identified by what it calls.

        Parsed, never matched as a substring: a marker or a path inside a
        comment reads the same as one inside an expression, and the whole point
        of this class is that a comment cannot be executed. The cell that stamps
        is the cell that calls `stamp()` on the one implementation.
        """
        found = cells_calling(notebook, "report_digest.stamp", self.NAME)
        self.assertEqual(
            len(found), 1,
            f"exactly one cell of {notebook} stamps the seal by calling the one "
            f"implementation; found {len(found)}")
        return found[0]

    @staticmethod
    def spawns_a_process(tree):
        """Whether a cell runs the report's work rather than describing it.

        Read as a call, not as a name: `probe.ipynb` imports `subprocess` in the
        cell that binds `ROOT`, several cells before the one that uses it, and
        skipping that cell would leave every later cell without a repository.
        """
        return any(isinstance(node, ast.Call)
                   and ast.unparse(node.func) in ("subprocess.run", "pytest.main")
                   for node in ast.walk(tree))

    def executed_seal(self, notebook_path, through):
        """The seal a notebook actually prints, obtained by running it.

        The notebook's own code cells run in order, up to and including the one
        that stamps, and the seal is read off standard output — the same way
        `notebook_execution` reads it out of a stored cell's output. Nothing
        after the stamping cell is run: in the probe those cells read a record
        the harness has not written.

        Cells that spawn another process are skipped. They are the report's
        work, not its seal, and running them here would run the target's suite
        or train a model.
        """
        loaded = json.loads(notebook_path.read_text(encoding="utf-8"))
        sources = []
        for index, cell in enumerate(loaded["cells"]):
            if index > through:
                break
            if cell["cell_type"] != "code":
                continue
            source = "".join(cell["source"])
            if not self.spawns_a_process(ast.parse(source)):
                sources.append(source)
        completed = subprocess.run(
            [sys.executable, "-c", "\n".join(sources)],
            cwd=str(notebook_path.parent), text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0,
                         f"the notebook's own cells failed:\n{completed.stderr[-2000:]}")
        seals = [line for line in completed.stdout.splitlines()
                 if line.startswith(impl.DIGEST_MARKER)]
        self.assertEqual(len(seals), 1,
                         f"the notebook printed {len(seals)} seals, not one")
        return seals[0]

    def stamped_as_executed(self, notebook_path, seal, through):
        """The notebook as it looks after a run that got as far as the seal.

        `notebook_execution` reads `execution_count` and the stored outputs, so
        that is what is written here. Every code cell counts as run — a probe
        whose harness cell never ran is unexecuted for a reason that has nothing
        to do with the seal, and would answer a different question.
        """
        loaded = json.loads(notebook_path.read_text(encoding="utf-8"))
        for index, cell in enumerate(loaded["cells"]):
            if cell["cell_type"] != "code":
                continue
            cell["execution_count"] = 1
            cell["outputs"] = ([{"output_type": "stream", "name": "stdout",
                                 "text": [seal + "\n"]}] if index == through else [])
        notebook_path.write_text(json.dumps(loaded), encoding="utf-8")

    def test_no_kit_notebook_computes_a_digest_of_its_own(self):
        """One algorithm, or the agreement is a coincidence waiting to end."""
        offenders = {}
        for notebook in ("verification.ipynb", impl.PROBE_NOTEBOOK):
            for index, source in self.code_cells(notebook):
                for node in ast.walk(ast.parse(source)):
                    named = (isinstance(node, ast.Import)
                             and any(alias.name.split(".")[0] == "hashlib"
                                     for alias in node.names))
                    called = (isinstance(node, ast.Call)
                              and "hashlib" in ast.unparse(node.func))
                    if named or called:
                        offenders.setdefault(notebook, []).append(index)
                        break
        self.assertEqual(offenders, {},
                         "a kit notebook hashes a tree of its own instead of "
                         "importing the one implementation")

    def test_the_verification_notebook_imports_the_seal_it_stamps(self):
        """It can, and only because the seal now has a scaffold destination
        inside the package: that cell already puts `src/` on `sys.path`."""
        _, source, tree = self.stamping_cell("verification.ipynb")
        imported = [node for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                    and any(alias.name == "report_digest" for alias in node.names)]
        self.assertEqual(
            [node.module for node in imported], [f"{self.PACKAGE}_Benchmark"],
            "the notebook must import the seal from the package the scaffold "
            "places it in")
        self.assertIn("sys.path.insert", source,
                      "the import only resolves once `src/` is on the path")

    def test_the_seal_the_notebook_stamps_is_the_seal_verify_recomputes(self):
        """The whole finding, as behaviour: run the notebook, run the checker,
        compare the two strings over the same tree."""
        index, _, _ = self.stamping_cell("verification.ipynb")
        box = doctrine_scaffold(self, self.NAME, self.SEED)
        notebook = box / self.NAME / "Notebooks" / "verification.ipynb"
        self.assertTrue(notebook.is_file(), "the scaffold carries no report")
        self.assertEqual(
            self.executed_seal(notebook, index),
            f"{impl.DIGEST_MARKER} {impl.source_digest(box, self.PACKAGE)}")

    def test_an_executed_report_is_not_born_stale(self):
        """What the disagreement cost, read through the checker that reports it.

        The digest is what `notebooks_state` compares, so a report that stamped
        a string the checker recomputes differently is `stale-sources` the
        moment it is written — and nothing about the target is wrong.
        """
        index, _, _ = self.stamping_cell("verification.ipynb")
        box = doctrine_scaffold(self, self.NAME, self.SEED)
        notebook = box / self.NAME / "Notebooks" / "verification.ipynb"
        seal = self.executed_seal(notebook, index)
        self.stamped_as_executed(notebook, seal, index)

        state = impl.notebooks_state(box, self.NAME, self.PACKAGE)
        self.assertEqual([report["status"] for report in state["reports"]],
                         ["executed"])
        self.assertEqual(state["unstamped"], [])
        self.assertEqual(state["status"], "ok")

    def test_a_report_names_what_the_digest_actually_compared(self):
        """`stale-sources` proves the tree moved, never that this notebook's
        own numbers are affected -- the comparison never asked.

        Measured 2026-08-26: three notebooks read `stale-sources` after one
        analysis function was added to a module no arm executes. No number had
        changed; the remote shards' own digests still matched the tree they ran
        on. A reader could not tell "the tree moved" from "these numbers are
        suspect", and the recorded consequence is someone re-running a campaign
        of hours over a module the campaign never executed.

        The digest is not narrowed -- three measured failures forbid that, and
        they are recorded beside `source_digest`. What changes is that the
        boundary now travels WITH the status, where a reader meets it, instead
        of living in a docstring they will not open.
        """
        index, _, _ = self.stamping_cell("verification.ipynb")
        box = doctrine_scaffold(self, self.NAME, self.SEED)
        notebook = box / self.NAME / "Notebooks" / "verification.ipynb"
        seal = self.executed_seal(notebook, index)
        self.stamped_as_executed(notebook, seal, index)

        state = impl.notebooks_state(box, self.NAME, self.PACKAGE)
        scope = state["reports"][0]["digestScope"]
        self.assertIn("src/", scope,
                      "the boundary must name what was compared")
        self.assertIn("import", scope,
                      "it must say the comparison is NOT this notebook's own "
                      "import closure -- that is the half a reader needs")

    def test_two_notebooks_importing_nothing_alike_report_the_same_boundary(self):
        """The on-path/off-path case, and why it reports identically.

        A digest over all of `src/` cannot distinguish a change on this
        notebook's import path from one nowhere near it, and narrowing it to
        find out is refused three times over. So both notebooks MUST carry the
        same boundary text: a reader who saw them differ would infer a
        distinction the comparison never made.
        """
        index, _, _ = self.stamping_cell("verification.ipynb")
        box = doctrine_scaffold(self, self.NAME, self.SEED)
        root = box / self.NAME / "Notebooks"
        notebook = root / "verification.ipynb"
        seal = self.executed_seal(notebook, index)
        self.stamped_as_executed(notebook, seal, index)
        # A second, unexecuted notebook: a different entry, same boundary.
        (root / "other.ipynb").write_text(
            json.dumps({"cells": [], "metadata": {}, "nbformat": 4,
                        "nbformat_minor": 5}), encoding="utf-8")

        state = impl.notebooks_state(box, self.NAME, self.PACKAGE)
        scopes = {report["digestScope"] for report in state["reports"]}
        self.assertEqual(len(state["reports"]), 2)
        self.assertEqual(
            len(scopes), 1,
            "two notebooks must carry one identical boundary; differing text "
            "would imply a per-notebook distinction the digest never computes")

    # -- the probe, which is not the same edit ------------------------------

    #: The tokens a probe carries beyond the five the scaffold answers. The
    #: agent answers these at step 12; nothing in the CLI writes them, so a
    #: fixture that wants an executable probe has to answer them itself.
    PROBE_ANSWERS = {
        "{{BASELINE}}": "Example-Baseline",
        "{{DATASET}}": "example-collection",
        "{{FRACTION}}": "0.05",
        "{{EPOCHS}}": "1",
        "{{SEEDS}}": "[0, 1]",
        "{{PROBE_RESULTS}}": impl.PROBE_RESULTS,
    }

    def placed_probe(self, box):
        """The probe where the copy step puts it, with every token answered.

        The probe is stage 2 — `scaffold_gaps` never asks for it — so a scaffold
        does not carry it and this is the placement doctrine's copy-step table
        states.
        """
        text = scaffold_substitute(
            (KIT / "nb" / impl.PROBE_NOTEBOOK).read_text(encoding="utf-8"),
            self.NAME, self.SEED)
        for token, value in self.PROBE_ANSWERS.items():
            text = text.replace(token, value)
        placed = box / self.NAME / "Notebooks" / impl.PROBE_NOTEBOOK
        placed.parent.mkdir(parents=True, exist_ok=True)
        placed.write_text(text, encoding="utf-8")
        return placed

    def test_the_probe_notebook_carries_its_own_path_insert(self):
        """The one way this is not the report's edit repeated.

        `verification.ipynb` stamps inside the cell that already put `src/` on
        `sys.path`. The probe's `ROOT` and `sys` first exist in the cell that
        writes the reduction, and that cell inserts nothing, so a stamping cell
        copied from the report would import a package that is not importable.
        """
        _, source, tree = self.stamping_cell(impl.PROBE_NOTEBOOK)
        inserts = [node for node in ast.walk(tree)
                   if isinstance(node, ast.Call)
                   and ast.unparse(node.func) == "sys.path.insert"]
        self.assertEqual(len(inserts), 1,
                         "the probe's stamping cell must put `src/` on the path "
                         "itself; no earlier cell of the probe does")
        self.assertEqual(ast.unparse(inserts[0].args[1]), "str(ROOT / 'src')")
        imported = [node.module for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                    and any(alias.name == "report_digest" for alias in node.names)]
        self.assertEqual(imported, [f"{self.PACKAGE}_Benchmark"])
        self.assertNotIn("subprocess", source,
                         "stamping adds no process; the harness cell is untouched")

    def test_an_executed_probe_can_be_stamped(self):
        """The finding, as behaviour.

        `notebooks_state` names an executed notebook that stamped nothing, and
        it counts: `unstamped` is what keeps a report that cannot be told from a
        relic out of `ok`. With no stamping cell at all, the probe could never
        leave that list, so `validation.status` was pinned to `incomplete` by a
        cell that was never written rather than by anything about the target.
        """
        index, _, _ = self.stamping_cell(impl.PROBE_NOTEBOOK)
        box = doctrine_scaffold(self, self.NAME, self.SEED)
        probe = self.placed_probe(box)

        seal = self.executed_seal(probe, index)
        self.assertEqual(
            seal, f"{impl.DIGEST_MARKER} {impl.source_digest(box, self.PACKAGE)}")
        self.stamped_as_executed(probe, seal, index)

        state = impl.notebooks_state(box, self.NAME, self.PACKAGE)
        report = next(r for r in state["reports"]
                      if r["notebook"].endswith(impl.PROBE_NOTEBOOK))
        self.assertEqual(report["status"], "executed")
        self.assertIs(report["sourcesMatch"], True)
        self.assertEqual(state["unstamped"], [])

    def test_the_probe_stamps_before_it_runs_the_harness(self):
        """A seal the harness cell can decide not to print is not a seal.

        The digest is over source, which the run does not change, so stamping
        early costs nothing and survives a harness that fails — which is the
        state a probe is most often read in.
        """
        index, _, _ = self.stamping_cell(impl.PROBE_NOTEBOOK)
        harness = [cell_index for cell_index, source
                   in self.code_cells(impl.PROBE_NOTEBOOK)
                   if self.spawns_a_process(ast.parse(source))]
        self.assertEqual(len(harness), 1, "exactly one cell runs the harness")
        self.assertLess(index, harness[0])


class SuiteFailureReachesTheVerdictTests(unittest.TestCase):
    """`verify` never runs the suite, and one unguarded line is why it may not.

    The chain is real and it is sound. `validation.status` reads `ok` only when
    the report reached `notebooks.status: ok`, and a report reaches that only
    when every code cell carries an `execution_count` and no cell stored an
    error output. The report's own cell runs the target's suite and asserts the
    exit code is zero, so a red tree stores an `AssertionError` on that cell and
    the whole chain reports `incomplete`. An executed, error-free report
    therefore does mean the suite was green when it ran.

    All of which hangs on a single statement in a template that nothing held.
    Write `pytest.main(...)` bare, or print the code instead of asserting on
    it, and a failing suite executes cleanly, stores no error, and
    `validation.status` reads `ok` over a red tree — silently. That is the
    failure this change exists to kill, one link further down the same chain.

    Two locks, because the chain has two ends and either one alone leaves the
    other free to rot: the template must raise on a non-zero exit code, and the
    reader must refuse `ok` to a report that stored an error. They are
    complements in the way the asset register and import closure are — one holds
    what ships, the other holds what reads it.
    """

    NAME = "Example-Method"
    PACKAGE = "Example_Method"
    SEED = "7"
    NOTEBOOK = "verification.ipynb"

    def one_cell(self, function):
        """The single cell of the report that calls this function."""
        found = cells_calling(self.NOTEBOOK, function, self.NAME)
        self.assertEqual(
            len(found), 1,
            f"exactly one cell of {self.NOTEBOOK} calls `{function}`; "
            f"found {len(found)}")
        return found[0]

    # -- the template: a red suite has to raise -----------------------------

    def test_the_suite_cell_binds_its_exit_code_and_reads_it_back(self):
        """Half the link, read structurally, and only half — measured, not claimed.

        A bare `pytest.main(...)` is a complete, legal, silent cell: it runs the
        suite, returns the exit code and drops it on the floor. This holds the
        cell to binding that code and to reading the name back somewhere at its
        own scope, which a comment about the exit code cannot do.

        It stops there, and the stopping point was found by inversion rather
        than reasoned about: rewriting the assertion as `print(code)` passes
        this test, because printing is reading it back. Nothing structural
        separates a cell that reports the verdict from one that acts on it —
        `test_a_red_suite_raises_out_of_the_cell_that_ran_it` is what closes
        that, and this test is not a substitute for it.
        """
        _, _, tree = self.one_cell("pytest.main")

        bound = [target.id
                 for node in tree.body
                 if isinstance(node, ast.Assign)
                 and isinstance(node.value, ast.Call)
                 and ast.unparse(node.value.func).endswith("pytest.main")
                 for target in node.targets if isinstance(target, ast.Name)]
        self.assertEqual(len(bound), 1,
                         "the cell that runs the suite must bind the exit code "
                         "it is given, not discard it")
        readers = [statement for statement in tree.body
                   if not isinstance(statement, ast.Assign)
                   and any(isinstance(node, ast.Name) and node.id == bound[0]
                           for node in ast.walk(statement))]
        self.assertTrue(readers,
                        f"nothing in the cell reads `{bound[0]}` back, so the "
                        f"suite's verdict leaves no trace in the report")

    def suite_cell_program(self, code):
        """The suite cell as it ships, compiled to run with the exit code pytest
        would have handed it.

        Only the call is replaced, by node and not by text. Every other byte of
        the cell is the one the scaffold writes, so a rewrite that keeps the
        guard in some other spelling still passes and one that drops it does
        not: this asserts that the code is acted on, not how.
        """
        _, _, tree = self.one_cell("pytest.main")

        class Answer(ast.NodeTransformer):
            def visit_Call(self, node):
                self.generic_visit(node)
                if ast.unparse(node.func).endswith("pytest.main"):
                    return ast.Constant(value=code)
                return node

        prepared = ast.fix_missing_locations(Answer().visit(tree))
        return compile(prepared, f"<{self.NOTEBOOK}>", "exec")

    def test_a_green_suite_leaves_the_cell_silent(self):
        """The control the lock below is worth nothing without: a cell that
        raised whatever it was told would prove only that it raises."""
        exec(self.suite_cell_program(0), {})

    def test_a_red_suite_raises_out_of_the_cell_that_ran_it(self):
        """The finding itself. Nothing else about the cell changed, so a run
        that ends quietly here can only have ended quietly for this reason.

        The exception type is pinned rather than left open because it is the
        `ename` nbconvert stores on the cell, and it is the one the reader half
        below writes into its fixture: both locks have to be naming the same
        event or they are not two ends of one chain.
        """
        program = self.suite_cell_program(1)

        with self.assertRaises(AssertionError) as raised:
            exec(program, {})
        self.assertIn("1", str(raised.exception),
                      "the failure has to name the exit code it saw")

    # -- the reader: a stored error has to gate the verdict ------------------

    def box(self):
        """A doctrine-exact target `verify` will agree to read.

        `verify` refuses any target outside `<forge>/implementations`, and it
        refuses a tree that is not a repository, so the box lives there and is
        initialized before it is read.
        """
        box = FORGE / "implementations" / f"_suite_gate_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        doctrine_scaffold(self, self.NAME, self.SEED, box=box)
        for product in impl.PRODUCT_DIRS:
            if product != "Data":
                (box / self.NAME / product).mkdir(parents=True, exist_ok=True)
        return box

    def executed(self, box, errored):
        """The report as a run leaves it: every code cell counted, the seal on
        the cell that stamps it, and — when the suite was red — the error that
        run stored on the cell that ran it.

        The seal is written from `impl.source_digest` rather than by executing
        the notebook. That the two agree is exactly what
        `NotebookSealAgreementTests` holds them to; this class is about what
        happens to a report that ran and failed, and borrowing that agreement
        here would only measure it twice.
        """
        stamping, _, _ = self.one_cell("report_digest.stamp")
        suite, _, _ = self.one_cell("pytest.main")
        notebook = box / self.NAME / "Notebooks" / self.NOTEBOOK
        seal = f"{impl.DIGEST_MARKER} {impl.source_digest(box, self.PACKAGE)}"

        loaded = json.loads(notebook.read_text(encoding="utf-8"))
        for index, cell in enumerate(loaded["cells"]):
            if cell["cell_type"] != "code":
                continue
            cell["execution_count"] = 1
            outputs = []
            if index == stamping:
                outputs = [{"output_type": "stream", "name": "stdout",
                            "text": [seal + "\n"]}]
            if errored and index == suite:
                outputs = [{"output_type": "error", "ename": "AssertionError",
                            "evalue": "test suite failed (pytest exit code 1)",
                            "traceback": []}]
            cell["outputs"] = outputs
        notebook.write_text(json.dumps(loaded), encoding="utf-8")
        return suite

    def verify(self, box):
        proc = subprocess.run(
            [sys.executable, str(CLI), "verify", "--target", str(box),
             "--name", self.NAME], capture_output=True, text=True, cwd=FORGE)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout or "{}")["validation"]

    def test_a_report_that_ran_clean_reaches_ok(self):
        """The control, and it is not decoration: a verdict already reading
        `incomplete` for some unrelated reason would make the lock below
        vacuous, and this is the assertion that says it is not."""
        box = self.box()
        self.executed(box, errored=False)
        validation = self.verify(box)

        self.assertEqual(validation["notebooks"]["status"], "ok")
        self.assertEqual(validation["status"], "ok")

    def test_a_report_whose_suite_cell_errored_never_reaches_ok(self):
        """The same tree, one stored output later. It is the whole reason
        `verify` is allowed not to run the suite itself.

        `unstamped` is asserted empty on purpose: the seal is present and it
        matches, so nothing but the stored error can be holding the verdict
        back, and the day something else does this test says so.
        """
        box = self.box()
        suite = self.executed(box, errored=True)
        validation = self.verify(box)
        notebooks = validation["notebooks"]

        self.assertEqual([report["status"] for report in notebooks["reports"]],
                         ["errored"])
        self.assertEqual(validation["notebook"]["errors"],
                         [f"cell {suite}: AssertionError"])
        self.assertEqual(notebooks["unstamped"], [],
                         "the seal is there and it matches; the stored error is "
                         "the only thing gating this")
        self.assertNotEqual(notebooks["status"], "ok")
        self.assertNotEqual(validation["status"], "ok")


class KitSurfaceLanguageTests(unittest.TestCase):
    """The kit ships into a target and is read there. It has one language.

    Seventeen of the eighteen assets are written in English; one is not. A
    reader who opens the file the scaffold placed in their package finds a
    language the rest of their tree does not use, and the skill has no way to
    say which one it meant.

    The rule is about language, not about bytes. A "no non-ASCII" rule sounds
    stricter and is wrong here: measured over this kit it flags ten files and
    sixty-six lines — em-dashes in prose, `±` in a printed interval, `§` and `→`
    in comments — all of them legitimate English typography. The Spanish
    accented-letter class isolates exactly the one file, so that is the rule.
    """

    ACCENTED = re.compile(r"[áéíóúÁÉÍÓÚñÑüÜ¿¡]")

    def test_no_asset_is_written_in_another_language(self):
        offenders = {}
        for asset in kit_assets():
            lines = (SKILL_ROOT / asset).read_text(encoding="utf-8").splitlines()
            hits = [number for number, line in enumerate(lines, 1)
                    if self.ACCENTED.search(line)]
            if hits:
                offenders[asset] = hits
        self.assertEqual(
            {asset: len(hits) for asset, hits in offenders.items()}, {},
            "an asset the kit ships into a target is written in another language")

    def test_the_rule_reads_language_and_not_bytes(self):
        """Why this class does not simply ban non-ASCII.

        Stated as a test rather than as a comment, because the tempting
        "strengthening" is to widen the class until it catches everything, and
        that would turn every em-dash in the kit's own English into a defect.
        """
        english = "the interval is 0.5 ± 0.1 — see §3 → the reduction table"
        spanish = "el árbol que produjo el informe, según la verificación"
        self.assertIsNone(self.ACCENTED.search(english),
                          "English typography is not another language")
        self.assertIsNotNone(self.ACCENTED.search(spanish))

    def test_the_seal_still_computes_the_digest_it_computed_before(self):
        """The translation must not move a byte of behaviour.

        A live target already holds its own copy of this file and is not edited
        here (C2), so nothing pairs the two copies and a changed algorithm would
        surface as a stale report rather than as an error. The digest is
        therefore pinned to a literal, over a tree the file itself is not part
        of — `stamp` takes its arguments for exactly this.
        """
        import importlib.util

        box = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        package = box / "src" / "Example_Method"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(
            '"""Reference implementation of the Example-Method formulation."""\n'
            "\n__all__ = []\n", encoding="utf-8")
        (package / "kernel.py").write_text("VALUE = 1\n", encoding="utf-8")

        seal = KIT / "nb" / "report_digest.py"
        spec = importlib.util.spec_from_file_location("kit_report_digest", seal)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.MARKER, impl.DIGEST_MARKER)
        self.assertEqual(
            module.stamp(box, "Example_Method"),
            "SOURCES-SHA256 "
            "a949588e5ddc5b528213b6ac5474309798fa50119b01e7e68fb858e1634a77b5")

    def test_the_translation_touched_no_code(self):
        """Same claim from the other side: the code is byte-identical.

        Read as a tree with every docstring dropped, so an identifier, a default
        or an annotation that moved shows up here even if it happened to leave
        this one fixture's digest alone.

        Comments are outside what this can see, and are outside what it claims:
        the translation reaches every line of prose in the file, docstring or
        comment, and neither is behaviour. What is asserted is that no line the
        interpreter reads changed.

        The subject here is SEMANTIC equivalence to a fixed reference source,
        not agreement with one interpreter's own unparse spelling.
        `ast.unparse` is not stable across versions for every construct --
        measured: a tuple assignment target like `(a, b) = f()` unparses with
        parentheses under Python 3.9 and without them under 3.12, even though
        the AST (and the behaviour) is identical either way. Pinning the
        unparsed STRING would silently re-pin this test to whichever
        interpreter last recorded it, and the same break would return on the
        next interpreter upgrade. Both sides are therefore put through the
        SAME `ast.unparse` -- the reference text is parsed and re-unparsed
        too, not compared as a raw literal -- so the comparison is of two
        canonicalized forms under THIS run's own interpreter, not of one
        canonicalized form against a string frozen under a different one.
        """
        def _stripped_unparse(tree: ast.AST) -> str:
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                    continue
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    node.body.pop(0)
            return ast.unparse(ast.fix_missing_locations(tree))

        actual = _stripped_unparse(
            ast.parse((KIT / "nb" / "report_digest.py").read_text(encoding="utf-8")))
        reference_source = (
            "from __future__ import annotations\n"
            "import hashlib\n"
            "from pathlib import Path\n"
            "MARKER = 'SOURCES-SHA256'\n"
            "\n"
            "def source_digest(repository: Path, package: str) -> str:\n"
            "    digest = hashlib.sha256()\n"
            "    root = repository / 'src'\n"
            "    if root.is_dir():\n"
            "        for file in sorted(root.rglob('*.py')):\n"
            "            if '__pycache__' in file.parts:\n"
            "                continue\n"
            "            digest.update(str(file.relative_to(repository))"
            ".encode('utf-8'))\n"
            "            digest.update(file.read_bytes())\n"
            "    return digest.hexdigest()\n"
            "\n"
            "def _here() -> tuple[Path, str]:\n"
            "    package_dir = Path(__file__).resolve().parent\n"
            "    return (package_dir.parents[1], "
            "package_dir.name.removesuffix('_Benchmark'))\n"
            "\n"
            "def stamp(repository: Path | None=None, package: str | None=None) -> str:\n"
            "    if repository is None or package is None:\n"
            "        (found_repository, found_package) = _here()\n"
            "        repository = repository or found_repository\n"
            "        package = package or found_package\n"
            "    return f'{MARKER} {source_digest(repository, package)}'")
        expected = _stripped_unparse(ast.parse(reference_source))
        self.assertEqual(actual, expected)


class StageTwoInstructionsTests(unittest.TestCase):
    """The step that writes a module per object never named the template it
    writes it from.

    Step 9 has always told the agent what to produce — one module per object
    with `__provenance__`, plus its invariant tests — and the kit has always
    shipped `module.py`, `test_invariants.py` and `test_synthetic.py` for
    exactly that. Nothing joined the two. An agent reading step 9 had no way to
    learn a template existed, and the templates had no reader.

    The placement further down, for `benchmark.py`, `verdict.py` and
    `probe.ipynb`, was stated correctly but as a sentence. A sentence cannot be
    held to code, so it could be reworded into something false with nothing
    going red. Both sites now use one table shape, read one way — the same
    relation step 5 already carries for the scaffold.
    """

    STEP_NINE = {
        "src/<Package>/<module>.py": "assets/kit/src/module.py",
        "tests/test_invariants.py": "assets/kit/tests/test_invariants.py",
        "tests/test_synthetic.py": "assets/kit/tests/test_synthetic.py",
    }
    COPY_STEP = {
        "src/<Package>_Benchmark/benchmark.py": "assets/kit/nb/benchmark.py",
        "src/<Package>_Benchmark/verdict.py": "assets/kit/nb/verdict.py",
        "<Name>/Notebooks/probe.ipynb": "assets/kit/nb/probe.ipynb",
    }

    def tables(self):
        return markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), STAGE_TWO_HEADER)

    def test_both_stage_two_placements_are_stated_as_a_parseable_table(self):
        """Reachable red: step 9 carried no table at all, and the copy step
        carried a sentence."""
        self.assertEqual(
            len(self.tables()), 2,
            "SKILL.md states stage-2 placement in a table at neither site, or "
            "at only one of them")

    def test_the_stage_two_tables_name_every_template_they_place(self):
        """Both directions, so neither a template without a reader nor an
        instruction without a template survives."""
        placements = {}
        for table in self.tables():
            for row in table:
                self.assertEqual(len(row), 2, row)
                assets = declared_assets(row[1])
                self.assertEqual(len(assets), 1,
                                 f"stage-2 row names {len(assets)} assets: {row}")
                placements[row[0].strip("`")] = assets[0]
        self.assertEqual(placements, {**self.STEP_NINE, **self.COPY_STEP})

    def test_every_stage_two_template_exists_on_disk(self):
        """A pointer at a file the kit does not ship is worse than no pointer:
        the agent goes looking, finds nothing, and writes something else."""
        for table in self.tables():
            for row in table:
                for asset in declared_assets(row[1]):
                    self.assertTrue((SKILL_ROOT / asset).is_file(),
                                    f"{asset} is named by doctrine and absent")


class SubstitutionStageTests(unittest.TestCase):
    """Which tokens an agent can answer, and when.

    `test_smoke.py` is placed at scaffold time and carries `{{MODULE}}`, a token
    only step 9 can answer. Without a stage beside each token there is no way to
    read that off the registry, and the agent either substitutes a guess or
    reads the leftover `{{MODULE}}` as a defect of the scaffold. It is neither:
    it is the question the scaffold is posing, and `test_smoke.py` failing until
    step 9 answers it is the suite doing its job.

    Five tokens are answerable at scaffold time, seven at step 9, six when the
    probe's reduction is chosen.
    """

    STAGES = ("scaffold", "step 9", "probe")
    TOKEN_RE = TOKEN_RE  # the module-level pattern; call sites are unchanged

    def staged_tokens(self):
        tables = markdown_table_rows(USAGE_MD.read_text(encoding="utf-8"),
                                     "| Token | Substituted with | Answered at |")
        self.assertEqual(len(tables), 1,
                         "the usage reference's token registry declares no stage")
        return {row[0].strip("`"): row[2] for row in tables[0]}

    def test_every_documented_token_declares_the_stage_that_answers_it(self):
        """Reachable red: the registry was two columns, so nothing said when."""
        staged = self.staged_tokens()
        documented = set(self.TOKEN_RE.findall(USAGE_MD.read_text(encoding="utf-8")))
        self.assertEqual(set(staged), documented)
        self.assertEqual(sorted(set(staged.values())), sorted(self.STAGES))

    def test_the_scaffold_stage_is_exactly_what_the_scaffold_can_substitute(self):
        """The registry's `scaffold` rows and the tokens a scaffold-time
        substitution actually resolves must be the same five. This is the
        column the kit's own stage discriminator reads."""
        staged = self.staged_tokens()
        self.assertEqual(
            sorted(token for token, stage in staged.items() if stage == "scaffold"),
            sorted(SCAFFOLD_TOKENS))


class KitAssetRegisterTests(unittest.TestCase):
    """Nothing held the kit's contents to the instructions that place them.

    Every defect this change repairs is one shape: a file ships in the kit and
    no instruction says where it goes, or an instruction exists and no producer
    honours it. Each was invisible for the same reason — the kit's contents were
    an input to no check. `scaffold_gaps` asks only for what doctrine already
    names, so a file nobody wrote down is a file nobody misses, and `verify`
    reported `scaffoldGaps: []` over a tree that could not be imported.

    The repair is a relation, not another list. Every text file under `assets/**`
    must appear in exactly one of three registers, and the coverage is asserted
    in both directions:

    - **stage 1** — written at scaffold time; step 5's table, `scaffold_gaps`'s
      `wanted` and the worked example, which an existing test already forces to
      agree with each other.
    - **stage 2** — written later, when the work its tokens answer has happened;
      the two `Written into` tables.
    - **forge-side, never placed** — used by the forge itself and copied into no
      target. Named explicitly below rather than inferred from absence, because
      a register that treats "unmatched" as a category has no way to tell a
      deliberate exclusion from a forgotten row.

    The walk runs assets to registers, never registers to assets. That direction
    is deliberate: `wiring.py` is an instruction with no template — the agent
    writes it from the map, and there is nothing to copy — and the inverse walk
    would report that healthy case as a defect. Do not "fix" it.
    """

    FORGE_SIDE = {
        "assets/requirements-dev.txt":
            "installed into the target's virtualenv by `env`, never copied into it",
    }

    NAME = "Example-Method"
    PACKAGE = "Example_Method"

    def stage_one(self):
        """Destination → the asset it is written from, for the scaffold.

        Column 1 is a gap string rather than a path — two of them carry a
        computed tail — so it is read as `scaffold_gaps` reports it and compared
        by what it names.
        """
        tables = markdown_table_rows(SKILL_MD.read_text(encoding="utf-8"),
                                     STAGE_ONE_HEADER)
        self.assertEqual(len(tables), 1, "step 5 carries no gap table")
        return {row[0].strip("`"): declared_assets(row[1]) for row in tables[0]}

    def stage_two(self):
        tables = markdown_table_rows(SKILL_MD.read_text(encoding="utf-8"),
                                     STAGE_TWO_HEADER)
        self.assertEqual(len(tables), 2, "SKILL.md states stage 2 in %d tables"
                         % len(tables))
        return {row[0].strip("`"): declared_assets(row[1])
                for table in tables for row in table}

    def registered_assets(self):
        found = {}
        for register, entries in (("stage 1", self.stage_one()),
                                  ("stage 2", self.stage_two())):
            for destination, assets in entries.items():
                for asset in assets:
                    found.setdefault(asset, []).append(f"{register} → {destination}")
        for asset in self.FORGE_SIDE:
            found.setdefault(asset, []).append("forge-side, never placed")
        return found

    def test_every_asset_appears_in_exactly_one_register(self):
        """Both directions at once. An asset in no register is a file that ships
        with no instruction — F-A's and F-E's shape. An asset in two is an
        instruction contradicting another.

        Reachable red both ways: adding a file to `assets/kit/` fails this until
        it is registered, and so does deleting any row that places one.
        """
        registered = self.registered_assets()
        assets = set(kit_assets())

        unregistered = sorted(assets - set(registered))
        self.assertEqual(unregistered, [],
                         "these ship in the kit and no instruction places them")

        duplicated = {asset: where for asset, where in registered.items()
                      if len(where) > 1}
        self.assertEqual(duplicated, {}, "these are placed twice")

        phantom = sorted(set(registered) - assets)
        self.assertEqual(phantom, [],
                         "these are placed by an instruction and do not exist")

    def test_the_stage_one_destinations_are_what_the_gap_checker_requires(self):
        """The register and the checker are the same set or the register is
        decoration. `ScaffoldInstructionsAgreementTests` already ties step 5's
        column 1 to `wanted`; this ties it to the assets as well, so a row
        cannot be moved between registers without moving the gap."""
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)

        def named(gap):
            for prefix in (".gitignore", "pyproject.toml"):
                if gap.startswith(prefix):
                    return prefix
            return gap

        documented = {named(gap.replace("<Name>", self.NAME)
                               .replace("<Package>", self.PACKAGE))
                      for gap in self.stage_one()}
        self.assertEqual(documented,
                         {named(gap) for gap in impl.scaffold_gaps(empty, self.NAME)})

    def test_a_stage_one_template_parses_once_the_scaffold_has_substituted_it(self):
        """The stage discriminator, and it runs one way only.

        A template that does not parse after the five scaffold-time tokens are
        answered has no business being written at scaffold time — its remaining
        tokens are answers to work nobody has done. Such a template is rejected
        from stage 1, never exempted from the check: teaching the checker to
        tolerate a file it cannot parse is worse than the file.

        The converse does not hold and is not asserted. `benchmark.py` carries no
        token at all and parses perfectly, and is still stage 2, because when a
        file is written is a question about the work, not about its syntax.
        """
        for destination, assets in sorted(self.stage_one().items()):
            for asset in assets:
                text = scaffold_substitute(
                    (SKILL_ROOT / asset).read_text(encoding="utf-8"),
                    self.NAME, "7", "r01.md")
                sources = []
                if asset.endswith(".ipynb"):
                    sources = ["".join(cell["source"])
                               for cell in json.loads(text)["cells"]
                               if cell["cell_type"] == "code"]
                elif asset.endswith(".py"):
                    sources = [text]
                for source in sources:
                    try:
                        ast.parse(source)
                    except SyntaxError as exc:
                        self.fail(
                            f"{asset} is registered stage 1 for {destination} and "
                            f"does not parse once the scaffold has substituted it: "
                            f"{exc.msg} at line {exc.lineno}. Its remaining tokens "
                            "answer work that has not happened, so it belongs in "
                            "stage 2 — the check is not what gives way.")

    def test_every_declared_destination_is_a_legal_place_for_it(self):
        """`SOURCE_ROOTS` is the boundary `strayModules` reports against, and it
        is not widened here. A notebook is the one thing that legally lives
        outside it — `.ipynb` is not `.py`, so the stray check never applies to
        it — and `<Name>/Notebooks/` is where the layout puts one."""
        for register in (self.stage_one(), self.stage_two()):
            for destination in register:
                path = (destination.replace("<Name>", self.NAME)
                                   .replace("<Package>", self.PACKAGE))
                if path.startswith((".gitignore", "pyproject.toml")):
                    continue
                with self.subTest(destination=destination):
                    if path.endswith(".ipynb"):
                        self.assertTrue(path.startswith(f"{self.NAME}/Notebooks/"))
                    else:
                        self.assertTrue(path.startswith(impl.SOURCE_ROOTS),
                                        f"{path} is a stray module by SOURCE_ROOTS")

    def test_the_forge_side_register_is_explicit_and_earns_its_place(self):
        """Named, and provably used by the forge. A category nobody has to
        justify becomes the place unregistered files go to be forgotten."""
        lines = CLI.read_text(encoding="utf-8").splitlines()
        for asset, reason in self.FORGE_SIDE.items():
            self.assertTrue((SKILL_ROOT / asset).is_file(), asset)
            self.assertTrue(reason.strip(), asset)
            # The bare filename is not evidence, and an inversion caught it
            # passing on one: `requirements-dev.txt` also occurs in the list of
            # dependency manifests the planner classifies, which says nothing
            # about who installs this one. The reference has to resolve it under
            # `assets/`, which only the forge-side use does.
            self.assertTrue(
                [line for line in lines
                 if Path(asset).name in line and "assets" in line],
                f"{asset} is registered as forge-side and no line of the CLI "
                "resolves it under `assets/`")

    def test_an_instruction_that_ships_no_template_is_not_a_defect(self):
        """`wiring.py` is written from the object → module map, not copied, so
        it has no asset and must not be reported as a missing one. Pinned so the
        walk's direction survives somebody's tidy-up."""
        self.assertIn("wiring.py", SKILL_MD.read_text(encoding="utf-8"))
        self.assertEqual(
            [asset for asset in kit_assets() if asset.endswith("wiring.py")], [])
        self.assertNotIn("assets/kit/nb/wiring.py", self.registered_assets())

    def test_a_generated_cache_is_never_granted_a_destination(self):
        """The register's domain, proven rather than declared.

        Running pytest inside `assets/kit/nb/` leaves `.pytest_cache/` and
        `__pycache__/` there. Measured: all six such files are untracked, so
        nothing is deleted here — but without a stated domain they read as
        assets nobody placed and demand rows for build output.

        Asserting that against this checkout's own caches would be circular: the
        walk would be filtered by the same constant the assertion reads. So the
        rule is exercised on a tree built to contain exactly one real asset and
        one artifact of each kind.
        """
        box = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        for relative in ("assets/kit/tests/real_asset.py",
                         "assets/kit/nb/__pycache__/generated.cpython-311.pyc",
                         "assets/kit/nb/.pytest_cache/v/cache/nodeids",
                         "assets/kit/nb/.ipynb_checkpoints/notebook-checkpoint.ipynb"):
            path = box / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("generated\n", encoding="utf-8")

        self.assertEqual(kit_assets(box), ["assets/kit/tests/real_asset.py"])
        self.assertEqual(
            [asset for asset in self.registered_assets()
             if any(part in CACHES for part in Path(asset).parts)], [],
            "a generated artifact was granted a destination")


class MaterializeWritesStageOneTests(unittest.TestCase):
    """Three of the files a fresh scaffold contained could not be parsed.

    `materialize.py` copied `assets/kit/src/module.py`,
    `assets/kit/tests/test_invariants.py` and `assets/kit/tests/test_synthetic.py`
    into the target and substituted only `{{PKG}}` and `{{SEED}}` over them.
    Their remaining tokens — `{{FUNCTION_NAME}}`, `{{INVARIANT_ID}}`,
    `{{EXPECTATION}}` — are not names; they are placeholders sitting where
    identifiers have to be, so the three files did not survive `ast.parse` and
    the tree could not be collected.

    Those tokens are answers to the object map step 8 approves, and nothing
    could have answered them at scaffold time. So the repair is not to write
    them more carefully — it is not to write them yet. Writing them with the
    tokens intact and exempting them from the parse checks teaches the checker
    to tolerate a file that cannot be imported; substituting dummy identifiers
    is worse still, because the result parses, collects and *passes* while
    asserting nothing.
    """

    NAME = "Example-Method"
    PACKAGE = "Example_Method"
    SEED = "7"

    STAGE_TWO = ("src/Example_Method/module.py",
                 "tests/test_invariants.py",
                 "tests/test_synthetic.py")

    def materialized(self):
        box = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/materialize.py"),
             str(box), self.NAME, self.SEED], check=True, capture_output=True)
        return box

    @staticmethod
    def files(box):
        return sorted(str(path.relative_to(box)) for path in box.rglob("*")
                      if path.is_file())

    def test_it_writes_the_stage_one_tree_and_nothing_besides(self):
        """The producer's tree and the doctrine's tree, compared directly.

        Nothing compared them before: the fixture that called itself
        doctrine-faithful was built by this producer, so the superset it wrote
        was measured against itself and agreed every time.
        """
        box = self.materialized()

        self.assertEqual(self.files(box),
                         self.files(doctrine_scaffold(self, self.NAME, self.SEED)))

    def test_it_leaves_no_scaffold_gap_behind(self):
        """`.gitignore` was the one gap it never filled, which is why a fixture
        had to hand-patch it afterwards — and a hand-patch beside a producer is
        how the two trees drifted without either being wrong on its own."""
        box = self.materialized()

        self.assertEqual(impl.scaffold_gaps(box, self.NAME), [])

    def test_no_stage_two_template_is_written_before_its_question_is_asked(self):
        box = self.materialized()

        self.assertEqual(
            [path for path in self.STAGE_TWO if (box / path).exists()], [],
            "a template whose tokens answer step 8's map was written at step 5")

    def test_every_python_file_it_writes_parses(self):
        """The behaviour, stated without naming the three: any file the
        materializer writes has to survive `ast.parse`, whichever file it is."""
        box = self.materialized()
        broken = {}
        for path in sorted(box.rglob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                broken[str(path.relative_to(box))] = f"{exc.msg} at line {exc.lineno}"

        self.assertEqual(broken, {})

    @staticmethod
    def declared_pythonpath(pyproject):
        """The one `pythonpath` a pyproject declares, read as the list it is."""
        line = next(line for line in pyproject.read_text(encoding="utf-8").splitlines()
                    if line.strip().startswith("pythonpath"))
        return ast.literal_eval(line.split("=", 1)[1].strip())

    def test_the_pythonpath_it_writes_is_the_one_the_template_declares(self):
        """Two spellings of the same anchor, and only one of them is documented.

        `assets/pyproject.template.toml` and step 5 both say `["src"]`. The
        materializer wrote `["src", "tests"]`, and pytest's prepend import mode
        hid the difference: it puts a test file's own directory on `sys.path`
        already, so the flat `from sweep import ...` style resolves either way
        and neither spelling ever announced itself.
        """
        box = self.materialized()

        self.assertEqual(self.declared_pythonpath(box / "pyproject.toml"),
                         self.declared_pythonpath(PYPROJECT_TEMPLATE))

    def test_the_flat_test_imports_still_resolve_without_tests_on_the_path(self):
        """Why the doctrine's spelling is the one to keep, run rather than argued.

        Listing `tests` would make the forge depend on an explicit path where it
        already depends on a pytest behaviour that is load-bearing everywhere
        else: prepend import mode puts a test file's own directory on
        `sys.path`, and `tests/` carries no `__init__.py` for it to prefer the
        rootdir over.

        What this locks is exactly that behaviour, and no more. Measured: an
        empty `pythonpath` collects too, because nothing under `tests/` imports
        the package until run time. The entry `tests/__init__.py` is what breaks
        it — prepend mode then inserts the rootdir instead, and `findings` and
        `admissibility` stop resolving, which is #807's failure returning by
        another route. The value itself is held by the agreement above.

        Collection is the bar: `test_smoke.py` must still fail at run time,
        because `MODULES` names a module step 9 has not written.
        """
        box = self.materialized()
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=str(box), capture_output=True, text=True)

        self.assertNotIn("ModuleNotFoundError", proc.stdout + proc.stderr,
                         proc.stdout[-3000:])
        self.assertNotIn("error", proc.stdout.splitlines()[-1].lower(),
                         proc.stdout[-3000:])

    def test_the_package_exports_nothing_it_does_not_define(self):
        """`__all__` was read off `assets/kit/src/*.py` — the stage-2 template
        directory — so the package advertised a `module` name that only existed
        because the unparseable template had been copied in beside it."""
        box = self.materialized()
        source = (box / "src" / self.PACKAGE / "__init__.py").read_text(encoding="utf-8")
        exported = next(
            ast.literal_eval(node.value) for node in ast.parse(source).body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets))

        self.assertEqual(exported, [],
                         "step 9 has written no module, so the package exports none")


class UnparsableTestVisibilityTests(unittest.TestCase):
    """A test file that could not be parsed was indistinguishable from one that
    declared no tests.

    `test_function_names` swallows `SyntaxError` and moves to the next file, so
    a `tests/` directory holding nothing but a broken file returns the same
    empty set as one holding nothing at all. `read_provenance` already refuses
    that silence — it reports an unparseable module as `__error__` — and this
    collector was the last reader that did not.

    The field is additive; the gate is not. A target carrying a file under
    `tests/` that cannot be parsed cannot be collected, and `structure.status`
    saying `ok` beside it is the same shape as a headline reading `ok` beside a
    benchmark it had just called `undeclared`.
    """

    NAME = "Example-Method"

    def box(self):
        box = FORGE / "implementations" / f"_unparsable_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        doctrine_scaffold(self, self.NAME, box=box)
        for product in impl.PRODUCT_DIRS:
            if product != "Data":
                (box / self.NAME / product).mkdir(parents=True, exist_ok=True)
        return box

    def verify(self, box):
        proc = subprocess.run(
            [sys.executable, str(CLI), "verify", "--target", str(box),
             "--name", self.NAME], capture_output=True, text=True, cwd=FORGE)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout or "{}")["structure"]

    def test_a_complete_scaffold_names_no_unparsable_test(self):
        """The control the gate is worth nothing without: every file a
        doctrine-faithful scaffold places under `tests/` parses today."""
        structure = self.verify(self.box())

        self.assertEqual(structure["unparsableTests"], [])
        self.assertEqual(structure["status"], "ok")

    def test_a_test_file_that_cannot_be_parsed_is_named_and_gates_the_status(self):
        """The same tree, one file later. Nothing else about it changed, so the
        status can only have moved for this reason."""
        box = self.box()
        (box / "tests" / "sweep.py").write_text(
            "def collapse({{FUNCTION_NAME}}):\n    return None\n", encoding="utf-8")
        structure = self.verify(box)

        self.assertEqual(structure["unparsableTests"], ["tests/sweep.py"])
        self.assertNotEqual(structure["status"], "ok")

    def test_a_broken_file_is_no_longer_read_as_an_empty_one(self):
        """The mechanism, isolated from `verify`: the collector returns the same
        empty set either way, and the sibling is what tells the two apart."""
        broken = Path(tempfile.mkdtemp()) / "tests"
        self.addCleanup(shutil.rmtree, broken.parent, ignore_errors=True)
        broken.mkdir()
        (broken / "test_broken.py").write_text("def f(:\n", encoding="utf-8")
        silent = Path(tempfile.mkdtemp()) / "tests"
        self.addCleanup(shutil.rmtree, silent.parent, ignore_errors=True)
        silent.mkdir()
        (silent / "test_silent.py").write_text("VALUE = 1\n", encoding="utf-8")

        self.assertEqual(impl.test_function_names(broken),
                         impl.test_function_names(silent),
                         "the collector cannot tell them apart, and never could")
        self.assertEqual(impl.unparsable_tests(broken), ["tests/test_broken.py"])
        self.assertEqual(impl.unparsable_tests(silent), [])

    def test_the_collector_keeps_its_contract_and_the_reader_is_a_sibling(self):
        """The wrapper idiom, not a rewrite: `test_function_names` keeps its
        exact signature, its set return and both of its callers, because the
        invariant pairing that reads it must not move for this."""
        signature = inspect.signature(impl.test_function_names)

        self.assertEqual(list(signature.parameters), ["tests_dir"])
        self.assertIsNot(impl.unparsable_tests, impl.test_function_names)
        with tempfile.TemporaryDirectory() as raw:
            (Path(raw) / "test_one.py").write_text(
                "def test_alpha():\n    pass\n", encoding="utf-8")
            self.assertEqual(impl.test_function_names(Path(raw)), {"test_alpha"})

    def test_a_directory_that_does_not_exist_names_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(impl.unparsable_tests(Path(raw) / "absent"), [])


class HarnessPlacementTests(unittest.TestCase):
    """Exactly one directory holds the probe harness, and it is `src/<Package>_Benchmark/`.

    Doctrine has always said so: the scaffold step sends `benchmark.py` and
    `verdict.py` into the Benchmark package, `wiring.py` is written beside them,
    and the harness's own `environment()` states its address in prose before it
    derives the repository from it. Two consumers disagreed and looked under
    `<Name>/Notebooks/` instead — `cmd_probe`, which therefore reported
    `harness: null` on a target that had followed the instructions exactly, and
    the kit's own probe notebook, which invoked a file beside itself.

    The contradiction stayed silent because `parents[2]` happens to reach the
    repository from either depth. Nothing else does: Python beside a notebook is
    a stray module by `SOURCE_ROOTS`, `wiring.py` cannot live there for the same
    reason, and both `declared_dimension_names` and `benchmark_reach` look only
    under `src/<Package>_Benchmark/`.
    """

    SKILL = FORGE / ".claude/skills/proposal-implementation"
    KIT = SKILL / "assets/kit"
    NAME = "Example-Method"
    PACKAGE = "Example_Method"

    def substituted(self, path):
        return path.replace("<Name>", self.NAME).replace("<Package>", self.PACKAGE)

    def copy_step(self):
        """The stage-2 placements the copy step performs, read from its table.

        Two tables state stage 2. Step 9's writes a module per object from
        `assets/kit/src/` and `assets/kit/tests/`, and no fixture can perform it
        — the object map it answers does not exist. The copy step's is the other
        one, and every asset it names is staged under `assets/kit/nb/`, which is
        the property this reads it by. A third table, or a copy step that
        started staging from somewhere else, turns this red rather than silently
        placing the wrong three files.
        """
        staged = []
        for table in markdown_table_rows(SKILL_MD.read_text(encoding="utf-8"),
                                         STAGE_TWO_HEADER):
            assets = [declared_assets(row[1]) for row in table]
            if assets and all(len(a) == 1 and a[0].startswith("assets/kit/nb/")
                              for a in assets):
                staged.append({row[0].strip("`"): declared_assets(row[1])[0]
                               for row in table})
        self.assertEqual(len(staged), 1,
                         "%d stage-2 tables stage out of `assets/kit/nb/`" % len(staged))
        return staged[0]

    def expected_files(self):
        """Every path a doctrine-faithful tree holds, computed rather than listed.

        Both halves are read from doctrine: the gaps `scaffold_gaps` reports for
        a repository holding none of it, and the copy step's own table. Nothing
        here is a literal, which is the point — the expected set used to be
        whatever the producer happened to write, so a producer writing one file
        more than doctrine names agreed with itself every time.
        """
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        return sorted(
            [gap_path(gap) for gap in impl.scaffold_gaps(empty, self.NAME)]
            + [self.substituted(destination) for destination in self.copy_step()])

    @staticmethod
    def present_files(box):
        """What the tree actually holds, minus what git keeps for itself."""
        return sorted(
            str(path.relative_to(box)) for path in box.rglob("*")
            if path.is_file() and ".git" not in path.parts
            and "__pycache__" not in path.parts)

    def scaffold(self, suffix):
        """A target holding exactly the tree doctrine describes, and nothing more.

        The fixture used to call itself doctrine-faithful while shelling
        `materialize.py` for its contents, and nothing compared the two. So the
        producer's superset — three files it could not parse — was the standard
        the fixture measured against, `scaffoldGaps: []` was satisfied by a tree
        larger than the one doctrine names, and each broken path kept the other
        out of sight. The tree is still produced by the materializer, because
        that is the path under test; what changed is that it is now checked
        against a set computed from `scaffold_gaps` and the copy step's table.

        The placement under test follows: the harness modules into
        `src/<Package>_Benchmark/` and the notebook into `<Name>/Notebooks/`,
        both read from the copy step rather than named here.
        """
        box = FORGE / "implementations" / f"_harness_placement_{suffix}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        subprocess.run(
            [sys.executable, str(self.SKILL / "scripts/materialize.py"),
             str(box), self.NAME, "7"], check=True, capture_output=True)
        for product in impl.PRODUCT_DIRS:
            if product != "Data":
                (box / self.NAME / product).mkdir(parents=True, exist_ok=True)
        for destination, asset in self.copy_step().items():
            placed = box / self.substituted(destination)
            placed.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.SKILL / asset, placed)

        self.assertEqual(
            self.present_files(box), self.expected_files(),
            "the fixture is not the doctrine's tree, so nothing it asserts is "
            "about the doctrine's tree")
        return box

    def run_cli(self, command, box):
        proc = subprocess.run(
            [sys.executable, str(CLI), command, "--target", str(box),
             "--name", self.NAME],
            capture_output=True, text=True, cwd=FORGE)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout or "{}")

    def declare_entry(self, box, module_name="benchmark", function_name="run"):
        """Fill in the scaffold's own `entry` block, as the agent would once
        the harness is written — the seventh block, prefilled empty by the
        kit and never invented by this fixture."""
        path = box / "src" / f"{self.PACKAGE}_Benchmark" / "__init__.py"
        source = path.read_text(encoding="utf-8")
        updated = source.replace(
            '"entry": {"module": "", "function": ""},',
            '"entry": {"module": "%s_Benchmark.%s", "function": "%s"},'
            % (self.PACKAGE, module_name, function_name))
        self.assertNotEqual(updated, source,
                            "the scaffold's `entry` block was not found to declare")
        path.write_text(updated, encoding="utf-8")

    def test_a_doctrine_faithful_scaffold_reports_no_stray_modules(self):
        """The reason the harness cannot move to the notebooks instead: a `.py`
        outside `SOURCE_ROOTS` is a stray module, and admitting `Notebooks/`
        would readmit every stray the check exists to catch."""
        structure = self.run_cli("verify", self.scaffold("structure"))["structure"]

        self.assertEqual(structure["strayModules"], [])
        self.assertEqual(structure["scaffoldGaps"], [])
        self.assertEqual(structure["status"], "ok")

    def test_probe_finds_the_harness_doctrine_told_the_agent_to_write(self):
        """Once the declaration names the harness, `probe` finds it at the
        place doctrine put it. The reader's cheapest wrong conclusion used
        to be that the file was in the wrong place; the instructions were
        right, and now the declaration is what says so."""
        box = self.scaffold("probe")
        self.declare_entry(box)
        probe = self.run_cli("probe", box)

        self.assertEqual(probe["harnessStatus"]["status"], "present")
        self.assertEqual(probe["harnessStatus"]["path"],
                         f"src/{self.PACKAGE}_Benchmark/{impl.BENCHMARK_MODULE}")
        self.assertEqual(probe["notebook"],
                         f"{self.NAME}/Notebooks/{impl.PROBE_NOTEBOOK}")

    def test_probe_reports_undeclared_on_a_fresh_scaffold(self):
        """A fresh scaffold's `entry` block is blank. This must not be read
        as "no harness file exists" — the file doctrine says to write is
        sitting right there, unreachable to the resolver until the
        declaration names it."""
        probe = self.run_cli("probe", self.scaffold("fresh"))
        self.assertEqual(probe["harnessStatus"]["status"], "undeclared")

    def test_probe_names_the_declared_module_and_where_it_looked_when_missing(self):
        """One target has no harness file under the name it declared; this is
        that target, told apart from absence by the declaration alone —
        `benchmark.py` sits on disk, but nothing is declared to call it
        `harness`, so the declared name is what is missing, not the file."""
        box = self.scaffold("declared_missing")
        self.declare_entry(box, module_name="harness")
        probe = self.run_cli("probe", box)

        self.assertEqual(probe["harnessStatus"]["status"], "declaredMissing")
        self.assertEqual(probe["harnessStatus"]["declaredModule"],
                         f"{self.PACKAGE}_Benchmark.harness")
        self.assertEqual(probe["harnessStatus"]["searchedPath"],
                         f"src/{self.PACKAGE}_Benchmark/harness.py")

    def test_the_harness_becoming_visible_does_not_turn_the_distribution_red(self):
        """New, and worth pinning. Placing the harness where doctrine says makes
        the kit's own `DIMENSIONS` reachable to `declared_dimension_names` for the
        first time, so a fresh scaffold now has a dimension universe where it had
        none. That must inform the reading, never fail it: the declaration has
        answered nothing yet, so there is nothing for a universe to contradict."""
        verify = self.run_cli("verify", self.scaffold("distribution"))
        distribution = verify["distribution"]

        self.assertEqual(distribution["status"], "undeclared")
        self.assertEqual(distribution["unpartitioned"], [])
        self.assertEqual(distribution["notADimension"], [])
        self.assertNotIn("could not be checked", distribution.get("note") or "",
                         "the universe is readable now, so nothing may say it is not")
        self.assertEqual(
            distribution["dimensionSource"],
            sorted(self.declared_kit_dimensions()),
            "the kit's own harness declares the universe once it is reachable")

    def test_the_harness_reaches_no_method_module_it_does_not_call(self):
        """The other half of the new visibility: `benchmark_reach` now walks the
        harness too. A fresh scaffold declares no arm, so nothing is claimed and
        nothing may be reported unreached."""
        probe = self.run_cli("probe", self.scaffold("reach"))

        self.assertEqual(probe["unreachedModules"], [])

    def declared_kit_dimensions(self):
        source = (self.KIT / "nb" / impl.BENCHMARK_MODULE).read_text(encoding="utf-8")
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "DIMENSIONS" for t in node.targets
            ):
                return [key.value for key in node.value.keys]
        self.fail("the kit's harness declares no DIMENSIONS")

    # -- the notebook half -------------------------------------------------

    def harness_cell(self):
        """The notebook cell that invokes the harness, parsed rather than matched.

        A substring assertion over notebook JSON passes on a path that appears in
        a comment. The command is built by an expression, so the expression is
        what gets read.
        """
        notebook = json.loads(
            (self.KIT / "nb" / impl.PROBE_NOTEBOOK).read_text(encoding="utf-8"))
        cells = [c for c in notebook["cells"] if c["cell_type"] == "code"
                 and "subprocess.run" in "".join(c["source"])]
        self.assertEqual(len(cells), 1, "exactly one cell invokes the harness")
        return ast.parse("".join(cells[0]["source"]))

    @staticmethod
    def path_chain(node):
        """`base / "a" / "b"` read as its base and its literal segments."""
        segments = []
        while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            segments.append(node.right.value if isinstance(node.right, ast.Constant)
                            else ast.unparse(node.right))
            node = node.left
        return ast.unparse(node), list(reversed(segments))

    def assigned(self, tree, target):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == target for t in node.targets
            ):
                return node.value
        self.fail(f"the harness cell binds no {target}")

    def test_the_notebook_builds_the_harness_path_under_the_source_root(self):
        """It composed `HERE / "benchmark.py"`, and `HERE` is the notebook's own
        directory: the notebook shipped in the kit could only ever have run a
        harness in the one place doctrine forbids."""
        base, segments = self.path_chain(self.assigned(self.harness_cell(), "HARNESS"))

        self.assertEqual(base, "ROOT", "the harness is addressed from the repository")
        self.assertEqual(segments, ["src", "{{PKG}}_Benchmark", impl.BENCHMARK_MODULE])

    def test_the_notebook_runs_the_harness_from_the_harness_own_directory(self):
        """`benchmark.py` imports `verdict` and `wiring` flat, which resolves
        because a script invoked by path puts its own directory on `sys.path` and
        all three are siblings there. Every path it is handed is absolute, so the
        working directory is free to be the one the imports need."""
        tree = self.harness_cell()
        call = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and ast.unparse(node.func) == "subprocess.run")
        keywords = {kw.arg: ast.unparse(kw.value) for kw in call.keywords}
        argv = [ast.unparse(element) for element in call.args[0].elts]

        self.assertEqual(argv[0], "sys.executable")
        self.assertEqual(argv[1], "str(HARNESS)")
        self.assertEqual(keywords["cwd"], "str(HARNESS.parent)")

    def test_the_toy_targets_left_nothing_behind(self):
        self.scaffold("cleanup")
        self.doCleanups()
        self.assertEqual(
            list((FORGE / "implementations").glob("_harness_placement_*")), [])


class FidelityUndeclaredTests(unittest.TestCase):
    """The headline read `ok` beside a benchmark it had just called `undeclared`.

    `fidelity.status` was computed from `stale or missing_provenance or untested
    or unreached`, and `unreached` is only ever populated inside the `declared`
    branch. So a target with real provenance on every module, every invariant
    tested and a `__benchmark__` still at the kit's six empty blocks satisfied
    none of the four and reported `ok` — with `fidelity.benchmark.status:
    "undeclared"` sitting directly underneath it.

    A reader who acts on the headline stops there. The fourth value is the word
    the nested block already uses, so the two say the same thing.
    """

    KIT_DECLARATION = (FORGE / ".claude/skills/proposal-implementation"
                       / "assets/kit/src_benchmark/__init__.py")

    DECLARED = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {'floor': {'sections': ['3']}},\n"
        "}\n"
    )

    MODULE = _module("r01.md", ["3"], ["11"])

    # The declared control needs an arm that actually calls its own mathematics,
    # or `unreachedModules` fires and the control measures the wrong thing.
    WIRING = "from Method.estimator import estimate\n"

    def verify(self, *, suffix, declaration, module=None, revision="r01.md",
               bench_package=True, wiring=None):
        """A target that is clean on every arm of the headline except the one
        under test: real provenance, and the one invariant it declares tested."""
        box = FORGE / "implementations" / f"_fidelity_undeclared_{suffix}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src/Method").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "src/Method/estimator.py").write_text(
            module if module is not None else self.MODULE, encoding="utf-8")
        (box / "tests/test_invariants.py").write_text(
            "def test_bounded():\n    pass\n", encoding="utf-8")
        if bench_package:
            (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "src/Method_Benchmark/__init__.py").write_text(
                declaration, encoding="utf-8")
            if wiring is not None:
                (box / "src/Method_Benchmark/wiring.py").write_text(
                    wiring, encoding="utf-8")

        empty_proposals = Path(tempfile.mkdtemp(prefix="pp-fidelity-proposals-"))
        self.addCleanup(shutil.rmtree, empty_proposals, ignore_errors=True)
        argv = [sys.executable, str(CLI), "verify", "--target", str(box),
                "--name", "Method"]
        if revision:
            argv += ["--revision", revision]
        return subprocess.run(
            argv, capture_output=True, text=True, cwd=FORGE,
            env={**os.environ, "IMPLEMENTATION_PROPOSALS": str(empty_proposals)})

    def fidelity(self, **kwargs):
        proc = self.verify(**kwargs)
        self.assertNotIn("Traceback", proc.stderr)
        return json.loads(proc.stdout or "{}")["fidelity"]

    def test_an_otherwise_clean_undeclared_target_does_not_read_green(self):
        """The four arms of the old condition are all clean here, and that was
        the whole test: nothing was stale, nothing lacked provenance, no
        invariant was untested, and `unreached` cannot be non-empty for a
        declaration that never named an arm."""
        fidelity = self.fidelity(
            suffix="undeclared",
            declaration=self.KIT_DECLARATION.read_text(encoding="utf-8"))

        self.assertEqual(fidelity["benchmark"]["status"], "undeclared")
        self.assertNotEqual(fidelity["status"], "ok")
        self.assertEqual(fidelity["status"], "undeclared")
        self.assertEqual(fidelity["staleModules"], [])
        self.assertEqual(fidelity["missingProvenance"], [])
        self.assertEqual(fidelity["invariantsWithoutTest"], [])

    def test_the_process_exit_status_is_untouched(self):
        """`verify` reports; only a refusal exits non-zero. A new reported value
        that changed the exit status would break every caller that reads the
        status instead of the JSON, and no requirement asks for it."""
        proc = self.verify(
            suffix="exit",
            declaration=self.KIT_DECLARATION.read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["fidelity"]["status"], "undeclared")

    def test_a_defect_still_outranks_a_state(self):
        """`drift` stays above `undeclared` for the same reason `unfaithful`
        already stands above `stale` one block down: a stale module is a defect
        in something that exists, an undeclared benchmark is the absence of a
        declaration. The defect is what a reader has to act on."""
        fidelity = self.fidelity(
            suffix="drift",
            declaration=self.KIT_DECLARATION.read_text(encoding="utf-8"),
            module=_module("r00.md", ["3"], ["11"]))

        self.assertEqual(fidelity["benchmark"]["status"], "undeclared")
        self.assertEqual(fidelity["staleModules"], ["src/Method/estimator.py"])
        self.assertEqual(fidelity["status"], "drift")

    def test_a_revision_nobody_could_establish_still_ranks_first(self):
        """`unknown` means nothing was measured at all, so it cannot be
        displaced by a statement about what was measured."""
        fidelity = self.fidelity(
            suffix="unknown",
            declaration=self.KIT_DECLARATION.read_text(encoding="utf-8"),
            module=_module(None, ["3"], ["11"]), revision=None)

        self.assertEqual(fidelity["latestRevision"], None)
        self.assertEqual(fidelity["status"], "unknown")

    def test_an_absent_benchmark_package_is_deliberately_not_folded_in(self):
        """A target with no Benchmark package has nothing to be unfaithful to,
        and `structure.scaffoldGaps` already names the file it is missing.
        Reporting it twice, in a field about fidelity, would teach the reader
        that `undeclared` means two different things."""
        proc = self.verify(suffix="absent", declaration="", bench_package=False)
        result = json.loads(proc.stdout or "{}")

        self.assertEqual(result["fidelity"]["benchmark"]["status"], "absent")
        self.assertEqual(result["fidelity"]["status"], "ok")
        self.assertIn("src/Method_Benchmark/__init__.py",
                      result["structure"]["scaffoldGaps"])

    def test_a_declared_benchmark_still_reports_ok(self):
        """The control pole. Without it a ladder that always answered
        `undeclared` would pass every assertion above."""
        fidelity = self.fidelity(suffix="declared", declaration=self.DECLARED,
                                 wiring=self.WIRING)

        self.assertEqual(fidelity["benchmark"]["status"], "ok")
        self.assertEqual(fidelity["status"], "ok")

    def test_the_toy_targets_left_nothing_behind(self):
        self.verify(suffix="cleanup", declaration=self.DECLARED)
        self.doCleanups()
        self.assertEqual(
            list((FORGE / "implementations").glob("_fidelity_undeclared_*")), [])


class RevisionDiscoveryMarkerTests(unittest.TestCase):
    """Two resolvers answered "which revision is the latest" and disagreed.

    The deliberation skill publishes a revision by writing an artifact marker as
    the first bytes of the file, and its own store refuses to consider anything
    that lacks it. This resolver derived a family from the digit runs of a name
    it was handed and took the highest, marker-blind. So an unmanaged file
    dropped into `proposals/` — a draft, a copy, an export — became "the latest"
    here while deliberation still reported the published one, and every module
    was marked stale against a document nobody ever published.

    The discriminator is the marker, never a filename shape. Teaching this side
    the other's naming convention would have created a third copy of a rule that
    already has two, and would have cost `latest_revision` the convention
    independence its docstring promises. If nothing in the family carries the
    marker the directory is not marker-owned and resolution is exactly what it
    was, which is what keeps every hand-authored family working.
    """

    STORE = (FORGE / ".claude/skills/_core/deliberation"
             / "engine/revision-lifecycle-store.ts")

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'draft-r17.md',\n"
        "    'arms': {'floor': {'sections': ['3']}},\n"
        "}\n"
    )
    WIRING = "from Method.estimator import estimate\n"

    def proposals(self, managed=(), unmanaged=(), body="## 3\ntext\n"):
        root = Path(tempfile.mkdtemp(prefix="pp-marker-proposals-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for name in managed:
            (root / name).write_bytes(
                impl.MANAGED_ARTIFACT_MARKER + body.encode("utf-8"))
        for name in unmanaged:
            (root / name).write_bytes(body.encode("utf-8"))
        return root

    def with_root(self, root):
        previous = os.environ.get("IMPLEMENTATION_PROPOSALS")
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(root)
        self.addCleanup(
            lambda: os.environ.__setitem__("IMPLEMENTATION_PROPOSALS", previous)
            if previous is not None
            else os.environ.pop("IMPLEMENTATION_PROPOSALS", None))
        return root

    def verify_against(self, root, *, suffix, revision=None):
        box = FORGE / "implementations" / f"_marker_discovery_{suffix}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src/Method").mkdir(parents=True)
        (box / "src/Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "src/Method/estimator.py").write_text(
            _module("draft-r17.md", ["3"], ["11"]), encoding="utf-8")
        (box / "src/Method_Benchmark/__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        (box / "src/Method_Benchmark/wiring.py").write_text(
            self.WIRING, encoding="utf-8")

        argv = [sys.executable, str(CLI), "verify", "--target", str(box),
                "--name", "Method"]
        if revision:
            argv += ["--revision", revision]
        return subprocess.run(
            argv, capture_output=True, text=True, cwd=FORGE,
            env=dict(os.environ, IMPLEMENTATION_PROPOSALS=str(root)))

    # -- the marker is one contract in two languages -----------------------

    def test_the_marker_is_the_one_the_publisher_writes(self):
        """Restating the bytes here would be a third copy of the rule. It is read
        out of the store that writes them, so the day one side moves this goes
        red instead of the two silently disagreeing again."""
        published = re.search(r"const MARKER=Buffer\.from\('(.*?)'\);",
                              self.STORE.read_text(encoding="utf-8"))
        self.assertTrue(published, "the deliberation store declares no MARKER")
        expected = published.group(1).encode("utf-8").decode("unicode_escape")

        self.assertEqual(impl.MANAGED_ARTIFACT_MARKER, expected.encode("utf-8"))

    def test_the_marker_is_a_leading_prefix_and_not_a_mention(self):
        """The store compares `bytes.subarray(0, MARKER.length)`. A document that
        quotes the marker further down is not a published artifact, and reading
        it as one would readmit exactly the file this excludes."""
        marker = impl.MANAGED_ARTIFACT_MARKER.decode("utf-8")
        root = self.with_root(self.proposals(
            unmanaged=("draft-1.md",), body=f"## 3\n{marker}text\n"))

        self.assertFalse(impl.revision_discovery("draft-1.md")["markerOwned"])
        self.assertEqual(list(root.glob("*.md")) and
                         impl.revision_discovery("draft-1.md")["revision"],
                         "draft-1.md")

    # -- discovery ---------------------------------------------------------

    def test_an_unmanaged_newer_file_cannot_manufacture_drift(self):
        """The reported failure. `draft-r18.md` is a file somebody dropped in;
        deliberation never published it, so nothing is stale against it."""
        root = self.proposals(managed=("draft-r17.md",), unmanaged=("draft-r18.md",))
        proc = self.verify_against(root, suffix="drift")
        fidelity = json.loads(proc.stdout or "{}")["fidelity"]

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(fidelity["latestRevision"], "draft-r17.md")
        self.assertEqual(fidelity["staleModules"], [])
        self.assertFalse(fidelity["benchmark"]["staleRevision"])
        self.assertEqual(fidelity["status"], "ok")

    def test_the_excluded_candidate_is_named_rather_than_swallowed(self):
        """Silently filtering it would be the same defect one layer over: the
        reader would see a resolution and never learn what was passed over.
        `verify` reads and reports; it refuses nothing."""
        root = self.proposals(managed=("draft-r17.md",), unmanaged=("draft-r18.md",))
        fidelity = json.loads(
            self.verify_against(root, suffix="named").stdout)["fidelity"]

        self.assertTrue(fidelity["markerOwned"])
        self.assertEqual(fidelity["nonManagedCandidates"], ["draft-r18.md"])
        self.assertEqual(fidelity["revisionTie"], [])

    def test_a_directory_nobody_manages_behaves_exactly_as_it_did(self):
        """The fallback that keeps every hand-authored family working, and the
        reason the whole existing suite stays green. It is disclosed rather than
        assumed, so a reader can tell the two regimes apart."""
        root = self.with_root(self.proposals(unmanaged=("draft-1.md", "draft-2.md")))

        discovery = impl.revision_discovery("draft-1.md")

        self.assertEqual(discovery["revision"], "draft-2.md")
        self.assertFalse(discovery["markerOwned"])
        self.assertEqual(discovery["nonManaged"], [])
        self.assertEqual(impl.latest_revision("draft-1.md"), "draft-2.md")
        self.assertTrue(root.is_dir())

    def test_a_tie_on_the_digit_tuple_is_reported_not_decided_in_silence(self):
        """`draft-1.md` and `draft-01.md` are one family and tie on the tuple.
        Today's deterministic pick is preserved — changing it would move a
        resolution nobody asked to move — but the ambiguity is now visible, the
        way deliberation surfaces MULTIPLE_ACTIVE_REVISIONS instead of guessing."""
        self.with_root(self.proposals(managed=("draft-1.md", "draft-01.md")))

        discovery = impl.revision_discovery("draft-1.md")

        self.assertEqual(discovery["revision"], "draft-01.md")
        self.assertEqual(discovery["tied"], ["draft-01.md", "draft-1.md"])

    def test_an_explicit_revision_is_still_read_verbatim(self):
        """The filter is on discovery only. A caller naming a file is answering
        the question, not asking it, and a forge whose revisions are authored by
        hand must keep working."""
        root = self.with_root(
            self.proposals(managed=("draft-r17.md",), unmanaged=("draft-r18.md",)))

        self.assertIn("text", impl.revision_source("draft-r18.md"))
        fidelity = json.loads(self.verify_against(
            root, suffix="argument", revision="draft-r18.md").stdout)["fidelity"]
        self.assertEqual(fidelity["latestRevision"], "draft-r18.md")
        self.assertEqual(fidelity["revisionSource"], "argument")
        self.assertEqual(fidelity["staleModules"], ["src/Method/estimator.py"])

    def test_the_resolver_knows_no_naming_convention(self):
        """Its docstring promises a forge whose revisions are `draft-4.md` is
        served by the identical code. A filename prefix compiled in here would
        make that false, and would be the third copy of a rule that already has
        two."""
        function = ast.parse(inspect.getsource(impl.revision_discovery)).body[0]
        # The docstring is scanned out on purpose: it names `draft-4.md` as the
        # family it deliberately does NOT know, and a guard that flagged its own
        # counter-example would be measuring the prose instead of the code.
        body = function.body[1:] if ast.get_docstring(function) else function.body
        literals = [node.value for statement in body for node in ast.walk(statement)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)]

        self.assertNotEqual(literals, [], "nothing was scanned")
        for literal in literals:
            self.assertNotIn(".md", literal, f"a filename suffix is compiled in: {literal!r}")
            self.assertNotIn("research", literal.lower(),
                             f"a project's revision family is compiled in: {literal!r}")

    def test_latest_revision_keeps_its_signature(self):
        """Five unit tests and one production caller read it as `str | None`.
        The richer answer is additive, never a replacement."""
        self.with_root(self.proposals(unmanaged=("draft-1.md", "draft-2.md")))

        self.assertEqual(impl.latest_revision("draft-1.md"), "draft-2.md")
        self.assertIsNone(impl.latest_revision(None))
        self.assertIsNone(impl.latest_revision("no-digits.md"))

    def test_the_toy_targets_left_nothing_behind(self):
        self.verify_against(self.proposals(managed=("draft-r17.md",)), suffix="cleanup")
        self.doCleanups()
        self.assertEqual(
            list((FORGE / "implementations").glob("_marker_discovery_*")), [])


class DecisionGateDocumentationTests(unittest.TestCase):
    """The Decision Gates table is where a reader is told what to do about a
    reported state, and nothing held it to the states the code reports.

    `fidelity.status` gained a fourth value and the table gained the row that
    says what it means, but the row was prose sitting beside code: delete it,
    or rename the value on one side alone, and nothing goes red. The scaffold
    file list is held to the gap checker in exactly this shape, and for the
    same reason — SKILL.md is what an agent reads, not a rendered artifact, so
    the only thing that can keep it true is a test that fails the moment either
    side moves alone.
    """

    SKILL_MD = CLI.parent.parent / "SKILL.md"
    GATES_HEADING = "## Decision Gates"
    HEADER_CELLS = ("Situation", "Action")
    FIDELITY_RE = re.compile(r'`fidelity: "([a-z]+)"`')

    def gate_rows(self):
        """Every `(situation, action)` pair in the table under the heading.

        The header and rule rows are dropped by what they are rather than by
        where they sit, so a row inserted above the ones read here does not
        shift the parse.
        """
        lines = [line.strip() for line
                 in self.SKILL_MD.read_text(encoding="utf-8").splitlines()]
        self.assertIn(self.GATES_HEADING, lines,
                      "the skill carries no Decision Gates section")

        table = []
        for line in lines[lines.index(self.GATES_HEADING) + 1:]:
            if line.startswith("|"):
                table.append(line)
            elif table:
                break
        self.assertNotEqual(
            table, [], "the Decision Gates heading is followed by no table")

        rows = []
        for line in table:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 2:
                continue
            if tuple(cells) == self.HEADER_CELLS:
                continue
            if set("".join(cells)) <= set("-: "):
                continue
            rows.append((cells[0], cells[1]))
        self.assertNotEqual(rows, [], "nothing was scanned")
        return rows

    def documented_fidelity_gates(self):
        """The fidelity states the table quotes, each mapped to its next step."""
        gates = {}
        for situation, action in self.gate_rows():
            found = self.FIDELITY_RE.search(situation)
            if found:
                gates[found.group(1)] = action
        return gates

    def reportable_fidelity_states(self):
        """Every value `cmd_verify` can assign to the headline, read off the
        tree. Restating the four here would make this test a third copy of the
        contract rather than a check on the other two."""
        tree = ast.parse(textwrap.dedent(inspect.getsource(impl.cmd_verify)))
        states = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Constant):
                continue
            if not isinstance(node.value.value, str):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "fidelity_status":
                    states.add(node.value.value)
        self.assertNotEqual(states, set(), "nothing was scanned")
        return states

    def test_the_undeclared_fidelity_gate_is_documented(self):
        """Reachable red: without the row, a reader who runs `verify` on a
        target whose declaration is still the kit's six empty blocks learns the
        state's name from the JSON and nothing about what to do with it."""
        gates = self.documented_fidelity_gates()

        self.assertIn("undeclared", gates,
                      "no gate row names `verify` reporting fidelity undeclared")
        self.assertNotEqual(gates["undeclared"], "",
                            "the row names the state but no next step")

    def test_every_documented_fidelity_gate_is_one_verify_can_report(self):
        """The other direction, and the half that catches a rename. A row
        quoting a value the ladder cannot assign describes a state no target
        can ever be in, which is worse than no row at all: a reader waits for
        a signal that never arrives."""
        documented = set(self.documented_fidelity_gates())
        reportable = self.reportable_fidelity_states()

        self.assertEqual(
            documented - reportable, set(),
            f"the table documents a state `verify` never reports; the ladder "
            f"assigns {sorted(reportable)}")


class PremiseContractAgreementTests(unittest.TestCase):
    """One premise contract, spelled in two files and checked by neither.

    The kit template comments the shape of the premise block beside the empty
    value it scaffolds; the declaration doctrine works the same block in full.
    Nothing parses `premises` — by decision, not by omission — so no consumer
    would ever report the two drifting apart. A field renamed in one file and
    not the other simply ships: every target scaffolded from the kit carries
    one spelling while every reader of the doctrine writes the other, and the
    first to notice is whoever reads a drift report and finds that the field
    they were told to write is not the field that is there.
    """

    SKILL_ROOT = CLI.parent.parent
    SKILL_MD = SKILL_ROOT / "SKILL.md"
    KIT_DECLARATION = SKILL_ROOT / "assets/kit/src_benchmark/__init__.py"

    BLOCK = "premises"

    def kit_block(self):
        """The kit writes its example inside a comment, because the value it
        scaffolds has to stay empty. Uncomment it and read it as the literal
        it is."""
        opener = f'"{self.BLOCK}": {{'
        body = []
        for line in self.KIT_DECLARATION.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text.startswith("#"):
                continue
            text = text[1:].strip()
            if not body and text != opener:
                continue
            body.append(text)
            if text == "}":
                break
        self.assertNotEqual(body, [],
                            f"the kit comments no {self.BLOCK!r} example")
        self.assertEqual(body[-1], "}", "the commented example never closes")
        return ast.literal_eval("{" + " ".join(body) + "}")[self.BLOCK]

    def doctrine_block(self):
        """The doctrine works the whole declaration as an indented literal, so
        it is read as one: a worked example that stopped parsing fails here
        rather than sitting in a passage nobody notices is broken."""
        opener = "__benchmark__ = {"
        body = []
        for line in self.SKILL_MD.read_text(encoding="utf-8").splitlines():
            if not body and line.strip() != opener:
                continue
            body.append(line)
            if line.strip() == "}":
                break
        self.assertNotEqual(body, [],
                            "the doctrine works no `__benchmark__` example")

        tree = ast.parse(textwrap.dedent("\n".join(body)))
        declared = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "__benchmark__"
                    for target in node.targets):
                declared = ast.literal_eval(node.value)
        self.assertIsNotNone(
            declared, "the worked example is not a `__benchmark__` literal")
        self.assertIn(self.BLOCK, declared,
                      f"the worked example declares no {self.BLOCK!r}")
        return declared[self.BLOCK]

    def test_the_kit_and_the_doctrine_name_the_same_premise_fields(self):
        """`premises` is written for a person reading a drift report beside
        changed sections, so no check parses it and no check would ever catch
        the two spellings diverging. This is that check, and it is the only
        one. The count is asserted too, because two examples emptied together
        would agree on nothing and pass."""
        kit = self.kit_block()
        doctrine = self.doctrine_block()

        self.assertEqual(len(kit), 4,
                         f"the kit's premise example names {sorted(kit)}")
        self.assertEqual(sorted(kit), sorted(doctrine))


class FreshScaffoldStaysRedTests(unittest.TestCase):
    """The one red this forge exists to keep red was held by nothing but prose.

    `assets/kit/tests/test_smoke.py` names `{{PKG}}.{{MODULE}}` — a module step 9
    has not written and could not have written, because the object map step 8
    approves is what answers `{{MODULE}}`. So a freshly scaffolded target's smoke
    suite MUST fail, and that failure is the scaffold posing its question rather
    than a defect in it. A suite that passed here would be asserting nothing, and
    a target reading green while step 9 has written no code is exactly the lie
    the whole change was built to prevent.

    Two tests in this file already *mention* that invariant in their docstrings.
    Neither asserted it. Rewriting the shipped template's `MODULES` to `["{{PKG}}"]`
    — the single edit that makes a fresh scaffold go green — left all 394 tests
    passing.

    **Which end is held, and why.** Pinning the literal `["{{PKG}}.{{MODULE}}"]`
    would be the cheap lock and the weakest: it holds a spelling, and commit 12
    already measured what a spelling is worth — `print(code)` kept the shape of
    reading a name back while dropping the meaning, and the structural half went
    green. So the lock here is behavioural. It builds the doctrine's own scaffold
    with `doctrine_scaffold()`, runs the smoke file, and requires the run to be
    red *for the stated reason*: no test passed, nothing was skipped, and the
    error names a module of the target's own package that the tree does not hold.
    It never reads `MODULES`, so renaming it changes nothing, and it cannot be
    satisfied by a rewrite that keeps the name and drops the question.

    Requiring the *reason* is not decoration. The edit that flipped this green
    still leaves the suite red — `MODULES = ["{{PKG}}"]` imports the package
    fine and then fails on the missing `__provenance__` — so a lock that asked
    only "does the suite fail?" would have passed over the exact defect.
    """

    NAME = "Example-Method"
    PACKAGE = "Example_Method"
    SEED = "7"

    SMOKE = "tests/test_smoke.py"

    @staticmethod
    def tally(output, word):
        """What pytest's own summary line counted, or zero when it counted none."""
        match = re.search(rf"(\d+) {word}\b", output)
        return int(match.group(1)) if match else 0

    def test_a_fresh_scaffold_s_smoke_suite_fails_naming_an_unwritten_module(self):
        """Reachable red, proven by inversion: with `MODULES = ["{{PKG}}"]` the
        package imports, one smoke test passes and the error is an absent
        `__provenance__` rather than an absent module — so `passed == 0` and the
        `ModuleNotFoundError` clause both fire, while a bare "it fails" would not.
        """
        box = doctrine_scaffold(self, self.NAME, self.SEED)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", self.SMOKE],
            cwd=str(box), capture_output=True, text=True)
        output = proc.stdout + proc.stderr
        tail = output[-3000:]

        self.assertNotEqual(
            proc.returncode, 0,
            "a freshly scaffolded target's smoke suite passed; step 9 has "
            f"written nothing, so there is nothing for it to assert\n{tail}")
        self.assertEqual(
            self.tally(output, "passed"), 0,
            f"a smoke test passed over a target holding no module\n{tail}")
        self.assertEqual(
            self.tally(output, "skipped"), 0,
            f"the red was suppressed by skipping rather than left red\n{tail}")
        self.assertGreaterEqual(
            self.tally(output, "failed"), 1,
            f"nothing failed, so nothing was asserted\n{tail}")

        missing = re.findall(r"No module named '([^']+)'", output)
        self.assertTrue(
            missing,
            "the smoke suite is red for some reason other than the module step "
            f"9 has not written\n{tail}")
        for name in missing:
            self.assertEqual(
                name.split(".")[0], self.PACKAGE,
                f"the red names {name!r}, which is not the target's own package: "
                "a missing dependency is not the question the scaffold poses")
            inside = box / "src" / Path(*name.split("."))
            self.assertFalse(
                inside.with_suffix(".py").is_file() or (inside / "__init__.py").is_file(),
                f"{name!r} is reported missing and the scaffold wrote it anyway")

    def test_the_smoke_template_still_carries_a_question_the_scaffold_cannot_answer(self):
        """Why the red is reachable at all, stated as the mechanism.

        This is the weaker half and says so. A token surviving substitution is
        not the same as a token being imported: moving `{{MODULE}}` into a
        comment would satisfy this and still hand a fresh target a green suite.
        The behavioural test above is what closes that, and this one is not a
        substitute for it — it only records that the template still asks
        something the scaffold has no answer for, which is what makes the
        behavioural red reachable rather than incidental.
        """
        template = (KIT / "tests" / "test_smoke.py").read_text(encoding="utf-8")
        survivors = sorted(set(TOKEN_RE.findall(scaffold_substitute(template))))
        self.assertTrue(
            survivors,
            "the smoke template is fully answered at scaffold time, so a fresh "
            "target's suite has nothing left to be red about")


class MaterializeIsNotAProductionStepTests(unittest.TestCase):
    """Three documents told three different lies about the same script, and no
    test read any of them.

    `scripts/materialize.py` is the forge's own harness. An agent fills the
    scaffold gaps by reading step 5; the script plays that part so this suite can
    examine a freshly scaffolded target. It is not a step of Flow A and it has no
    production caller. All three sites that once said otherwise —
    `SKILL.md`'s step 5 ("performs this exact mapping for eight of the nine",
    false in both halves), `README.md`'s Flow A diagram, and the docstring of
    `assets/kit/src_benchmark/__init__.py`, a template that ships *into* targets
    and told their readers the script had written their file — were corrected.
    Reinstating all three at once left all 394 tests passing.

    **What is held, and where the guard deliberately does not go.** `README.md`
    is not added to `guarded_documents()`. That set is the C1 vocabulary guard,
    and the README legitimately names one hosted service fourteen times because
    it documents the skill that ships an adapter for it; widening C1 to reach the
    README would fail on the first run for a reason that has nothing to do with
    this finding, and would force an exemption broad enough to make the guard
    stop meaning anything. So the README is read here, by one narrow test, for
    one fact — and the C1 surface is left exactly as commit 11 set it.

    Each site is held at the level its claim lives at rather than by matching the
    sentence that happened to be written:

    - the shipped kit names no forge harness at all, and the test is non-vacuous
      because the kit names the *production engine* four times, legitimately;
    - no flow diagram draws the harness as a node;
    - the count step 5 attributes to the harness is one its own table yields;
    - step 5 repeats the standing the harness claims for itself, in the
      harness's own words rather than in a third copy of them;
    - the production engine never reaches the harness, while the harness reaches
      the engine — the direction is the fact;
    - everything doctrine tells the agent to run is a real CLI command.
    """

    SCRIPTS = SKILL_ROOT / "scripts"
    README = FORGE / "README.md"

    MERMAID_RE = re.compile(r"^```mermaid\n(.*?)^```", re.DOTALL | re.MULTILINE)
    RUN_RE = re.compile(r"Run `([^` ]+)")
    HEADING_RE = re.compile(r"^\d+\. \*\*")
    STANDING_RE = re.compile(
        r"[^.]*\b(?:never|not)\b[^.]*\bflow\s+\w+", re.IGNORECASE)

    NUMBER_WORDS = {
        word: value for value, word in enumerate(
            "zero one two three four five six seven eight nine ten eleven "
            "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
            "nineteen twenty".split())}
    COUNT_RE = re.compile(
        r"\b({}|\d+)\b".format(
            "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))),
        re.IGNORECASE)

    def harness(self):
        """The one script the forge ships that is not the production engine.

        Derived rather than named, so renaming the harness renames it here too
        and the lock does not quietly stop pointing at anything.
        """
        others = sorted(path for path in self.SCRIPTS.glob("*.py")
                        if path.resolve() != CLI.resolve())
        self.assertEqual(
            len(others), 1,
            f"the forge ships {len(others)} scripts besides its engine; these "
            "tests are written for exactly one harness and need revisiting")
        return others[0]

    @classmethod
    def counts_in(cls, text):
        """Every count the text states, in order, spelled either way.

        Doctrine writes its quantities as words; a later edit may well write one
        as a digit, and a lock that only read one spelling would go quiet at
        exactly the moment the sentence changed.
        """
        found = []
        for token in cls.COUNT_RE.findall(text):
            found.append(int(token) if token.isdigit()
                         else cls.NUMBER_WORDS[token.lower()])
        return found

    @classmethod
    def standing_clause(cls, text):
        """The one sentence in `text` that denies the harness a flow's standing.

        Found by its meaning — a negation and the name of a flow inside one
        sentence — rather than by where it sits, so neither the document nor the
        docstring has to keep the sentence in place for this to keep pointing at
        it. Whitespace is flattened first: doctrine wraps its prose and a
        docstring wraps it differently.
        """
        match = cls.STANDING_RE.search(" ".join(text.split()))
        return match.group(0).strip() if match else None

    @staticmethod
    def import_roots(source):
        """Every top-level name a module imports, absolute or relative."""
        roots = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        return roots

    def test_no_asset_the_scaffold_ships_names_the_forge_s_own_harness(self):
        """Reachable red: the template's docstring once opened by telling a
        target's readers that `materialize.py` had written their file.

        Absence is the whole assertion, so it is proven non-vacuous by the
        inverse: the kit names `implementation_cli.py` four times, because a
        target really does run the engine. Naming a script is possible here; the
        harness is the one that must never be named.
        """
        harness = self.harness()
        named, engine = {}, []
        for asset in kit_assets():
            text = (SKILL_ROOT / asset).read_text(
                encoding="utf-8", errors="replace").lower()
            if harness.stem in text:
                named[asset] = harness.name
            if CLI.stem in text:
                engine.append(asset)

        self.assertEqual(
            named, {},
            f"a file the scaffold copies into a target names {harness.name}, "
            "which is the forge's own harness and nothing a target ever runs")
        self.assertTrue(
            engine,
            "no shipped asset names the engine either, so this scan proves "
            "nothing about whether it can see a script name at all")

    def test_no_flow_diagram_draws_the_harness_as_a_step(self):
        """Reachable red: the Flow A diagram drew `materialize.py` as the node
        that fills the scaffold, where the agent belongs.

        Non-vacuous by the same inverse: the diagrams do name real CLI commands,
        so a node naming a script would have been drawn and read.
        """
        harness = self.harness()
        blocks = self.MERMAID_RE.findall(
            self.README.read_text(encoding="utf-8"))
        self.assertTrue(blocks, "the README draws no flow at all")

        commanded = {command for block in blocks for command in impl.COMMANDS
                     if re.search(rf"\b{command}\b", block)}
        self.assertTrue(
            commanded,
            "no diagram names a single CLI command, so this scan proves nothing")

        for index, block in enumerate(blocks):
            with self.subTest(diagram=index):
                self.assertNotIn(
                    harness.stem, block.lower(),
                    f"a flow diagram draws {harness.name} as a step; it is the "
                    "forge's harness, and the agent is what fills the scaffold")

    def step_five(self):
        """The producer step carrying the stage-1 table.

        Located by the table rather than by its own wording, so rewording the
        step does not silently move this test off the paragraph it holds.
        """
        lines = SKILL_MD.read_text(encoding="utf-8").splitlines()
        anchors = [index for index, line in enumerate(lines)
                   if line.strip() == STAGE_ONE_HEADER]
        self.assertEqual(len(anchors), 1,
                         "SKILL.md carries the stage-1 table neither once nor "
                         f"once only: {len(anchors)} occurrences")
        anchor = anchors[0]
        starts = [index for index in range(anchor)
                  if self.HEADING_RE.match(lines[index])]
        self.assertTrue(starts, "the stage-1 table sits inside no numbered step")
        ends = [index for index in range(anchor + 1, len(lines))
                if self.HEADING_RE.match(lines[index])]
        return "\n".join(lines[starts[-1]:ends[0] if ends else len(lines)])

    def harness_clause(self, step):
        """The paragraph of `step` that names the harness.

        One spelling for the two tests that read it, because two copies of the
        same three lines is the drift this change exists to end.
        """
        harness = self.harness()
        index = step.find(harness.name)
        self.assertNotEqual(
            index, -1,
            f"step 5 no longer names {harness.name}; if the mention was removed "
            "on purpose, remove this test with it rather than leaving it green")
        return step[index:].split("\n\n")[0]

    def test_the_count_step_five_attributes_to_the_harness_is_one_its_table_yields(self):
        """Reachable red, and the exact claim that was false: "performs this
        exact mapping for eight of the nine" was wrong in both halves — the
        harness covers all of them, and there are thirteen, not nine.

        The clause is required to state a count. A prose rewrite that drops the
        number states nothing false, but it also leaves the coverage claim held
        by nobody, which is the condition this whole change exists to end. That
        the harness's tree really is the stage-1 register is a separate and
        behavioural matter, and `MaterializeWritesStageOneTests` owns it; what is
        held here is only that the number doctrine prints agrees with the table
        doctrine prints it beside.
        """
        harness = self.harness()
        step = self.step_five()

        tables = markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), STAGE_ONE_HEADER)
        self.assertEqual(len(tables), 1)
        rows = tables[0]
        total = len(rows)
        authored = sum(1 for row in rows if row[1].startswith("authored:"))

        clause = self.harness_clause(step)

        counts = self.counts_in(clause)
        self.assertTrue(
            counts,
            f"step 5 attributes no count at all to {harness.name}; the coverage "
            "claim it makes is what this test holds, so it has to make one")
        self.assertEqual(
            counts[0], total,
            f"step 5 says {harness.name} covers {counts[0]} of the gaps and its "
            f"own table has {total} rows")
        self.assertEqual(
            sorted(set(counts) - {total, authored}), [],
            f"step 5's clause about {harness.name} states a count its table "
            f"does not yield; the table has {total} rows, {authored} authored")

    def test_step_five_carries_the_standing_the_harness_claims_for_itself(self):
        """Reachable red, and red when it was written: step 5 named the harness
        inside the very step that tells an agent to fill the gaps, and said
        nothing about what the harness is.

        `README.md` and the script's own docstring both deny it the standing of
        a flow step. `SKILL.md` — the document an agent actually reads — did
        not, so a reader stopped at step 5 could take the mention for an
        invitation to run it.

        The sentence is not spelled here. It is read out of the harness's own
        docstring, where the claim belongs, and doctrine is required to repeat
        it: there is no third copy for the other two to drift away from, and
        rewording the denial means rewording it at its source. It is required in
        the harness's own clause rather than anywhere in the step, because the
        sentence that names the script is the one a reader takes the invitation
        from.

        **Knowingly weaker than its behavioural partners, and says so.** All
        this holds is that doctrine states the fact.
        `test_the_production_engine_never_reaches_the_harness` holds the fact
        itself, and
        `test_the_only_things_doctrine_tells_the_agent_to_run_are_cli_commands`
        holds that doctrine never tells an agent to run it. Delete either of
        those and a document still repeating this sentence would pass over a
        harness that had quietly become a production step.
        """
        harness = self.harness()
        docstring = ast.get_docstring(
            ast.parse(harness.read_text(encoding="utf-8")))
        standing = self.standing_clause(docstring or "")
        self.assertIsNotNone(
            standing,
            f"{harness.name}'s own docstring no longer denies that it is a step "
            "of the flow, and that docstring is the source this reads; the "
            "claim has to be made there before doctrine can be held to it")

        clause = " ".join(self.harness_clause(self.step_five()).split())
        self.assertIn(
            standing.lower(), clause.lower(),
            f"the step that tells the agent to fill the gaps names "
            f"{harness.name} without saying \"{standing}\"; the script's own "
            "docstring says it and the README says it, and the document an "
            "agent actually reads is the one where it matters")

    def test_the_production_engine_never_reaches_the_harness(self):
        """The claim behind all three documents, held as behaviour rather than
        as prose: the harness is test-only.

        The direction is the fact, so both directions are asserted. The harness
        imports the engine — that is what gives `.gitignore` one author instead
        of a producer writing half and a fixture hand-patching the other — and
        the engine imports nothing back. A dependency that ran the other way
        would make the harness a production path whatever any document said.
        """
        harness = self.harness()
        engine_source = CLI.read_text(encoding="utf-8")

        self.assertNotIn(
            harness.stem, self.import_roots(engine_source),
            f"the engine imports {harness.name}; the harness is test-only and "
            "an import is what would stop it being that")

        mentions = sorted(
            {node.value for node in ast.walk(ast.parse(engine_source))
             if isinstance(node, ast.Constant) and isinstance(node.value, str)
             and harness.name in node.value})
        self.assertEqual(
            mentions, [],
            f"the engine carries {harness.name} in a string, which is how a "
            f"script gets shelled without being imported: {mentions}")

        self.assertIn(
            CLI.stem, self.import_roots(harness.read_text(encoding="utf-8")),
            f"{harness.name} no longer imports the engine, so the one-way "
            "dependency this asserts the direction of is not there to assert")

    def test_the_only_things_doctrine_tells_the_agent_to_run_are_cli_commands(self):
        """"The path an agent runs" is a testable notion: SKILL.md's imperative
        for invoking anything is ``Run `x` ``, and every `x` must be a command the
        CLI actually dispatches.

        Reachable red by adding ``Run `materialize.py <target>` `` anywhere in the
        document. This is the general form of the finding rather than its
        instance — the harness is only the script that happened to be drawn as a
        step; nothing else may be either.
        """
        harness = self.harness()
        invoked = self.RUN_RE.findall(SKILL_MD.read_text(encoding="utf-8"))
        self.assertTrue(
            invoked,
            "doctrine tells the agent to run nothing at all, so this scan "
            "proves nothing about what it tells the agent to run")
        self.assertEqual(
            sorted(set(invoked) - set(impl.COMMANDS)), [],
            "doctrine tells the agent to run something that is not a command "
            f"the CLI dispatches; it dispatches {sorted(impl.COMMANDS)}")
        self.assertNotIn(
            harness.stem, impl.COMMANDS,
            f"{harness.name} became a CLI command, which is the one thing the "
            "framing of this change says it must never be")


#: The vocabulary the forge legitimately owns, word to the reason it was admitted.
#:
#: Rule B derives its denylist from whatever targets are on disk and subtracts
#: this. A dict rather than a set because the reason column is the review
#: artifact: admitting a word has to cost an argument, not a comma. A meta-test
#: below asserts every reason is a sentence, and a second asserts this and
#: `FORGE_VOCABULARY_FLOOR` are disjoint — so no leak already found can be
#: silenced by adding it here.
FORGE_LEXICON: dict[str, str] = {
    "adaptation": "ordinary English in doctrine prose about an arm with its "
                  "adaptation switched off, and the name of the forge's own "
                  "worked example of an assertion that cannot fail",
    "artifacts": "ordinary English for what a run leaves behind, and the "
                 "invented module in the usage reference's worked walkthrough",
    "attention": "ordinary English about what a report spends of its reader, "
                 "used in three places that describe writing rather than code",
    "bag": "the canonical illustration of two incomparable statistical units, "
           "one predicting per instance and the other per bag, which the kit "
           "needs in order to explain when a metric is not applicable",
    "benchmark": "the central noun of this whole skill: the kit ships "
                 "benchmark.py and every target declares a benchmark package",
    "confidence": "ordinary English about how sure a reading is, used in the "
                  "usage reference's prose and in no code path at all",
    "config": "a universal name for the module that holds settings, shipped by "
              "the kit itself and used by every scaffold this forge writes",
    "digest": "the forge's own kit module report_digest.py, which reduces a "
              "report to the numbers a verification can be run against",
    "domain": "an ENVIRONMENT_HINTS entry beside dataset, task and corpus: "
              "generic vocabulary for where data comes from, named by no target",
    "figures": "one of the two module names rule A allows a worked example to "
               "draw from, because the kit's own declaration already uses it",
    "harness": "probe returns a harnessStatus key and the doctrine says the "
               "harness refuses; the kit's own scaffold default for it is "
               "benchmark.py",
    "init": "the __init__.py every Python package on earth is required to have, "
            "including the declaration this skill writes",
    "kernel": "generic compute vocabulary for the unit a device queues, needed "
              "by the kit's note on why a timer stopped too early lies",
    "kernels": "the plural of the same generic compute vocabulary, in the same "
               "note in the kit's benchmark module",
    "local": "ordinary English for a remedy or a path that stays on this "
             "machine, used throughout the doctrine and the checker",
    "models": "generic machine-learning vocabulary and the name of this "
              "repository's own checkpoint directory, which no target owns",
    "objective": "the forge's declared report vocabulary for what a run is "
                 "trying to optimize, and ordinary English besides",
    "pipeline": "ordinary English for a sequence of steps, used twice in "
                "doctrine prose about how a construction arranges itself",
    "record": "the forge's own evidence vocabulary: `@record` is one of the "
              "four witness kinds `impl_position` recognizes, and the report "
              "contract has declared `records` since before any target did",
    "report": "the central noun of the report contract this skill exists to "
              "check, appearing in doctrine on nearly every page",
    "steps": "the forge's own declaration surface and its command: a target "
             "declares `__steps__`, `impl_steps.py` runs one, and `step` is "
             "the subcommand -- named by this skill, never by a repository",
    "shard": "the forge's own distribution vocabulary: a declaration says which "
             "fields must be identical across shards and verify reads it",
    "shards": "the plural of the same distribution vocabulary, in the same "
              "declaration and the same checker",
    "tables": "the other module name rule A allows a worked example to draw "
              "from, because the kit's own declaration already uses it",
    "term": "ordinary English for a word being defined, and for a component of "
            "a sum the report contract already names generically",
    "training": "ordinary English and generic machine-learning vocabulary: the "
                "harness owns training and measuring and nothing else",
    "verdict": "the forge's own kit module verdict.py and the noun the whole "
               "flow ends on, named by the skill long before any target",
    "wiring": "the forge's own vocabulary for how a benchmark reaches prior "
              "work, checked by this skill and shipped in its kit",
}

#: Rule A's allowlist. A worked report example may draw its module names from
#: these two and nothing else, because these two are what the kit's own
#: declaration already uses (`assets/kit/src_benchmark/__init__.py:55-57`).
EXAMPLE_MODULE_NAMES = frozenset({"tables", "figures"})


class RehearsalAuthorityTests(unittest.TestCase):
    """A rehearsal is not a campaign, and this flow only ever declined the
    campaign.

    The remote-execution roster's `submit` row says this flow "offers a campaign
    to a human and never sends one itself" — a sentence about the long run, and
    the right one for it: a campaign costs hours and real quota, so a person
    authorizes it. A rehearsal is the opposite thing. It is one arm, one seed,
    minutes, and it exists to find cheaply what the long run would find
    expensively.

    Nothing forbade the agent from running it. Nothing told it to either, so it
    stopped and asked — and asking is what made the cheap check feel as costly as
    the expensive one. The gap was a missing instruction, not a rule to relax.

    Deliberately untouched: `smokeReady` still gates nothing. It cannot, for the
    reason the doctrine already gives — the fact answers identically for a
    repository with no remote-execution CLI at all and one that has generated no
    job — and this change does not pretend otherwise. What routes the agent is
    the Decision Gates row a reader already follows, not a new rung.
    """

    def rehearsal_paragraph(self) -> str:
        text = SKILL_MD.read_text(encoding="utf-8")
        marker = "### The rehearsal is the agent's to run"
        self.assertIn(marker, text,
                      "no section says whose job the rehearsal is, so an agent "
                      "reaching a job that never rehearsed can only ask")
        return text.split(marker, 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]

    def test_the_flow_is_told_to_run_the_rehearsal_and_names_the_command(self):
        """An instruction that never names the command is a sentence a reader
        agrees with and cannot act on.
        """
        paragraph = self.rehearsal_paragraph()
        self.assertIn("--smoke", paragraph)
        self.assertIn("smoke record", paragraph)
        self.assertIn("readiness", paragraph)

    def test_the_campaign_stays_the_human_s_to_authorise(self):
        """The distinction is the whole point: relaxing the rehearsal must not
        quietly relax the run it protects.
        """
        paragraph = self.rehearsal_paragraph()
        self.assertRegex(paragraph, r"campaign")
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("never sends one itself", text,
                      "the campaign's own refusal was removed along with the "
                      "rehearsal's permission")

    def test_smoke_ready_still_gates_nothing(self):
        """Locked because this change is exactly the kind that would erode it:
        permitting the rehearsal is not the same as branching on the fact, and
        the fact still cannot tell `not ready` from `not applicable`.
        """
        text = SKILL_MD.read_text(encoding="utf-8")
        row = [line for line in text.splitlines()
               if line.startswith("| `smokeReady` |")]
        self.assertEqual(len(row), 1, "no smokeReady row to hold")
        self.assertIn("**Never**", row[0])


class ForgeVocabularyDerivedGuardTests(unittest.TestCase):
    """A guard that scans a fixed word list can only catch a leak somebody has
    already found. This derives the denylist from the targets on disk instead.

    Two rules at two units, because neither one covers the other:

    - **Rule A** reads a worked report example and demands every dotted name
      draw its module from `EXAMPLE_MODULE_NAMES`. It needs no lexicon and it is
      the only rule that can catch a leak spelled with a word the forge
      legitimately owns — `harness` is in the lexicon by necessity, so no
      word-level rule can ever object to `harness.render_panorama`.
    - **Rule B** derives every target's vocabulary from directory, package and
      module names, subtracts `FORGE_LEXICON`, and objects to what is left.

    `FORGE_VOCABULARY_FLOOR` is rule C and lives on the class next door, which
    already scans it over the same surface.
    """

    SKILL_ROOT = ReportFirstSectionProseTests.SKILL_ROOT
    CACHES = ReportFirstSectionProseTests.CACHES
    BINARY_SUFFIXES = ReportFirstSectionProseTests.BINARY_SUFFIXES

    # One definition of the guarded surface, borrowed rather than restated: a
    # second spelling of "what the forge ships" is how the two go out of step.
    guarded_documents = ReportFirstSectionProseTests.guarded_documents
    scannable_text = ReportFirstSectionProseTests.scannable_text

    TARGETS = FORGE / "implementations"

    #: Split on punctuation and on camel-case boundaries, so `MIL_CREDA_Benchmark`
    #: and `reportDigest` both come apart into the words a reader would say.
    WORD_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+|(?<=[a-z])(?=[A-Z])")

    #: Two-letter fragments match too much ordinary text to carry a verdict.
    MINIMUM_WORD = 3

    def split(self, name):
        return [part.lower() for part in self.WORD_SPLIT_RE.split(name) if part]

    def target_words(self, root=None):
        """Every word the targets on disk own, and the targets they came from.

        Names only: directory, package and module basenames. No file under
        `implementations/` is opened, which is what keeps this read-only and
        keeps the cost proportional.

        Directories beginning with `_` are skipped because that is where this
        suite builds its own throwaway targets; deriving the denylist from them
        would make the guard depend on which tests happened to run first.
        """
        base = self.TARGETS if root is None else Path(root)
        words: set[str] = set()
        targets: list[str] = []
        if not base.is_dir():
            return words, targets
        for target in sorted(base.iterdir()):
            if not target.is_dir() or target.name.startswith((".", "_")):
                continue
            targets.append(target.name)
            words.update(self.split(target.name))
            source = target / "src"
            if not source.is_dir():
                continue
            for package in sorted(source.iterdir()):
                if not package.is_dir() or package.name in self.CACHES:
                    continue
                words.update(self.split(package.name))
                for module in sorted(package.glob("*.py")):
                    words.update(self.split(module.stem))
        return {word for word in words if len(word) >= self.MINIMUM_WORD}, targets

    def derived_denylist(self, root=None):
        """Rule B's denylist, or a skip when nobody has a target.

        Silence is the right answer for a clone with no `implementations/`
        repository, but it has to be an announced silence: a guard that passes
        because it had nothing to look at reads exactly like a guard that
        looked and found nothing.
        """
        words, targets = self.target_words(root)
        if not targets:
            self.skipTest(
                "no repository under implementations/, so rule B has no "
                "vocabulary to derive and this is silence rather than a pass")
        return sorted(words - set(FORGE_LEXICON))

    def leaks(self, denylist, root=None):
        found = {}
        for document in self.guarded_documents(root):
            text = self.scannable_text(document)
            hits = [word for word in denylist
                    if re.search(rf"\b{re.escape(word)}\b", text)]
            if hits:
                base = self.SKILL_ROOT if root is None else Path(root)
                found[str(document.relative_to(base))] = hits
        return found

    def test_rule_b_finds_no_target_vocabulary_in_the_forge(self):
        """The denylist is whatever the targets on disk own, minus what the
        forge owns. Anything left that appears in a forge file is a leak, and
        it is a leak whether or not anybody wrote it on a list first.
        """
        denylist = self.derived_denylist()
        self.assertTrue(
            denylist,
            "every derived word is in the lexicon, so rule B is deriving "
            "nothing and cannot object to anything")
        self.assertEqual(
            self.leaks(denylist), {},
            "these words belong to a repository under implementations/ and "
            "are neither in FORGE_LEXICON nor repaired")

    #: The keys a worked report declaration is written with. A dotted name is
    #: subject to rule A when it stands on a line that also carries one of these,
    #: which is what separates `"figures.curves"` in an example from `"README.md"`
    #: in a list of real filenames. Measured before it was written: scoped this
    #: way the rule sees 23 dotted names across the whole forge and objects to
    #: exactly the leaked ones; unscoped it sees sixty, nearly all of them real
    #: files, and would have to grow an exemption list to say anything at all.
    REPORT_KEY_RE = re.compile(
        r"""['"](renderers|conclusions|conclusionEntry|objectiveEntry"""
        r"""|figures|record)['"]""")

    #: `module.attribute`, quoted, both halves identifiers. A path keeps its
    #: slash and so never matches, which is why `"Results/summary.json"` is not
    #: read as a module name.
    DOTTED_RE = re.compile(
        r"""(?P<quote>['"])"""
        r"""(?P<name>[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)"""
        r"""(?P=quote)""")

    def example_names(self, root=None):
        """Every dotted name a worked report example spells, with its place."""
        base = self.SKILL_ROOT if root is None else Path(root)
        found = []
        for document in self.guarded_documents(root):
            text = document.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                if not self.REPORT_KEY_RE.search(line):
                    continue
                for match in self.DOTTED_RE.finditer(line):
                    found.append((str(document.relative_to(base)), number,
                                  match.group("name")))
        return found

    def example_violations(self, root=None):
        return [place for place in self.example_names(root)
                if place[2].split(".")[0] not in EXAMPLE_MODULE_NAMES]

    def scratch_forge(self):
        """The forge's shape, built for the purpose rather than borrowed.

        A rule that passes because nothing is wrong today has not been shown to
        do anything, so this is proven the way `test_a_leak_into_a_script_is_caught`
        already proves the fixed list: build the surface, plant one leak in it,
        and read back exactly what was named.
        """
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        (base / "references").mkdir()
        (base / "assets").mkdir()
        (base / "scripts").mkdir()
        (base / "SKILL.md").write_text("Generic doctrine.\n", encoding="utf-8")
        (base / "references" / "usage.md").write_text("Generic.\n", encoding="utf-8")
        return base

    def scratch_targets(self):
        """A target root built for the purpose, owning words nothing else uses.

        Rule B derives its denylist from `implementations/` on disk, so proving
        the rule reachable means owning both ends of it. Borrowing the checkout's
        real target would not do: its vocabulary is whatever somebody happens to
        have cloned, and the forge is clean of it, which is the condition under
        which rule B says nothing at all.

        The names are invented. No repository is called `Nimbus_Benchmark` and no
        forge file says `paddock`, so a hit read back from this tree is
        attributable to the derivation and to nothing else.
        """
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        package = base / "Nimbus_Benchmark" / "src" / "nimbus_benchmark"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
        (package / "paddock.py").write_text("VALUE = 2\n", encoding="utf-8")
        return base

    def test_rule_b_names_the_file_and_the_word_a_planted_leak_is_in(self):
        """Rule B, proven the way rules A and C already are.

        Against a clean checkout rule B is green because nothing is wrong, and a
        rule that is green because nothing is wrong cannot be told apart from a
        rule that is switched off: neuter the matcher in `leaks` so it can never
        fire and the whole suite still passes. The rule was reachable the day it
        was written and nothing kept that proof, which is the same objection this
        file makes about everything else.

        So this owns both ends — a target that owns `paddock` and a forge file
        that borrows it — and reads back the exact pair the guard reports, not
        merely that something failed. `paddock` is in neither `FORGE_LEXICON` nor
        `FORGE_VOCABULARY_FLOOR`, so no fixed list could have caught it, and it
        is derived from a module basename rather than the target's own directory
        name, so a rule reading only the top level could not have either.
        """
        self.assertNotIn("paddock", FORGE_LEXICON)
        self.assertNotIn("paddock", FORGE_VOCABULARY_FLOOR)

        denylist = self.derived_denylist(self.scratch_targets())
        self.assertEqual(
            denylist, ["nimbus", "paddock"],
            "the denylist is every word the target owns minus the lexicon, so "
            "`benchmark`, `config` and `init` are subtracted and these are left")

        forge = self.scratch_forge()
        (forge / "scripts" / "leaky.py").write_text(
            "# staged in the paddock before the run\nVALUE = 1\n",
            encoding="utf-8")
        (forge / "scripts" / "clean.py").write_text(
            "VALUE = 2\n", encoding="utf-8")
        self.assertEqual(
            self.leaks(denylist, forge), {"scripts/leaky.py": ["paddock"]},
            "rule B has to name the file and the word, because a guard that "
            "reports only that something is wrong repairs nothing")

    def test_rule_a_names_the_file_a_planted_example_leak_is_in(self):
        base = self.scratch_forge()
        (base / "scripts" / "leaky.py").write_text(
            'CONTRACT = {"figures": ["figures.curves", "latent.grid"]}\n',
            encoding="utf-8")
        (base / "scripts" / "clean.py").write_text(
            'CONTRACT = {"figures": ["figures.curves"]}\n', encoding="utf-8")
        self.assertEqual(
            self.example_violations(base),
            [("scripts/leaky.py", 1, "latent.grid")])

    def test_rule_a_objects_to_a_module_the_forge_legitimately_owns(self):
        """The reason rule A exists at all.

        `harness` is in `FORGE_LEXICON` by necessity — `probe` returns a
        `harness` key and the doctrine says the harness refuses — so rule B can
        never object to `harness.render_panorama`, which is one of the leaks the
        derived guard was adopted to catch. An allowlist over invented example
        names is the only rule that can, and this is that claim measured rather
        than argued.
        """
        base = self.scratch_forge()
        (base / "scripts" / "borrowed.py").write_text(
            'CONTRACT = {"renderers": ["tables.render", "harness.render_panorama"]}\n',
            encoding="utf-8")
        self.assertIn("harness", FORGE_LEXICON)
        self.assertEqual(self.leaks(self.derived_denylist(), base), {})
        self.assertEqual(
            self.example_violations(base),
            [("scripts/borrowed.py", 1, "harness.render_panorama")])

    def test_rule_a_lets_a_worked_example_draw_from_two_module_names(self):
        """An allowlist, which is why it is precise where rule B is not.

        A worked example is invented prose: nothing forces it to reach outside
        the two module names the kit's own declaration already uses. So the rule
        needs no list of forbidden words, and catches a leak nobody enumerated —
        including one spelled with a word the forge legitimately owns, which no
        word-level rule can ever object to.
        """
        names = self.example_names()
        self.assertTrue(
            names,
            "no worked report example was found at all, so this rule is "
            "reading nothing and proving nothing")
        self.assertEqual(
            self.example_violations(), [],
            "a worked report example names a module outside "
            f"{sorted(EXAMPLE_MODULE_NAMES)}, which means it was copied from "
            "somebody's repository instead of invented")

    def test_a_clone_with_no_target_skips_instead_of_passing(self):
        """Rule B is the one rule in this file that reads outside the forge, and
        the price is that it says nothing at all in a clone where nobody has
        checked a repository out yet.

        Saying nothing has to be visible. A skip with a reason tells a reader the
        rule did not run; a green tick tells them it ran and found the forge
        clean, which would be a claim nobody made.
        """
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        with self.assertRaises(unittest.SkipTest) as raised:
            self.derived_denylist(empty)
        self.assertIn("implementations/", str(raised.exception))
        self.assertIn("silence rather than a pass", str(raised.exception))

    def test_every_lexicon_entry_costs_an_argument(self):
        """The reason column is the review artifact.

        A set would let the lexicon grow by one comma per inconvenient failure,
        which is how a derived denylist quietly becomes an empty one. A sentence
        is not proof that the word belongs to the forge, but it is a thing a
        reviewer can disagree with, and that is the whole mechanism.
        """
        thin = {word: reason for word, reason in FORGE_LEXICON.items()
                if len(reason.split()) < 4}
        self.assertEqual(
            thin, {},
            "a lexicon entry has to say why the forge owns the word")

    def test_the_lexicon_cannot_silence_a_leak_already_found(self):
        """The floor and the lexicon are disjoint, structurally.

        Without this, the cheapest way to make rule B green is to declare the
        leaking word forge vocabulary — and the words most likely to be declared
        that way are exactly the ones already proven to be somebody else's.
        """
        self.assertEqual(
            sorted(set(FORGE_LEXICON) & set(FORGE_VOCABULARY_FLOOR)), [],
            "a word on the floor is a leak somebody already found, so it can "
            "never also be vocabulary the forge owns")


class UndeclaredRecordEndToEndTests(unittest.TestCase):
    """The other half of the vocabulary repair, which is not a vocabulary
    question at all: what the checker does when a report declares no record.

    It used to substitute a filename — one particular repository's filename —
    so a target that declared nothing got somebody else's answer. Dropping the
    default is the repair, but the two sites cannot drop it the same way:
    `_is_reporting_cell` is typed `str | None` and answers `False` for anything
    falsy, while `report_state` reads the declared name as text and `p.name in
    None` raises. So one site takes `None` and the other takes `""`.

    This runs the real command over a real target that declares no record,
    because the difference between those two is invisible until something
    actually asks.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'renderers': ['tables.render'],\n"
        "        'conclusions': ['tables.conclusion'],\n"
        "        'objectiveEntry': 'tables.objective',\n"
        "        'figures': ['figures.curves'],\n"
        "        'components': {'terms': ['fit'], 'share': None},\n"
        "        'dimensions': {'accuracy': 'higher', 'fit': None},\n"
        "    },\n"
        "}\n"
    )

    def verify(self):
        box = FORGE / "implementations" / f"_norecord_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src/Method_Benchmark").mkdir(parents=True)
        (box / "Method/Notebooks").mkdir(parents=True)
        (box / "Method/Results").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        (box / "src/Method_Benchmark/__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        # At least one JSON under the product, or the membership test the repair
        # touches is never reached and this proves nothing.
        (box / "Method/Results/summary.json").write_text(
            json.dumps({"runs": []}), encoding="utf-8")
        cells = [_cell("markdown", "The figure shows the curves."),
                 _cell("code", "figures.curves(path)",
                       outputs=[_shown("image/png")])]
        (box / "Method/Notebooks/Report.ipynb").write_text(
            json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                        "nbformat_minor": 5}), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(CLI), "verify", "--target", str(box),
             "--name", "Method", "--revision", "r01.md"],
            capture_output=True, text=True, cwd=FORGE)

    def test_a_target_that_declares_no_record_still_gets_an_answer(self):
        """Reachable red by making either default `None`: the membership test at
        the top of `report_state` runs before anything else in the report check,
        so `p.name in None` takes down the whole command for every target that
        declared no record — which is every target that has not got that far yet.
        """
        proc = self.verify()
        self.assertEqual(proc.stderr, "", proc.stderr)
        report = json.loads(proc.stdout or "{}")["report"]
        self.assertIn(
            report["status"], ("ok", "drift", "incomplete"),
            "the report check has to reach a verdict on a target that declared "
            "no record, rather than reaching for a filename it read in somebody "
            "else's repository or falling over on the way")

    def test_the_toy_target_left_nothing_behind(self):
        self.verify()
        # Run the registered cleanup now, so what is asserted is the state a
        # later test would find rather than the state mid-test.
        self.doCleanups()
        leftover = list((FORGE / "implementations").glob("_norecord_*"))
        self.assertEqual([str(path) for path in leftover], [])


class DeclarationBlockRosterTests(unittest.TestCase):
    """Three places say this flow asks for the declaration's `revision` and
    `premises`, and no step of it did.

    The doctrine says so where the declaration is described, `declare-first`
    blames the reader for not having done it, and the kit's own scaffold says
    the value is "asked for by the flow, never invented here". Flow A's sixteen
    steps contain no such ask: every `revision` in them is the `--revision` flag
    of `admit` and `verify`, and `premises` appears nowhere at all. So the first
    pass of every new target ends at a rung whose named remedy does not exist.

    What this holds is weaker than it looks and is stated rather than claimed
    away: Flow A is prose executed by an agent, so there is no runtime path to
    assert against and no behavioural partner for these tests. What they can do
    is hold every declaration block to a step that exists and mentions it, which
    is what makes a renumbering or a deleted step fail here instead of silently
    on somebody's first pass.
    """

    KIT_DECLARATION = KIT / "src_benchmark" / "__init__.py"
    BLOCK_TABLE_HEADER = "| Block | Filled by | When |"
    FLOW_HEADING = "## Flow A — first pass"
    STEP_RE = re.compile(r"^(\d+)\.\s")

    def declared_blocks(self):
        """The six top-level keys of `__benchmark__`, read from the kit.

        From the file the scaffold actually copies, so a block added there has
        to be given a filling step rather than appearing in a target nobody told
        how to fill it.
        """
        tree = ast.parse(self.KIT_DECLARATION.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "__benchmark__" not in names:
                continue
            self.assertIsInstance(node.value, ast.Dict)
            return [key.value for key in node.value.keys
                    if isinstance(key, ast.Constant)]
        self.fail("the kit declares no `__benchmark__` literal")

    def flow_steps(self):
        """Flow A's numbered steps, as {number: the whole step's text}."""
        text = SKILL_MD.read_text(encoding="utf-8")
        start = text.index(self.FLOW_HEADING)
        end = text.index("\n## ", start + len(self.FLOW_HEADING))
        steps: dict[int, list[str]] = {}
        current = None
        for line in text[start:end].splitlines():
            match = self.STEP_RE.match(line)
            if match:
                current = int(match.group(1))
                steps[current] = []
            if current is not None:
                steps[current].append(line)
        return {number: "\n".join(lines) for number, lines in steps.items()}

    def block_rows(self):
        tables = markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), self.BLOCK_TABLE_HEADER)
        self.assertEqual(
            len(tables), 1,
            "the declaration's blocks are stated in no parseable table, so "
            "which step fills each one is prose and drifts unobserved")
        return tables[0]

    def test_every_declaration_block_has_a_row(self):
        self.assertEqual(
            sorted(row[0].strip("`") for row in self.block_rows()),
            sorted(self.declared_blocks()),
            "a block the kit scaffolds is named in no row, or a row names a "
            "block the kit does not scaffold")

    def test_every_flow_a_cell_names_a_step_that_mentions_its_block(self):
        """The clause that makes the table more than a list.

        A cell saying `step 8` is worth nothing if step 8 was renumbered, or if
        it never mentions the block the row is about. Reachable red by changing
        one cell to a step that does not exist, and by deleting the mention.
        """
        steps = self.flow_steps()
        broken = []
        for row in self.block_rows():
            block, filled_by = row[0].strip("`"), row[1]
            match = re.search(r"Flow A step (\d+)", filled_by)
            if not match:
                continue
            number = int(match.group(1))
            if number not in steps:
                broken.append((block, f"step {number} does not exist"))
            elif block not in steps[number]:
                broken.append((block, f"step {number} never mentions it"))
        self.assertEqual(broken, [])

    def test_flow_a_asks_for_the_revision_and_the_premises(self):
        """The finding itself: three assertions and no step.

        Scoped to the step behind the authorization gate, because that is where
        the answers exist — the gate's own protocol draft has already produced a
        prediction, a statistical unit, a metric and a direction — and because
        `AGREEMENTS.md`'s rule is already "append at every gate, before writing
        any code the gate authorized".
        """
        steps = self.flow_steps()
        self.assertIn(8, steps, "Flow A has no step 8 to hold this to")
        for field in ("revision", "premises"):
            self.assertIn(
                f"`{field}`", steps[8],
                f"Flow A step 8 never asks for the declaration's `{field}`, "
                "which the doctrine, `declare-first` and the kit all say it does")

    def test_the_three_assertions_still_say_the_flow_asks(self):
        """If any of the three stopped claiming it, this repair would be
        answering a question nobody asks any more — so the claims are pinned
        beside the step that now honours them."""
        skill = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn(
            "**`revision` and `premises` are asked by this flow, never invented.**",
            skill)
        self.assertIn("Flow A's ask for `revision` and `premises`", skill)
        self.assertIn(
            "asked for by the flow, never invented here",
            self.KIT_DECLARATION.read_text(encoding="utf-8"))


class SeventhScaffoldBlockTests(unittest.TestCase):
    """The scaffold's `__benchmark__` literal gains a seventh block, `entry`,
    prefilled empty exactly like the other six — and the doctrine's own count
    of "six blocks" moves to seven with it, named here rather than absorbed
    silently.

    This is the one non-additive cost of Decision 10: `probe`'s harness
    resolution can only stop naming `benchmark.py` for every target once a
    target has somewhere of its own to declare a different name instead.
    """

    KIT_DECLARATION = KIT / "src_benchmark" / "__init__.py"

    def declared_blocks(self) -> dict:
        tree = ast.parse(self.KIT_DECLARATION.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "__benchmark__"
                    for t in node.targets):
                return ast.literal_eval(node.value)
        self.fail("the kit declares no `__benchmark__` literal")

    def test_the_scaffold_declares_seven_blocks_not_six(self):
        declared = self.declared_blocks()
        self.assertEqual(
            sorted(declared),
            ["arms", "distribution", "entry", "premises", "report",
             "revision", "search"],
            "the scaffold must carry exactly seven top-level blocks")

    def test_the_entry_block_is_prefilled_empty(self):
        declared = self.declared_blocks()
        self.assertEqual(declared["entry"], {"module": "", "function": ""})

    def test_the_doctrine_names_seven_blocks_not_six(self):
        """The prose that counted the blocks has to count seven now, or the
        doctrine is the one place still telling a reader the old number."""
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("its seven blocks", text)
        self.assertNotIn("its six blocks", text)
        self.assertIn("all seven top-level blocks", text)

    def test_a_fresh_untouched_scaffold_still_reads_as_blank(self):
        """The seventh block's own blank value is `{"module": "", "function":
        ""}` — a non-empty dict, unlike every other block's `{}` or `""`.
        Bare truthiness would read that dict as an answer nobody gave, and a
        freshly materialized target would report `"declared"` before a
        single block had anything written into it."""
        self.assertTrue(impl._declaration_is_blank(self.declared_blocks()))


class VerifyStatusRosterTests(unittest.TestCase):
    """The Output Contract enumerated eleven statuses and `verify` reports
    thirteen.

    `coupling` and `lfs` were computed, returned and named in no doctrine at
    all — not in the contract that lists what the command reports, not in the
    usage reference a reader follows to read the output. A reader who took the
    contract at its word would find two keys in the JSON nobody had told them
    existed, and would have no way to know whether either one gates.

    The repair is not a longer sentence. A prose list cannot be held to a return
    statement, so the list becomes a table with one row per status, and the
    table is derived-against rather than proof-read: adding a status to `verify`
    now fails this suite until its row exists, which is the whole point.

    What the table cannot do: columns two and three are prose and are not
    asserted. That a row says `never gates` is a claim a human makes; the
    behavioural partner for `coupling` is the `coupling_state` tests that
    already exist.
    """

    STATUS_TABLE_HEADER = "| Status | What it reports | Gates? |"

    #: The envelope, not a status: which command answered, about what, under
    #: which name. Documenting these as statuses would be documenting the shape
    #: of the reply rather than anything the command found.
    IDENTITY_KEYS = frozenset({"command", "target", "name"})

    def reported_statuses(self):
        return sorted(set(returned_keys(CLI, "cmd_verify")) - self.IDENTITY_KEYS)

    def status_rows(self):
        tables = markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), self.STATUS_TABLE_HEADER)
        self.assertEqual(
            len(tables), 1,
            "`verify`'s statuses are stated in no parseable table, so the "
            "Output Contract cannot be held to what the command returns")
        return tables[0]

    def documented_statuses(self):
        return sorted(row[0].strip("`") for row in self.status_rows())

    def test_the_contract_names_every_status_verify_reports(self):
        reported = self.reported_statuses()
        documented = self.documented_statuses()
        self.assertEqual(
            sorted(set(reported) - set(documented)), [],
            "`verify` returns these and the Output Contract names them nowhere")
        self.assertEqual(
            sorted(set(documented) - set(reported)), [],
            "the Output Contract names these and `verify` returns no such key")

    def test_coupling_is_documented_as_reported_and_never_gating(self):
        """The row that had to exist before the roster could be honest.

        The rejected fourth rule was "every reported fact must be branched on or
        documented", and it is false by construction: `coupling` is computed,
        reported, and deliberately gates nothing. So the bar is documentation,
        and the `Gates?` column is what carries the difference.
        """
        gating = {row[0].strip("`"): row[2] for row in self.status_rows()}
        self.assertIn("coupling", gating)
        self.assertIn("never", gating["coupling"].lower())

    def test_the_usage_reference_tells_a_reader_how_to_read_them(self):
        """The contract says what is reported; `usage.md` is where somebody
        goes to find out what to do about it. Two statuses reached the JSON
        without reaching either."""
        usage = USAGE_MD.read_text(encoding="utf-8")
        section = usage[usage.index("## Reading `verify`"):]
        section = section[:section.index("\n## ", 1)]
        for status in ("coupling", "lfs", "position"):
            self.assertIn(f"`{status}`", section)

    def test_the_roster_names_a_renamed_key(self):
        """Reachability, measured rather than asserted.

        This test is red by construction — it was written against a contract
        naming eleven statuses and a command returning thirteen — so it needs no
        inversion of the doctrine. What it does still owe is a demonstration
        that the failure *names* the divergence rather than reporting a bare
        inequality, which is the difference between a lock somebody can act on
        and one they have to go looking behind.
        """
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        copy = scratch / "renamed_cli.py"
        copy.write_text(
            CLI.read_text(encoding="utf-8").replace(
                '        "lfs": lfs_state(target),',
                '        "largeFiles": lfs_state(target),'),
            encoding="utf-8")
        renamed = set(returned_keys(copy, "cmd_verify")) - self.IDENTITY_KEYS
        self.assertEqual(sorted(renamed - set(self.documented_statuses())),
                         ["largeFiles"])
        self.assertEqual(sorted(set(self.documented_statuses()) - renamed),
                         ["lfs"])


class ProbeReportedFactsRosterTests(unittest.TestCase):
    """`probe` computes seventeen keys and the doctrine enumerated none of
    them, so two facts a reader needs before spending machine time — whether
    a job ever rehearsed, and whether the commit it is pinned to still
    matches the repository — reached the JSON and no page.

    **Why they are documented and never gating, stated as a position rather
    than left as an omission.** `remote_execution_jobs_state()` answers
    `{"jobs": [], "services": 0, "smokeReady": {}}` when the remote-execution
    CLI is not on disk at all, which is byte-identical to what it answers for
    a repository that has the CLI and has generated no job. The fact as
    computed cannot tell "not ready" from "does not apply", and a rung needs
    exactly that difference: branching on it would suppress a legitimate
    `benchmark` answer for every repository that never sends work anywhere.
    So the ladder is left alone and the reader is handed the fact beside the
    answer.

    **The falsifier, recorded rather than implied.** If
    `remote_execution_jobs_state()` grew a per-job link to the campaign about
    to be offered — so that an unrehearsed job could be tied to the run being
    proposed rather than to the repository in general — the distinction
    becomes expressible and this position should be revisited. Until then it
    is not, and the behavioural test below is what makes that a decision
    somebody can overturn instead of a gap nobody noticed.

    What this roster cannot do is the same limit the `verify` roster carries:
    columns two and three are prose and are not asserted. That a row says a
    fact never gates is a claim a human makes; the behavioural test in this
    class is what carries it for `smokeReady`.
    """

    FACT_TABLE_HEADER = "| Fact | What it reports | Gates? |"
    JOB_FACT_TABLE_HEADER = "| Job fact | What it reports | Gates? |"
    GATES_TABLE_HEADER = "| Situation | Action |"

    #: The envelope, not a fact about the repository: `status` and `kind` are
    #: string literals in the return, identical for every target that reaches
    #: it, and `target`/`name` say which repository was asked. Documenting any
    #: of the four as a reported fact would document the shape of the reply.
    IDENTITY_KEYS = frozenset({"status", "target", "name", "kind"})

    def reported_facts(self):
        return sorted(set(returned_keys(CLI, "cmd_probe")) - self.IDENTITY_KEYS)

    def fact_rows(self):
        tables = markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), self.FACT_TABLE_HEADER)
        self.assertEqual(
            len(tables), 1,
            "`probe`'s reported facts are stated in no parseable table, so "
            "the doctrine cannot be held to what the command returns")
        return tables[0]

    def job_fact_rows(self):
        tables = markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), self.JOB_FACT_TABLE_HEADER)
        self.assertEqual(
            len(tables), 1,
            "the job-folder facts folded into `remoteExecution` are stated in "
            "no parseable sub-table, so nothing holds them to the function "
            "that computes them")
        return tables[0]

    def test_the_doctrine_names_every_fact_probe_reports(self):
        reported = self.reported_facts()
        documented = sorted(row[0].strip("`") for row in self.fact_rows())
        self.assertEqual(
            sorted(set(reported) - set(documented)), [],
            "`probe` returns these and the doctrine names them nowhere")
        self.assertEqual(
            sorted(set(documented) - set(reported)), [],
            "the doctrine names these and `probe` returns no such key")

    def test_the_remote_execution_row_carries_its_job_facts(self):
        """`remoteExecution` is two sources folded under one key: the ledger
        and the filesystem. One row cannot say what a reader is looking at,
        so the row has a sub-table, and the sub-table is derived from the
        function that computes the second half.
        """
        derived = sorted(returned_keys(CLI, "remote_execution_jobs_state"))
        documented = sorted(row[0].strip("`") for row in self.job_fact_rows())
        self.assertEqual(
            sorted(set(derived) - set(documented)), [],
            "`remote_execution_jobs_state` returns these and the sub-table "
            "names them nowhere")
        self.assertEqual(
            sorted(set(documented) - set(derived)), [],
            "the sub-table names these and no such key is computed")

    def test_smoke_ready_is_documented_as_reported_and_never_gating(self):
        gating = {row[0].strip("`"): row[2] for row in self.job_fact_rows()}
        self.assertIn("smokeReady", gating)
        self.assertIn("never", gating["smokeReady"].lower())

    def test_the_decision_gates_send_a_reader_to_both_facts(self):
        """A fact reported beside an offer to run is only read if something
        tells the reader to read it. The Decision Gates table is where this
        skill says what to do about a state, so that is where both belong.
        """
        rows = markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), self.GATES_TABLE_HEADER)
        self.assertEqual(len(rows), 1, "the Decision Gates table moved")
        situations = "\n".join(row[0] for row in rows[0])
        self.assertIn("smokeReady", situations,
                      "no gate row tells a reader to read a job that never "
                      "rehearsed before offering a campaign")
        self.assertIn("staleness", situations,
                      "no gate row tells a reader to read a job pinned to a "
                      "commit the repository has moved past")
        self.assertIn("position: \"stale\"", situations,
                      "no gate row tells a reader the position section is "
                      "bound to a revision that has moved on")
        self.assertIn("position.disagreements", situations,
                      "no gate row tells a reader a recorded mark contradicts "
                      "its own measured evidence")
        self.assertIn("NOT_READY", situations,
                      "no gate row tells a reader why `gate` refused a launch "
                      "with no passing rehearsal on file")

    def test_the_usage_reference_tells_a_reader_what_to_do_about_them(self):
        usage = USAGE_MD.read_text(encoding="utf-8")
        section = usage[usage.index("## Reading `probe`"):]
        section = section[:section.index("\n## ", 1)]
        for fact in ("smokeReady", "staleness"):
            self.assertIn(f"`{fact}`", section)

    #: A target the ladder actually offers a run for. Every earlier rung has
    #: to be satisfied — a baseline to compare against, a trainable backend,
    #: a declaration, a faithful arm, no submission out, no declared search,
    #: and a report that agrees with the code — because a fixture answering
    #: `report-first` would never reach the branch this class is about.
    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {'floor': {'sections': ['3']}, "
        "'full': {'sections': ['3']}},\n"
        "    'report': {'renderers': ['tables.render'],\n"
        "               'conclusions': ['tables.conclude'],\n"
        "               'conclusionEntry': 'tables.conclude',\n"
        "               'objectiveEntry': 'tables.aim',\n"
        "               'figures': [],\n"
        "               'dimensions': {'scale': 'higher'},\n"
        "               'components': {'first': 'the first term'},\n"
        "               'record': 'summary.json',\n"
        "               'records': ['Results/summary.json']},\n"
        "    'entry': {'module': 'Method_Benchmark.benchmark',\n"
        "              'function': 'run'},\n"
        "}\n")
    WIRING = ("from Method.called import called\n"
              "from Method.never_called import total\n")
    TABLES = ("def render(record):\n"
              "    return record\n\n"
              "def aim(record):\n"
              "    return {'scale': 0.5}\n\n"
              "def conclude(record):\n"
              "    return {'scale': f\"{record['cells'][0]['value']}\"}\n")

    def build_target(self, suffix):
        """A target the ladder answers `benchmark` for, built for the purpose.

        The interpreter under `.venv/` is a link to the one running this suite
        rather than a built environment: the live half of the report check only
        needs an interpreter that can import the target's own package off
        `src/`, and building a real environment per test would buy nothing and
        cost seconds.
        """
        box = FORGE / "implementations" / f"_smokebox_{suffix}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        for directory in ("src/Method", "src/Method_Benchmark", "src/Prior",
                          "Method/Results"):
            (box / directory).mkdir(parents=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "src/Method/called.py").write_text(
            _module("r01.md", ["3"], ["11"], imports="import torch\n"),
            encoding="utf-8")
        (box / "src/Method/never_called.py").write_text(
            _module("r01.md", ["3"], ["12"], imports="import torch\n"),
            encoding="utf-8")
        (box / "src/Prior/model.py").write_text("import torch\n", encoding="utf-8")
        (box / "src/Method_Benchmark/__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        (box / "src/Method_Benchmark/wiring.py").write_text(
            self.WIRING, encoding="utf-8")
        (box / "src/Method_Benchmark/config.py").write_text(
            "SCALES = [1, 2, 3]\n", encoding="utf-8")
        (box / "src/Method_Benchmark/tables.py").write_text(
            self.TABLES, encoding="utf-8")
        # The declared entry module `introspect` now executes as its liveness
        # check (Decision 9) — undeclared here, so it falls back to the
        # scaffold's own harness-file convention (`BENCHMARK_MODULE`). Present
        # and importable, exactly as a repository that has actually run one
        # would have it.
        (box / f"src/Method_Benchmark/{impl.BENCHMARK_MODULE}").write_text(
            "import torch\n", encoding="utf-8")
        (box / "Method/Results/summary.json").write_text(
            json.dumps({"cells": [{"value": 1.0, "first": 0.5}]}),
            encoding="utf-8")

        write_fixture_interpreter(
            box / ".venv" / ("Scripts" if os.name == "nt" else "bin"))

        git = ["git", "-c", "user.email=forge@example.invalid",
               "-c", "user.name=forge", "-C", str(box)]
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-qm", "toy"], check=True,
                       capture_output=True)
        head = subprocess.run(git + ["rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
        return box, head

    def write_job_folder(self, box, commit):
        """One job folder in the shape `guard_entrypoint()` admits and
        `generate-job` writes — `<target>/tools/<service>/<job-name>/` around a
        `run-config.json`. Written to disk rather than faked, because the fact
        under test is read from disk by the same reader every other command
        uses, and a hand-shaped dict would prove nothing about what `probe`
        finds.
        """
        job_dir = box / "tools" / "service" / "job"
        job_dir.mkdir(parents=True)
        (job_dir / "run-config.json").write_text(json.dumps({
            "schemaVersion": 1,
            "product": "Method",
            "service": "service",
            "jobName": "job",
            "commit": commit,
            "repo": {"url": "https://example.invalid/toy.git", "ref": "main"},
            "clonePaths": ["src"],
            "run": {"module": "Method_Benchmark.wiring", "function": "main",
                    "kwargs": {}},
            "runnerTemplate": {},
        }), encoding="utf-8")

    def probe(self, box):
        proc = subprocess.run(
            [sys.executable, str(CLI), "probe", "--target", str(box),
             "--name", "Method", "--revision", "r01.md"],
            capture_output=True, text=True, cwd=FORGE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout or "{}")

    def test_the_fixture_reaches_the_run_offer_before_any_job_folder_exists(self):
        """The pole. Without it every assertion below could be passing because
        the ladder never got near the offer, and nothing would say so."""
        box, _ = self.build_target("pole")
        probe = self.probe(box)
        self.assertEqual(probe["report"]["status"], "ok")
        self.assertEqual(probe["nextStep"], "benchmark")

    def test_a_job_that_never_rehearsed_still_reaches_the_benchmark_offer(self):
        """The position, made behavioural.

        A sentence saying the ladder does not branch on `smokeReady` is a
        sentence anybody can contradict with four lines of code and nothing
        going red. This is the test such a change has to break.
        """
        box, head = self.build_target("ready")
        self.write_job_folder(box, head)
        probe = self.probe(box)
        self.assertEqual(
            probe["remoteExecution"]["smokeReady"], {"job": False},
            "the fixture stopped producing an unrehearsed job, so this test "
            "is no longer about anything")
        self.assertEqual(probe["nextStep"], "benchmark")

    def test_a_job_pinned_to_a_commit_that_is_not_in_the_history_still_offers_the_run(self):
        """The other half of the same position. A pin nothing in the history
        matches reports `unknown` — the honest verdict, and still not a rung.
        """
        box, _ = self.build_target("stale")
        self.write_job_folder(box, "0" * 40)
        probe = self.probe(box)
        self.assertEqual(
            [job["staleness"]["status"]
             for job in probe["remoteExecution"]["jobs"]],
            ["unknown"])
        self.assertEqual(probe["nextStep"], "benchmark")

    def test_the_toy_targets_left_nothing_behind(self):
        box, head = self.build_target("cleanup")
        self.write_job_folder(box, head)
        self.probe(box)
        self.doCleanups()
        leftover = list((FORGE / "implementations").glob("_smokebox_*"))
        self.assertEqual(leftover, [], leftover)


def dict_literal_keys(source: Path, name: str) -> list[str]:
    """The string keys of a module-level dict assigned to `name`.

    The same argument `returned_keys` makes, one scope out: a list of commands
    written twice — once in the code that dispatches them and once in the
    reference somebody reads — is a list that loses one. Read it from the
    dispatch table instead.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        return sorted(key.value for key in node.value.keys
                      if isinstance(key, ast.Constant)
                      and isinstance(key.value, str))
    raise AssertionError(f"{source.name} assigns no module-level dict {name}")


class WorkedInvocationRosterTests(unittest.TestCase):
    """`usage.md` opens by promising that everything below it is a real
    invocation of the CLI, and three of the CLI's nine commands had none.

    `probe` is the one that costs something. It is the command the whole
    benchmark half of this skill turns on — it is what answers `nextStep`,
    what the Decision Gates rows are written about, and what a reader is sent
    to before every offer to run — and the worked-invocation reference never
    showed anybody how to call it. `name` and `compose` are the same absence
    with less riding on it.

    The lock is a roster rather than three assertions, so a command added to
    the dispatch table fails this suite until somebody has shown how to run
    it. What it cannot check is whether the invocation shown is *correct*:
    that the flags exist is asserted below against the parser, but that the
    output described underneath is what the command actually prints is prose,
    and the end-to-end tests elsewhere in this file are what carry it.
    """

    INVOCATION_RE = re.compile(r"implementation_cli\.py\s+([a-z][a-z-]*)")

    def worked_invocations(self):
        return sorted(set(self.INVOCATION_RE.findall(
            USAGE_MD.read_text(encoding="utf-8"))))

    def dispatched_commands(self):
        return dict_literal_keys(CLI, "COMMANDS")

    def test_every_command_the_cli_dispatches_has_a_worked_invocation(self):
        dispatched = self.dispatched_commands()
        self.assertTrue(dispatched, "the dispatch table was read as empty")
        worked = self.worked_invocations()
        self.assertEqual(
            sorted(set(dispatched) - set(worked)), [],
            "the CLI dispatches these and `usage.md` works none of them, "
            "though it opens by saying everything below it is a real "
            "invocation")
        self.assertEqual(
            sorted(set(worked) - set(dispatched)), [],
            "`usage.md` works these and the CLI dispatches no such command")

    def worked_block(self, command):
        """The fenced invocation for one command, as argv."""
        usage = USAGE_MD.read_text(encoding="utf-8")
        block = usage[usage.index(f"implementation_cli.py {command}"):]
        block = block[:block.index("```")]
        argv = [command]
        for line in block.splitlines()[1:]:
            argv.extend(line.strip().rstrip("\\").strip().split())
        return argv

    def test_the_probe_invocation_uses_flags_the_real_parser_accepts(self):
        """A worked invocation nobody can run is a worse promise than none.

        Proven against the CLI's own parser rather than against a second copy
        of its argument list: the example is handed to the real process with a
        target that does not exist, so argparse sees every flag. A guard
        refusal prints JSON and means the flags were accepted; an unrecognized
        flag never gets that far.
        """
        argv = self.worked_block("probe")
        self.assertIn("--target", argv)
        self.assertIn("--name", argv)
        proc = subprocess.run(
            [sys.executable, str(CLI), *argv], capture_output=True, text=True,
            cwd=FORGE)
        self.assertNotIn("unrecognized arguments", proc.stderr)
        self.assertEqual(json.loads(proc.stdout or "{}").get("status"),
                         "refused", proc.stderr)

    def test_the_step_invocation_uses_flags_the_real_parser_accepts(self):
        argv = self.worked_block("step")
        self.assertIn("--target", argv)
        self.assertIn("--name", argv)
        self.assertIn("--step", argv)
        proc = subprocess.run(
            [sys.executable, str(CLI), *argv], capture_output=True, text=True,
            cwd=FORGE)
        self.assertNotIn("unrecognized arguments", proc.stderr)
        self.assertEqual(json.loads(proc.stdout or "{}").get("status"),
                         "refused", proc.stderr)

    def test_the_reference_shows_what_probe_answers(self):
        """An invocation with no output beside it teaches a reader to run the
        command and nothing about how to read what comes back. `nextStep` is
        the answer, so it belongs where the invocation is."""
        usage = USAGE_MD.read_text(encoding="utf-8")
        section = usage[usage.index("## Probe — what stands between this"):]
        section = section[:section.index("\n## ", 1)]
        self.assertIn("implementation_cli.py probe", section)
        self.assertIn("`nextStep`", section)


def subcommand_surface(source: Path, function: str) -> dict[str, tuple[str, ...]]:
    """Every subcommand a parser-building function declares, with its flags.

    Nested groups are followed, so a subcommand reached only through another
    one is reported by the whole path a reader would have to type. Only the
    leaves are returned: a group parser whose subcommands are `required=True`
    names no invocation — typing it alone is refused — so documenting it as a
    command would document something nobody can run.

    Read from the parser rather than from a list beside it, for the reason
    `returned_keys` is: a roster restated by hand is a roster that loses one.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    definition = next(
        (node for node in ast.walk(tree)
         if isinstance(node, ast.FunctionDef) and node.name == function), None)
    if definition is None:
        raise AssertionError(f"{source.name} defines no {function}")

    groups: dict[str, str] = {}
    commands: dict[str, str] = {}
    flags: dict[str, list[str]] = {}
    owners: set[str] = set()

    def only_target(node):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None
        return node.targets[0].id

    for node in ast.walk(definition):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call, name = node.value, only_target(node)
            attribute = call.func.attr if isinstance(call.func, ast.Attribute) else ""
            holder = (call.func.value.id
                      if isinstance(call.func, ast.Attribute)
                      and isinstance(call.func.value, ast.Name) else "")
            if attribute == "add_subparsers":
                if name is not None:
                    groups[name] = commands.get(holder, "")
                owners.add(commands.get(holder, ""))
                continue
            if attribute == "add_parser" and holder in groups and call.args:
                literal = call.args[0]
                if not isinstance(literal, ast.Constant):
                    continue
                path = f"{groups[holder]} {literal.value}".strip()
                flags.setdefault(path, [])
                if name is not None:
                    commands[name] = path
                continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument" \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in commands and node.args \
                and isinstance(node.args[0], ast.Constant) \
                and str(node.args[0].value).startswith("--"):
            flags[commands[node.func.value.id]].append(node.args[0].value)

    return {path: tuple(sorted(set(declared)))
            for path, declared in flags.items() if path not in owners}


def required_flags(source: Path, function: str) -> dict[str, tuple[str, ...]]:
    """The subset of `subcommand_surface` each subcommand marks `required=True`.

    A standalone reading, deliberately not folded into `subcommand_surface`
    itself: that function is one of `CopiedHelperFidelityTests`' pinned
    copies (`test_skill_audit.py` holds a byte-identical one), so changing
    its body here would drift the copy out from under a suite this change
    does not own. This performs the identical `_build_parser()` walk,
    narrowed to the flags that define a row's shape -- the reason
    `readiness` (`--job-dir`/`--worker`) is not `--target`/`--entrypoint`
    shaped the way every neighbouring row in the guiding table is.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    definition = next(
        (node for node in ast.walk(tree)
         if isinstance(node, ast.FunctionDef) and node.name == function), None)
    if definition is None:
        raise AssertionError(f"{source.name} defines no {function}")

    groups: dict[str, str] = {}
    commands: dict[str, str] = {}
    flags: dict[str, list[str]] = {}
    owners: set[str] = set()

    def only_target(node):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None
        return node.targets[0].id

    def is_required(call: ast.Call) -> bool:
        for keyword in call.keywords:
            if keyword.arg == "required":
                return isinstance(keyword.value, ast.Constant) \
                    and keyword.value.value is True
        return False

    for node in ast.walk(definition):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call, name = node.value, only_target(node)
            attribute = call.func.attr if isinstance(call.func, ast.Attribute) else ""
            holder = (call.func.value.id
                      if isinstance(call.func, ast.Attribute)
                      and isinstance(call.func.value, ast.Name) else "")
            if attribute == "add_subparsers":
                if name is not None:
                    groups[name] = commands.get(holder, "")
                owners.add(commands.get(holder, ""))
                continue
            if attribute == "add_parser" and holder in groups and call.args:
                literal = call.args[0]
                if not isinstance(literal, ast.Constant):
                    continue
                path = f"{groups[holder]} {literal.value}".strip()
                flags.setdefault(path, [])
                if name is not None:
                    commands[name] = path
                continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument" \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in commands and node.args \
                and isinstance(node.args[0], ast.Constant) \
                and str(node.args[0].value).startswith("--") \
                and is_required(node):
            flags[commands[node.func.value.id]].append(node.args[0].value)

    return {path: tuple(sorted(set(declared)))
            for path, declared in flags.items() if path not in owners}


class RemoteExecutionCommandRosterTests(unittest.TestCase):
    """This flow depends on a CLI it never names.

    `probe` reports a remote-execution state, the `poll-first` rung tells a
    reader to wait for a submission's answer, the drift and unreliable states
    told them to reconcile the ledger by hand, and the argument for a `tools/`
    directory rests on a job folder somebody has to have produced. Not one of
    the eight subcommands that do any of that appeared anywhere a reader of
    this skill looks — not in `SKILL.md`, not in `references/usage.md`. The
    remedy for a drifted ledger existed only inside a Python docstring.

    Two rules, because the repair has two halves that fail differently:

    - the roster derives the subcommands from the parser and holds them to a
      table, so a subcommand added there forces a doctrine decision;
    - the flag lists are deliberately *not* duplicated. `usage.md` shows the
      shape of three invocations and points at the `remote-execution` skill
      for the rest, and a test asserts that what it shows stays a proper
      subset of what the parser declares. Two copies of a flag list is the
      drift this whole change is about.

    What the table cannot check is whether the state named in column two is
    the state that really routes there. That is prose, and `probe`'s own
    end-to-end tests are what carry it.
    """

    TABLE_HEADER = SEAM_TABLE_HEADER
    GATES_TABLE_HEADER = "| Situation | Action |"

    @classmethod
    def remote_cli(cls):
        return impl.REMOTE_EXECUTION_CLI_SCRIPT

    def declared_subcommands(self):
        surface = subcommand_surface(self.remote_cli(), "_build_parser")
        self.assertTrue(surface, "the remote-execution parser was read as empty")
        return surface

    def table_rows(self):
        tables = markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), self.TABLE_HEADER)
        self.assertEqual(
            len(tables), 1,
            "the remote-execution subcommands are stated in no parseable "
            "table, so nothing holds this flow to the CLI it depends on")
        return tables[0]

    def test_every_subcommand_the_parser_declares_has_a_row(self):
        declared = sorted(self.declared_subcommands())
        documented = sorted(row[0].strip("`") for row in self.table_rows())
        self.assertEqual(
            sorted(set(declared) - set(documented)), [],
            "the remote-execution CLI declares these and this skill names "
            "them nowhere")
        self.assertEqual(
            sorted(set(documented) - set(declared)), [],
            "the table names these and the parser declares no such subcommand")

    def test_the_rung_that_says_to_wait_names_the_subcommand_that_waits(self):
        """`poll-first` tells a reader a submission is out and the answer has
        not come back. It never said what to run. The row exists so the rung
        resolves to something typeable."""
        rows = {row[0].strip("`"): row[1] for row in self.table_rows()}
        self.assertIn("poll", rows)
        self.assertIn("poll-first", rows["poll"])

    def test_the_named_remedy_reaches_the_reader_at_both_ends(self):
        """A remedy reachable only from a Python docstring is not a remedy.

        `drift` and `unreliable` are the two states this flow reports and
        explicitly refuses to treat as "wait for it", and the fix for both was
        described as manual work. It is a subcommand, and it is named where
        the state is reported and again in the table a reader consults about
        what to do."""
        text = SKILL_MD.read_text(encoding="utf-8")
        section = text[text.index('### `nextStep: "poll-first"`'):]
        section = section[:section.index("\n### ", 1)]
        self.assertIn("`remote_cli reconcile`", section,
                      "the drift paragraph still describes the fix as manual "
                      "work and names no command")
        gates = markdown_table_rows(text, self.GATES_TABLE_HEADER)
        self.assertEqual(len(gates), 1, "the Decision Gates table moved")
        actions = "\n".join(row[1] for row in gates[0])
        self.assertIn("remote_cli reconcile", actions,
                      "no Decision Gates row names the command that repairs a "
                      "drifted ledger")

    def test_the_tools_argument_names_what_writes_the_directory(self):
        """The layout section argues at length that `tools/` has to exist and
        never said what puts anything in it. One command does, and it writes
        one exact shape."""
        text = SKILL_MD.read_text(encoding="utf-8")
        section = text[text.index("**And `tools/` exists for the same reason"):]
        section = section[:section.index("\n## ", 1)]
        self.assertIn("`remote_cli generate-job`", section)
        self.assertIn("tools/<service>/<job-name>/", section)

    def test_the_usage_reference_works_three_invocations_and_copies_no_flag_list(self):
        """The other half of the repair, and the one that could rot.

        A reference that reprints the flag list is a second copy of it, and
        two copies of a flag list is exactly the drift this change exists to
        remove. So what `usage.md` shows has to stay a proper subset of what
        the parser declares, measured rather than promised.
        """
        usage = USAGE_MD.read_text(encoding="utf-8")
        section = usage[usage.index("## The remote-execution seam"):]
        section = section[:section.index("\n## ", 1)]
        self.assertIn("remote-execution", section,
                      "the section points nowhere for the flags it withholds")
        declared = self.declared_subcommands()
        for command in ("poll", "reconcile", "generate-job"):
            self.assertIn(f"remote_cli.py {command}", section)
            shown = {flag for flag in re.findall(r"--[a-z][a-z-]*", section)
                     if flag in declared[command]}
            self.assertTrue(
                shown, f"the {command} invocation shows no flag at all")
            self.assertLess(
                len(shown), len(declared[command]),
                f"`usage.md` reprints every flag {command} declares, which is "
                "a second copy of a list this skill does not own")


class GuidingTableFlagsTests(unittest.TestCase):
    """The table named subcommands and never how to call them.

    Followed literally, `readiness` reads like every neighbouring row —
    `--target`/`--entrypoint` — because nothing in the table said otherwise.
    It takes `--job-dir`/`--worker` instead, and the mismatch surfaces only
    as a usage error, which reads like the reader's fault rather than the
    table's.

    And no row at all answered a job folder that *exists* and is pinned to a
    commit that has moved: `generate-job`'s row covers an absent folder,
    `reconcile`'s covers the ledger and the service disagreeing, and a
    stale pin fell between both.

    Both repairs read `_build_parser()` rather than restate it, the same way
    `RemoteExecutionCommandRosterTests` already derives column one: a flags
    column that is hand-typed is the exact drift this table exists to
    remove, so it is checked against `required_flags()` — the same walk,
    narrowed to what `required=True` marks — instead of being taken on
    faith.
    """

    TABLE_HEADER = SEAM_TABLE_HEADER

    @classmethod
    def remote_cli(cls):
        return impl.REMOTE_EXECUTION_CLI_SCRIPT

    def declared_required(self):
        surface = required_flags(self.remote_cli(), "_build_parser")
        self.assertTrue(surface, "the remote-execution parser was read as empty")
        return surface

    def table_rows(self):
        tables = markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), self.TABLE_HEADER)
        self.assertEqual(
            len(tables), 1,
            "the remote-execution seam table is stated in no parseable "
            "table with a flags column")
        return tables[0]

    @staticmethod
    def flags_cell(cell):
        return {flag.strip().strip("`") for flag in cell.split(",") if flag.strip()}

    def test_every_row_names_its_required_flags(self):
        """Column three has to match `_build_parser()`, not a guess made from
        the shape of the row above it."""
        required = self.declared_required()
        for row in self.table_rows():
            command = row[0].strip("`")
            self.assertIn(command, required,
                          f"{command!r} names no subcommand `_build_parser()` declares")
            self.assertEqual(
                self.flags_cell(row[2]), set(required[command]),
                f"the flags column for {command!r} does not match the "
                "required arguments `_build_parser()` declares for it")

    def test_readiness_is_not_target_entrypoint_shaped(self):
        """The exact mismatch that cost three flag-shape errors in a row."""
        rows = {row[0].strip("`"): row[2] for row in self.table_rows()}
        self.assertIn("readiness", rows)
        shown = self.flags_cell(rows["readiness"])
        self.assertEqual(shown, {"--job-dir", "--worker"})
        self.assertNotIn("--target", shown)
        self.assertNotIn("--entrypoint", shown)

    def test_a_stale_pinned_job_folder_has_its_own_row(self):
        """A job folder that exists, pinned to a commit that has moved, maps
        to no row today — the exact state that blocked a launch this week.
        `generate-job`'s existing row only covers an absent folder."""
        stale_rows = [row for row in self.table_rows()
                      if row[0].strip("`") == "generate-job"
                      and "drift" in row[1]]
        self.assertEqual(
            len(stale_rows), 1,
            "no row answers a job folder that exists with a pin that has "
            "drifted from what the clone paths hold")
        required = self.declared_required()
        self.assertEqual(
            self.flags_cell(stale_rows[0][2]), set(required["generate-job"]),
            "the stale-pin row's flags column does not match "
            "`_build_parser()`'s required generate-job arguments")


class ShardRefusalCrossJoinTests(unittest.TestCase):
    """The doctrine promised a refusal nothing could produce.

    `SKILL.md` says a merge refuses when shards disagree on what they declared
    had to agree — "Not averages — refuses" — and `distribution_state` has
    read a `merged` argument for that purpose since it was written. Nothing in
    this skill ever built one. `shardsDisagree` was empty on every target
    because the only input that could fill it had no caller, and a reader
    seeing an empty list read a refusal that had never been attempted.

    `verify --shards <dir>` is that caller. The disagreement is computed by
    `shard_io.disagreements`, which reads a stamp field at a time and names no
    grouping vocabulary, so the refusal stays as general as the doctrine
    claiming it.

    And the same key that reports the arrived shards was missing from three
    of `distribution_state`'s branches, so it vanished for exactly the targets
    that declare no distribution. That was found by the roster helper rather
    than by reading: its all-returns-agree assertion is what makes a key that
    exists on some branches and not others a failure instead of a surprise.
    """

    def test_every_distribution_branch_reports_the_same_keys(self):
        """Red by construction: the `none`, `absent` and `undeclared` branches
        return `shardsDisagree` and omit `shardsArrived`, so which keys a
        caller gets depends on which branch answered."""
        self.assertIn("shardsArrived", returned_keys(CLI, "distribution_state"))

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {'floor': {'sections': ['3']}, "
        "'full': {'sections': ['3']}},\n"
        "    'distribution': {'axis': 'repetition',\n"
        "                     'poolable': ['score'],\n"
        "                     'perEnvironment': ['wallSeconds'],\n"
        "                     'perRun': ['seed'],\n"
        "                     'identicalAcrossShards': ['epochs', 'datasetSize']},\n"
        "}\n")

    def build_target(self, suffix):
        box = FORGE / "implementations" / f"_shardbox_{suffix}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        for directory in ("src/Method", "src/Method_Benchmark", "Method"):
            (box / directory).mkdir(parents=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "src/Method_Benchmark/__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        return box

    def build_shards(self, stamps):
        """A real shard directory on disk, in the ambient shape `read_shards`
        assumes: one directory per shard, each holding a `shard.json` stamp.

        Written rather than faked, because the whole objection this repairs is
        that a number nobody read off a disk is a number nobody measured.
        """
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for shard, stamp in stamps.items():
            folder = root / shard
            folder.mkdir()
            (folder / "shard.json").write_text(json.dumps(stamp),
                                               encoding="utf-8")
        return root

    def verify(self, box, shards=None, expect=0):
        argv = [sys.executable, str(CLI), "verify", "--target", str(box),
                "--name", "Method"]
        if shards is not None:
            argv += ["--shards", str(shards)]
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=FORGE)
        self.assertEqual(proc.returncode, expect, proc.stderr)
        return proc

    def test_verify_accepts_a_shard_directory(self):
        """Red by construction: the flag the doctrine's refusal needs in order
        to have any input at all does not exist, so `argparse` rejects it
        before the command runs."""
        box = self.build_target("flag")
        shards = self.build_shards({"a": {"epochs": 5}})
        proc = self.verify(box, shards)
        self.assertNotIn("unrecognized arguments", proc.stderr)

    AGREE = {"a": {"epochs": 5, "datasetSize": 100, "score": 0.1},
             "b": {"epochs": 5, "datasetSize": 100, "score": 0.2},
             "c": {"epochs": 5, "datasetSize": 100, "score": 0.3}}
    DISAGREE = {"a": {"epochs": 5, "datasetSize": 100},
                "b": {"epochs": 9, "datasetSize": 100}}

    def distribution(self, box, shards=None):
        return json.loads(self.verify(box, shards).stdout)["distribution"]

    def test_shards_that_disagree_are_refused_and_named(self):
        """The refusal the doctrine promised, produced for the first time.

        Read off the command's own stdout rather than off a call to
        `distribution_state`, because the claim is about what `verify` reports
        and every layer between the flag and the report is part of it.
        """
        box = self.build_target("disagree")
        distribution = self.distribution(box, self.build_shards(self.DISAGREE))

        self.assertEqual(distribution["shardsDisagree"], ["epochs"])
        self.assertEqual(distribution["shardsArrived"], ["a", "b"])
        self.assertEqual(distribution["status"], "incomplete")

    def test_shards_that_agree_report_no_disagreement_and_still_name_what_arrived(self):
        """The pole. Without it the refusal could be firing on any shard
        directory at all and nothing here would notice."""
        box = self.build_target("agree")
        distribution = self.distribution(box, self.build_shards(self.AGREE))

        self.assertEqual(distribution["shardsDisagree"], [])
        self.assertEqual(distribution["shardsArrived"], ["a", "b", "c"])
        # And the shards changed no verdict: agreeing shards are exactly as
        # silent as no shards at all. Compared against the same target rather
        # than against a literal, because this fixture declares dimensions no
        # `config.py` names and would report `incomplete` for that reason
        # alone — which has nothing to do with what came back.
        self.assertEqual(distribution["status"],
                         self.distribution(box)["status"])

    def test_the_arrived_count_is_read_from_disk_and_not_from_a_fixture(self):
        """Behavioural variation rather than inversion.

        A number a test hands to itself proves nothing about a campaign. So one
        shard directory is deleted between two runs of the same command over
        the same target, and what the command reports has to move with it.
        """
        box = self.build_target("shrink")
        shards = self.build_shards(self.AGREE)
        self.assertEqual(self.distribution(box, shards)["shardsArrived"],
                         ["a", "b", "c"])

        shutil.rmtree(shards / "b")
        self.assertEqual(self.distribution(box, shards)["shardsArrived"],
                         ["a", "c"])

    def test_omitting_the_flag_changes_nothing_else_verify_reports(self):
        """A new optional argument is a promise that everything else is where
        it was. Measured by running the same command twice over the same
        target and diffing everything but the three keys the flag exists to
        move."""
        box = self.build_target("omitted")
        without = json.loads(self.verify(box).stdout)
        with_shards = json.loads(self.verify(box, self.build_shards(
            self.DISAGREE)).stdout)

        self.assertEqual(without["distribution"]["shardsDisagree"], [])
        self.assertEqual(without["distribution"]["shardsArrived"], [])
        moved = {"shardsDisagree", "shardsArrived", "status"}
        self.assertEqual(
            {key: value for key, value in without["distribution"].items()
             if key not in moved},
            {key: value for key, value in with_shards["distribution"].items()
             if key not in moved})
        self.assertEqual({k: v for k, v in without.items() if k != "distribution"},
                         {k: v for k, v in with_shards.items()
                          if k != "distribution"})

    def test_a_shard_directory_that_does_not_exist_is_a_smaller_campaign(self):
        """Three shards planned and none returned is a legitimate answer, not
        an error: the doctrine already says the scale is recomputed from what
        came back. So an absent directory reports nothing arrived rather than
        refusing."""
        box = self.build_target("absent")
        missing = Path(tempfile.mkdtemp()) / "never-written"
        self.addCleanup(shutil.rmtree, missing.parent, ignore_errors=True)
        distribution = self.distribution(box, missing)

        self.assertEqual(distribution["shardsArrived"], [])
        self.assertEqual(distribution["shardsDisagree"], [])

    def test_a_shard_that_cannot_be_read_is_not_treated_as_a_shard_that_never_came(self):
        """The other half of the same boundary, and the one that has to be
        loud. A `shard.json` that is not JSON is not a smaller campaign; it is
        an unreadable one, and reporting it as absent is exactly the silence
        this skill exists to break."""
        box = self.build_target("malformed")
        shards = self.build_shards({"a": {"epochs": 5}})
        (shards / "a" / "shard.json").write_text("{not json", encoding="utf-8")
        proc = self.verify(box, shards, expect=1)

        self.assertIn("JSONDecodeError", proc.stderr)
        self.assertIn("read_shards", proc.stderr)

    def test_a_target_declaring_no_distribution_still_reports_both_keys(self):
        """The symmetry half, end to end. `shardsArrived` used to vanish for
        exactly the targets that declare no distribution, so a reader could
        not tell an absent key from an absent answer."""
        box = self.build_target("undeclared")
        (box / "src/Method_Benchmark/__init__.py").write_text(
            "__benchmark__ = {'revision': 'r01.md'}\n", encoding="utf-8")
        distribution = self.distribution(box)

        self.assertEqual(distribution["status"], "none")
        self.assertEqual(distribution["shardsDisagree"], [])
        self.assertEqual(distribution["shardsArrived"], [])

    def test_the_toy_targets_left_nothing_behind(self):
        self.build_target("cleanup")
        self.doCleanups()
        leftover = list((FORGE / "implementations").glob("_shardbox_*"))
        self.assertEqual(leftover, [], leftover)

    def test_the_doctrine_names_the_flag_and_says_which_half_refuses(self):
        """A promise with no producer is what this repairs, so the doctrine has
        to name the producer — and has to say plainly that refusing is where
        this skill stops, because the alternative reading is that a forge which
        refuses will eventually average."""
        text = SKILL_MD.read_text(encoding="utf-8")
        section = text[text.index("**Shards agree on what they said had to agree"):]
        section = section[:section.index("\n- **", 1)]
        self.assertIn("`verify --shards <dir>`", section)
        self.assertIn("shardsArrived", section)
        self.assertIn("never averages, pools or merges", section)

    def test_the_usage_reference_works_the_shard_invocation(self):
        usage = USAGE_MD.read_text(encoding="utf-8")
        section = usage[usage.index("### `--shards` — the refusal"):]
        section = section[:section.index("\n### ", 1)]
        self.assertIn("--shards", section)
        self.assertIn("`shardsDisagree`", section)
        self.assertIn("`shardsArrived`", section)


class ManifestProvisioningTests(unittest.TestCase):
    """`env`'s `nextCommand` must install the target's own declared manifests,
    beside the forge's `requirements-dev.txt` — never instead of them, and
    never before them, per Decision 8.
    """

    def box(self, suffix, files=()):
        path = FORGE / "implementations" / f"_manifest_{suffix}_{os.getpid()}"
        path.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        for name, text in files:
            (path / name).write_text(text, encoding="utf-8")
        return path

    def test_no_manifest_reports_an_empty_list_and_a_stated_absence(self):
        target = self.box("bare")
        found = impl.manifest_provisioning(target)
        self.assertEqual(found["rows"], [])
        self.assertTrue(found["absentNote"],
                         "an empty list alone cannot be told apart from a check "
                         "that never ran; the absence has to be stated")

    def test_requirements_and_dev_requirements_are_honoured_in_order(self):
        target = self.box("reqs", [("requirements.txt", "numpy\n"),
                                    ("requirements-dev.txt", "pytest\n")])
        found = impl.manifest_provisioning(target)
        names = [row["name"] for row in found["rows"]]
        self.assertEqual(names, ["requirements.txt", "requirements-dev.txt"])
        self.assertTrue(all(row["status"] == "honoured" for row in found["rows"]))
        self.assertEqual(found["args"],
                          ["-r", str(target / "requirements.txt"),
                           "-r", str(target / "requirements-dev.txt")])

    def test_a_buildable_project_is_installed_editable_last(self):
        target = self.box("editable", [("requirements.txt", "numpy\n"),
                                        ("pyproject.toml", "[project]\nname='x'\n")])
        found = impl.manifest_provisioning(target)
        names = [row["name"] for row in found["rows"]]
        self.assertEqual(names, ["requirements.txt", "pyproject.toml"])
        self.assertEqual(found["args"][-2:], ["-e", str(target)])

    def test_setup_py_alone_is_also_installed_editable(self):
        target = self.box("setuppy", [("setup.py", "from setuptools import setup\n")])
        found = impl.manifest_provisioning(target)
        self.assertEqual([row["name"] for row in found["rows"]], ["setup.py"])
        self.assertEqual(found["args"], ["-e", str(target)])

    def test_environment_yml_is_named_unhonoured_with_a_reason_never_ignored(self):
        target = self.box("conda", [("environment.yml", "name: x\n")])
        found = impl.manifest_provisioning(target)
        self.assertEqual(len(found["rows"]), 1)
        row = found["rows"][0]
        self.assertEqual(row["name"], "environment.yml")
        self.assertEqual(row["status"], "unhonoured")
        self.assertTrue(row["reason"])
        # An unhonoured manifest names nothing pip is asked to install.
        self.assertEqual(found["args"], [])

    def test_cmd_env_lists_the_forge_dev_reqs_first_then_target_manifests_last(self):
        target = self.box("order", [("requirements.txt", "numpy\n"),
                                     ("environment.yml", "name: x\n")])
        subprocess.run(["git", "init", "-q", str(target)], check=True, capture_output=True)
        result = impl.cmd_env(argparse.Namespace(target=str(target), python=sys.executable))
        forge_reqs = str(impl.SKILL_ROOT / "assets" / "requirements-dev.txt")
        self.assertLess(
            result["nextCommand"].index(forge_reqs),
            result["nextCommand"].index(str(target / "requirements.txt")),
            "the forge's own dev requirements must be listed before any target "
            "manifest, per Decision 8")
        self.assertEqual([row["name"] for row in result["manifests"]["rows"]],
                          ["requirements.txt", "environment.yml"])
        self.assertEqual(result["manifests"]["rows"][1]["status"], "unhonoured")

    def test_cmd_env_construction_names_no_target_package(self):
        """The forge-vocabulary guard: `cmd_env`'s own construction and its
        `manifest_provisioning` helper must name only manifest filenames the
        forge already enumerates in `ROOT_KEEP`, never a target's package,
        device or repository name.
        """
        source = inspect.getsource(impl.cmd_env) + inspect.getsource(impl.manifest_provisioning)
        for word in FORGE_VOCABULARY_FLOOR:
            self.assertNotIn(word, source.lower())


class PythonFloorTests(unittest.TestCase):
    """`env` used to promise a floor (`--help`: "The layout templates
    assume 3.10+") and check nothing: a 3.9.6 interpreter built a venv and
    reported `status: "created"` with no warning. Two check sites, one
    shared predicate (`_python_floor`) -- a fresh-build route
    (`--python` below the floor) and a reuse route (an existing venv whose
    own interpreter is below the floor); neither can see the other's
    failure mode.
    """

    def box(self, suffix, files=()):
        path = FORGE / "implementations" / f"_pyfloor_{suffix}_{os.getpid()}"
        path.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        for name, text in files:
            (path / name).write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
        return path

    def fake_interpreter(self, target: Path, version_text: str) -> Path:
        """A stand-in `python` that answers only `--version`, never a real
        interpreter -- this test never needs one to reach far enough to
        exercise a REFUSAL, which must happen before any real `venv`
        invocation.
        """
        script = target / "fake_python"
        script.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "--version" ]; then\n'
            f'    echo "{version_text}"\n'
            "    exit 0\n"
            "fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def test_cmd_env_refuses_under_floor_interpreter_skill_default(self):
        target = self.box("skillfloor")
        fake = self.fake_interpreter(target, "Python 3.9.6")
        with self.assertRaises(impl.Refused) as caught:
            impl.cmd_env(argparse.Namespace(target=str(target), python=str(fake)))
        self.assertEqual(caught.exception.code, "PYTHON_BELOW_FLOOR")
        self.assertIn("3.10", caught.exception.detail)
        self.assertIn("skill default", caught.exception.detail)
        self.assertFalse((target / ".venv").exists(),
                          "a refused build must leave no venv behind")

    def test_cmd_env_refuses_under_floor_interpreter_target_declaration_higher(self):
        target = self.box(
            "targetfloor",
            [("setup.cfg", "[options]\npython_requires = >=3.11\n")],
        )
        fake = self.fake_interpreter(target, "Python 3.10.4")
        with self.assertRaises(impl.Refused) as caught:
            impl.cmd_env(argparse.Namespace(target=str(target), python=str(fake)))
        self.assertEqual(caught.exception.code, "PYTHON_BELOW_FLOOR")
        self.assertIn("3.11", caught.exception.detail)
        self.assertIn("target declaration", caught.exception.detail)

    def test_cmd_env_reuse_site_refuses_existing_under_floor_venv(self):
        target = self.box("reuse")
        venv_dir = target / ".venv"
        bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        bin_dir.mkdir(parents=True)
        (venv_dir / "pyvenv.cfg").write_text("", encoding="utf-8")
        fake = self.fake_interpreter(target, "Python 3.9.6")
        interpreter_path = bin_dir / ("python.exe" if os.name == "nt" else "python")
        shutil.copy(fake, interpreter_path)
        interpreter_path.chmod(0o755)
        with self.assertRaises(impl.Refused) as caught:
            impl.cmd_env(argparse.Namespace(target=str(target), python=None))
        self.assertEqual(caught.exception.code, "PYTHON_BELOW_FLOOR")
        self.assertIn("3.10", caught.exception.detail)

    def test_at_or_above_floor_created_reporting_unchanged(self):
        target = self.box("atfloor")
        env_result = impl.cmd_env(
            argparse.Namespace(target=str(target), python=sys.executable))
        self.assertEqual(env_result["status"], "created")
        self.assertNotIn("PYTHON_BELOW_FLOOR", json.dumps(env_result))

    def test_fresh_venv_is_seeded_with_a_build_backend(self):
        """Python 3.12 dropped `setuptools` from `ensurepip`; a fresh venv's
        own `pip` alone cannot satisfy `nextCommand`'s editable install
        (`pip install -e <target>`), which needs a PEP 517 backend.
        """
        target = self.box("seeded")
        env_result = impl.cmd_env(
            argparse.Namespace(target=str(target), python=sys.executable))
        pip = Path(env_result["pip"])
        listing = subprocess.run(
            [str(pip), "list"], capture_output=True, text=True, check=True,
        ).stdout.lower()
        self.assertIn("setuptools", listing)

    def test_python_floor_prefers_the_higher_of_skill_and_target(self):
        lower = self.box("lower", [("setup.cfg", "[options]\npython_requires = >=3.8\n")])
        floor, source = impl._python_floor(lower)
        self.assertEqual(floor, impl.SKILL_PYTHON_FLOOR)
        self.assertEqual(source, "skill default")

        higher = self.box("higher", [("setup.cfg", "[options]\npython_requires = >=3.12\n")])
        floor, source = impl._python_floor(higher)
        self.assertEqual(floor, (3, 12))
        self.assertEqual(source, "target declaration")


class EntryModuleLivenessTests(unittest.TestCase):
    """`live` must come from an EXECUTED import of the target's own entry
    module, never from `config` alone — a pure-Python module imports fine on
    an empty venv and answered `ok` on a repository that could not run.
    """

    def box(self, suffix):
        path = FORGE / "implementations" / f"_liveness_{suffix}_{os.getpid()}"
        (path / "src" / "Method_Benchmark").mkdir(parents=True)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        (path / "src" / "Method_Benchmark" / "__init__.py").write_text(
            "__benchmark__ = {'revision': 'r01.md'}\n", encoding="utf-8")
        # Pure Python: imports fine with nothing installed. This is the exact
        # module whose successful import used to answer `live: ok` alone.
        (path / "src" / "Method_Benchmark" / "config.py").write_text(
            "SCALES = [1, 2, 3]\n", encoding="utf-8")
        write_fixture_interpreter(
            path / ".venv" / ("Scripts" if os.name == "nt" else "bin"))
        return path

    def test_a_pure_python_config_import_alone_is_not_enough_evidence(self):
        """The exact defect measured: `introspect` must not report `ok` from
        `config` importing cleanly while the declared entry module cannot be
        imported at all."""
        target = self.box("bare_entry")
        # No `benchmark.py` on disk at all: the declared entry module cannot
        # be found, let alone executed.
        result = impl.introspect(target, "Method", None,
                                  entry_module="Method_Benchmark.benchmark")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("benchmark", result["detail"])

    def test_an_entry_module_importing_an_absent_dependency_is_unavailable(self):
        target = self.box("missing_dep")
        (target / "src" / "Method_Benchmark" / "benchmark.py").write_text(
            "import _pp_entry_liveness_absent_dependency\n", encoding="utf-8")
        result = impl.introspect(target, "Method", None,
                                  entry_module="Method_Benchmark.benchmark")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("_pp_entry_liveness_absent_dependency", result["detail"])

    def test_a_present_and_importable_entry_module_reports_ok(self):
        target = self.box("present")
        (target / "src" / "Method_Benchmark" / "benchmark.py").write_text(
            "VALUE = 1\n", encoding="utf-8")
        result = impl.introspect(target, "Method", None,
                                  entry_module="Method_Benchmark.benchmark")
        self.assertEqual(result["status"], "ok")


class EntryModuleResolutionTests(unittest.TestCase):
    """Where `introspect` gets the entry module's dotted name from — the
    target's own declaration when it names one, reachable only as the
    scaffold's own harness-file convention (`BENCHMARK_MODULE`) otherwise.
    A later phase adds the declared `entry` block; until it lands, this is
    the narrowest path that names no target package of its own.
    """

    def box(self, suffix, declaration):
        path = FORGE / "implementations" / f"_entrymod_{suffix}_{os.getpid()}"
        (path / "src" / "Method_Benchmark").mkdir(parents=True)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        (path / "src" / "Method_Benchmark" / "__init__.py").write_text(
            declaration, encoding="utf-8")
        return path

    def test_an_undeclared_entry_resolves_to_nothing_rather_than_a_guess(self):
        """This asserted the guess, and the guess was the defect.

        Falling back to the forge's own filename convention meant an
        undeclared entry produced a module name that does not exist, whose
        failed import was then reported as the interpreter's. A target whose
        harness carries any other name got sent to repair a working
        environment. `resolve_harness_status` already refuses to guess for
        this reason; its sibling now refuses too.
        """
        target = self.box("fallback", "__benchmark__ = {'revision': 'r01.md'}\n")
        self.assertIsNone(
            impl.resolve_entry_module(target, "Method", "Method"),
            "an absent declaration is an absence, not a name to invent")

    def test_an_explicitly_declared_entry_module_wins(self):
        target = self.box(
            "declared",
            "__benchmark__ = {'revision': 'r01.md', "
            "'entry': {'module': 'Method_Benchmark.custom_entry', 'function': 'run'}}\n")
        self.assertEqual(impl.resolve_entry_module(target, "Method", "Method"),
                          "Method_Benchmark.custom_entry")


class HarnessStatusResolutionTests(unittest.TestCase):
    """Where `probe` gets its harness's name from — the target's own
    declaration, `entry.module`, never a second hardcoded filename beside
    `BENCHMARK_MODULE`.

    Three states, and they answer three different questions: `undeclared`
    (nothing named yet — silence about the tree says nothing), `present` (the
    declared module's file exists), and `declaredMissing` (a module is named
    and its file is not where the declaration says — named with the declared
    module and the exact path looked for, because a refusal that does not say
    where it looked cannot be acted on).
    """

    def box(self, suffix, declaration):
        path = FORGE / "implementations" / f"_harnessstatus_{suffix}_{os.getpid()}"
        (path / "src" / "Method_Benchmark").mkdir(parents=True)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        (path / "src" / "Method_Benchmark" / "__init__.py").write_text(
            declaration, encoding="utf-8")
        return path

    def test_an_empty_entry_module_reports_undeclared(self):
        """Nothing declared yet. This must never be read as "no harness
        file exists" — the tree may hold one under any name at all."""
        target = self.box("undeclared", "__benchmark__ = {'revision': 'r01.md'}\n")
        status = impl.resolve_harness_status(target, "Method", "Method")
        self.assertEqual(status["status"], "undeclared")
        self.assertIsNone(status["declaredModule"])
        self.assertIsNone(status["path"])
        self.assertIsNone(status["searchedPath"])

    def test_a_declared_module_present_on_disk_reports_its_path(self):
        target = self.box(
            "present",
            "__benchmark__ = {'revision': 'r01.md', "
            "'entry': {'module': 'Method_Benchmark.benchmark', 'function': 'run'}}\n")
        (target / "src" / "Method_Benchmark" / "benchmark.py").write_text(
            "VALUE = 1\n", encoding="utf-8")
        status = impl.resolve_harness_status(target, "Method", "Method")
        self.assertEqual(status["status"], "present")
        self.assertEqual(status["declaredModule"], "Method_Benchmark.benchmark")
        self.assertEqual(status["path"], "src/Method_Benchmark/benchmark.py")
        self.assertIsNone(status["searchedPath"])

    def test_a_declared_module_missing_from_disk_names_it_and_where_it_looked(self):
        """Present under a different name is not the same fact as absent, and
        this is the case that tells the two apart without a second hardcoded
        filename: the target names its harness `harness.py`, nothing at
        `benchmark.py` was ever written, and the declared name is honoured."""
        target = self.box(
            "declared_missing",
            "__benchmark__ = {'revision': 'r01.md', "
            "'entry': {'module': 'Method_Benchmark.harness', 'function': 'run'}}\n")
        status = impl.resolve_harness_status(target, "Method", "Method")
        self.assertEqual(status["status"], "declaredMissing")
        self.assertEqual(status["declaredModule"], "Method_Benchmark.harness")
        self.assertIsNone(status["path"])
        self.assertEqual(status["searchedPath"], "src/Method_Benchmark/harness.py")

    def test_absent_and_missing_are_told_apart_by_the_declaration_alone(self):
        """One target has no harness file at all; another has it under the
        declared name. Neither reads the forge's own filename convention to
        tell them apart."""
        absent = self.box("absent_pole",
                          "__benchmark__ = {'revision': 'r01.md', "
                          "'entry': {'module': 'Method_Benchmark.harness', "
                          "'function': 'run'}}\n")
        present = self.box("present_pole",
                           "__benchmark__ = {'revision': 'r01.md', "
                           "'entry': {'module': 'Method_Benchmark.harness', "
                           "'function': 'run'}}\n")
        (present / "src" / "Method_Benchmark" / "harness.py").write_text(
            "VALUE = 1\n", encoding="utf-8")

        self.assertEqual(
            impl.resolve_harness_status(absent, "Method", "Method")["status"],
            "declaredMissing")
        self.assertEqual(
            impl.resolve_harness_status(present, "Method", "Method")["status"],
            "present")

    def test_no_second_hardcoded_filename_names_the_harness(self):
        """The design's own rejected alternative, measured rather than
        argued: a second hardcoded name beside `BENCHMARK_MODULE` would be
        the same defect twice."""
        source = inspect.getsource(impl.resolve_harness_status)
        self.assertNotIn("BENCHMARK_MODULE", source,
                         "the declared entry name is the only lookup here")


class EnvFirstGateTests(unittest.TestCase):
    """`nextStep` must not advance past `env-first` while the target's own
    declared entry module cannot be imported — Decision 12's new rung,
    inserted immediately after `declare-first`. Reuses
    `ProbeReportedFactsRosterTests`'s fixture builder by composition, never by
    subclassing, so its own test methods are not rediscovered under this
    class name too.
    """

    DECLARATION = ProbeReportedFactsRosterTests.DECLARATION
    WIRING = ProbeReportedFactsRosterTests.WIRING
    TABLES = ProbeReportedFactsRosterTests.TABLES

    def build_target(self, suffix):
        return ProbeReportedFactsRosterTests.build_target(self, suffix)

    def probe(self, box):
        return ProbeReportedFactsRosterTests.probe(self, box)

    def test_an_unimportable_entry_module_reports_env_first_not_benchmark(self):
        """The exact defect this rung exists to close: an empty venv whose
        pure-Python `config` still imports fine used to clear the way to a run
        the environment could not perform."""
        box, _ = self.build_target("envfirst_broken")
        (box / "src/Method_Benchmark/benchmark.py").write_text(
            "import _pp_env_first_absent_dependency\n", encoding="utf-8")
        probe = self.probe(box)
        self.assertEqual(probe["report"]["live"], "unavailable")
        self.assertEqual(probe["nextStep"], "env-first")
        self.assertNotEqual(probe["nextStep"], "benchmark")

    def test_an_undeclared_entry_is_a_declaration_gap_not_a_broken_environment(self):
        """Measured against a real target: six of seven blocks declared, the
        seventh empty, an environment that imports everything it needs — and
        the flow answered that the interpreter could not import the entry
        module. It could. Nothing had said which module to import.

        `resolve_harness_status` already refuses to guess a filename and
        reports `undeclared` instead. Its sibling guessed the forge's own
        convention, handed the guess to liveness, and liveness reported the
        guess's failure as the environment's. Two different facts under one
        message, which is the shape this whole flow exists to remove.
        """
        box, _ = self.build_target("entry_undeclared")
        # Six blocks declared, the seventh absent — a target written before
        # `entry` existed. The environment is sound; the module simply is not
        # under the name the forge would have assumed.
        init = box / "src/Method_Benchmark/__init__.py"
        text = init.read_text(encoding="utf-8")
        start = text.index("    'entry'")
        end = text.index("\n", text.index("'function'", start)) + 1
        init.write_text(text[:start] + text[end:], encoding="utf-8")
        module = box / "src/Method_Benchmark/benchmark.py"
        module.rename(module.with_name("harness.py"))
        probe = self.probe(box)
        self.assertNotEqual(
            probe["report"]["live"], "unavailable",
            "an undeclared entry is not an environment that cannot import; "
            "reporting it as one sends the reader to repair what is working")
        self.assertEqual(probe["report"]["live"], "undeclared")
        self.assertNotEqual(
            probe["nextStep"], "env-first",
            "the missing thing is a declaration, and the rung for a missing "
            "declaration already exists")
        self.assertEqual(probe["nextStep"], "declare-first")

    def test_the_same_target_reaches_benchmark_once_the_entry_module_imports(self):
        box, _ = self.build_target("envfirst_ok")
        probe = self.probe(box)
        self.assertEqual(probe["report"]["live"], "ok")
        self.assertEqual(probe["nextStep"], "benchmark")


class ProvisionedEntryLivenessIntegrationTests(unittest.TestCase):
    """A real, freshly-built `.venv` — never a symlink to the interpreter
    running this suite — proving the whole chain end to end: `env`'s
    `nextCommand` names the target's own manifest, installing it makes the
    declared entry module importable with no `ModuleNotFoundError`, and doing
    so through the venv's own prescribed interpreter never trips the same
    "foreign interpreter" refusal every target harness under this doctrine
    carries (`sys.prefix` scoped to the repository's own virtualenv).

    Nothing is launched anywhere; this only builds a venv, installs one local,
    offline package, and imports a module — the shape Unit 5's own tasks call
    for: "no launch".
    """

    VENDOR_SETUP = (
        "from setuptools import setup\n"
        "setup(name='pptinypkg', version='0.0.1', packages=['pptinypkg'])\n"
    )
    VENDOR_INIT = "VALUE = 42\n"

    #: The identical mechanism every target harness under this doctrine
    #: carries: refuse an interpreter whose `sys.prefix` sits outside the
    #: repository, once the repository has a virtualenv of its own. Proven
    #: inline rather than by invoking a real target's own harness — that
    #: repository is a separate one, out of scope here — but the check is the
    #: forge's own generic kit convention (`environment()` in
    #: `assets/kit/nb/benchmark.py`), reproduced at the one line that matters.
    ENTRY_MODULE = (
        "import sys\n"
        "from pathlib import Path\n"
        "import pptinypkg\n"
        "repository = Path(__file__).resolve().parents[2]\n"
        "prefix = Path(sys.prefix).resolve()\n"
        "if not prefix.is_relative_to(repository):\n"
        "    raise SystemExit(f'refusing to run under {prefix}')\n"
        "VALUE = pptinypkg.VALUE\n"
    )

    def build_target(self):
        target = FORGE / "implementations" / f"_env_live_{os.getpid()}"
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        (target / "vendor" / "pptinypkg" / "pptinypkg").mkdir(parents=True)
        (target / "vendor" / "pptinypkg" / "setup.py").write_text(
            self.VENDOR_SETUP, encoding="utf-8")
        (target / "vendor" / "pptinypkg" / "pptinypkg" / "__init__.py").write_text(
            self.VENDOR_INIT, encoding="utf-8")
        (target / "requirements.txt").write_text(
            "-e ./vendor/pptinypkg\n", encoding="utf-8")
        (target / "src" / "Method_Benchmark").mkdir(parents=True)
        (target / "src" / "Method_Benchmark" / "__init__.py").write_text(
            "__benchmark__ = {'revision': 'r01.md'}\n", encoding="utf-8")
        (target / "src" / "Method_Benchmark" / "config.py").write_text(
            "SCALES = [1, 2, 3]\n", encoding="utf-8")
        (target / "src" / "Method_Benchmark" / "benchmark.py").write_text(
            self.ENTRY_MODULE, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(target)], check=True, capture_output=True)
        return target

    def test_the_prescribed_interpreter_runs_the_declared_manifest_with_no_launch(self):
        target = self.build_target()

        # 1. `env`: a real venv, never symlinked, created fresh with nothing installed.
        env_result = impl.cmd_env(
            argparse.Namespace(target=str(target), python=sys.executable))
        self.assertEqual(env_result["status"], "created")
        interpreter = Path(env_result["interpreter"])
        self.assertTrue(interpreter.is_relative_to(target),
                         "the prescribed interpreter must live inside the target")

        # 2. Before install: the entry module cannot be imported at all — the
        #    empty-venv state `env-first` exists to catch. `config.py` is not
        #    even present here, so there is nothing pure-Python to hide behind.
        before = impl.introspect(target, "Method", None,
                                  entry_module="Method_Benchmark.benchmark")
        self.assertEqual(before["status"], "unavailable")
        self.assertIn("pptinypkg", before["detail"])

        # 3. Install exactly the target's own honoured manifest — the part of
        #    `nextCommand` this test can run offline. `--no-build-isolation`
        #    is this test's own concession to a sandbox with no network; it
        #    changes nothing about what `manifest_provisioning` reports.
        manifests = impl.manifest_provisioning(target)
        self.assertEqual([row["name"] for row in manifests["rows"]],
                          ["requirements.txt"])
        proc = subprocess.run(
            [str(env_result["pip"]), "install", "--no-build-isolation",
             "--disable-pip-version-check", "-q", *manifests["args"]],
            capture_output=True, text=True, cwd=str(target))
        self.assertEqual(proc.returncode, 0, proc.stderr)

        # 4. After install: the prescribed interpreter imports the declared
        #    entry module with no `ModuleNotFoundError`, and the same
        #    "foreign interpreter" refusal every target harness under this
        #    doctrine carries is not triggered — `sys.prefix` is genuinely
        #    inside the target now, not a symlink borrowing another one's.
        after = impl.introspect(target, "Method", None,
                                 entry_module="Method_Benchmark.benchmark")
        self.assertEqual(after["status"], "ok", after.get("detail"))

        direct = subprocess.run(
            [str(interpreter), "-c",
             "import Method_Benchmark.benchmark as m; print(m.VALUE)"],
            capture_output=True, text=True, cwd=str(target),
            env={**os.environ, "PYTHONPATH": str(target / "src")})
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertNotIn("refusing to run under", direct.stdout + direct.stderr)
        self.assertIn("42", direct.stdout)


class PositionModuleTests(unittest.TestCase):
    """`impl_position`'s pure grammar and splice, exercised directly against
    the module — no target, no repository, no subprocess.

    The two byte-preservation properties below are ported from the
    deliberation engine's own suite
    (`tests/proposal-deliberation-successor-byte-preservation.test.mjs:41-78`),
    not re-derived: a replacement argument that interprets its own bytes as
    escapes is the same bug class in a different language, and `AGREED.md`
    already carries the payload that would expose it — `$$`, `\\tag{}`, and
    backslashes (design lines 197-261 of a real target).
    """

    HEADER = {
        "revision": "research-concept-r17",
        "revisionSha256": "a" * 64,
        "derivedAt": "2026-08-27T00:00:00Z",
        "session": "s1",
        "target": "final",
    }

    def block_text(self, items):
        return impl_position.render(self.HEADER, items)

    # --- ported: "$$" survives, never collapsed by a replacement-pattern escape ---

    def test_a_dollar_dollar_and_backslash_payload_survives_splice_byte_for_byte(self):
        payload_text = "The identity is $$E=mc^2$$ and \\tag{39} names it."
        items = [{"ordinal": 1, "mark": " ", "text": payload_text,
                  "witness": {"kind": "record", "operand": None}}]
        new_block = self.block_text(items).encode("utf-8")
        original = "# Title\n\nSome prose already here.\n".encode("utf-8")

        spliced = impl_position.splice(original, new_block, None)

        self.assertIn(payload_text.encode("utf-8"), spliced)
        self.assertTrue(spliced.startswith(original))
        # Round-trip: locate + parse recovers the identical payload text,
        # which is only possible if the bytes were concatenated rather than
        # run through anything that treats "$$" or "\t" as an escape.
        block = impl_position.locate_block(spliced)
        parsed = impl_position.parse_items(block["body"])
        self.assertEqual(parsed[0]["text"], payload_text)

    # --- ported: only the located span changes; an identical string elsewhere stays ---

    def test_replacing_the_block_leaves_an_identical_string_elsewhere_untouched(self):
        outside = "Shared line.\n"
        placeholder = [{"ordinal": 1, "mark": " ", "text": "placeholder",
                        "witness": {"kind": "record", "operand": None}}]
        old_block = self.block_text(placeholder).encode("utf-8")
        original = ("# Doc\n\n" + outside + "\n").encode("utf-8") + old_block

        block = impl_position.locate_block(original)
        self.assertIsNotNone(block)

        new_items = [{"ordinal": 1, "mark": " ", "text": "Shared line.",
                      "witness": {"kind": "record", "operand": None}}]
        new_block = self.block_text(new_items).encode("utf-8")
        spliced = impl_position.splice(original, new_block, block)

        # The outside occurrence, at its original byte offset, is untouched.
        outside_at = original.index(outside.encode("utf-8"))
        self.assertEqual(spliced[outside_at:outside_at + len(outside)],
                          outside.encode("utf-8"))
        # It appears exactly once outside the block and once inside the
        # freshly spliced-in block -- never merged, never duplicated by the
        # splice itself.
        self.assertEqual(spliced.count(b"Shared line."), 2)

    # --- location: uniqueness required, never first-occurrence-wins ---

    def test_two_position_blocks_refuse_rather_than_pick_the_first(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "record", "operand": None}}]
        block = self.block_text(items).encode("utf-8")
        doc = block + b"\n" + block

        with self.assertRaises(impl.Refused) as ctx:
            impl_position.locate_block(doc)
        self.assertEqual(ctx.exception.code, "POSITION_BLOCK_NOT_UNIQUE")

    def test_absent_block_is_a_state_not_an_error(self):
        self.assertIsNone(impl_position.locate_block(b"# Doc\n\nNo block here.\n"))

    # --- derive(): three-valued, per witness kind, never guessing on absence ---

    def test_derive_record_ticks_on_found_and_required_scale_satisfied(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "record", "operand": None}}]
        self.assertIs(impl_position.derive(
            items, {"search": {"recordFound": False}, "requiredScale": {}}
        )[0]["derived"], False)
        self.assertIs(impl_position.derive(
            items, {"search": {"recordFound": True}, "requiredScale": {}}
        )[0]["derived"], True)
        self.assertIs(impl_position.derive(
            items, {"search": {"recordFound": True, "scaleSatisfied": False},
                    "requiredScale": {"seeds": 30}}
        )[0]["derived"], False)
        self.assertIsNone(impl_position.derive(items, {})[0]["derived"])

    def test_derive_notebook_ticks_on_executed_and_sources_match(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "notebook",
                             "operand": "Notebooks/campaign.ipynb"}}]
        evidence = {"notebooks": {"reports": [
            {"notebook": "Method/Notebooks/campaign.ipynb",
             "status": "executed", "sourcesMatch": True}]}}
        self.assertIs(impl_position.derive(items, evidence)[0]["derived"], True)
        evidence["notebooks"]["reports"][0]["sourcesMatch"] = False
        self.assertIs(impl_position.derive(items, evidence)[0]["derived"], False)
        self.assertIsNone(impl_position.derive(items, {})[0]["derived"])

    def test_derive_rehearsal_ticks_on_smoke_ready(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "rehearsal", "operand": "ceiling-search"}}]
        self.assertIs(impl_position.derive(
            items, {"smokeReady": {"ceiling-search": True}})[0]["derived"], True)
        self.assertIs(impl_position.derive(
            items, {"smokeReady": {"ceiling-search": False}})[0]["derived"], False)
        self.assertIsNone(impl_position.derive(items, {})[0]["derived"])

    def test_derive_shard_is_unmeasured_without_shard_evidence(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "shard", "operand": "s3"}}]
        self.assertIs(impl_position.derive(
            items, {"shardsArrived": ["s3"]})[0]["derived"], True)
        self.assertIs(impl_position.derive(
            items, {"shardsArrived": ["s1"]})[0]["derived"], False)
        # `probe` never supplies `shardsArrived`; `verify` without `--shards`
        # does not either. Both leave this `None` -- never a false "did not
        # arrive" for a shard this invocation was simply not told to check.
        self.assertIsNone(impl_position.derive(items, {})[0]["derived"])

    def test_derive_flags_disagreement_between_disk_mark_and_measurement(self):
        items = [{"ordinal": 1, "mark": "x", "text": "x",
                  "witness": {"kind": "rehearsal", "operand": "job"}}]
        result = impl_position.derive(items, {"smokeReady": {"job": False}})[0]
        self.assertIs(result["derived"], False)
        self.assertTrue(result["disagrees"])

    def test_derive_unmeasured_never_disagrees(self):
        items = [{"ordinal": 1, "mark": "x", "text": "x",
                  "witness": {"kind": "shard", "operand": "s3"}}]
        result = impl_position.derive(items, {})[0]
        self.assertIsNone(result["derived"])
        self.assertFalse(result["disagrees"])

    # --- parse_items(): malformed witness is refused, never silently accepted ---

    def test_item_without_a_witness_is_refused(self):
        with self.assertRaises(impl.Refused) as ctx:
            impl_position.parse_items("- [ ] 1. No witness token at all.\n")
        self.assertEqual(ctx.exception.code, "POSITION_ITEM_WITHOUT_WITNESS")

    def test_item_naming_an_unknown_witness_kind_is_refused(self):
        with self.assertRaises(impl.Refused) as ctx:
            impl_position.parse_items("- [ ] 1. Something. `@wat`\n")
        self.assertEqual(ctx.exception.code, "POSITION_WITNESS_UNKNOWN_KIND")

    # --- ledger fold: append-only, absent file is zero events, not an error ---

    def test_ledger_round_trips_and_is_empty_when_absent(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "Method" / ".implementation" / "position.jsonl"
            self.assertEqual(impl_position.read_events(path), [])
            impl_position.append_event(path, {"kind": "gate", "jobName": "j1"})
            impl_position.append_event(path, {"kind": "close", "session": "s1"})
            events = impl_position.read_events(path)
            self.assertEqual([e["kind"] for e in events], ["gate", "close"])


class PositionLevelGrammarTests(unittest.TestCase):
    """PR10, `the-position-nobody-holds`: the boolean tick becomes an ordered
    level, without collapsing `None` ("unmeasured") into the floor rung, and
    without ever assigning a two-state item a rung it never declared.

    The two tests immediately below are the mandated first tests: written and
    confirmed RED for the stated reason before the production grammar in
    `impl_position.py` existed. Levels used throughout are deliberately
    generic (`"local"`, `"cluster"`, ...) — the ladder's own names are never
    the forge's; see `derive`'s and `level_index`'s docstrings.
    """

    LEVELS = ["local", "staging", "cluster"]

    # --- mandated test 1: a two-state item cannot be assigned a middle rung ---

    def test_a_two_state_item_is_never_assigned_a_level_string(self):
        """A `:level`-less witness stays two-state even when the evidence
        underneath it (a record, found but short of the declared scale)
        would otherwise resolve to a real middle rung for a leveled item —
        proving the two-state grammar is not just "leveled with no ladder
        declared", it actively refuses the rung.
        """
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "record", "operand": None}}]  # no twostate key: default
        evidence = {
            "search": {"recordFound": True, "scaleSatisfied": False},
            "requiredScale": {"seeds": 30},
            "levels": self.LEVELS, "targetLevel": "cluster",
        }
        result = impl_position.derive(items, evidence)[0]
        self.assertTrue(result["twostate"])
        self.assertIn(result["derived"], (True, False, None))
        self.assertNotIn(result["derived"], self.LEVELS)

    # --- mandated test 2: unreadable evidence reports unmeasured, never the floor ---

    def test_unreadable_evidence_reports_unmeasured_not_the_floor_rung(self):
        """A leveled item whose evidence dict carries nothing to read (the
        same shape `probe` or a flagless `verify` already hands a `@shard`
        witness) must derive `None`, not `self.LEVELS[0]` — "we did not
        look" and "it has not started" stay two different facts.
        """
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "shard", "operand": "s3", "twostate": False}}]
        result = impl_position.derive(items, {"levels": self.LEVELS})[0]
        self.assertIsNone(result["derived"])
        self.assertNotEqual(result["derived"], self.LEVELS[0])
        self.assertIsNone(result["satisfied"])
        self.assertFalse(result["disagrees"])

    # --- twostate default: unmarked items behave exactly as the prior revision ---

    def test_an_unmarked_witness_defaults_to_two_state_unchanged_from_before(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "rehearsal", "operand": "job"}}]
        result = impl_position.derive(items, {"smokeReady": {"job": True}})[0]
        self.assertTrue(result["twostate"])
        self.assertIs(result["derived"], True)
        self.assertIs(result["satisfied"], True)

    # --- :level grammar round-trips through render/parse/locate ---

    def test_a_level_marked_witness_round_trips_through_render_and_parse(self):
        header = {**PositionModuleTests.HEADER, "target": "staging"}
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "rehearsal", "operand": "job", "twostate": False}}]
        text = impl_position.render(header, items)
        self.assertIn("`@rehearsal:level job`", text)
        block = impl_position.locate_block(text.encode("utf-8"))
        self.assertEqual(block["target"], "staging")
        parsed = impl_position.parse_items(block["body"])
        self.assertFalse(parsed[0]["witness"]["twostate"])

    def test_an_unmarked_witness_round_trips_as_two_state_with_no_suffix(self):
        text = impl_position.render(PositionModuleTests.HEADER, [
            {"ordinal": 1, "mark": " ", "text": "x",
             "witness": {"kind": "notebook", "operand": "a.ipynb"}}])
        self.assertIn("`@notebook a.ipynb`", text)
        self.assertNotIn("`@notebook:level", text)
        block = impl_position.locate_block(text.encode("utf-8"))
        parsed = impl_position.parse_items(block["body"])
        self.assertTrue(parsed[0]["witness"]["twostate"])

    # --- header migration: a block written by the prior grammar is refused ---

    def test_a_pre_pr10_block_with_no_target_field_is_refused_not_migrated(self):
        old_style = (
            "<!-- position revision=r1 sha256=" + "b" * 64 +
            " derivedAt=2026-01-01T00:00:00Z session=s1 -->\n"
            "- [ ] 1. Something. `@record`\n"
            "<!-- /position -->\n"
        ).encode("utf-8")
        with self.assertRaises(impl.Refused) as ctx:
            impl_position.locate_block(old_style)
        self.assertEqual(ctx.exception.code, "POSITION_BLOCK_MALFORMED")

    def test_allow_legacy_reads_a_pre_pr10_block_as_migratable(self):
        """`position` is the one place a caller may opt into reading an old
        block at all (`allow_legacy=True`) -- everyone else keeps refusing,
        exercised immediately above. This is what makes migration reachable:
        without it, `cmd_position` could never even see the block it is
        supposed to rewrite.
        """
        old_style = (
            "<!-- position revision=r1 sha256=" + "b" * 64 +
            " derivedAt=2026-01-01T00:00:00Z session=s1 -->\n"
            "- [ ] 1. Something. `@record`\n"
            "<!-- /position -->\n"
        ).encode("utf-8")
        block = impl_position.locate_block(old_style, allow_legacy=True)
        self.assertIsNotNone(block)
        self.assertIsNone(block["target"])
        self.assertTrue(block["legacy"])
        # The item grammar itself needs no migration -- unaffected by the
        # header's shape.
        items = impl_position.parse_items(block["body"])
        self.assertEqual(items[0]["witness"], {"kind": "record", "operand": None,
                                                "twostate": True})

    # --- level_index(): the whole of what the forge knows about a ladder ---

    def test_level_index_reads_position_never_semantics(self):
        self.assertEqual(impl_position.level_index(self.LEVELS, "local"), 0)
        self.assertEqual(impl_position.level_index(self.LEVELS, "cluster"), 2)
        self.assertIsNone(impl_position.level_index(self.LEVELS, "nonexistent"))
        self.assertIsNone(impl_position.level_index(self.LEVELS, None))
        self.assertIsNone(impl_position.level_index([], "local"))

    # --- @record leveled: found-but-short-of-scale is a real middle rung ---

    def test_record_leveled_found_short_of_declared_scale_is_the_middle_rung(self):
        """The exact motivating defect: a record structurally present (a
        notebook reading it would report `sourcesMatch: True`) but short of
        the declared scale must resolve to the middle rung, not the top —
        visible on the item itself, not something a reader has to remember.
        """
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "record", "operand": None, "twostate": False}}]
        evidence = {"search": {"recordFound": True, "scaleSatisfied": False},
                    "requiredScale": {"seeds": 30}, "levels": self.LEVELS,
                    "targetLevel": "cluster"}
        result = impl_position.derive(items, evidence)[0]
        self.assertEqual(result["derived"], "staging")
        self.assertFalse(result["satisfied"])

    def test_record_leveled_found_and_satisfied_is_the_top_rung(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "record", "operand": None, "twostate": False}}]
        evidence = {"search": {"recordFound": True, "scaleSatisfied": True},
                    "requiredScale": {"seeds": 30}, "levels": self.LEVELS,
                    "targetLevel": "cluster"}
        result = impl_position.derive(items, evidence)[0]
        self.assertEqual(result["derived"], "cluster")
        self.assertTrue(result["satisfied"])

    def test_record_leveled_not_found_is_the_floor_rung(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "record", "operand": None, "twostate": False}}]
        evidence = {"search": {"recordFound": False}, "requiredScale": {},
                    "levels": self.LEVELS, "targetLevel": "local"}
        result = impl_position.derive(items, evidence)[0]
        self.assertEqual(result["derived"], "local")
        self.assertTrue(result["satisfied"])

    def test_record_leveled_insufficient_scale_on_a_two_rung_ladder_collapses_to_floor(self):
        """A two-rung ladder has no honest place for "something ran, but not
        enough of it" except the floor -- there is nowhere else to put it.
        """
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "record", "operand": None, "twostate": False}}]
        evidence = {"search": {"recordFound": True, "scaleSatisfied": False},
                    "requiredScale": {"seeds": 30}, "levels": ["local", "cluster"],
                    "targetLevel": "local"}
        result = impl_position.derive(items, evidence)[0]
        self.assertEqual(result["derived"], "local")

    # --- @rehearsal leveled: a two-valued fact can only reach the first rung ---

    def test_rehearsal_leveled_ready_reaches_the_second_rung_never_further(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "rehearsal", "operand": "job", "twostate": False}}]
        result = impl_position.derive(
            items, {"smokeReady": {"job": True}, "levels": self.LEVELS,
                    "targetLevel": "cluster"})[0]
        self.assertEqual(result["derived"], "staging")
        self.assertFalse(result["satisfied"])

    def test_rehearsal_leveled_not_ready_is_the_floor_rung(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "rehearsal", "operand": "job", "twostate": False}}]
        result = impl_position.derive(
            items, {"smokeReady": {"job": False}, "levels": self.LEVELS,
                    "targetLevel": "local"})[0]
        self.assertEqual(result["derived"], "local")

    # --- @shard leveled: arrival is full-scale evidence in its own right ---

    def test_shard_leveled_arrived_is_the_top_rung(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "shard", "operand": "s3", "twostate": False}}]
        result = impl_position.derive(
            items, {"shardsArrived": ["s3"], "levels": self.LEVELS,
                    "targetLevel": "cluster"})[0]
        self.assertEqual(result["derived"], "cluster")
        self.assertTrue(result["satisfied"])

    def test_shard_leveled_not_arrived_is_the_floor_rung(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "shard", "operand": "s1", "twostate": False}}]
        result = impl_position.derive(
            items, {"shardsArrived": ["s3"], "levels": self.LEVELS,
                    "targetLevel": "local"})[0]
        self.assertEqual(result["derived"], "local")

    # --- @notebook leveled: a stale report cannot attribute a rung to anything ---

    def test_notebook_leveled_stale_report_is_unmeasured_not_the_floor(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "notebook", "operand": "a.ipynb", "twostate": False}}]
        evidence = {"notebooks": {"reports": [
                        {"notebook": "a.ipynb", "status": "executed",
                         "sourcesMatch": False}]},
                    "search": {"recordFound": True, "scaleSatisfied": True},
                    "requiredScale": {"seeds": 30}, "levels": self.LEVELS}
        result = impl_position.derive(items, evidence)[0]
        self.assertIsNone(result["derived"])

    def test_notebook_leveled_current_report_reads_the_record_s_own_rung(self):
        items = [{"ordinal": 1, "mark": " ", "text": "x",
                  "witness": {"kind": "notebook", "operand": "a.ipynb", "twostate": False}}]
        evidence = {"notebooks": {"reports": [
                        {"notebook": "a.ipynb", "status": "executed",
                         "sourcesMatch": True}]},
                    "search": {"recordFound": True, "scaleSatisfied": False},
                    "requiredScale": {"seeds": 30}, "levels": self.LEVELS,
                    "targetLevel": "cluster"}
        result = impl_position.derive(items, evidence)[0]
        self.assertEqual(result["derived"], "staging")
        self.assertFalse(result["satisfied"])


class KitScaffoldLevelsDeclarationJoinTests(unittest.TestCase):
    """PR11, a defect found in PR10: the kit ships `__levels__` as an
    *annotated* assignment (`__levels__: list = [...]`, `ast.AnnAssign`), but
    `read_declaration` walked only `ast.Assign`. A target that uses the
    scaffold the skill itself ships therefore declared a ladder the skill
    could not read — the writer (`assets/kit/src_benchmark/__init__.py`) and
    the reader (`read_declaration`, and everything built on it) are in the
    same work unit and were never crossed until this test.

    Not "an annotated assignment parses" in the abstract: this reads the
    exact file the kit ships, unmodified, through the exact reader every
    caller uses.
    """

    KIT_INIT = (FORGE / ".claude/skills/proposal-implementation"
                / "assets/kit/src_benchmark/__init__.py")

    def test_the_shipped_scaffold_s_annotated_levels_literal_is_readable(self):
        """The kit's own `__levels__: list = []` -- an `ast.AnnAssign`, not
        an `ast.Assign` -- must be read as an empty list declared, not as
        nothing declared. Before the fix this fails: `read_declaration`
        returns `None` for a file that plainly declares `__levels__`.
        """
        result = impl.read_declaration(self.KIT_INIT, "__levels__")
        self.assertIsNotNone(
            result, "read_declaration saw no __levels__ in the kit's own "
            "scaffold, which declares one as `__levels__: list = []`")
        self.assertEqual(result, [])

    def test_a_filled_in_annotated_levels_literal_is_readable_end_to_end(self):
        """The realistic case: a target copies the scaffold and fills the
        ladder in, keeping the annotation exactly as shipped. Exercises the
        full join through `resolve_levels_declaration`, the function every
        caller actually uses -- not `read_declaration` in isolation.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bench = root / "src" / "Method_Benchmark"
            bench.mkdir(parents=True)
            source = self.KIT_INIT.read_text(encoding="utf-8").replace(
                "__levels__: list = []",
                '__levels__: list = ["local", "cluster"]')
            self.assertIn('__levels__: list = ["local", "cluster"]', source)
            (bench / "__init__.py").write_text(source, encoding="utf-8")
            levels = impl.resolve_levels_declaration(root, "Method")
        self.assertEqual(levels, ["local", "cluster"])

    def test_an_annotation_with_no_value_declares_nothing_not_a_crash(self):
        """`x: list` alone (no `=`) is a bare annotation -- `ast.AnnAssign.value`
        is `None` -- and must read as nothing declared, never raise inside
        `read_declaration` and never be mistaken for a declared empty list.
        """
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "__init__.py"
            path.write_text("__levels__: list\n", encoding="utf-8")
            result = impl.read_declaration(path, "__levels__")
        self.assertIsNone(result)

    # --- sweep: every other declaration this reader (or its siblings) is
    # --- asked for, checked against what the kit actually ships ---

    def test_the_shipped_scaffold_s_benchmark_literal_is_also_readable(self):
        """Sweep result: `__benchmark__` goes through the same
        `read_declaration` reader. It is a plain `ast.Assign` in the shipped
        kit, not annotated -- unaffected by the `AnnAssign` hole, confirmed
        directly against the shipped file rather than assumed.
        """
        result = impl.read_declaration(self.KIT_INIT, "__benchmark__")
        self.assertIsNotNone(result)
        self.assertIn("revision", result)

    def test_the_shipped_scaffold_s_dimensions_literal_is_also_unaffected(self):
        """Sweep result: `DIMENSIONS` is read by a separate, bespoke AST walk
        in `declared_dimension_names` (never `read_declaration`), with the
        identical `isinstance(node, ast.Assign)` restriction -- the same hole
        class, in a different function. The kit's own template
        (`assets/kit/nb/benchmark.py`) ships it unannotated, so this reader
        is not exercised by the PR10 defect today; confirmed directly against
        the shipped file rather than assumed, not left as a guess.
        """
        kit_benchmark = (FORGE / ".claude/skills/proposal-implementation"
                          / "assets/kit/nb/benchmark.py")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bench = root / "src" / "Method_Benchmark"
            bench.mkdir(parents=True)
            (bench / "benchmark.py").write_text(
                kit_benchmark.read_text(encoding="utf-8"), encoding="utf-8")
            names = impl.declared_dimension_names(root, "Method")
        self.assertEqual(names, ["accuracy", "seconds", "peakMiB", "parameters"])


class PositionKeyExitStatusTests(unittest.TestCase):
    """The `position` key is reported and never gates — the same discipline
    `coupling` (`CouplingNeverGatesTests`) and `smokeReady`
    (`ProbeReportedFactsRosterTests`) already carry. `position_state` is
    exercised directly across all four statuses; one end-to-end `verify`/
    `probe` run proves the key's mere presence never changes the process's
    own exit status, mirroring `CouplingNeverGatesTests._run` exactly.
    """

    HEADER = {
        "revision": "r01.md", "revisionSha256": "a" * 64,
        "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final",
    }

    def write_position(self, root, mark, sha256=None):
        (root / "Method").mkdir(parents=True, exist_ok=True)
        items = [{"ordinal": 1, "mark": mark, "text": "Rehearse the job.",
                  "witness": {"kind": "rehearsal", "operand": "job1"}}]
        header = {**self.HEADER, "revisionSha256": sha256 or self.HEADER["revisionSha256"]}
        (root / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")

    def test_position_state_reports_all_four_statuses_without_raising(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True)
            absent = impl.position_state(root, "Method", {}, None, None)
            self.assertEqual(absent["status"], "absent")

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.write_position(root, " ")
            open_state = impl.position_state(root, "Method", {}, None, None)
            self.assertEqual(open_state["status"], "open")

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.write_position(root, "x")
            evidence = {"smokeReady": {"job1": True}}
            complete = impl.position_state(root, "Method", evidence, None, None)
            self.assertEqual(complete["status"], "complete")

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.write_position(root, "x", sha256="b" * 64)
            evidence = {"smokeReady": {"job1": True}}
            stale = impl.position_state(root, "Method", evidence, "r01.md", "some content")
            self.assertEqual(stale["status"], "stale")

    def test_position_key_never_changes_exit_status(self):
        box = FORGE / "implementations" / f"_e2e_position_{os.getpid()}"
        try:
            (box / "src" / "Method").mkdir(parents=True)
            (box / "src" / "Method_Benchmark").mkdir(parents=True)
            (box / "tests").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
            (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
                _COUPLING_DECLARATION, encoding="utf-8")
            self.write_position(box, " ")
            verify = subprocess.run(
                [sys.executable, str(CLI), "verify", "--target", str(box),
                 "--name", "Method"],
                capture_output=True, text=True, cwd=FORGE)
            probe = subprocess.run(
                [sys.executable, str(CLI), "probe", "--target", str(box),
                 "--name", "Method"],
                capture_output=True, text=True, cwd=FORGE)
        finally:
            shutil.rmtree(box, ignore_errors=True)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        verify_json = json.loads(verify.stdout or "{}")
        probe_json = json.loads(probe.stdout or "{}")
        self.assertIn("position", verify_json)
        self.assertIn("position", probe_json)
        self.assertEqual(verify_json["position"]["status"], "open")
        self.assertEqual(probe_json["position"]["status"], "open")


class PositionCommandTests(unittest.TestCase):
    """`position` — the only writer into `<Name>/AGREED.md`'s section.

    No flag: REFRESH — re-derive the marks of whatever block is already
    there, and touch nothing else about it. `--sequence -`: INSTALL — a
    fresh sequence from stdin JSON becomes the block, refused as
    `POSITION_BLOCK_EXISTS` unless `--replace` says otherwise (design §3.3).

    Every test supplies a real `--revision`, resolved against a throwaway
    `proposals/` root: the header this command writes is bound to a
    revision's own content hash (`impl_position.locate_block`'s
    `sha256=` field), so there is no code path here that skips resolving
    one, and a test that omitted it would exercise `REVISION_UNREADABLE`
    rather than the refusal it names.
    """

    #: Fixed so a test that needs the header's `sha256=` to actually MATCH
    #: this revision (the `unchanged`/byte-preservation tests) can compute
    #: it once, the same way `cmd_position` itself will.
    PROPOSAL_TEXT = "## 1\ntexto\n"
    PROPOSAL_SHA256 = hashlib.sha256(PROPOSAL_TEXT.encode("utf-8")).hexdigest()

    def _proposals(self, text=None):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "r1.md").write_text(
            self.PROPOSAL_TEXT if text is None else text, encoding="utf-8")
        return root

    def _box(self):
        box = FORGE / "implementations" / f"_e2e_position_cmd_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        (box / "Method").mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text("", encoding="utf-8")
        return box

    def run_cli(self, *args, stdin=None, proposals=None):
        env = dict(os.environ)
        if proposals is not None:
            env["IMPLEMENTATION_PROPOSALS"] = str(proposals)
        return subprocess.run([sys.executable, str(CLI), *args], input=stdin,
                              capture_output=True, text=True, cwd=FORGE, env=env)

    def block_text(self, body, sha256=None, target="final"):
        return (f"<!-- position revision=r1.md sha256={sha256 or 'a' * 64} "
                f"derivedAt=2026-08-27T00:00:00Z session=s0 target={target} -->\n"
                f"{body}<!-- /position -->\n")

    # --- 3.1 refusals: a malformed artifact exits 2 with a code ---

    def test_refuses_when_the_existing_block_has_an_item_without_a_witness(self):
        box = self._box()
        (box / "Method" / "AGREED.md").write_text(
            self.block_text("- [ ] 1. No witness token at all.\n"), encoding="utf-8")
        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_ITEM_WITHOUT_WITNESS")

    def test_refuses_when_the_existing_block_names_an_unknown_witness_kind(self):
        box = self._box()
        (box / "Method" / "AGREED.md").write_text(
            self.block_text("- [ ] 1. Something. `@wat`\n"), encoding="utf-8")
        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_WITNESS_UNKNOWN_KIND")

    def test_refuses_installing_when_no_markdown_file_holds_anything_to_append_into(self):
        box = self._box()
        sequence = json.dumps([{"text": "Rehearse the job.",
                                "witness": {"kind": "rehearsal", "operand": "job1"}}])
        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            "--sequence", "-", stdin=sequence, proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_HOLDER_ABSENT")

    def test_refuses_when_two_files_already_carry_a_position_block(self):
        box = self._box()
        block = self.block_text("- [ ] 1. Step. `@rehearsal job1`\n")
        (box / "Method" / "AGREED.md").write_text(block, encoding="utf-8")
        (box / "Method" / "SECOND.md").write_text(block, encoding="utf-8")
        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_HOLDER_AMBIGUOUS")

    # --- compare-and-swap: the holder moving under a write (design decision 2) ---

    def test_refuses_when_the_holder_moves_between_location_and_write(self):
        """Mutation B (design decision 2, "stale offsets"): the holder file
        changes AFTER the read that located `existing_block`'s own offsets
        but BEFORE the write reaches it. Proxied by patching
        `impl_position.render` -- the last hook `cmd_position` calls before
        `write_spliced`'s own re-check -- to write concurrently as a side
        effect, then delegate to the real `render`. In-process (not
        `run_cli`'s subprocess) so the patch reaches the exact module
        object `cmd_position` itself imports.

        Distinct from `WriteSplicedCasTests` in `test_implementation_core.py`
        (which drives `write_spliced` directly with a hand-built mismatched
        digest): this proves the WIRING -- that `cmd_position` really does
        carry the location read's own digest all the way to the write call,
        never a digest of the second, later read `before_bytes` itself is.
        """
        box = self._box()
        holder = box / "Method" / "AGREED.md"
        holder.write_text(
            self.block_text("- [ ] 1. Something. `@record`\n",
                            sha256=self.PROPOSAL_SHA256, target="final"),
            encoding="utf-8")
        concurrent_bytes = b"# Rewritten by something else entirely\n"
        original_render = impl_position.render

        def _rewrite_holder_then_render(header, items):
            holder.write_bytes(concurrent_bytes)
            return original_render(header, items)

        proposals = self._proposals()
        (proposals / "r2.md").write_text("## 2\notro texto\n", encoding="utf-8")
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(proposals)
        self.addCleanup(os.environ.pop, "IMPLEMENTATION_PROPOSALS", None)

        args = argparse.Namespace(
            target=str(box), name="Method", sequence=None, reconcile=False,
            # A different revision than the block's own recorded one, so
            # this call is never `unchanged` and the write path -- and this
            # seam -- is actually reached.
            revision="r2.md", session="s1", replace=False)

        with unittest.mock.patch.object(impl_position, "render",
                                        side_effect=_rewrite_holder_then_render):
            with self.assertRaises(impl.Refused) as ctx:
                impl.cmd_position(args)
        self.assertEqual(ctx.exception.code, "POSITION_HOLDER_MOVED")
        # The offsets `existing_block` located are never applied to
        # `concurrent_bytes` -- the file holds exactly what the concurrent
        # write put there, untouched by the refused splice.
        self.assertEqual(holder.read_bytes(), concurrent_bytes)

    # --- migration: a pre-PR10 block is refused for reading, migratable for writing ---

    def test_a_legacy_block_refuses_verify_but_position_migrates_it(self):
        box = self._box()
        legacy = (
            "<!-- position revision=r1.md sha256=" + "a" * 64 +
            " derivedAt=2026-01-01T00:00:00Z session=s0 -->\n"
            "- [ ] 1. Old-grammar step. `@rehearsal job1`\n"
            "<!-- /position -->\n"
        )
        (box / "Method" / "AGREED.md").write_text(legacy, encoding="utf-8")

        verify_proc = self.run_cli("verify", "--target", str(box), "--name", "Method",
                                   "--revision", "r1.md", proposals=self._proposals())
        self.assertEqual(verify_proc.returncode, 2, verify_proc.stdout)
        self.assertEqual(json.loads(verify_proc.stdout)["code"], "POSITION_BLOCK_MALFORMED")

        migrate = self.run_cli("position", "--target", str(box), "--name", "Method",
                               "--revision", "r1.md", "--session", "s1",
                               "--target-level", "final",
                               proposals=self._proposals())
        self.assertEqual(migrate.returncode, 0, migrate.stdout)
        result = json.loads(migrate.stdout)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["targetLevel"], "final")
        self.assertEqual([item["text"] for item in result["sequence"]],
                         ["Old-grammar step."])

        on_disk = (box / "Method" / "AGREED.md").read_text(encoding="utf-8")
        self.assertIn("target=final", on_disk)

        verify_again = self.run_cli("verify", "--target", str(box), "--name", "Method",
                                    "--revision", "r1.md", proposals=self._proposals())
        self.assertEqual(verify_again.returncode, 0, verify_again.stdout)
        self.assertEqual(
            json.loads(verify_again.stdout)["position"]["targetLevel"], "final")

    # --- 3.2 refresh: item text and order survive byte-for-byte ---

    def test_refresh_leaves_item_text_and_order_untouched(self):
        box = self._box()
        payload = "The identity is $$E=mc^2$$ and \\tag{39} names it."
        body = (f"- [ ] 1. {payload} `@notebook Notebooks/nope.ipynb`\n"
                "- [ ] 2. Second step. `@rehearsal job-none`\n")
        (box / "Method" / "AGREED.md").write_text(
            self.block_text(body, sha256=self.PROPOSAL_SHA256), encoding="utf-8")
        before = (box / "Method" / "AGREED.md").read_bytes()

        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            proposals=self._proposals())

        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual([item["ordinal"] for item in result["sequence"]], [1, 2])
        self.assertEqual(result["sequence"][0]["text"], payload)
        self.assertEqual(result["sequence"][1]["text"], "Second step.")
        # Neither witness is measurable in this box (no such notebook, no
        # such job), so nothing could have flipped a mark -- and a refresh
        # that found nothing to flip never rewrites the file at all.
        after = (box / "Method" / "AGREED.md").read_bytes()
        self.assertEqual(before, after)

    # --- 3.3 install: writes the section and derives its marks immediately ---

    def test_install_writes_a_fresh_sequence_and_derives_marks_immediately(self):
        box = self._box()
        (box / "Method" / "AGREED.md").write_text(
            "# Agreed\n\n- [x] 1. Something already settled.\n", encoding="utf-8")
        sequence = json.dumps([
            {"text": "Ceiling search.", "witness": {"kind": "record"}},
            {"text": "Rehearse the job.",
             "witness": {"kind": "rehearsal", "operand": "job1"}},
        ])
        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            "--target-level", "final",
                            "--sequence", "-", stdin=sequence, proposals=self._proposals())

        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["holder"], "Method/AGREED.md")
        self.assertEqual([item["witness"]["kind"] for item in result["sequence"]],
                         ["record", "rehearsal"])
        # Neither witness is measurable in this box (no search declared, no
        # job ever rehearsed), so install DERIVES rather than assuming every
        # fresh item starts ticked.
        self.assertEqual(result["unmeasured"], [1, 2])
        on_disk = (box / "Method" / "AGREED.md").read_text(encoding="utf-8")
        self.assertIn("Something already settled.", on_disk)
        self.assertIn("<!-- position", on_disk)

    def test_refuses_installing_over_an_existing_block_without_replace(self):
        box = self._box()
        (box / "Method" / "AGREED.md").write_text(
            self.block_text("- [ ] 1. Old step. `@rehearsal job1`\n"), encoding="utf-8")
        sequence = json.dumps([{"text": "New step.",
                                "witness": {"kind": "rehearsal", "operand": "job2"}}])
        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            "--sequence", "-", stdin=sequence, proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_BLOCK_EXISTS")

    def test_replace_overwrites_the_existing_block(self):
        box = self._box()
        (box / "Method" / "AGREED.md").write_text(
            self.block_text("- [ ] 1. Old step. `@rehearsal job1`\n"), encoding="utf-8")
        sequence = json.dumps([{"text": "New step.",
                                "witness": {"kind": "rehearsal", "operand": "job2"}}])
        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            "--sequence", "-", "--replace", stdin=sequence,
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "written")
        self.assertEqual([item["text"] for item in result["sequence"]], ["New step."])
        on_disk = (box / "Method" / "AGREED.md").read_text(encoding="utf-8")
        self.assertNotIn("Old step.", on_disk)
        self.assertIn("New step.", on_disk)

    # --- 3.4 the ledger: appended on a real write, never on a no-op ---

    def test_refresh_flips_a_measurable_mark_and_appends_one_ledger_event(self):
        box = self._box()
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
            "__benchmark__ = {'search': {'record': 'Results/record.json'}}\n",
            encoding="utf-8")
        (box / "Method" / "Results").mkdir(parents=True)
        (box / "Method" / "Results" / "record.json").write_text("{}", encoding="utf-8")
        (box / "Method" / "AGREED.md").write_text(
            self.block_text("- [ ] 1. Ceiling search. `@record`\n"), encoding="utf-8")

        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            proposals=self._proposals())

        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["wrote"], [1])
        on_disk = (box / "Method" / "AGREED.md").read_text(encoding="utf-8")
        self.assertIn("- [x] 1. Ceiling search.", on_disk)
        ledger = box / "Method" / ".implementation" / "position.jsonl"
        events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "position")

    def test_refresh_reports_unchanged_and_appends_no_event_when_nothing_moves(self):
        box = self._box()
        (box / "Method" / "AGREED.md").write_text(
            self.block_text("- [ ] 1. Step. `@rehearsal job-none`\n",
                            sha256=self.PROPOSAL_SHA256), encoding="utf-8")

        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1",
                            proposals=self._proposals())

        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "unchanged")
        self.assertFalse((box / "Method" / ".implementation" / "position.jsonl").exists())


class CommandRosterTests(unittest.TestCase):
    """`COMMANDS` binds every subcommand `main()` accepts; a table in
    `SKILL.md` is the human-facing roster of what each of the four
    write-verbs this change adds writes and refuses on — the same
    table-vs-code mechanism the `verify`/`probe` rosters already apply,
    one level up (design §7.1), narrowed to the commands that write.

    Full coverage over every key of `COMMANDS` (nine to thirteen, design
    §7.1) is `test_every_command_dispatched_is_accounted_for`'s assertion:
    the four write-verbs are held to a row here, and the remaining nine are
    named explicitly as read-only or otherwise out of this table's own
    scope — `env`/`name`/`plan`/`apply`/`admit`/`handoff`/`compose` predate
    this change, and `probe`/`verify` already carry their own status/fact
    rosters (`ProbeReportedFactsRosterTests`/`VerifyStatusRosterTests`), so
    documenting their statuses a second time here would be the second
    definition of one rule this file's own doctrine keeps rejecting.
    """

    COMMAND_TABLE_HEADER = "| Command | What it writes | Refuses on |"

    #: Predates this change, or already carries its own roster elsewhere —
    #: named explicitly rather than left as a silent gap in this table.
    DOCUMENTED_ELSEWHERE = frozenset(
        {"env", "name", "plan", "apply", "admit", "handoff", "compose",
         "probe", "verify"})

    def command_rows(self):
        tables = markdown_table_rows(
            SKILL_MD.read_text(encoding="utf-8"), self.COMMAND_TABLE_HEADER)
        self.assertEqual(
            len(tables), 1,
            "the command roster is stated in no parseable table, so nothing "
            "holds a new command to a documented row")
        return tables[0]

    def test_position_is_registered_and_documented(self):
        self.assertIn("position", impl.COMMANDS)
        rows = {row[0].strip("`"): row for row in self.command_rows()}
        self.assertIn("position", rows)
        writes, refuses = rows["position"][1], rows["position"][2]
        self.assertTrue(writes.strip(), "the `position` row names nothing it writes")
        self.assertTrue(refuses.strip(), "the `position` row names nothing it refuses on")

    def test_every_command_dispatched_is_accounted_for(self):
        write_verbs = {"position", "discuss", "gate", "offer", "close", "step"}
        dispatched = set(impl.COMMANDS)
        self.assertEqual(
            dispatched, self.DOCUMENTED_ELSEWHERE | write_verbs,
            "`COMMANDS` dispatches a command this roster neither documents "
            "nor names as out of scope")

        rows = {row[0].strip("`"): row for row in self.command_rows()}
        for command in sorted(write_verbs):
            self.assertIn(command, rows,
                          f"`{command}` writes and has no row in the command roster")
            writes, refuses = rows[command][1], rows[command][2]
            self.assertTrue(writes.strip(), f"the `{command}` row names nothing it writes")
            self.assertTrue(refuses.strip(), f"the `{command}` row names nothing it refuses on")


class PositionReconcileTests(unittest.TestCase):
    """`--reconcile` — reconstruction from a target that already has
    notebooks, job folders and a declared search, but no position section
    yet (design §3.3, spec "Reconstruction From an Existing Target").

    The fixture (`tests/fixtures/agreed_shape_reconcile.md`) mirrors the
    real `implementations/Domain_Adaptation/MIL-CREDA/AGREED.md`'s *shape*
    — ~90 checklist items across sixteen `##` sections, plus a trailing
    no-bullet `Reversed` section — because `implementations/` is gitignored
    and reconciliation has to be proven against a realistically dense,
    hand-curated document, not a two-line toy nobody would mistake for a
    stress test.
    """

    FIXTURE = Path(__file__).resolve().parent / "fixtures" / "agreed_shape_reconcile.md"

    def _proposals(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "r1.md").write_text("## 1\ntexto\n", encoding="utf-8")
        return root

    def _box(self, agreed_text=None):
        box = FORGE / "implementations" / f"_e2e_position_reconcile_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        (box / "Method").mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text("", encoding="utf-8")
        if agreed_text is not None:
            (box / "Method" / "AGREED.md").write_text(agreed_text, encoding="utf-8")
        return box

    def run_cli(self, *args, proposals=None):
        env = dict(os.environ)
        if proposals is not None:
            env["IMPLEMENTATION_PROPOSALS"] = str(proposals)
        return subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, cwd=FORGE, env=env)

    def _shards(self, stamps):
        """A real shard directory on disk, one subdirectory per shard, each
        holding a `shard.json` stamp -- the exact shape `shard_io.read_shards`
        assumes, and the same shape `ShardRefusalCrossJoinTests.build_shards`
        builds elsewhere in this file for `verify`. Duplicated here rather
        than shared across classes because a stray cross-class dependency
        would make this class's own fixtures harder to read in isolation.
        """
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for shard, stamp in stamps.items():
            folder = root / shard
            folder.mkdir()
            (folder / "shard.json").write_text(json.dumps(stamp), encoding="utf-8")
        return root

    # --- 4.2: the fixture's 90 items and its Reversed section survive ---

    def test_reconcile_appends_without_disturbing_existing_items_or_reversed_section(self):
        fixture_text = self.FIXTURE.read_text(encoding="utf-8")
        box = self._box(agreed_text=fixture_text)
        (box / "Method" / "Notebooks").mkdir(parents=True)
        (box / "Method" / "Notebooks" / "pilot.ipynb").write_text("{}", encoding="utf-8")

        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1", "--target-level", "final",
                            "--reconcile", proposals=self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["holder"], "Method/AGREED.md")
        self.assertGreaterEqual(len(result["sequence"]), 1)

        after = (box / "Method" / "AGREED.md").read_text(encoding="utf-8")
        self.assertTrue(after.startswith(fixture_text))
        # Every one of the fixture's 90 items, verbatim, still present --
        # not merely a prefix check, which a splice that silently truncated
        # mid-file could still pass.
        for line in fixture_text.splitlines():
            if line.strip().startswith("- ["):
                self.assertIn(line, after)
        self.assertIn("## Reversed", after)
        self.assertIn(
            "This reversal was made without reading this file", after)
        self.assertIn("<!-- position", after)

    # --- 4.3: witness identity across reruns ---

    def test_reconcile_preserves_witness_identity_across_reruns(self):
        box = self._box(agreed_text="# Agreed\n\n- [x] Something already settled.\n")
        (box / "Method" / "Notebooks").mkdir(parents=True)
        (box / "Method" / "Notebooks" / "a.ipynb").write_text("{}", encoding="utf-8")
        proposals = self._proposals()

        first = self.run_cli("position", "--target", str(box), "--name", "Method",
                             "--revision", "r1.md", "--session", "s1", "--target-level", "final",
                             "--reconcile", proposals=proposals)
        self.assertEqual(first.returncode, 0, first.stdout)
        first_result = json.loads(first.stdout)
        self.assertEqual(len(first_result["sequence"]), 1)
        self.assertEqual(first_result["sequence"][0]["witness"],
                         {"kind": "notebook", "operand": "Notebooks/a.ipynb", "twostate": True})

        # A human writes the real sentence over the placeholder.
        agreed_path = box / "Method" / "AGREED.md"
        agreed_path.write_text(
            agreed_path.read_text(encoding="utf-8").replace(
                impl.POSITION_PLACEHOLDER_TEXT,
                "Read the pilot notebook into the report."),
            encoding="utf-8")

        # A second notebook appears before the second reconcile.
        (box / "Method" / "Notebooks" / "b.ipynb").write_text("{}", encoding="utf-8")
        second = self.run_cli("position", "--target", str(box), "--name", "Method",
                              "--revision", "r1.md", "--session", "s2",
                              "--reconcile", proposals=proposals)
        self.assertEqual(second.returncode, 0, second.stdout)
        second_result = json.loads(second.stdout)
        self.assertEqual(len(second_result["sequence"]), 2)
        self.assertEqual(second_result["sequence"][0]["ordinal"], 1)
        self.assertEqual(second_result["sequence"][0]["text"],
                         "Read the pilot notebook into the report.")
        self.assertEqual(second_result["sequence"][0]["witness"],
                         {"kind": "notebook", "operand": "Notebooks/a.ipynb", "twostate": True})
        self.assertEqual(second_result["sequence"][1]["ordinal"], 2)
        self.assertEqual(second_result["sequence"][1]["witness"],
                         {"kind": "notebook", "operand": "Notebooks/b.ipynb", "twostate": True})

    # --- 4.4: `--reconcile --shards` measures what it just discovered ---

    def test_reconcile_measures_an_arrived_shard_it_discovers(self):
        """RED before the fix, for the exact reason design §11 names:
        `--reconcile --shards <dir>` discovers a `@shard` witness for every
        arrived shard, but `position`'s own evidence
        (`_position_write_evidence`) hardcoded `shardsArrived: None`
        regardless of `--shards`, so the very witness this call just
        discovered from `<dir>` read `unmeasured` instead of `True` -- the
        arrival evidence was a function argument away and never read.
        """
        box = self._box(agreed_text="# Agreed\n\n- [x] Something already settled.\n")
        shards = self._shards({"a": {"epochs": 5}})

        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", "r1.md", "--session", "s1", "--target-level", "final",
                            "--reconcile", "--shards", str(shards),
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        shard_item = next(item for item in result["sequence"]
                          if item["witness"] == {"kind": "shard", "operand": "a", "twostate": True})
        self.assertTrue(
            shard_item["derived"],
            f"a shard just discovered from --shards's own directory reads "
            f"derived={shard_item['derived']!r} instead of True; --reconcile "
            "found it but position's own evidence never learns --shards was "
            "given at all.")

    # --- 4.5: the falsifier, an assertion that runs (design §11) ---

    def test_unmeasured_never_outnumbers_measured_on_reconciled_target(self):
        """If this fails, the fix is design §11's own escalation — move
        `@shard` off the no-flag default — never loosening this assertion.

        Ten shard directories against six other witnesses (one `@record`,
        five `@notebook`) is not an arbitrary ratio: it is the real shape
        measured against a MIL-CREDA-shaped target (ten shards under
        `Results/Benchmark/shards`, five notebooks, one declared record),
        reproduced with `position --reconcile --shards <dir>` -- the exact
        invocation that surfaced `_position_write_evidence`'s hardcoded
        `shardsArrived: None`. RED before that function threads `--shards`
        through (6 measured vs 10 unmeasured); GREEN once it does.
        """
        box = self._box(agreed_text=self.FIXTURE.read_text(encoding="utf-8"))
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
            "__benchmark__ = {'search': {'record': 'Results/record.json'}}\n",
            encoding="utf-8")
        (box / "Method" / "Results").mkdir(parents=True)
        (box / "Method" / "Results" / "record.json").write_text("{}", encoding="utf-8")
        (box / "Method" / "Notebooks").mkdir(parents=True)
        for notebook in ("a", "b", "c", "d", "e"):
            (box / "Method" / "Notebooks" / f"{notebook}.ipynb").write_text(
                "{}", encoding="utf-8")
        shards = self._shards({f"s{i:02d}": {"epochs": 5} for i in range(10)})
        proposals = self._proposals()

        reconcile = self.run_cli("position", "--target", str(box), "--name", "Method",
                                 "--revision", "r1.md", "--session", "s1", "--target-level", "final",
                                 "--reconcile", "--shards", str(shards),
                                 proposals=proposals)
        self.assertEqual(reconcile.returncode, 0, reconcile.stdout)
        position = json.loads(reconcile.stdout)

        measured = sum(1 for item in position["sequence"] if item["derived"] is not None)
        unmeasured = sum(1 for item in position["sequence"] if item["derived"] is None)
        self.assertGreaterEqual(
            measured, unmeasured,
            f"`unmeasured` ({unmeasured}) outnumbers `measured` ({measured}) on "
            "a reconciled target shaped like a real one (10 shards, 6 other "
            "witnesses), given the exact `--shards` directory that discovered "
            "them -- the mechanism is decaying into the prose it replaced "
            "(design §11's own falsifier).")


class DiscussCommandTests(unittest.TestCase):
    """`discuss` -- discussion as an operation with a return value (design §3.3).

    Replaces the prose at `SKILL.md`'s AGREEMENTS doctrine telling the agent to
    name a collision with an existing agreement and wait for the user: prose
    cannot be held to a return statement, so this makes "I asked" a fact with
    a ledger line instead. It never gates -- there is no refusal here for an
    unanswered question, only a reported `status`.
    """

    def _box(self):
        box = FORGE / "implementations" / f"_e2e_discuss_cmd_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        (box / "Method").mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text("", encoding="utf-8")
        return box

    def run_cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(CLI), *args], input=stdin,
                              capture_output=True, text=True, cwd=FORGE)

    # --- 5.1: collides is computed fresh each call, never remembered ---

    def test_discuss_computes_collides_not_remembers(self):
        box = self._box()
        (box / "Method" / "AGREED.md").write_text(
            "# Agreed\n\n"
            "- [x] Read the pilot notebook, Notebooks/pilot.ipynb, into the report.\n",
            encoding="utf-8")

        first = self.run_cli("discuss", "--target", str(box), "--name", "Method",
                             "--about", "notebook Notebooks/pilot.ipynb",
                             "--question", "Does an agreement already name this notebook?")
        self.assertEqual(first.returncode, 0, first.stdout)
        first_result = json.loads(first.stdout)
        self.assertEqual(len(first_result["collides"]), 1)
        self.assertIn("Notebooks/pilot.ipynb", first_result["collides"][0])

        # The identical call, after the collision is edited out of the file --
        # if `collides` were remembered from the first call rather than
        # computed fresh, it would still report one here.
        (box / "Method" / "AGREED.md").write_text(
            "# Agreed\n\n- [x] Something unrelated.\n", encoding="utf-8")
        second = self.run_cli("discuss", "--target", str(box), "--name", "Method",
                              "--about", "notebook Notebooks/pilot.ipynb",
                              "--question", "Does an agreement already name this notebook?")
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertEqual(json.loads(second.stdout)["collides"], [])

    # --- 5.2: open, then answered -- a real status transition ---

    def test_discuss_open_then_answered_status_transition(self):
        box = self._box()
        (box / "Method" / "AGREED.md").write_text("# Agreed\n", encoding="utf-8")

        opened = self.run_cli("discuss", "--target", str(box), "--name", "Method",
                              "--about", "rehearsal governing-search",
                              "--question", "Should this job rehearse before the campaign?")
        self.assertEqual(opened.returncode, 0, opened.stdout)
        opened_result = json.loads(opened.stdout)
        self.assertEqual(opened_result["status"], "open")
        self.assertIsNone(opened_result["answered"])

        answered = self.run_cli("discuss", "--target", str(box), "--name", "Method",
                                "--about", "rehearsal governing-search",
                                "--question", "Should this job rehearse before the campaign?",
                                "--answer", "Yes, rehearse it first.")
        self.assertEqual(answered.returncode, 0, answered.stdout)
        answered_result = json.loads(answered.stdout)
        self.assertEqual(answered_result["status"], "answered")
        self.assertEqual(answered_result["answered"], "Yes, rehearse it first.")

        ledger = box / "Method" / ".implementation" / "position.jsonl"
        events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["kind"] for e in events], ["discuss", "discuss"])
        self.assertEqual([e["status"] for e in events], ["open", "answered"])

    def test_discuss_about_accepts_an_ordinal_into_the_position_sequence(self):
        """The other half of `--about <ordinal|witness>` (design §3.3): a
        caller may name a step by its number instead of repeating its witness.
        """
        box = self._box()
        header = {"revision": "r1.md", "revisionSha256": "a" * 64,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
        items = [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                  "witness": {"kind": "rehearsal", "operand": "job1"}}]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")

        proc = self.run_cli("discuss", "--target", str(box), "--name", "Method",
                            "--about", "1", "--question", "Is job1 the right job?")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["about"], {"ordinal": 1, "kind": "rehearsal",
                                           "operand": "job1", "twostate": True})

    def test_discuss_refuses_an_ordinal_not_in_the_sequence(self):
        box = self._box()
        (box / "Method" / "AGREED.md").write_text("# Agreed\n", encoding="utf-8")
        proc = self.run_cli("discuss", "--target", str(box), "--name", "Method",
                            "--about", "9", "--question", "What is step 9?")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "DISCUSS_ABOUT_NOT_FOUND")


class GateCommandTests(unittest.TestCase):
    """`gate` -- the launch authorization record (design §4, domain
    launch-authorization). Checked in refusing-costs-nothing order: the
    justification first (pure argv), then whether a position section exists
    to reach a rung in, then the un-forgeable readiness measurement itself,
    then whether the rung this job's witness names has actually been
    reached.
    """

    PROPOSAL_REVISION = "r1.md"
    PROPOSAL_TEXT = "## 1\ntexto\n"
    PROPOSAL_SHA256 = hashlib.sha256(PROPOSAL_TEXT.encode("utf-8")).hexdigest()

    def _proposals(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / self.PROPOSAL_REVISION).write_text(self.PROPOSAL_TEXT, encoding="utf-8")
        (root / "r2.md").write_text("## 2\notro\n", encoding="utf-8")
        return root

    def _box(self, packages=("Method",)):
        self._box_count = getattr(self, "_box_count", 0) + 1
        box = FORGE / "implementations" / f"_e2e_gate_cmd_{os.getpid()}_{id(self)}_{self._box_count}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "gate-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "gate-tests@example.invalid"
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        for package in packages:
            (box / "src" / package).mkdir(parents=True, exist_ok=True)
            (box / "src" / package / "__init__.py").write_text("", encoding="utf-8")
            (box / "src" / f"{package}_Benchmark").mkdir(parents=True, exist_ok=True)
            (box / "src" / f"{package}_Benchmark" / "__init__.py").write_text(
                "", encoding="utf-8")
            (box / package).mkdir(parents=True, exist_ok=True)
        (box / "tests").mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "add", "-A"], cwd=box, env=env, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=box, env=env,
                       check=True, capture_output=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=box, env=env, check=True,
            capture_output=True, text=True).stdout.strip()
        return box, commit

    def _write_job_folder(self, box, commit, *, service="svc", job_name="job1",
                          product="Method", clone_paths=("src/Method",)):
        job_dir = box / "tools" / service / job_name
        job_dir.mkdir(parents=True, exist_ok=True)
        run_config = {
            "schemaVersion": 1, "product": product, "service": service,
            "jobName": job_name, "commit": commit,
            "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
            "clonePaths": list(clone_paths),
            "run": {"module": f"{product}.module", "function": "run", "kwargs": {}},
            "runnerTemplate": [
                {"path": "assets/runner_bootstrap.py", "sha256": "0" * 64},
                {"path": "assets/runner_invoke.py", "sha256": "0" * 64},
            ],
        }
        (job_dir / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
        return job_dir

    def _write_smoke_pass(self, box, *, product="Method", job_name="job1",
                          commit, worker="w1"):
        smoke_path = box / product / ".remote-execution" / "smoke.jsonl"
        smoke_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"kind": "smokeResult", "ts": "2026-08-27T00:00:00Z",
                  "jobName": job_name, "result": "pass", "commit": commit,
                  "worker": worker, "missing": []}
        with smoke_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    def run_cli(self, *args, proposals=None):
        env = dict(os.environ)
        if proposals is not None:
            env["IMPLEMENTATION_PROPOSALS"] = str(proposals)
        return subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, cwd=FORGE, env=env)

    # --- 6.1: no passing rehearsal on file -- refused, never asserted ---

    def test_gate_refuses_not_ready_when_smoke_ready_false(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        header = {"revision": self.PROPOSAL_REVISION,
                  "revisionSha256": self.PROPOSAL_SHA256,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
        items = [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                  "witness": {"kind": "rehearsal", "operand": "job1"}}]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")

        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1", "--worker", "w1",
                            "--justification", "Because it is time.",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "NOT_READY")

    # --- 6.2: the rest of the refusals ---

    def test_gate_refuses_empty_justification(self):
        box, _ = self._box()
        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1", "--worker", "w1",
                            "--justification", "   ",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "EMPTY_JUSTIFICATION")

    def test_gate_refuses_on_absent_or_stale_position(self):
        proposals = self._proposals()

        with self.subTest("absent"):
            box, _ = self._box()
            proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                                "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                                "--job", "job1", "--worker", "w1",
                                "--justification", "Because it is time.",
                                proposals=proposals)
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_ABSENT")

        with self.subTest("stale"):
            box, _ = self._box()
            header = {"revision": self.PROPOSAL_REVISION, "revisionSha256": "a" * 64,
                      "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
            items = [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                      "witness": {"kind": "rehearsal", "operand": "job1"}}]
            (box / "Method" / "AGREED.md").write_text(
                impl_position.render(header, items), encoding="utf-8")
            # Bound to r1.md's name, but "a"*64 never matches r2.md's real
            # content -- gating against r2.md finds the header stale.
            proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                                "--revision", "r2.md", "--session", "s1",
                                "--job", "job1", "--worker", "w1",
                                "--justification", "Because it is time.",
                                proposals=proposals)
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_STALE")

    def test_gate_refuses_sequence_not_reached(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        header = {"revision": self.PROPOSAL_REVISION,
                  "revisionSha256": self.PROPOSAL_SHA256,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
        items = [
            {"ordinal": 1, "mark": " ", "text": "Read the pilot notebook.",
             "witness": {"kind": "notebook", "operand": "Notebooks/pilot.ipynb"}},
            {"ordinal": 2, "mark": " ", "text": "Rehearse the job.",
             "witness": {"kind": "rehearsal", "operand": "job1"}},
        ]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")

        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1", "--worker", "w1",
                            "--justification", "Because it is time.",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "SEQUENCE_NOT_REACHED")

    # --- 6.3: the record itself, once every precondition is real ---

    def test_gate_records_the_authorization_after_a_passing_rehearsal(self):
        """The runtime harness this task is scored against: a rehearsal
        actually recorded via `readiness`'s own three-fact bind (through
        `remote_execution_jobs_state`'s `smokeReady`) on a scratch job
        folder, then `gate` reads it back rather than trusting an assertion.
        """
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        header = {"revision": self.PROPOSAL_REVISION,
                  "revisionSha256": self.PROPOSAL_SHA256,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
        items = [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                  "witness": {"kind": "rehearsal", "operand": "job1"}}]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")

        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1", "--worker", "w1",
                            "--justification", "Rehearsal passed at the pinned commit.",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "recorded")
        self.assertEqual(result["job"], "job1")
        self.assertEqual(result["commit"], commit)
        # No token: the whole point (design §4.1) is that this record cannot
        # be minted by computing a digest over the caller's own argv.
        self.assertNotIn("token", "".join(result.keys()).lower())

        ledger = box / "Method" / ".implementation" / "position.jsonl"
        events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[-1]["kind"], "gate")
        self.assertEqual(events[-1]["jobName"], "job1")
        self.assertEqual(events[-1]["justification"], "Rehearsal passed at the pinned commit.")

    # --- 6.4: the campaign form (PR8, design revision) ------------------
    #
    # PR7 shipped `gate` with no way to authorize a campaign at all --
    # `remote_cli._verify_launch_authorization()` exempted `units` truthy
    # entirely, which left the single send authorized and the campaign
    # (the full-scale, multi-worker launch this mechanism exists to gate)
    # not. `--unit`, repeatable, closes that: it binds the exact ordered
    # unit list a later `submit --unit ...` will carry, the same
    # derivation `campaign_consent_token()` already uses for consent.

    def test_gate_refuses_worker_and_unit_together(self):
        box, _ = self._box()
        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1", "--worker", "w1",
                            "--unit", "u0", "--unit", "u1",
                            "--justification", "Because it is time.",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "GATE_WORKER_UNIT_CONFLICT")

    def test_gate_refuses_when_neither_worker_nor_unit_given(self):
        box, _ = self._box()
        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1",
                            "--justification", "Because it is time.",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "GATE_WORKER_REQUIRED")

    def test_gate_records_a_campaign_authorization_with_ordered_units_and_no_worker(
        self,
    ):
        """The runtime harness for the campaign form, mirroring `test_gate_
        records_the_authorization_after_a_passing_rehearsal` above: a real
        rehearsal recorded through `readiness`'s own three-fact bind, then
        `--unit` authorizes the launch with `worker: None` recorded --
        never a named account, matching what a campaign `submit`
        invocation's own binding always is.
        """
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        header = {"revision": self.PROPOSAL_REVISION,
                  "revisionSha256": self.PROPOSAL_SHA256,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
        items = [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                  "witness": {"kind": "rehearsal", "operand": "job1"}}]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")

        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1", "--unit", "u0", "--unit", "u1",
                            "--justification", "Rehearsal passed; launching the campaign.",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "recorded")
        self.assertIsNone(result["worker"])
        self.assertEqual(result["units"], ["u0", "u1"])

        ledger = box / "Method" / ".implementation" / "position.jsonl"
        events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[-1]["kind"], "gate")
        self.assertIsNone(events[-1]["worker"])
        # Order preserved, never sorted -- the same rule `campaign_consent_
        # token()` documents for consent (Decision 5).
        self.assertEqual(events[-1]["units"], ["u0", "u1"])


class OfferCommandTests(unittest.TestCase):
    """`offer` -- the state-derived action menu. Refuses to publish before
    the run-all-pilots question has an answer on record, then publishes a
    closed action set derived entirely from the identical facts `gate`
    itself reads (spec "One shared availability rule for the publisher and
    `cmd_gate`").
    """

    PROPOSAL_REVISION = "r1.md"
    PROPOSAL_TEXT = "## 1\ntexto\n"
    PROPOSAL_SHA256 = hashlib.sha256(PROPOSAL_TEXT.encode("utf-8")).hexdigest()

    def _proposals(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / self.PROPOSAL_REVISION).write_text(self.PROPOSAL_TEXT, encoding="utf-8")
        (root / "r2.md").write_text("## 2\notro\n", encoding="utf-8")
        return root

    def setUp(self):
        """Every in-process `impl.cmd_offer(...)` call in this class reads
        `revision_source()` straight off `os.environ`, in THIS process --
        unlike `run_cli`'s own subprocess calls, which pass `proposals=`
        as a child environment variable, an in-process call has no such
        seam, so this class-wide fixture is set once here and every
        `_offer_args(...)` call below relies on it being present.
        """
        proposals = self._proposals()
        patcher = unittest.mock.patch.dict(
            os.environ, {"IMPLEMENTATION_PROPOSALS": str(proposals)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _box(self, packages=("Method",)):
        self._box_count = getattr(self, "_box_count", 0) + 1
        box = FORGE / "implementations" / f"_e2e_offer_cmd_{os.getpid()}_{id(self)}_{self._box_count}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "offer-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "offer-tests@example.invalid"
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        for package in packages:
            (box / "src" / package).mkdir(parents=True, exist_ok=True)
            (box / "src" / package / "__init__.py").write_text("", encoding="utf-8")
            (box / "src" / f"{package}_Benchmark").mkdir(parents=True, exist_ok=True)
            (box / "src" / f"{package}_Benchmark" / "__init__.py").write_text(
                "", encoding="utf-8")
            (box / package).mkdir(parents=True, exist_ok=True)
        (box / "tests").mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "add", "-A"], cwd=box, env=env, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=box, env=env,
                       check=True, capture_output=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=box, env=env, check=True,
            capture_output=True, text=True).stdout.strip()
        return box, commit

    def _write_job_folder(self, box, commit, *, service="offer-fixture-svc",
                          job_name="job1", product="Method",
                          clone_paths=("src/Method",)):
        job_dir = box / "tools" / service / job_name
        job_dir.mkdir(parents=True, exist_ok=True)
        run_config = {
            "schemaVersion": 1, "product": product, "service": service,
            "jobName": job_name, "commit": commit,
            "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
            "clonePaths": list(clone_paths),
            "run": {"module": f"{product}.module", "function": "run", "kwargs": {}},
            "runnerTemplate": [
                {"path": "assets/runner_bootstrap.py", "sha256": "0" * 64},
                {"path": "assets/runner_invoke.py", "sha256": "0" * 64},
            ],
        }
        (job_dir / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
        return job_dir

    def _write_smoke_pass(self, box, *, product="Method", job_name="job1",
                          commit, worker="w1"):
        smoke_path = box / product / ".remote-execution" / "smoke.jsonl"
        smoke_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"kind": "smokeResult", "ts": "2026-08-27T00:00:00Z",
                  "jobName": job_name, "result": "pass", "commit": commit,
                  "worker": worker, "missing": []}
        with smoke_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    def _write_smoke_fail(self, box, *, product="Method", job_name="job1",
                          commit, worker="w1"):
        """A recorded, matching-commit smoke result whose own `result` is
        `"fail"` -- so `smokeReady`/`derive()` measure `False`, not
        `None`. Distinct from never running one at all: an unmeasured
        witness is `unbacked`, a measured-and-failing one that is ticked
        anyway is `disagrees`, and only the latter is this helper's job.
        """
        smoke_path = box / product / ".remote-execution" / "smoke.jsonl"
        smoke_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"kind": "smokeResult", "ts": "2026-08-27T00:00:00Z",
                  "jobName": job_name, "result": "fail", "commit": commit,
                  "worker": worker, "missing": []}
        with smoke_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    def _write_agreed(self, box, items):
        header = {"revision": self.PROPOSAL_REVISION,
                  "revisionSha256": self.PROPOSAL_SHA256,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")

    def run_cli(self, *args, proposals=None):
        env = dict(os.environ)
        if proposals is not None:
            env["IMPLEMENTATION_PROPOSALS"] = str(proposals)
        return subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, cwd=FORGE, env=env)

    def _register_fixture_reporter(self, box, service, capacity=(3, 2)):
        """Registers a capacity reporter directly, bypassing the file-based
        `_load_backend_module` mechanism -- this test runs `cmd_offer`
        IN-PROCESS (never as a subprocess) specifically so this
        registration, made through the exact `ADAPTER` module object
        `cmd_offer` itself reads, is visible to it.
        """
        rcli = impl._load_remote_execution_cli()
        rcli.ADAPTER.register_declared_capacity(service, lambda: capacity)
        return rcli

    def _offer_args(self, box, *, answer=None, session="s1",
                    revision=None):
        return argparse.Namespace(
            target=str(box), name="Method",
            revision=revision or self.PROPOSAL_REVISION, session=session,
            answer=answer)

    # --- refusal shape and pre-answer behavior ----------------------------

    def test_offer_refuses_a_non_token_answer_with_the_same_json_refusal_shape(self):
        box, _ = self._box()
        proc = self.run_cli("offer", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--answer", "maybe", proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["code"], "OFFER_ANSWER_NOT_A_TOKEN")
        # The identical key shape every other refusal prints -- proves this
        # went through the coded `Refused` path, never argparse `choices`,
        # which would have printed usage text on stderr and nothing
        # JSON-shaped on stdout at all.
        self.assertEqual(set(result), {"status", "code", "detail"})

    def test_offer_refuses_before_any_answer_and_publishes_no_actions_key(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        proc = self.run_cli("offer", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        result = json.loads(proc.stdout)
        self.assertEqual(result["code"], "OFFER_UNANSWERED")
        self.assertNotIn("actions", result)

    def test_a_pre_existing_ledger_with_no_offer_event_reads_as_unanswered(self):
        """A `position.jsonl` written before this event kind existed --
        only `gate`/`step` events on it -- must read the same as a fresh
        target: absence, never an error.
        """
        box, commit = self._box()
        self._write_job_folder(box, commit)
        ledger = box / "Method" / ".implementation" / "position.jsonl"
        impl_position.append_event(ledger, {
            "kind": "gate", "jobName": "job1", "worker": "w1", "commit": commit,
            "revision": self.PROPOSAL_REVISION, "revisionSha256": self.PROPOSAL_SHA256,
            "entrypoint": "tools/offer-fixture-svc/job1/run.py", "units": [],
            "justification": "prior work", "session": "s0", "at": "2026-08-27T00:00:00Z",
        })
        proc = self.run_cli("offer", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "OFFER_UNANSWERED")

    def test_offer_records_the_answer_on_first_call_and_reuses_it_after(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        proposals = self._proposals()

        first = self.run_cli("offer", "--target", str(box), "--name", "Method",
                             "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                             "--answer", "no", proposals=proposals)
        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertEqual(json.loads(first.stdout)["status"], "recorded")

        second = self.run_cli("offer", "--target", str(box), "--name", "Method",
                              "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                              proposals=proposals)
        self.assertEqual(second.returncode, 0, second.stdout)
        result = json.loads(second.stdout)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["answer"], "no")

        ledger = box / "Method" / ".implementation" / "position.jsonl"
        offer_events = [json.loads(line) for line
                        in ledger.read_text(encoding="utf-8").splitlines()
                        if json.loads(line).get("kind") == "offer"]
        self.assertEqual(len(offer_events), 1,
                         "a repeat call with no --answer must not append a "
                         "second offer event")

    # --- action shape -------------------------------------------------

    def test_action_shape_is_exactly_the_four_closed_keys_and_never_carries_a_reason(self):
        box, commit = self._box()
        self._register_fixture_reporter(box, "offer-fixture-svc")
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])

        result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        self.assertGreaterEqual(len(result["actions"]), 2)
        for action in result["actions"]:
            self.assertEqual(set(action), {"id", "command", "establishes", "binding"})
            self.assertNotIn("reason", action)
            self.assertIn(action["id"], impl.ACTION_IDS)

    def test_launch_binding_carries_declared_capacity_never_ceiling(self):
        box, commit = self._box()
        self._register_fixture_reporter(box, "offer-fixture-svc", capacity=(3, 2))
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])

        result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        launch = next(a for a in result["actions"] if a["id"] == "launch")
        self.assertEqual(launch["binding"]["declaredCapacity"], 6)
        self.assertNotIn("ceiling", launch["binding"])
        self.assertEqual(launch["binding"]["workers"], 3)
        self.assertEqual(launch["binding"]["perWorker"], 2)
        self.assertEqual(launch["binding"]["job"], "job1")
        self.assertEqual(launch["binding"]["commit"], commit)
        self.assertEqual(launch["binding"]["units"], [])
        self.assertEqual(launch["binding"]["rung"], 1)

    def test_the_answer_token_alone_decides_pilot_all_versus_expand_contract(self):
        box, commit = self._box()
        proposals = self._proposals()

        yes_box, _ = self._box()
        yes = impl.cmd_offer(self._offer_args(yes_box, answer="yes"))
        self.assertIn("pilot-all", {a["id"] for a in yes["actions"]})
        self.assertNotIn("expand-contract", {a["id"] for a in yes["actions"]})

        no_box, _ = self._box()
        no = impl.cmd_offer(self._offer_args(no_box, answer="no"))
        self.assertIn("expand-contract", {a["id"] for a in no["actions"]})
        self.assertNotIn("pilot-all", {a["id"] for a in no["actions"]})

    def test_branch_action_prose_names_no_specific_experiment_or_notebook(self):
        """Decision (settled for this change): the `pilot-all`/
        `expand-contract` prose describes only what the branch establishes
        -- never a specific experiment, notebook or run by name, which is
        the out-of-scope line the design itself flagged as closest.
        """
        yes = impl.cmd_offer(self._offer_args(self._box()[0], answer="yes"))
        no = impl.cmd_offer(self._offer_args(self._box()[0], answer="no"))
        pilot_all = next(a for a in yes["actions"] if a["id"] == "pilot-all")
        expand_contract = next(a for a in no["actions"] if a["id"] == "expand-contract")
        for action in (pilot_all, expand_contract):
            text = (action["command"] + " " + action["establishes"]).lower()
            for leaked in FORGE_VOCABULARY_FLOOR:
                self.assertIsNone(re.search(rf"\b{leaked}\b", text), leaked)

    # --- ACTION_IDS: pinned three ways ---------------------------------

    def test_action_ids_constant_covers_every_id_literal_in_the_source_and_at_runtime(self):
        source = CLI.read_text(encoding="utf-8")
        literal_ids = set(re.findall(r'"id":\s*"([a-z-]+)"', source))
        self.assertEqual(literal_ids, set(impl.ACTION_IDS))

        box, commit = self._box()
        self._register_fixture_reporter(box, "offer-fixture-svc")
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])
        result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        runtime_ids = {a["id"] for a in result["actions"]}
        self.assertTrue(runtime_ids.issubset(impl.ACTION_IDS))

    # --- requirement 5: no drift between gate and offer -----------------

    def test_gate_and_offer_call_the_identical_shared_availability_symbol(self):
        """Structural proof that the two callers cannot drift: both call
        the SAME `impl_availability.launch_available` symbol -- never a
        second, independently-written check either one could disagree
        with.
        """
        source = CLI.read_text(encoding="utf-8")
        self.assertIn("import impl_availability", source)
        self.assertEqual(
            source.count("impl_availability.launch_available("), 2,
            "cmd_gate and cmd_offer (through _offer_launch_action) must "
            "each call the shared rule exactly once")

    def test_gate_and_offer_agree_on_every_one_of_the_six_refusal_codes(self):
        """Cross-join (spec "No drift between callers"): for each of the
        six state codes, `gate` refuses with that code and `offer` omits
        that job's launch action, over identical target/job/revision facts.
        """
        proposals = self._proposals()

        def offer_omits_job1(box):
            # A reporter is registered so the ONLY thing that can suppress
            # job1's launch action is the shared availability rule itself
            # -- if capacity resolution failed too, the cross-join below
            # would pass regardless of whether the availability check ran
            # at all, proving nothing.
            self._register_fixture_reporter(box, "offer-fixture-svc")
            result = impl.cmd_offer(self._offer_args(box, answer="yes"))
            self.assertNotIn(
                "job1",
                [a["binding"].get("job") for a in result["actions"]
                 if a["id"] == "launch"])

        # POSITION_ABSENT
        with self.subTest("POSITION_ABSENT"):
            box, commit = self._box()
            self._write_job_folder(box, commit)
            proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                                "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                                "--job", "job1", "--worker", "w1",
                                "--justification", "Because it is time.",
                                proposals=proposals)
            self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_ABSENT")
            offer_omits_job1(box)

        # POSITION_STALE
        with self.subTest("POSITION_STALE"):
            box, commit = self._box()
            self._write_job_folder(box, commit)
            header = {"revision": self.PROPOSAL_REVISION, "revisionSha256": "a" * 64,
                      "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
            items = [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                      "witness": {"kind": "rehearsal", "operand": "job1"}}]
            (box / "Method" / "AGREED.md").write_text(
                impl_position.render(header, items), encoding="utf-8")
            proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                                "--revision", "r2.md", "--session", "s1",
                                "--job", "job1", "--worker", "w1",
                                "--justification", "Because it is time.",
                                proposals=proposals)
            self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_STALE")
            offer_omits_job1(box)

        # POSITION_DISAGREES -- the reproduced incident: a rehearsal item
        # ticked `x` whose own witness measured `fail`, so `derive()`
        # verdicts `satisfied=False, disagrees=True, unbacked=False`.
        # Before this refusal existed, this exact shape reached
        # `available: True`.
        with self.subTest("POSITION_DISAGREES"):
            box, commit = self._box()
            self._write_job_folder(box, commit)
            self._write_smoke_fail(box, commit=commit)
            self._write_agreed(box, [{"ordinal": 1, "mark": "x", "text": "Rehearse the job.",
                                      "witness": {"kind": "rehearsal", "operand": "job1"}}])
            proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                                "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                                "--job", "job1", "--worker", "w1",
                                "--justification", "Because it is time.",
                                proposals=proposals)
            self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_DISAGREES")
            offer_omits_job1(box)

        # POSITION_UNBACKED
        with self.subTest("POSITION_UNBACKED"):
            box, commit = self._box()
            self._write_job_folder(box, commit)
            self._write_smoke_pass(box, commit=commit)
            self._write_agreed(box, [
                {"ordinal": 1, "mark": "x", "text": "Collect the shard.",
                 "witness": {"kind": "shard", "operand": "s0"}},
                {"ordinal": 2, "mark": " ", "text": "Rehearse the job.",
                 "witness": {"kind": "rehearsal", "operand": "job1"}},
            ])
            proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                                "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                                "--job", "job1", "--worker", "w1",
                                "--justification", "Because it is time.",
                                proposals=proposals)
            self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_UNBACKED")
            offer_omits_job1(box)

        # NOT_READY
        with self.subTest("NOT_READY"):
            box, commit = self._box()
            self._write_job_folder(box, commit)
            self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                      "witness": {"kind": "rehearsal", "operand": "job1"}}])
            proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                                "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                                "--job", "job1", "--worker", "w1",
                                "--justification", "Because it is time.",
                                proposals=proposals)
            self.assertEqual(json.loads(proc.stdout)["code"], "NOT_READY")
            offer_omits_job1(box)

        # SEQUENCE_NOT_REACHED
        with self.subTest("SEQUENCE_NOT_REACHED"):
            box, commit = self._box()
            self._write_job_folder(box, commit)
            self._write_smoke_pass(box, commit=commit)
            self._write_agreed(box, [
                {"ordinal": 1, "mark": " ", "text": "Read the pilot notebook.",
                 "witness": {"kind": "notebook", "operand": "Notebooks/pilot.ipynb"}},
                {"ordinal": 2, "mark": " ", "text": "Rehearse the job.",
                 "witness": {"kind": "rehearsal", "operand": "job1"}},
            ])
            proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                                "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                                "--job", "job1", "--worker", "w1",
                                "--justification", "Because it is time.",
                                proposals=proposals)
            self.assertEqual(json.loads(proc.stdout)["code"], "SEQUENCE_NOT_REACHED")
            offer_omits_job1(box)

    def test_a_blank_unreconciled_item_never_refuses_position_disagrees(self):
        """The filter's other pole (`_launch_disagreements`): a blank box
        whose own witness already measures satisfied is `disagrees=True`
        too -- `derive()`'s fact is bidirectional -- but it asserts
        nothing, so it is not a false claim and must never refuse a
        launch. `gate` records normally and `offer` still publishes the
        job's launch action, over the identical shape the reproduced
        incident above (ticked, contradicted) correctly refuses.

        Mutation proving the filter matters, not merely present: removing
        `_launch_disagreements`'s `mark == "x"` condition (passing
        `position["disagreements"]` unfiltered again, as both call sites
        did before this filter existed) turns this test red -- `gate`
        would refuse `POSITION_DISAGREES` and `offer` would omit job1,
        exactly the regression this test exists to catch.
        """
        proposals = self._proposals()
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])

        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1", "--worker", "w1",
                            "--justification", "Because it is time.",
                            proposals=proposals)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["status"], "recorded")

        self._register_fixture_reporter(box, "offer-fixture-svc")
        result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        self.assertIn(
            "job1",
            [a["binding"].get("job") for a in result["actions"] if a["id"] == "launch"])

    # --- Phase 4: two-layer no-network proof at publish time -----------

    def test_the_publisher_never_reaches_a_live_adapter_for_capacity(self):
        """Layer 1: a fixture adapter registered under a fixture service
        name whose `workers`/`list_active`/`submit` all raise if called.
        `cmd_offer` publishes `declaredCapacity: 6` without ever invoking
        any of them -- capacity comes from the fourth registry alone,
        never from `Adapter.workers()`.
        """
        box, commit = self._box()
        rcli = impl._load_remote_execution_cli()
        service = "offer-fixture-poisoned-adapter"

        class _RaisingAdapter(rcli.ADAPTER.Adapter):
            def workers(self):
                raise AssertionError("cmd_offer must never call Adapter.workers()")

            def submit(self, job):
                raise AssertionError("cmd_offer must never call Adapter.submit()")

            def poll(self, submission_id):
                raise AssertionError("unreachable")

            def fetch(self, submission_id, into):
                raise AssertionError("unreachable")

            def cancel(self, submission_id):
                raise AssertionError("unreachable")

            def list_active(self, worker):
                raise AssertionError("cmd_offer must never call Adapter.list_active()")

        rcli.ADAPTER.register(service, _RaisingAdapter)
        rcli.ADAPTER.register_declared_capacity(service, lambda: (3, 2))

        self._write_job_folder(box, commit, service=service)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])

        result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        launch = next(a for a in result["actions"] if a["id"] == "launch")
        self.assertEqual(launch["binding"]["declaredCapacity"], 6)

    def test_the_publisher_makes_no_network_read_even_with_sockets_poisoned(self):
        """Layer 2: with the identical fixture reporter, `socket.socket`
        and `socket.create_connection` are patched to raise. Kept as a
        SEPARATE test/mutation from the layer-1 fixture above: the design
        measured that each layer catches a distinct injection point the
        other misses -- a `urlopen(...)` call placed INSIDE the fixture
        reporter itself would never touch the fake adapter's raising
        methods (layer 1 would not catch it), but firing this patched
        socket would.
        """
        box, commit = self._box()
        rcli = impl._load_remote_execution_cli()
        service = "offer-fixture-poisoned-socket"
        rcli.ADAPTER.register_declared_capacity(service, lambda: (3, 2))

        self._write_job_folder(box, commit, service=service)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])

        import socket

        def _raise(*_args, **_kwargs):
            raise AssertionError("cmd_offer must make no network read at publish time")

        with unittest.mock.patch.object(socket, "socket", side_effect=_raise), \
             unittest.mock.patch.object(socket, "create_connection", side_effect=_raise):
            result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        launch = next(a for a in result["actions"] if a["id"] == "launch")
        self.assertEqual(launch["binding"]["declaredCapacity"], 6)

    # --- Phase 5: dynamic-load and subprocess threat matrix ------------

    def test_a_path_traversal_service_name_loads_nothing_and_omits_the_action(self):
        box, commit = self._box()
        self._write_job_folder(box, commit, service="offer-fixture-svc")
        # `service` is overwritten directly on disk -- `_BACKEND_NAME_RE`
        # would refuse this at the CLI layer for a REAL run-config, but the
        # threat this covers is what `_load_backend_module` itself does
        # when handed a hostile string, unconditionally.
        job_dir = box / "tools" / "offer-fixture-svc" / "job1"
        run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
        run_config["service"] = "../../evil"
        (job_dir / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])

        result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        self.assertNotIn("launch", {a["id"] for a in result["actions"]})

    def test_an_absolute_path_service_name_loads_nothing_and_omits_the_action(self):
        box, commit = self._box()
        self._write_job_folder(box, commit, service="offer-fixture-svc")
        job_dir = box / "tools" / "offer-fixture-svc" / "job1"
        run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
        run_config["service"] = "/etc/passwd"
        (job_dir / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])

        result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        self.assertNotIn("launch", {a["id"] for a in result["actions"]})

    def test_a_service_nothing_registers_omits_the_action_without_raising(self):
        box, commit = self._box()
        self._write_job_folder(box, commit, service="nonexistent-backend")
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])

        result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        self.assertNotIn("launch", {a["id"] for a in result["actions"]})

    def test_a_reporter_answering_none_omits_the_launch_action_without_raising(self):
        """The publisher-level consequence (task 5.4/5.5) of a registered
        reporter answering `None` -- whether the root cause is a failing
        subprocess or unparsable stdout is already proven one layer down,
        at `_declared_capacity()` itself (`KaggleDeclaredCapacityTests` in
        `tests/test_remote_execution.py`); the publisher only ever sees
        the one signal `None`, so this collapses both root causes into
        the single consequence the publisher can actually observe.
        """
        box, commit = self._box()
        rcli = impl._load_remote_execution_cli()
        rcli.ADAPTER.register_declared_capacity(
            "offer-fixture-none-reporter", lambda: None)
        self._write_job_folder(box, commit, service="offer-fixture-none-reporter")
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                                  "witness": {"kind": "rehearsal", "operand": "job1"}}])

        result = impl.cmd_offer(self._offer_args(box, answer="yes"))
        self.assertNotIn("launch", {a["id"] for a in result["actions"]})


class CloseCommandTests(unittest.TestCase):
    """`close` -- the finishing precondition (design §3.3). Writing the
    position becomes a precondition of finishing, not a courtesy: `close`
    refuses while a transition has been made and not recorded, and names
    which one, rather than always succeeding.

    Checked against the position exactly as recorded, BEFORE the refresh
    that follows (see `cmd_close`'s own docstring): refreshing first would
    silently correct a disagreement by rewriting the very mark this refusal
    exists to catch.
    """

    PROPOSAL_REVISION = "r1.md"
    PROPOSAL_TEXT = "## 1\ntexto\n"
    PROPOSAL_SHA256 = hashlib.sha256(PROPOSAL_TEXT.encode("utf-8")).hexdigest()

    def _proposals(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / self.PROPOSAL_REVISION).write_text(self.PROPOSAL_TEXT, encoding="utf-8")
        (root / "r2.md").write_text("## 2\notro\n", encoding="utf-8")
        return root

    def _box(self, packages=("Method",)):
        self._box_count = getattr(self, "_box_count", 0) + 1
        box = FORGE / "implementations" / f"_e2e_close_cmd_{os.getpid()}_{id(self)}_{self._box_count}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "close-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "close-tests@example.invalid"
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        for package in packages:
            (box / "src" / package).mkdir(parents=True, exist_ok=True)
            (box / "src" / package / "__init__.py").write_text("", encoding="utf-8")
            (box / "src" / f"{package}_Benchmark").mkdir(parents=True, exist_ok=True)
            (box / "src" / f"{package}_Benchmark" / "__init__.py").write_text(
                "", encoding="utf-8")
            (box / package).mkdir(parents=True, exist_ok=True)
        (box / "tests").mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "add", "-A"], cwd=box, env=env, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=box, env=env,
                       check=True, capture_output=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=box, env=env, check=True,
            capture_output=True, text=True).stdout.strip()
        return box, commit

    def _write_job_folder(self, box, commit, *, service="svc", job_name="job1",
                          product="Method", clone_paths=("src/Method",)):
        job_dir = box / "tools" / service / job_name
        job_dir.mkdir(parents=True, exist_ok=True)
        run_config = {
            "schemaVersion": 1, "product": product, "service": service,
            "jobName": job_name, "commit": commit,
            "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
            "clonePaths": list(clone_paths),
            "run": {"module": f"{product}.module", "function": "run", "kwargs": {}},
            "runnerTemplate": [
                {"path": "assets/runner_bootstrap.py", "sha256": "0" * 64},
                {"path": "assets/runner_invoke.py", "sha256": "0" * 64},
            ],
        }
        (job_dir / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
        return job_dir

    def run_cli(self, *args, proposals=None):
        env = dict(os.environ)
        if proposals is not None:
            env["IMPLEMENTATION_PROPOSALS"] = str(proposals)
        return subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, cwd=FORGE, env=env)

    # --- 6.4: absent, stale, or disagreeing -- three ways "not true" ---

    def test_close_refuses_absent_stale_or_disagreeing_position(self):
        proposals = self._proposals()

        with self.subTest("absent"):
            box, _ = self._box()
            proc = self.run_cli("close", "--target", str(box), "--name", "Method",
                                "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                                proposals=proposals)
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_ABSENT")

        with self.subTest("stale"):
            box, _ = self._box()
            header = {"revision": self.PROPOSAL_REVISION, "revisionSha256": "a" * 64,
                      "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
            items = [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                      "witness": {"kind": "rehearsal", "operand": "job1"}}]
            (box / "Method" / "AGREED.md").write_text(
                impl_position.render(header, items), encoding="utf-8")
            proc = self.run_cli("close", "--target", str(box), "--name", "Method",
                                "--revision", "r2.md", "--session", "s1",
                                proposals=proposals)
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_STALE")
            # A refused close never writes: the file this refusal exists to
            # protect is unchanged.
            on_disk = (box / "Method" / "AGREED.md").read_text(encoding="utf-8")
            self.assertIn("revision=r1.md", on_disk)

        with self.subTest("disagrees"):
            box, commit = self._box()
            self._write_job_folder(box, commit)
            header = {"revision": self.PROPOSAL_REVISION,
                      "revisionSha256": self.PROPOSAL_SHA256,
                      "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
            # Falsely marked "x": job1's folder exists but never rehearsed,
            # so `smokeReady["job1"]` measures a definite False.
            items = [{"ordinal": 1, "mark": "x", "text": "Rehearse the job.",
                      "witness": {"kind": "rehearsal", "operand": "job1"}}]
            (box / "Method" / "AGREED.md").write_text(
                impl_position.render(header, items), encoding="utf-8")
            proc = self.run_cli("close", "--target", str(box), "--name", "Method",
                                "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                                proposals=proposals)
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_DISAGREES")
            on_disk = (box / "Method" / "AGREED.md").read_text(encoding="utf-8")
            self.assertIn("- [x] 1. Rehearse the job.", on_disk,
                          "a refused close must not silently correct the very "
                          "mark its refusal exists to report")

    # --- 6.4: a second close over the identical, unmoved position ---

    def test_close_second_call_is_not_open_not_error(self):
        box, _ = self._box()
        header = {"revision": self.PROPOSAL_REVISION,
                  "revisionSha256": self.PROPOSAL_SHA256,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1", "target": "final"}
        items = [{"ordinal": 1, "mark": " ", "text": "Rehearse the job.",
                  "witness": {"kind": "rehearsal", "operand": "job-none"}}]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")
        proposals = self._proposals()

        first = self.run_cli("close", "--target", str(box), "--name", "Method",
                             "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                             proposals=proposals)
        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertEqual(json.loads(first.stdout)["status"], "closed")

        second = self.run_cli("close", "--target", str(box), "--name", "Method",
                              "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                              proposals=proposals)
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertEqual(json.loads(second.stdout)["status"], "not_open")

        ledger = box / "Method" / ".implementation" / "position.jsonl"
        events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["kind"] for e in events], ["close"])


class ResolveStepsDeclarationTests(unittest.TestCase):
    """`__steps__` -- read exactly the way `resolve_levels_declaration` reads
    `__levels__` (design "Execute a Declared Local Step" — decision "entries
    carry {module, function}, no kwargs"; spec "`__steps__` declaration
    surface"), held apart from `__benchmark__` for the identical reason.
    """

    def bench(self, root: Path) -> Path:
        path = root / "src" / "Method_Benchmark"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_no_benchmark_directory_is_empty(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(
                impl.resolve_steps_declaration(Path(raw), "Method"), {})

    def test_directory_with_no_declaration_is_empty(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.bench(root)
            self.assertEqual(impl.resolve_steps_declaration(root, "Method"), {})

    def test_declared_in_init_py_is_found(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "__init__.py").write_text(
                "__steps__ = {'verification': {'module': 'Method_Benchmark.steps', "
                "'function': 'run_verification'}}\n", encoding="utf-8")
            resolved = impl.resolve_steps_declaration(root, "Method")
        self.assertEqual(resolved, {"verification": {
            "module": "Method_Benchmark.steps", "function": "run_verification"}})

    def test_declared_in_config_py_alone_is_found(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "config.py").write_text(
                "__steps__ = {'a': {'module': 'm', 'function': 'f'}}\n",
                encoding="utf-8")
            resolved = impl.resolve_steps_declaration(root, "Method")
        self.assertEqual(resolved, {"a": {"module": "m", "function": "f"}})

    def test_a_non_dict_value_reads_as_nothing_declared(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "__init__.py").write_text(
                "__steps__ = ['verification']\n", encoding="utf-8")
            self.assertEqual(impl.resolve_steps_declaration(root, "Method"), {})

    def test_the_annotated_form_is_read(self):
        """The kit's own scaffold writes `__steps__: dict = {}` -- an
        `ast.AnnAssign`, not an `ast.Assign` -- so a reader that only walked
        the plain form would never see the scaffold's own shape."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "__init__.py").write_text(
                "__steps__: dict = {'a': {'module': 'm', 'function': 'f'}}\n",
                encoding="utf-8")
            resolved = impl.resolve_steps_declaration(root, "Method")
        self.assertEqual(resolved, {"a": {"module": "m", "function": "f"}})

    def test_resolves_without_reading_or_mutating_the_benchmark_declaration(self):
        """Spec scenario 'Declared step resolves'."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "__init__.py").write_text(
                "__benchmark__ = {'revision': 'r01.md'}\n"
                "__steps__ = {'a': {'module': 'm', 'function': 'f'}}\n",
                encoding="utf-8")
            steps = impl.resolve_steps_declaration(root, "Method")
            benchmark = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(steps, {"a": {"module": "m", "function": "f"}})
        self.assertEqual(benchmark["contract"], {"revision": "r01.md"})

    def test_steps_never_flips_the_benchmark_verdict_when_every_block_is_blank(self):
        """Spec scenario '`__steps__` never flips the benchmark verdict':
        `_declaration_is_blank` checks only `BENCHMARK_BLOCKS`, so a target
        declaring `__steps__` while every `__benchmark__` block sits at its
        scaffold-empty value still reads `undeclared`."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (self.bench(root) / "__init__.py").write_text(
                "__benchmark__ = {'revision': '', 'premises': {}, 'arms': {}, "
                "'search': {}, 'report': {}, 'distribution': {}, "
                "'entry': {'module': '', 'function': ''}}\n"
                "__steps__ = {'a': {'module': 'm', 'function': 'f'}}\n",
                encoding="utf-8")
            steps = impl.resolve_steps_declaration(root, "Method")
            benchmark = impl.resolve_benchmark_declaration(root, "Method")
        self.assertEqual(steps, {"a": {"module": "m", "function": "f"}})
        self.assertEqual(benchmark["status"], "undeclared")


class ImplStepsVerdictStateMachineTests(unittest.TestCase):
    """`impl_steps._verdict_result` -- the five-row state machine `RUNNER`'s
    own docstring names, proven by handing it hand-written verdict dicts
    directly, one call per row, rather than only ever reaching a row by
    making a real subprocess die at exactly the right instant.
    """

    def test_no_verdict_file_is_runner_silent(self):
        with self.assertRaises(impl_steps.Refused) as ctx:
            impl_steps._verdict_result(None, 137, "m", "f")
        self.assertEqual(ctx.exception.code, "STEP_RUNNER_SILENT")

    def test_unresolvable_module_reads_as_step_module_missing(self):
        with self.assertRaises(impl_steps.Refused) as ctx:
            impl_steps._verdict_result(
                {"outcome": "unresolvable", "reason": "module",
                 "detail": "No module named 'nope'"}, 1, "nope", "f")
        self.assertEqual(ctx.exception.code, "STEP_MODULE_MISSING")
        self.assertIn("nope", ctx.exception.detail)

    def test_unresolvable_function_reads_as_step_function_missing(self):
        with self.assertRaises(impl_steps.Refused) as ctx:
            impl_steps._verdict_result(
                {"outcome": "unresolvable", "reason": "function",
                 "detail": "'m' has no attribute 'nope'"}, 1, "m", "nope")
        self.assertEqual(ctx.exception.code, "STEP_FUNCTION_MISSING")

    def test_unresolvable_notcallable_reads_as_step_not_callable(self):
        with self.assertRaises(impl_steps.Refused) as ctx:
            impl_steps._verdict_result(
                {"outcome": "unresolvable", "reason": "notcallable",
                 "detail": "not callable"}, 1, "m", "f")
        self.assertEqual(ctx.exception.code, "STEP_NOT_CALLABLE")

    def test_resolved_only_reads_as_unknown_never_a_pass(self):
        """Entered the callable, then the process vanished before the
        second write -- `os._exit`, a `SIGKILL`. A missing second write is
        reported as an inability to tell, never guessed at as a pass."""
        result = impl_steps._verdict_result({"outcome": "resolved"}, 137, "m", "f")
        self.assertEqual(
            result, {"outcome": "unknown", "exitStatus": 137, "error": None})

    def test_returned_is_recorded_with_the_real_exit_status(self):
        result = impl_steps._verdict_result({"outcome": "returned"}, 0, "m", "f")
        self.assertEqual(
            result, {"outcome": "returned", "exitStatus": 0, "error": None})

    def test_raised_carries_the_error_string_verbatim(self):
        result = impl_steps._verdict_result(
            {"outcome": "raised", "error": "ValueError: boom"}, 1, "m", "f")
        self.assertEqual(
            result,
            {"outcome": "raised", "exitStatus": 1, "error": "ValueError: boom"})


class StepEnvironmentTests(unittest.TestCase):
    """`impl_steps.step_environment` -- `PATH` prefixed, never replaced."""

    def test_path_is_prefixed_and_the_inherited_path_survives(self):
        env = impl_steps.step_environment(Path("/venv/bin"), Path("/target/src"))
        self.assertEqual(
            env["PATH"],
            f"/venv/bin{os.pathsep}{os.environ.get('PATH', '')}")
        self.assertEqual(env["PYTHONPATH"], "/target/src")

    def test_every_other_inherited_variable_passes_through_unchanged(self):
        env = impl_steps.step_environment(Path("/venv/bin"), Path("/target/src"))
        for key, value in os.environ.items():
            if key in ("PATH", "PYTHONPATH"):
                continue
            self.assertEqual(env.get(key), value)


class StepCommandTests(unittest.TestCase):
    """`step` -- run one declared local step, isolated (design "Execute a
    Declared Local Step"; spec "Local Step Execution"). Proves the whole
    chain end to end: the CLI wiring, the forge-side static refusals, and
    the isolation `impl_steps.run_step` supplies.
    """

    def _box(self, suffix):
        box = FORGE / "implementations" / f"_e2e_step_{suffix}_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "Method").mkdir(parents=True, exist_ok=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        write_fixture_interpreter(
            box / ".venv" / ("Scripts" if os.name == "nt" else "bin"))
        return box

    def _commit(self, box):
        git = ["git", "-c", "user.email=forge@example.invalid",
               "-c", "user.name=forge", "-C", str(box)]
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-qm", "toy"], check=True, capture_output=True)
        head = subprocess.run(git + ["rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
        return head

    def _declare(self, box, steps):
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
            f"__steps__ = {steps!r}\n", encoding="utf-8")

    def run_cli(self, *args, env=None):
        full_env = dict(os.environ)
        if env is not None:
            full_env = env
        return subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, cwd=FORGE, env=full_env)

    def ledger_events(self, box):
        path = box / "Method" / ".implementation" / "position.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    # --- Spec "Record a `step` ledger event" ---

    def test_a_passing_step_is_recorded_with_exit_zero_and_no_digest_field(self):
        box = self._box("pass")
        (box / "src" / "Method_Benchmark" / "steps.py").write_text(
            "def run_ok():\n    return None\n", encoding="utf-8")
        self._declare(box, {"verification": {"module": "Method_Benchmark.steps",
                                              "function": "run_ok"}})
        self._commit(box)

        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["outcome"], "returned")
        self.assertEqual(result["exitStatus"], 0)
        self.assertIsNone(result["error"])

        events = self.ledger_events(box)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["kind"], "step")
        self.assertEqual(event["step"], "verification")
        self.assertEqual(event["callable"], "Method_Benchmark.steps.run_ok")
        self.assertEqual(event["exitStatus"], 0)
        self.assertEqual(event["session"], "s1")
        self.assertEqual(
            [key for key in event if "digest" in key.lower()], [],
            "the step ledger event carries a digest field; the spec's own "
            "scenario requires none -- notebooks_state recomputes it fresh")

    def test_a_raising_step_is_still_recorded_with_a_nonzero_exit(self):
        box = self._box("raise")
        (box / "src" / "Method_Benchmark" / "steps.py").write_text(
            "def run_bad():\n    raise ValueError('boom')\n", encoding="utf-8")
        self._declare(box, {"verification": {"module": "Method_Benchmark.steps",
                                              "function": "run_bad"}})
        self._commit(box)

        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["outcome"], "raised")
        self.assertNotEqual(result["exitStatus"], 0)
        self.assertIn("boom", result["error"])

        events = self.ledger_events(box)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "raised")
        self.assertNotEqual(events[0]["exitStatus"], 0)

    def test_a_step_that_hard_exits_mid_call_is_recorded_as_unknown_not_silent(self):
        """`RUNNER` writes the verdict file TWICE -- the instant resolution
        succeeds, before the call, and again once the call returns or
        raises. `os._exit` inside the callable simulates a process dying
        hard mid-call (a `SIGKILL`, a segfault): the pre-call write is the
        only thing standing between this and `STEP_RUNNER_SILENT`, which
        would wrongly report a step that never even entered its callable.
        """
        box = self._box("hardexit")
        (box / "src" / "Method_Benchmark" / "steps.py").write_text(
            "import os\ndef run_ok():\n    os._exit(9)\n", encoding="utf-8")
        self._declare(box, {"verification": {"module": "Method_Benchmark.steps",
                                              "function": "run_ok"}})
        self._commit(box)

        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(result["exitStatus"], 9)

        events = self.ledger_events(box)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "unknown")

    # --- Spec "Refuse an unresolvable step" ---

    def test_undeclared_target_refuses_steps_undeclared(self):
        box = self._box("undeclared")
        self._commit(box)
        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "STEPS_UNDECLARED")
        self.assertEqual(self.ledger_events(box), [])

    def test_unknown_step_name_refuses_step_unknown_naming_it(self):
        box = self._box("unknown")
        self._declare(box, {"other": {"module": "m", "function": "f"}})
        self._commit(box)
        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        body = json.loads(proc.stdout)
        self.assertEqual(body["code"], "STEP_UNKNOWN")
        self.assertIn("verification", body["detail"])
        self.assertEqual(self.ledger_events(box), [])

    def test_a_declared_entry_missing_function_refuses_step_malformed(self):
        box = self._box("malformed")
        self._declare(box, {"verification": {"module": "Method_Benchmark.steps"}})
        self._commit(box)
        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "STEP_MALFORMED")
        self.assertEqual(self.ledger_events(box), [])

    def test_no_venv_refuses_interpreter_absent(self):
        box = FORGE / "implementations" / f"_e2e_step_novenv_{os.getpid()}_{id(self)}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "Method").mkdir(parents=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
            "__steps__ = {'verification': {'module': 'Method_Benchmark.steps', "
            "'function': 'run'}}\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        git = ["git", "-c", "user.email=forge@example.invalid",
               "-c", "user.name=forge", "-C", str(box)]
        subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-qm", "toy"], check=True, capture_output=True)

        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "INTERPRETER_ABSENT")

    def test_missing_module_refuses_step_module_missing(self):
        box = self._box("modmissing")
        self._declare(box, {"verification": {"module": "Method_Benchmark.nope",
                                              "function": "run"}})
        self._commit(box)
        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "STEP_MODULE_MISSING")
        self.assertEqual(self.ledger_events(box), [])

    def test_missing_function_refuses_step_function_missing(self):
        box = self._box("funcmissing")
        (box / "src" / "Method_Benchmark" / "steps.py").write_text("", encoding="utf-8")
        self._declare(box, {"verification": {"module": "Method_Benchmark.steps",
                                              "function": "nope"}})
        self._commit(box)
        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "STEP_FUNCTION_MISSING")
        self.assertEqual(self.ledger_events(box), [])

    def test_a_non_callable_attribute_refuses_step_not_callable(self):
        box = self._box("notcallable")
        (box / "src" / "Method_Benchmark" / "steps.py").write_text(
            "run = 1\n", encoding="utf-8")
        self._declare(box, {"verification": {"module": "Method_Benchmark.steps",
                                              "function": "run"}})
        self._commit(box)
        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "STEP_NOT_CALLABLE")
        self.assertEqual(self.ledger_events(box), [])

    # --- Spec "Refuse on a dirty target worktree" ---

    def test_a_staged_change_refuses_before_any_subprocess_or_event(self):
        box = self._box("dirtystaged")
        marker = box / "src" / "Method_Benchmark" / "ran.marker"
        (box / "src" / "Method_Benchmark" / "steps.py").write_text(
            f"def run_ok():\n    open({str(marker)!r}, 'w').write('yes')\n",
            encoding="utf-8")
        self._declare(box, {"verification": {"module": "Method_Benchmark.steps",
                                              "function": "run_ok"}})
        self._commit(box)
        (box / "src" / "Method" / "extra.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(box), "add", "src/Method/extra.py"],
                       check=True, capture_output=True)

        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "DIRTY_WORKTREE")
        self.assertFalse(
            marker.exists(),
            "the step's own callable ran despite a staged, uncommitted "
            "change -- the dirty-worktree guard must refuse before any "
            "subprocess spawns")
        self.assertEqual(self.ledger_events(box), [])

    def test_an_untracked_file_refuses_before_any_subprocess_or_event(self):
        box = self._box("dirtyuntracked")
        marker = box / "src" / "Method_Benchmark" / "ran.marker"
        (box / "src" / "Method_Benchmark" / "steps.py").write_text(
            f"def run_ok():\n    open({str(marker)!r}, 'w').write('yes')\n",
            encoding="utf-8")
        self._declare(box, {"verification": {"module": "Method_Benchmark.steps",
                                              "function": "run_ok"}})
        self._commit(box)
        (box / "src" / "Method" / "untracked.py").write_text("x = 1\n", encoding="utf-8")

        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "DIRTY_WORKTREE")
        self.assertFalse(marker.exists())
        self.assertEqual(self.ledger_events(box), [])

    # --- Spec "Notebook step runs under the right interpreter" (design §4b) ---

    def test_path_is_prefixed_pythonpath_and_cwd_are_correct(self):
        box = self._box("envdump")
        dump_path = box / "env_dump.json"
        (box / "src" / "Method_Benchmark" / "steps.py").write_text(
            "import json, os\n"
            "def dump():\n"
            f"    with open({str(dump_path)!r}, 'w', encoding='utf-8') as fh:\n"
            "        json.dump({'path': os.environ.get('PATH', ''),\n"
            "                   'pythonpath': os.environ.get('PYTHONPATH', ''),\n"
            "                   'cwd': os.getcwd(),\n"
            "                   'virtualEnv': os.environ.get('VIRTUAL_ENV')}, fh)\n",
            encoding="utf-8")
        self._declare(box, {"dump": {"module": "Method_Benchmark.steps",
                                     "function": "dump"}})
        self._commit(box)

        # Task 4f's own measurement: `VIRTUAL_ENV` is deliberately left
        # unset in the process running the CLI itself, so nothing here could
        # be inheriting a value by accident -- the step still has to resolve
        # and run to completion on `pyvenv.cfg` and the absolute interpreter
        # path alone.
        env = dict(os.environ)
        env.pop("VIRTUAL_ENV", None)
        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "dump", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        dumped = json.loads(dump_path.read_text(encoding="utf-8"))
        venv_bin = str(box / ".venv" / ("Scripts" if os.name == "nt" else "bin"))
        path_entries = dumped["path"].split(os.pathsep)
        self.assertEqual(
            path_entries[0], venv_bin,
            "PATH's first element must be the target venv's own bin dir")
        for inherited in env.get("PATH", "").split(os.pathsep):
            self.assertIn(
                inherited, path_entries,
                "the inherited PATH must survive after the venv prefix")
        self.assertEqual(dumped["pythonpath"], str(box / "src"))
        self.assertEqual(Path(dumped["cwd"]).resolve(), box.resolve())
        # Recorded as a measurement, never asserted as a mechanism this
        # module owns (design's own open question, settled by task 4f):
        # the step resolved and ran with `VIRTUAL_ENV` absent throughout.
        self.assertIsNone(dumped["virtualEnv"])

        events = self.ledger_events(box)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "returned")

    # --- Threat matrix "Argument composition" (added row) ---

    def test_a_hostile_function_name_never_reaches_a_shell(self):
        box = self._box("hostile")
        marker_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, marker_dir, ignore_errors=True)
        marker = marker_dir / "pwned"
        (box / "src" / "Method_Benchmark" / "steps.py").write_text(
            "def run():\n    pass\n", encoding="utf-8")
        self._declare(box, {"verification": {
            "module": "Method_Benchmark.steps",
            "function": f"run; touch {marker}"}})
        self._commit(box)

        proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "s1", "--step", "verification")
        self.assertEqual(proc.returncode, 2)
        body = json.loads(proc.stdout)
        self.assertEqual(body["code"], "STEP_FUNCTION_MISSING")
        self.assertFalse(
            marker.exists(),
            "a hostile function-name string reached a shell and created a "
            "marker file; argv must never be interpolated into a command "
            "line (list argv, shell=False)")
        self.assertEqual(self.ledger_events(box), [])

    # --- Spec "Remote launch stays structurally unreachable" ---

    def test_running_a_step_never_touches_gate_authorization(self):
        box = self._box("nonreach")
        (box / "src" / "Method_Benchmark" / "steps.py").write_text(
            "def run_ok():\n    return None\n"
            "def run_bad():\n    raise ValueError('boom')\n",
            encoding="utf-8")
        self._declare(box, {
            "ok": {"module": "Method_Benchmark.steps", "function": "run_ok"},
            "bad": {"module": "Method_Benchmark.steps", "function": "run_bad"},
        })
        self._commit(box)

        ledger = box / "Method" / ".implementation" / "position.jsonl"
        gate_event = {
            "kind": "gate", "jobName": "job", "worker": "acct",
            "commit": "0" * 40, "revision": "r1.md",
            "revisionSha256": "0" * 64, "entrypoint": "tools/service/job/run.py",
            "units": [], "justification": "measured, rehearsed, launching",
            "session": "s0", "at": "2026-08-27T00:00:00Z",
        }
        impl_position.append_event(ledger, gate_event)
        gate_line_before = ledger.read_text(encoding="utf-8").splitlines()[0]
        # A second commit so the seeded ledger itself is not what `step`'s
        # own `require_clean_worktree` refuses on -- this test is about
        # what running a step does to an ALREADY-recorded gate, not about
        # the dirty-worktree guard (covered on its own above).
        self._commit(box)

        rcli = impl._load_remote_execution_cli()

        def assert_still_authorized():
            rcli._verify_launch_authorization(
                smoke=False, target=box, product="Method",
                pin_commit=gate_event["commit"],
                relative_entrypoint=Path(gate_event["entrypoint"]),
                units=None, worker=gate_event["worker"])

        assert_still_authorized()  # accepted before any step ever ran

        for step_name in ("ok", "bad"):
            proc = self.run_cli("step", "--target", str(box), "--name", "Method",
                                "--session", "s1", "--step", step_name)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            # `step` itself just modified the tracked ledger (and running
            # under the fixture interpreter leaves an untracked
            # `__pycache__` behind) -- committed so the NEXT step call in
            # this loop meets `require_clean_worktree` too. The property
            # under test is what a step does to the recorded GATE, never
            # about the dirty-worktree guard (covered on its own above).
            self._commit(box)

        lines = ledger.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            lines[0], gate_line_before,
            "the recorded gate event's own bytes moved after a step ran")
        self.assertEqual(
            [json.loads(line)["kind"] for line in lines[1:]], ["step", "step"])
        assert_still_authorized()  # still accepted after two steps ran

    def test_cmd_step_calls_none_of_the_remote_execution_loaders(self):
        """Design mechanism 1 ('No door'): the three lazy loaders are the
        only path to `remote_cli`/`shard_io`/`ledger`, and `cmd_step` calls
        none of them. Checked over the AST's `Call` nodes, not the raw
        source text -- `cmd_step`'s own docstring names these loaders in
        prose (explaining exactly why it never reaches them), and a plain
        substring check would trip over the very sentence proving the
        property.
        """
        tree = ast.parse(inspect.getsource(impl.cmd_step))
        called = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        loaders = {"_load_remote_execution_cli", "_load_remote_execution_shard_io",
                   "_load_remote_execution_ledger"}
        self.assertEqual(
            called & loaders, set(),
            "cmd_step calls a loader that is a door to remote launch this "
            "command must never have")

    def test_no_reader_anywhere_selects_kind_equals_step(self):
        """Design mechanism 2: every gate consumer selects on the exact
        string "gate"; nothing anywhere selects on "step" -- a step line is
        invisible to every existing ledger reader by construction, not by
        convention."""
        sources = [
            (CLI.parent / "implementation_cli.py").read_text(encoding="utf-8"),
            (FORGE / ".claude" / "skills" / "remote-execution" / "scripts"
             / "remote_cli.py").read_text(encoding="utf-8"),
            Path(impl_position.__file__).read_text(encoding="utf-8"),
        ]
        pattern = re.compile(r'kind[\'"]?\s*\)?\s*==\s*[\'"]step[\'"]')
        for source in sources:
            self.assertIsNone(pattern.search(source))


class AnnotatedDeclarationReaderTests(unittest.TestCase):
    """`NAME: type = value` is `ast.AnnAssign`, and a reader walking only
    `ast.Assign` sees nothing there at all.

    Not hypothetical: the forge's own kit ships `__levels__: list = []`, and
    `read_declaration` was already repaired for exactly this. Three further
    readers were still walking one node family, and each one answered its
    caller's question with the word for "nobody declared anything" over a file
    that declares it on the line being looked at.

    Every test here exercises BOTH forms and asserts they agree, because the
    claim is not "the annotated form works" -- it is that an annotation does
    not change what a declaration says. A test that only pinned the annotated
    form would pass just as well against a reader that had stopped reading the
    flat one.
    """

    def _module(self, text: str) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = root / "module.py"
        path.write_text(text, encoding="utf-8")
        return path

    def _findings_target(self, text: str) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "tests").mkdir()
        (root / "tests" / "findings.py").write_text(text, encoding="utf-8")
        return root

    def _dimensions_target(self, text: str) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        bench = root / "src" / "Method_Benchmark"
        bench.mkdir(parents=True)
        (bench / "config.py").write_text(text, encoding="utf-8")
        return root

    # --- read_provenance ------------------------------------------------

    PROVENANCE = "{'sections': ['3.1'], 'equations': ['12']}"

    def test_read_provenance_agrees_across_both_assignment_forms(self):
        """Measured before this: the annotated form answered `None`, which
        every caller reads as "this module declares no provenance" -- the
        opposite of what the file says, and the input to `missingProvenance`."""
        annotated = impl.read_provenance(self._module(
            f"__provenance__: dict = {self.PROVENANCE}\n"))
        flat = impl.read_provenance(self._module(
            f"__provenance__ = {self.PROVENANCE}\n"))

        self.assertEqual(annotated, flat)
        self.assertEqual(annotated, {"sections": ["3.1"], "equations": ["12"]})

    def test_a_bare_provenance_annotation_declares_nothing(self):
        """`__provenance__: dict` with no value binds nothing. Absent is the
        honest answer; an error would claim the file said something wrong."""
        self.assertIsNone(impl.read_provenance(
            self._module("__provenance__: dict\n")))

    # --- read_findings --------------------------------------------------

    FINDINGS = ("[{'id': 'F1', 'kind': 'defect', 'status': 'open', "
                "'equations': ['12']}]")

    def test_read_findings_agrees_across_both_assignment_forms(self):
        """The worst instance of the class. `read_findings`'s own comment says
        an empty list is "indistinguishable from a repository that has been
        audited and found nothing" -- and returning `[]` over an annotated
        declaration is precisely that, with the findings sitting in the file."""
        annotated = impl.read_findings(self._findings_target(
            f"FINDINGS: list[dict] = {self.FINDINGS}\n"))
        flat = impl.read_findings(self._findings_target(
            f"FINDINGS = {self.FINDINGS}\n"))

        self.assertEqual(annotated, flat)
        self.assertEqual([f["id"] for f in annotated], ["F1"])

    def test_an_annotated_findings_list_that_is_not_a_literal_still_refuses(self):
        """The refusal must reach the annotated form too, or admitting it
        would have opened a second, quieter way past the same guard."""
        with self.assertRaises(impl.Refused) as ctx:
            impl.read_findings(self._findings_target(
                "def build():\n    return []\n\nFINDINGS: list = build()\n"))
        self.assertEqual(ctx.exception.code, "MALFORMED_FINDINGS")

    def test_a_bare_findings_annotation_is_an_unaudited_repository(self):
        """`FINDINGS: list[dict]` with no value declares nothing, which is
        what an empty list already means here -- no findings were written."""
        self.assertEqual(
            impl.read_findings(self._findings_target("FINDINGS: list[dict]\n")),
            [])

    # --- declared_dimension_names ---------------------------------------

    DIMENSIONS = "{'accuracy': HIGHER, 'seconds': LOWER}"
    DIRECTIONS = "HIGHER = 'higher'\nLOWER = 'lower'\n\n"

    def test_declared_dimension_names_agrees_across_both_assignment_forms(self):
        """Measured before this: the annotated form answered `None`, which
        `verify` reports as "the universe could not be determined" and which
        makes an empty `unpartitioned` no evidence of anything."""
        annotated = impl.declared_dimension_names(
            self._dimensions_target(
                f"{self.DIRECTIONS}DIMENSIONS: dict = {self.DIMENSIONS}\n"),
            "Method")
        flat = impl.declared_dimension_names(
            self._dimensions_target(
                f"{self.DIRECTIONS}DIMENSIONS = {self.DIMENSIONS}\n"),
            "Method")

        self.assertEqual(annotated, flat)
        self.assertEqual(annotated, ["accuracy", "seconds"])

    def test_an_annotated_dimensions_bound_to_a_call_is_still_undeterminable(self):
        """`None` rather than `[]` for a binding this reading cannot make
        sense of -- unchanged, and now unchanged for both forms."""
        self.assertIsNone(impl.declared_dimension_names(
            self._dimensions_target(
                "def build():\n    return {}\n\nDIMENSIONS: dict = build()\n"),
            "Method"))

    def test_a_bare_dimensions_annotation_determines_no_universe(self):
        self.assertIsNone(impl.declared_dimension_names(
            self._dimensions_target("DIMENSIONS: dict\n"), "Method"))

    # --- the boundary of the class --------------------------------------

    def test_an_import_based_reader_is_not_an_instance_of_this_class(self):
        """Stated as a test so the next sweep stops where this one did.

        `refuse_offpath_push.py` reads an annotated `PUSH_SURFACE` through
        `getattr` on an imported module, where an annotation is invisible by
        construction. AST readers are the vulnerable ones; import-based
        readers are not, and widening the repair to them would be repairing
        something that was never broken.
        """
        hook = (FORGE / ".claude/skills/remote-execution/scripts/hooks"
                / "refuse_offpath_push.py")
        text = hook.read_text(encoding="utf-8")
        self.assertIn("getattr", text)
        self.assertNotIn("ast.Assign", text)


class ShardCurrencyDeclarationTests(unittest.TestCase):
    """A shard folder is a file left behind by whatever ran. Arrival says it
    exists; it never says which code produced it.

    Measured before this: `verify --shards` built its merge from
    `[entry["shard"] for entry in shards]` and threw each shard's stamp away,
    so a `@shard` witness ticked on arrival alone -- including for shards
    returned by code the repository has long since moved past.

    The forge is not allowed to know which stamp field carries that identity:
    it is the repository's vocabulary, not the forge's. So the declaration
    grows one OPTIONAL key, `currentWhen`, naming a dotted path into the
    shard's own stamp -- the same division `identicalAcrossShards` already
    keeps, where the target names the field and the forge only compares.
    """

    def _declaration(self, current_when=None):
        extra = (f"\n                     'currentWhen': {current_when!r},"
                 if current_when is not None else "")
        return ("__benchmark__ = {\n"
                "    'revision': 'r01.md',\n"
                "    'arms': {'floor': {'sections': ['3']}},\n"
                "    'distribution': {'axis': 'repetition',\n"
                "                     'poolable': ['score'],\n"
                "                     'perEnvironment': [],\n"
                "                     'perRun': [],\n"
                f"                     'identicalAcrossShards': [],{extra}\n"
                "                     },\n"
                "}\n")

    def build_target(self, suffix, current_when=None):
        box = FORGE / "implementations" / f"_shardcurrent_{suffix}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        for directory in ("src/Method", "src/Method_Benchmark", "Method"):
            (box / directory).mkdir(parents=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "src/Method_Benchmark/__init__.py").write_text(
            self._declaration(current_when), encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        header = {"revision": "r01.md", "revisionSha256": "a" * 64,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1",
                  "target": "final"}
        items = [{"ordinal": 1, "mark": " ", "text": "Collect the shard.",
                  "witness": {"kind": "shard", "operand": "s0"}}]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")
        return box

    def build_shards(self, stamps):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for shard, stamp in stamps.items():
            (root / shard).mkdir()
            (root / shard / "shard.json").write_text(
                json.dumps(stamp), encoding="utf-8")
        return root

    def derived(self, box, shards):
        """What `verify --shards` derives for the one `@shard` item, read off
        the command's own stdout rather than off a function call: the claim is
        about what `verify` reports, and every layer between the flag and the
        report is part of it."""
        proc = subprocess.run(
            [sys.executable, str(CLI), "verify", "--target", str(box),
             "--name", "Method", "--shards", str(shards)],
            capture_output=True, text=True, cwd=FORGE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["position"]["sequence"][0]["derived"]

    def digest(self, box):
        """The current source digest, taken from the production function that
        computes it rather than restated -- `notebooks_state` compares a
        report's own stamp against this exact value, and a second definition
        of "current" here would test a comparison the forge never makes."""
        return impl.source_digest(box, "Method")

    # --- case 1: nothing declared -- behaviour is unchanged, byte for byte --

    def test_a_target_declaring_no_currency_still_ticks_on_arrival(self):
        box = self.build_target("undeclared")
        shards = self.build_shards({"s0": {"evidence": {"codeDigest": "stale"}}})
        self.assertIs(self.derived(box, shards), True)

    # --- case 2: declared, and the shard answers with the current digest ---

    def test_a_declared_shard_that_is_current_reads_as_it_always_did(self):
        box = self.build_target("current", current_when="evidence.codeDigest")
        shards = self.build_shards(
            {"s0": {"evidence": {"codeDigest": self.digest(box)}}})
        self.assertIs(self.derived(box, shards), True)

    # --- case 3: declared, and the shard answers with something else -------

    def test_a_declared_shard_that_is_stale_is_unmeasured_not_absent(self):
        """`None`, never `False`. The shard demonstrably ran; what cannot be
        said is that it ran this code -- the same distinction
        `_derive_notebook_level` keeps for a report whose sources moved."""
        box = self.build_target("stale", current_when="evidence.codeDigest")
        shards = self.build_shards(
            {"s0": {"evidence": {"codeDigest": "some other code entirely"}}})
        self.assertIsNone(self.derived(box, shards))

    # --- case 4: declared, and the stamp cannot answer at all --------------

    def test_a_stamp_that_cannot_answer_is_not_evidence_that_it_is_current(self):
        """The decision this case forces, written down: a stamp holding
        nothing at the declared path has not said the shard is current, and
        reading silence as agreement is the same move as reading an unstamped
        notebook as executed against current sources. Unmeasured."""
        box = self.build_target("silent", current_when="evidence.codeDigest")
        shards = self.build_shards({"s0": {"epochs": 5}})
        self.assertIsNone(self.derived(box, shards))

    # --- the comparison itself, at the unit that performs it ---------------

    def test_the_subset_is_none_when_nobody_declared_the_field(self):
        """`None` and `[]` are opposite answers: `[]` says every shard was
        asked and none of them speaks for this code, `None` says nobody was
        asked. `impl_position` reads that difference directly."""
        shards = [{"shard": "s0", "stamp": {"d": "x"}}]
        self.assertIsNone(impl._shards_current(shards, {}, "x"))
        self.assertEqual(impl._shards_current(shards, {"currentWhen": "d"}, "x"),
                         ["s0"])
        self.assertEqual(impl._shards_current(shards, {"currentWhen": "d"}, "y"),
                         [])

    def test_a_dotted_path_walks_the_stamp_and_never_guesses_past_a_gap(self):
        stamp = {"evidence": {"codeDigest": "abc"}}
        self.assertEqual(impl._stamp_at(stamp, "evidence.codeDigest"), "abc")
        self.assertIs(impl._stamp_at(stamp, "evidence.missing"), impl._STAMP_ABSENT)
        self.assertIs(impl._stamp_at(stamp, "evidence.codeDigest.deeper"),
                      impl._STAMP_ABSENT)
        self.assertIs(impl._stamp_at({}, "evidence"), impl._STAMP_ABSENT)

    def test_the_optional_key_is_never_reported_missing(self):
        """It is optional, and a required key added to `DISTRIBUTION_
        DECLARATION` would declare every existing target incomplete for never
        having answered a question nobody had asked them yet."""
        self.assertNotIn("currentWhen", impl.DISTRIBUTION_DECLARATION)
        self.assertIn("currentWhen", impl.DISTRIBUTION_OPTIONAL)
        self.assertIn("currentWhen", impl.DISTRIBUTION_SHAPE)

        state = impl.distribution_state(
            {"distribution": {"axis": "repetition", "poolable": [],
                              "perEnvironment": [], "perRun": [],
                              "identicalAcrossShards": []}}, {})
        self.assertEqual([f["field"] for f in state["missing"]], [])

    def test_a_currency_declaration_of_the_wrong_shape_is_malformed(self):
        """Optional, and still schema: a target that answered badly hears
        about it rather than having its answer quietly ignored."""
        state = impl.distribution_state(
            {"distribution": {"axis": "repetition", "poolable": [],
                              "perEnvironment": [], "perRun": [],
                              "identicalAcrossShards": [],
                              "currentWhen": ["evidence", "codeDigest"]}}, {})
        self.assertEqual([f["field"] for f in state["malformed"]], ["currentWhen"])

    def test_the_kit_documents_the_optional_key_and_prefills_nothing(self):
        kit = KIT / "src_benchmark" / "__init__.py"
        text = kit.read_text(encoding="utf-8")
        self.assertIn("currentWhen", text)
        for line in text.splitlines():
            if "currentWhen" in line:
                self.assertTrue(line.strip().startswith("#"),
                                f"the kit prefills a value: {line!r}")

    def test_the_toy_targets_left_nothing_behind(self):
        self.build_target("cleanup")
        self.doCleanups()
        leftover = list((FORGE / "implementations").glob("_shardcurrent_*"))
        self.assertEqual(leftover, [], leftover)


class UnbackedPositionSurfaceTests(unittest.TestCase):
    """A ticked box nobody measured, wherever the position is already reported.

    `disagrees` is surfaced by `position_state`, by `verify`, by `probe` and by
    `position` itself, and `unbacked` is the same kind of fact about the same
    item: a reader who is told which marks contradict their evidence, and not
    which marks have none, has been told the honest half.

    And `gate` refuses on one. A record whose whole purpose is that the
    recorded sequence is honest cannot be minted over a step asserted by a
    hand-typed `x` whose witness nothing ever looked at.
    """

    PROPOSAL_REVISION = "r1.md"
    PROPOSAL_TEXT = "## 1\nprose\n"
    PROPOSAL_SHA256 = hashlib.sha256(PROPOSAL_TEXT.encode("utf-8")).hexdigest()

    def _proposals(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / self.PROPOSAL_REVISION).write_text(self.PROPOSAL_TEXT,
                                                   encoding="utf-8")
        return root

    def _box(self, suffix, *, mark):
        """A target whose one sequence item names a `@shard` witness -- the
        witness no invocation here supplies evidence for, so `satisfied` is
        `None` and only the mark decides whether that is honest."""
        box = FORGE / "implementations" / f"_unbacked_{suffix}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        for directory in ("src/Method", "src/Method_Benchmark", "Method", "tests"):
            (box / directory).mkdir(parents=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "src/Method_Benchmark/__init__.py").write_text(
            "__benchmark__ = {'revision': 'r1.md'}\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        header = {"revision": self.PROPOSAL_REVISION,
                  "revisionSha256": self.PROPOSAL_SHA256,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1",
                  "target": "final"}
        items = [{"ordinal": 1, "mark": mark, "text": "Collect the shard.",
                  "witness": {"kind": "shard", "operand": "s0"}}]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")
        return box

    def run_cli(self, *args, proposals=None):
        env = dict(os.environ)
        if proposals is not None:
            env["IMPLEMENTATION_PROPOSALS"] = str(proposals)
        return subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, cwd=FORGE, env=env)

    def position_block(self, command, box, *extra, proposals=None):
        proc = self.run_cli(command, "--target", str(box), "--name", "Method",
                            *extra, proposals=proposals)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)["position"]

    def test_verify_names_the_unbacked_tick_and_leaves_the_blank_box_alone(self):
        """Both halves in one test, because the claim is a distinction: a
        reporter that named every unmeasured item would be as useless as one
        that named none."""
        ticked = self.position_block("verify", self._box("verify_x", mark="x"))
        blank = self.position_block("verify", self._box("verify_blank", mark=" "))

        self.assertEqual([e["ordinal"] for e in ticked["unbacked"]], [1])
        self.assertEqual(blank["unbacked"], [])
        # Both are unmeasured -- that was never the question.
        self.assertEqual([e["ordinal"] for e in ticked["unmeasured"]], [1])
        self.assertEqual([e["ordinal"] for e in blank["unmeasured"]], [1])
        # And neither is a disagreement: there is no measurement to contradict.
        self.assertEqual(ticked["disagreements"], [])
        self.assertTrue(ticked["sequence"][0]["unbacked"])
        self.assertFalse(blank["sequence"][0]["unbacked"])

    def test_probe_reports_it_too(self):
        """`probe` reads the same position through the same function; a key
        surfaced in one reader and not the other is a key a reader cannot
        rely on."""
        block = self.position_block("probe", self._box("probe", mark="x"))
        self.assertEqual([e["ordinal"] for e in block["unbacked"]], [1])

    def test_position_reports_the_tick_its_own_refresh_cannot_correct(self):
        """The sharpest of the three. A refresh rewrites a contradicted mark
        on the spot -- but an unmeasured item is skipped and its mark survives
        untouched, so `position` is exactly the command whose silence left the
        assertion standing."""
        box = self._box("position", mark="x")
        proc = self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION,
                            "--session", "s1", proposals=self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)

        self.assertEqual(result["unbacked"], [1])
        self.assertEqual(result["unmeasured"], [1])
        self.assertTrue(result["sequence"][0]["unbacked"])
        # And the mark really did survive: this is not a report about a
        # correction that happened.
        self.assertEqual(result["sequence"][0]["mark"], "x")

    def test_an_absent_position_reports_the_key_rather_than_omitting_it(self):
        """The uniform-key-set rule `position_state` already documents: a key
        that appears on some branches and not others vanishes for exactly the
        callers that took the early ones."""
        box = FORGE / "implementations" / f"_unbacked_absent_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src/Method").mkdir(parents=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)

        block = self.position_block("verify", box)
        self.assertEqual(block["status"], "absent")
        self.assertEqual(block["unbacked"], [])

    def test_gate_refuses_a_launch_authorized_over_an_unbacked_tick(self):
        box = self._box("gate", mark="x")
        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1", "--worker", "w1",
                            "--justification", "Because it is time.",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "POSITION_UNBACKED")

    def test_the_same_gate_over_a_blank_box_reaches_the_readiness_check(self):
        """The pole, and the ordering proof in one: with the mark blanked and
        nothing else changed, the refusal moves on to `NOT_READY` -- so this
        check sits before that one and fires on the tick, not on the target."""
        box = self._box("gate_blank", mark=" ")
        proc = self.run_cli("gate", "--target", str(box), "--name", "Method",
                            "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                            "--job", "job1", "--worker", "w1",
                            "--justification", "Because it is time.",
                            proposals=self._proposals())
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["code"], "NOT_READY")

    def test_absent_and_stale_still_refuse_first(self):
        """Ordered AFTER the two checks about whether there is a position to
        read at all: an unbacked list computed from a section bound to a
        revision that has moved on would be naming ticks against the wrong
        evidence entirely."""
        box = FORGE / "implementations" / f"_unbacked_order_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src/Method").mkdir(parents=True)
        (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (box / "Method").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        proposals = self._proposals()

        absent = self.run_cli("gate", "--target", str(box), "--name", "Method",
                              "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                              "--job", "job1", "--worker", "w1",
                              "--justification", "Because it is time.",
                              proposals=proposals)
        self.assertEqual(json.loads(absent.stdout)["code"], "POSITION_ABSENT")

        header = {"revision": self.PROPOSAL_REVISION, "revisionSha256": "b" * 64,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1",
                  "target": "final"}
        items = [{"ordinal": 1, "mark": "x", "text": "Collect the shard.",
                  "witness": {"kind": "shard", "operand": "s0"}}]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")
        stale = self.run_cli("gate", "--target", str(box), "--name", "Method",
                             "--revision", self.PROPOSAL_REVISION, "--session", "s1",
                             "--job", "job1", "--worker", "w1",
                             "--justification", "Because it is time.",
                             proposals=proposals)
        self.assertEqual(json.loads(stale.stdout)["code"], "POSITION_STALE")

    def test_the_doctrine_names_the_refusal(self):
        """A refusal a reader meets for the first time in a terminal is a
        refusal nobody designed for."""
        self.assertIn("POSITION_UNBACKED", SKILL_MD.read_text(encoding="utf-8"))
        self.assertIn("POSITION_UNBACKED", USAGE_MD.read_text(encoding="utf-8"))

    def test_the_toy_targets_left_nothing_behind(self):
        self._box("cleanup", mark=" ")
        self.doCleanups()
        leftover = list((FORGE / "implementations").glob("_unbacked_*"))
        self.assertEqual(leftover, [], leftover)


class NotebookInterpreterTests(unittest.TestCase):
    """The isolation rule was the one rule nothing could check.

    The skill's own first section says target code runs under the target
    repository's `.venv` and never under system Python. A notebook obeys no
    such thing on its own: it names a KERNELSPEC, and the ordinary `python3`
    kernelspec's `argv` starts with a bare `"python"` resolved off `PATH` when
    the kernel starts. So `<target>/.venv/bin/python -m jupyter nbconvert
    --execute` -- the obvious invocation, and the one that reads as isolated --
    runs the cells under whatever `python` was already first on `PATH`.

    Measured on a real target: a suite passing 297/297 standalone produced
    fifteen failures inside the notebook, and no line of the failure text named
    an interpreter.

    The signal was measured before anything was built on it. One notebook was
    executed twice through the identical `.venv/bin/python -m jupyter nbconvert
    --to notebook --execute --inplace`, varying only which directory came first
    on `PATH`; `metadata.language_info.version` came back `3.12.13` and `3.9.6`
    respectively, overwriting a value seeded into the file beforehand. It tracks
    the process that ran the cells, not the kernelspec the file names, and that
    is what these fixtures reproduce.
    """

    def _target(self, suffix, *, venv_version=None):
        box = FORGE / "implementations" / f"_nbinterp_{suffix}_{os.getpid()}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        (box / "src" / "Method").mkdir(parents=True)
        (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
        (box / "Method" / "Notebooks").mkdir(parents=True)
        if venv_version is not None:
            (box / ".venv").mkdir()
            (box / ".venv" / "pyvenv.cfg").write_text(
                "home = /somewhere/bin\n"
                "include-system-site-packages = false\n"
                f"version = {venv_version}\n", encoding="utf-8")
        return box

    def _notebook(self, box, name, *, version, executed=True):
        """A notebook in the exact shape `nbconvert` leaves behind: a
        kernelspec naming `python3` -- the label that resolves off `PATH` and
        says nothing -- and a `language_info.version` written by whichever
        kernel actually ran."""
        metadata = {"kernelspec": {"display_name": "Python 3",
                                    "language": "python", "name": "python3"}}
        if version is not None:
            metadata["language_info"] = {"name": "python", "version": version}
        notebook = {
            "cells": [{"cell_type": "code",
                       "execution_count": 1 if executed else None,
                       "metadata": {}, "outputs": [],
                       "source": "print('measured')\n"}],
            "metadata": metadata, "nbformat": 4, "nbformat_minor": 5,
        }
        path = box / "Method" / "Notebooks" / name
        path.write_text(json.dumps(notebook), encoding="utf-8")
        return path

    # --- what the venv says it is, read and never run ---------------------

    def test_the_target_version_is_read_from_the_venv_config(self):
        box = self._target("version", venv_version="3.12.13")
        self.assertEqual(impl.target_python_version(box), "3.12.13")

    def test_a_four_component_version_info_reads_as_three(self):
        """Newer CPythons write `version_info = 3.12.13.final.0`. Two
        spellings of one fact have to compare as one, or the check would
        report every notebook foreign on exactly those machines."""
        box = self._target("info")
        (box / ".venv").mkdir()
        (box / ".venv" / "pyvenv.cfg").write_text(
            "version_info = 3.12.13.final.0\n", encoding="utf-8")
        self.assertEqual(impl.target_python_version(box), "3.12.13")

    def test_no_venv_is_unmeasured_and_never_a_default(self):
        """A comparison against a version nobody could read is not a
        comparison, and answering one would be inventing the baseline."""
        self.assertIsNone(impl.target_python_version(self._target("novenv")))

    def test_one_spelling_of_the_target_interpreter_path(self):
        """`introspect` runs it, `env` builds it, this reads it. Three
        spellings of one path is how one of them eventually differs."""
        box = self._target("path")
        self.assertEqual(impl.target_interpreter(box).parent.parent,
                         box / ".venv")
        source = inspect.getsource(impl)
        self.assertEqual(
            source.count('target / ".venv" / bin_dir'), 1,
            "the venv interpreter path is spelled more than once")

    # --- what the notebook says ran it ------------------------------------

    def test_the_notebook_reports_the_version_that_executed_it(self):
        box = self._target("executedby", venv_version="3.12.13")
        state = impl.notebook_execution(
            self._notebook(box, "one.ipynb", version="3.9.6"))
        self.assertEqual(state["executedBy"], "3.9.6")

    def test_a_notebook_with_no_language_info_reports_nothing_rather_than_a_guess(self):
        box = self._target("nolang", venv_version="3.12.13")
        state = impl.notebook_execution(
            self._notebook(box, "one.ipynb", version=None))
        self.assertIsNone(state["executedBy"])

    # --- the join: the two questions, asked separately ---------------------

    def test_a_foreign_interpreter_is_named_and_a_matching_one_is_not(self):
        """Both halves in one test, because the claim is a distinction. The
        kernelspec is identical in both files -- it is the label that lies --
        and only the version the kernel wrote differs."""
        box = self._target("join", venv_version="3.12.13")
        self._notebook(box, "own.ipynb", version="3.12.13")
        self._notebook(box, "foreign.ipynb", version="3.9.6")

        state = impl.notebooks_state(box, "Method", "Method")
        by_name = {r["notebook"]: r for r in state["reports"]}

        self.assertEqual(state["interpreterVersion"], "3.12.13")
        self.assertIs(by_name["Method/Notebooks/own.ipynb"]["interpreterMatch"], True)
        self.assertIs(by_name["Method/Notebooks/foreign.ipynb"]["interpreterMatch"], False)
        self.assertEqual(state["foreignInterpreter"],
                         ["Method/Notebooks/foreign.ipynb"])

    def test_an_unmeasurable_interpreter_is_none_and_never_a_pass(self):
        """Two ways to be unmeasured -- the notebook records no version, or
        there is no venv to compare against -- and neither reads as agreement.
        Silence is not a pass here for the same reason an unstamped notebook
        is not current."""
        silent = self._target("silent", venv_version="3.12.13")
        self._notebook(silent, "one.ipynb", version=None)
        self.assertIsNone(impl.notebooks_state(silent, "Method", "Method")
                          ["reports"][0]["interpreterMatch"])

        nobaseline = self._target("nobaseline")
        self._notebook(nobaseline, "one.ipynb", version="3.9.6")
        state = impl.notebooks_state(nobaseline, "Method", "Method")
        self.assertIsNone(state["interpreterVersion"])
        self.assertIsNone(state["reports"][0]["interpreterMatch"])
        self.assertEqual(state["foreignInterpreter"], [],
                         "unmeasured must never be reported as foreign")

    def test_a_foreign_interpreter_does_not_drift_the_status_on_its_own(self):
        """A wrong interpreter is not a wrong number: it is a reason to
        distrust the numbers, and one status cannot say which a reader is
        looking at. Held explicitly, because folding it in is the tempting
        move and it would destroy the distinction the key exists to draw."""
        box = self._target("nodrift", venv_version="3.12.13")
        notebook = self._notebook(box, "one.ipynb", version="3.9.6")
        stamped = json.loads(notebook.read_text(encoding="utf-8"))
        stamped["cells"][0]["outputs"] = [{
            "output_type": "stream", "name": "stdout",
            "text": [f"{impl.DIGEST_MARKER} {impl.source_digest(box, 'Method')}\n"]}]
        notebook.write_text(json.dumps(stamped), encoding="utf-8")

        state = impl.notebooks_state(box, "Method", "Method")
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["reports"][0]["status"], "executed")
        self.assertIs(state["reports"][0]["sourcesMatch"], True)
        self.assertIs(state["reports"][0]["interpreterMatch"], False)
        self.assertEqual(state["foreignInterpreter"], ["Method/Notebooks/one.ipynb"])

    def test_verify_carries_the_fact_all_the_way_to_the_reader(self):
        """A key computed and never surfaced is a key nobody reads."""
        box = self._target("verify", venv_version="3.12.13")
        self._notebook(box, "one.ipynb", version="3.9.6")
        subprocess.run(["git", "init", "-q", str(box)], check=True,
                       capture_output=True)
        proc = subprocess.run(
            [sys.executable, str(CLI), "verify", "--target", str(box),
             "--name", "Method"], capture_output=True, text=True, cwd=FORGE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        notebooks = json.loads(proc.stdout)["validation"]["notebooks"]
        self.assertEqual(notebooks["foreignInterpreter"],
                         ["Method/Notebooks/one.ipynb"])
        self.assertEqual(notebooks["interpreterVersion"], "3.12.13")

    # --- the doctrine, where a reader meets it -----------------------------

    def test_the_doctrine_gives_the_safe_invocation_and_says_why(self):
        """Prose nobody executes is the defect class this whole change is
        about, so the mechanism above is the real repair -- but a reader about
        to type the command still has to be told, in the section that states
        the rule the command breaks."""
        text = SKILL_MD.read_text(encoding="utf-8")
        section = text[text.index("## Non-negotiable isolation"):]
        section = section[:section.index("\n## ", 1)]
        self.assertIn('PATH="$PWD/.venv/bin:$PATH"', section,
                      "the safe invocation is not written down")
        self.assertIn("kernelspec", section,
                      "nothing says WHY the obvious invocation is wrong")
        self.assertIn("interpreterMatch", section,
                      "the doctrine never names the fact `verify` reports")

    def test_the_toy_targets_left_nothing_behind(self):
        self._target("cleanup")
        self.doCleanups()
        leftover = list((FORGE / "implementations").glob("_nbinterp_*"))
        self.assertEqual(leftover, [], leftover)

    def test_the_shipped_scaffold_obeys_the_doctrine_it_ships_with(self):
        """The doctrine is checked one file away from the file that breaks it.

        `test_the_isolation_section_carries_the_safe_invocation` above reads
        `SKILL.md` and passes when the rule is written down. It stayed green
        while the shipped scaffold told a reader to run a notebook the way that
        same section calls "reads as isolated and is not". Doctrine only its own
        page is held to is doctrine the forge ships past.

        Two spellings, because the first version of this test caught one and
        walked past the other. `nbconvert` is the command form. "run the
        notebook" is the prose form -- `benchmark.py`'s refusal named an
        interpreter without the prefix and never said `nbconvert` at all, so a
        check keyed on the command alone reported the scaffold clean while the
        message a reader sees AT the isolation failure prescribed the remedy
        that does not fix it.

        Every shipped asset, `.py` and `.ipynb` alike, not the one file that
        was wrong on the day this was written.
        """
        kit = Path(impl.SKILL_ROOT) / "assets" / "kit"
        assets = sorted(path for path in kit.rglob("*")
                        if path.suffix in (".py", ".ipynb")
                        and "__pycache__" not in path.parts)
        self.assertTrue(assets, f"no shipped assets under {kit}")
        prefix = '.venv/bin:$PATH'
        seen, offenders = 0, []
        for path in assets:
            if path.suffix == ".ipynb":
                text = "".join(
                    "".join(cell["source"])
                    for cell in json.loads(
                        path.read_text(encoding="utf-8"))["cells"])
            else:
                text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            for n, line in enumerate(lines):
                if "nbconvert" not in line and "run the notebook" not in line:
                    continue
                seen += 1
                # The prefix may sit on a neighbouring line: a shell command
                # wrapped for width, or a refusal built from several f-strings.
                window = "\n".join(lines[max(0, n - 2):n + 6])
                if prefix not in window:
                    offenders.append(f"{path.name}:{n + 1}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "shipped assets tell a reader to run a notebook without the PATH "
            "prefix the isolation doctrine requires")
        self.assertTrue(
            seen, "no shipped asset mentions running a notebook at all, so "
                  "this test proves nothing about the ones that do")


class StepSequenceOrderTests(unittest.TestCase):
    """A step that says which rung it advances cannot run ahead of that rung.

    An ordering that lives only in prose is an ordering nobody is stopped from
    skipping, and this repository skipped one: a pilot search ran through a
    hand-rolled invocation while the step it belonged to sat behind an unticked
    predecessor, and nothing in `step` had anything to say about it.

    `advances` is the TARGET's word. The forge compares ordinals and knows
    nothing about what any rung means -- the same division `gate` already
    keeps when it refuses `SEQUENCE_NOT_REACHED` for a launch.
    """

    _box = StepCommandTests._box
    _commit = StepCommandTests._commit
    run_cli = StepCommandTests.run_cli

    def _position(self, box, marks):
        """An AGREED.md whose position block carries `marks`, in order.

        Rendered by `impl_position.render` rather than hand-written: a
        fixture that spells the grammar a second time is a fixture that can
        drift away from the parser it is meant to feed, and the first version
        of this one did exactly that -- it produced `POSITION_BLOCK_MALFORMED`
        and proved nothing about ordering.
        """
        # A real 64-hex digest: `_BLOCK_OPEN_RE` requires exactly that width,
        # and a short stand-in is refused as a malformed opener -- which is
        # what the first version of this fixture produced.
        header = {"revision": "r01.md", "revisionSha256": "a" * 64,
                  "derivedAt": "2026-01-01T00:00:00Z", "session": "t",
                  "target": "pilot"}
        items = [{"mark": mark, "ordinal": n, "text": f"rung {n}",
                  "witness": {"kind": "record", "operand": None,
                              "twostate": True}}
                 for n, mark in enumerate(marks, start=1)]
        (box / "Method").mkdir(parents=True, exist_ok=True)
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, items), encoding="utf-8")

    def _declare(self, box, advances):
        (box / "src" / "Method_Benchmark").mkdir(parents=True, exist_ok=True)
        (box / "src" / "Method_Benchmark" / "work.py").write_text(
            "def run():\n    return 'ran'\n", encoding="utf-8")
        entry = {"module": "Method_Benchmark.work", "function": "run"}
        if advances is not None:
            entry["advances"] = advances
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
            f"__steps__ = {{'later': {entry!r}}}\n", encoding="utf-8")

    def _run(self, box):
        return self.run_cli("step", "--target", str(box), "--name", "Method",
                            "--session", "t", "--step", "later")

    def test_an_earlier_open_rung_refuses_the_step(self):
        box = self._box("behind")
        self._declare(box, advances=3)
        self._position(box, ["x", " ", " "])
        self._commit(box)
        result = self._run(box)
        body = json.loads(result.stdout)
        self.assertEqual(body["code"], "STEP_SEQUENCE_NOT_REACHED", result.stdout)
        self.assertIn("item 2", body["detail"])

    def test_every_earlier_rung_ticked_lets_the_step_run(self):
        box = self._box("ahead")
        self._declare(box, advances=3)
        self._position(box, ["x", "x", " "])
        self._commit(box)
        body = json.loads(self._run(box).stdout)
        self.assertEqual(body.get("outcome"), "returned", body)

    def test_a_step_declaring_no_rung_runs_exactly_as_before(self):
        """A target that never opted into ordering must not change behaviour."""
        box = self._box("unbound")
        self._declare(box, advances=None)
        self._position(box, [" ", " ", " "])
        self._commit(box)
        body = json.loads(self._run(box).stdout)
        self.assertEqual(body.get("outcome"), "returned", body)

    def test_a_non_integer_rung_is_refused_rather_than_coerced(self):
        box = self._box("bogus")
        self._declare(box, advances="third")
        self._position(box, ["x", "x", " "])
        self._commit(box)
        body = json.loads(self._run(box).stdout)
        self.assertEqual(body["code"], "STEP_MALFORMED", body)
