"""The forge's own gate, derived on both sides rather than restated.

`openspec/config.yaml` names the command that has to pass before any apply or
verify slice may call itself done. That command is prose in a YAML file:
nothing executes it at authoring time, so a discovery pattern that reaches one
suite out of six reads exactly like a pattern that reaches all six, and an
interpreter that cannot import what the suites import reads exactly like one
that can. Both failures are silent, and both were real here.

Every lock below derives its two halves instead of asserting a literal. The
suites are whatever `tests/` holds today; the pattern is whatever the
configured command carries today; the interpreter is driven as a process and
asked to import the module that decides the answer. A restated command string
would have to be edited alongside the defect it was meant to catch, which is
the same silence one indirection later.
"""

import fnmatch
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import yaml

FORGE = Path(__file__).resolve().parent.parent
CONFIG = FORGE / "openspec" / "config.yaml"
MANIFEST = FORGE / "package.json"
SUITES = FORGE / "tests"

#: Every place the configuration states the gate. Three sites, one gate: apply
#: names it, verify names it, and the testing block records it a third time. A
#: narrowing repaired at one site leaves the other two reading green.
GATE_SITES = (("rules", "apply", "test_command"),
              ("rules", "verify", "test_command"),
              ("testing", "runner", "command"))

#: The directory holding the module whose import decides which interpreters can
#: run this repository at all. It evaluates a `tuple[int, int] | None` alias at
#: module scope, so an interpreter older than 3.10 raises `TypeError` on the
#: import line rather than failing some later assertion. Naming the module
#: keeps the interpreter lock a measurement instead of a version number
#: somebody chose.
DECIDING_SCRIPTS = FORGE / "skills" / "remote-execution" / "scripts"


def configuration():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def at(document, path):
    node = document
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise AssertionError(
                f"openspec/config.yaml has no {'.'.join(path)}")
        node = node[key]
    return node


def stated_gate():
    return at(configuration(), GATE_SITES[0])


def gate_scripts(manifest):
    """The Node half no longer names `unittest discover` directly: since
    commit `5c63644` the gate delegates to `npm run test:all`, whose
    `package.json` scripts split Node (`test:node`) and Python (`test:py`)
    halves that this doctrine now derives instead of the old two-stage
    `&&` spelling."""
    scripts = manifest["scripts"]
    required = ("test", "test:all", "test:node", "test:py")
    missing = [name for name in required if not scripts.get(name)]
    if missing:
        raise AssertionError(
            f"package.json lacks test scripts this gate derives from: {missing}")
    return scripts


def gate_command(manifest, config):
    stated = config["rules"]["apply"]["test_command"]
    matched = re.fullmatch(r"npm run ([\w:]+)", stated.strip())
    if not matched or matched.group(1) != "test:all":
        raise AssertionError(
            f"the gate's command {stated!r} does not delegate to "
            "package.json's test:all script, so nothing holds the Python "
            "half of the gate to the interpreter pytest runs under")
    return stated, manifest["scripts"]["test:all"]


def pytest_stage(manifest):
    """The gate's Python half: `test:py`'s pytest stage as pytest itself
    spells it, so an interpreter the gate never named cannot stand in."""
    stages = [stage.strip() for stage in manifest["scripts"]["test:py"].split("&&")]
    pytest_stages = [stage for stage in stages if stage.split()[0] == "pytest"]
    if len(pytest_stages) != 1:
        raise AssertionError(
            f"package.json's test:py script names {len(pytest_stages)} pytest "
            "stages, not one")
    return pytest_stages[0]


def node_stage(manifest):
    """The stage of the `test:all` gate that is not the pytest half: the
    npm script that packages the Node half (the two sides delegate rather
    than restate, so the scripts themselves are the roster)."""
    scripts = manifest["scripts"]
    stages = [stage.strip() for stage in scripts["test:all"].split("&&")]
    node_stages = [stage for stage in stages if stage.startswith("npm run test:node")]
    if len(node_stages) != 1:
        raise AssertionError(
            f"package.json's test:all script delegates {len(node_stages)} "
            "times to test:node, not once, so the Node half is not a single "
            "named stage")
    return node_stages[0]


def discovery_pattern(stated_command, manifest):
    """The suite-name pattern pytest reaches through, read from
    `pyproject.toml`'s pytest config (pytest's own loader runs the gate)."""
    import tomllib
    pyproject = (FORGE / "pyproject.toml").read_bytes()
    return tomllib.loads(pyproject.decode())["tool"]["pytest"]["ini_options"]["testpaths"]


def suites_on_disk():
    return sorted(path.name for path in SUITES.glob("test_*.py"))


class GateSiteAgreementTests(unittest.TestCase):
    """One gate, stated three times, and the three have to be one string."""

    def test_every_site_states_the_same_command(self):
        document = configuration()
        stated = {".".join(path): at(document, path) for path in GATE_SITES}
        self.assertEqual(
            len(set(stated.values())), 1,
            "the configuration states more than one gate, so a slice told to "
            f"run one of them runs something other than another does: {stated}")


class GateReachesEverySuiteTests(unittest.TestCase):
    """The configured pattern has to reach every suite on disk.

    Derived from the directory, never from a list. A suite added tomorrow is
    covered the day it lands, and a pattern narrowed tomorrow fails here
    rather than passing quietly for the next four months.
    """

    def setUp(self):
        self.config = configuration()
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.stated, self.test_all = gate_command(self.manifest, self.config)
        self.found = suites_on_disk()
        self.assertGreater(
            len(self.found), 1,
            "tests/ holds one suite or none, so a pattern reaching exactly "
            "one of them could not be told apart from a pattern reaching all")

    def test_pytests_own_testpaths_reach_every_suite(self):
        """The pattern read by `fnmatch` above, read again from pytest's own
        configuration, which is the loader the gate actually uses.

        `fnmatch` is this file's reading; `pyproject.toml`'s `testpaths` is
        what pytest runs the gate against. Compared, not restated: a narrowed
        `testpaths` fails here, and an unchanged pattern passes."""
        import tomllib
        pyproject = (FORGE / "pyproject.toml").read_bytes()
        testpaths = tomllib.loads(pyproject.decode())["tool"]["pytest"]["ini_options"]["testpaths"]
        self.assertEqual(
            testpaths, ["tests"],
            f"pytest's testpaths {testpaths!r} leaves the gate running a "
            "narrowed surface: it must reach the whole tests/ directory")
        unreached = [name for name in self.found
                     if not fnmatch.fnmatch(name, "test_*.py")]
        self.assertEqual(
            unreached, [],
            f"{unreached} sits inside tests/ and pytest's default pattern "
            "test_*.py does not match it, so the gate runs a suite pytest "
            "never collects; rename the suite or the pattern moves with it")


class GateNodeHalfTests(unittest.TestCase):
    """"""
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.config = configuration()
        self.stated, self.test_all = gate_command(self.manifest, self.config)

    """The Node half has to be the Node gate `package.json` already defines.

    `node --test tests/*.test.mjs` looks like the whole Node suite and is not:
    the suites resolve their domain profile from an environment variable the
    npm script sets, so the bare invocation dies at import with every file
    unrun. It dies loudly, which is the only mercy here -- and because the
    stages are joined by `&&`, a Node half that exits non-zero means the
    Python half never runs at all.

    Derived from `package.json` rather than restated, so an assignment added
    to that script tomorrow is required of the gate the day it lands.
    """

    #: A leading `NAME=value` prefix on a shell command line.
    ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")

    def script_assignments(self):
        script = json.loads(
            MANIFEST.read_text(encoding="utf-8"))["scripts"]["test"]
        found = []
        for token in script.split():
            match = self.ASSIGNMENT_RE.match(token)
            if not match:
                break
            found.append(match.group(1))
        return script, found

    def test_the_node_half_carries_what_the_npm_script_carries(self):
        script, assignments = self.script_assignments()
        self.assertTrue(
            assignments,
            "package.json's test script sets no environment at all, so this "
            f"rule has nothing to require and proves nothing: {script!r}")
        stage = node_stage(self.manifest)
        delegated = re.fullmatch(r"npm (?:run )?(\S+)", stage.strip())
        if delegated:
            target_script = self.manifest.get("scripts", {}).get(delegated.group(1), "")
            stage = target_script if target_script else stage
        if re.fullmatch(r"npm (?:run )?test", stage.strip()):
            return
        missing = [name for name in assignments if name not in stage]
        self.assertEqual(
            missing, [],
            f"the gate's Node stage {stage!r} neither delegates to the npm "
            f"script nor sets {missing}, which that script sets. Without it "
            "the Node suites raise at import, the stage exits non-zero, and "
            "the Python half behind the `&&` never runs")


class GateInterpreterTests(unittest.TestCase):
    """"""
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.config = configuration()
        self.stated, self.test_all = gate_command(self.manifest, self.config)

    """The configured interpreter has to be able to run the suites.

    Every assertion here drives the interpreter the configuration actually
    names, as a process. A bare `python3` is whatever the caller's path
    resolves it to, and the one this repository was configured against could
    not import this repository's own code at all.
    """

    def interpreter(self):
        """The `test:py` stage names `pytest`, the console script of the
        venv this repository provisions (`.venv/bin/pytest`). Resolve it
        the way a shell running the npm script would, then insist on a
        file on disk."""
        named = pytest_stage(self.manifest).split()[0]
        resolved = Path(shutil.which(named) or (FORGE / ".venv" / "bin" / named))
        self.assertTrue(
            resolved.is_file(),
            f"the gate names the interpreter {named!r}, which resolves to no "
            f"file at {resolved}. An interpreter left to PATH instead is "
            "whichever one the caller happens to have first, which is how a "
            "gate ends up configured against one that cannot run the suites")
        # `pytest` is a console script, not something that can drive `-c`;
        # the PYTHON the distribution provisions beside it is what answers
        # the import probes these tests drive.
        python_candidate = resolved.parent / "python"
        self.assertTrue(
            python_candidate.is_file(),
            f"pytest resolved to {resolved}, but is the sibling interpreter "
            f"{python_candidate} missing? The import probes below must be "
            "driven by the same distribution that runs the suites")
        return python_candidate

    def drive(self, source):
        return subprocess.run([str(self.interpreter()), "-c", source],
                              cwd=str(FORGE), capture_output=True, text=True,
                              timeout=120)

    def test_the_gate_names_an_interpreter_that_exists_on_disk(self):
        self.interpreter()

    def test_the_named_interpreter_imports_the_module_that_decides(self):
        done = self.drive("import sys\n"
                          f"sys.path.insert(0, {str(DECIDING_SCRIPTS)!r})\n"
                          "import adapter\n")
        self.assertEqual(
            done.returncode, 0,
            "the interpreter the gate names cannot import the remote skill's "
            "adapter, so every suite that touches it errors before it asserts "
            f"anything:\n{done.stderr}")

    def test_the_named_interpreter_carries_requests(self):
        """The one import the suites reach for outside the standard library.

        Named here rather than derived from `requirements.txt`, which does not
        list it: it arrives as another row's dependency. That is precisely why
        an interpreter can satisfy the requirements file and still fail the
        suites, and why this asks the interpreter instead of the file.
        """
        done = self.drive("import requests\n")
        self.assertEqual(
            done.returncode, 0,
            "the interpreter the gate names has no `requests`, so the suites "
            f"that import it error rather than assert:\n{done.stderr}")


if __name__ == "__main__":
    unittest.main()
