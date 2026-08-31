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
DECIDING_SCRIPTS = FORGE / ".claude" / "skills" / "remote-execution" / "scripts"


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


def python_half(command):
    """The `unittest discover` half of the gate, split off from the Node half.

    Split on `&&` rather than searched for by interpreter name: the
    interpreter is exactly what is under test, so a helper that went looking
    for a known spelling of it could never object to the wrong one.
    """
    stages = [stage.strip() for stage in command.split("&&")]
    discovery = [stage for stage in stages if "unittest discover" in stage]
    if len(discovery) != 1:
        raise AssertionError(
            f"the gate names {len(discovery)} unittest discovery stages, "
            "not one")
    return discovery[0]


def node_half(command):
    """The stage of the gate that is not the Python discovery stage."""
    stages = [stage.strip() for stage in command.split("&&")]
    other = [stage for stage in stages if "unittest discover" not in stage]
    if len(other) != 1:
        raise AssertionError(
            f"the gate names {len(other)} stages beside Python discovery, "
            "not one")
    return other[0]


def discovery_pattern(command):
    tokens = python_half(command).split()
    if "-p" not in tokens:
        raise AssertionError("the gate's discovery stage names no -p pattern")
    return tokens[tokens.index("-p") + 1].strip("'\"")


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
        self.found = suites_on_disk()
        self.assertGreater(
            len(self.found), 1,
            "tests/ holds one suite or none, so a pattern reaching exactly "
            "one of them could not be told apart from a pattern reaching all")

    def test_the_configured_pattern_reaches_every_suite(self):
        pattern = discovery_pattern(stated_gate())
        unreached = [name for name in self.found
                     if not fnmatch.fnmatch(name, pattern)]
        self.assertEqual(
            unreached, [],
            f"the gate's discovery pattern {pattern!r} reaches none of these "
            "suites, so a verification satisfied by that command goes green "
            "having run almost nothing")

    def test_unittests_own_loader_collects_every_suite(self):
        """The pattern read by `fnmatch` above, read again by the loader.

        `fnmatch` is this file's reading of the pattern; `unittest`'s loader is
        the one the gate actually uses. Loading is enough -- running the
        collected suite here would be the gate running itself.
        """
        loaded = unittest.defaultTestLoader.discover(
            str(SUITES), pattern=discovery_pattern(stated_gate()),
            top_level_dir=str(SUITES))
        collected, pending = set(), [loaded]
        while pending:
            node = pending.pop()
            if isinstance(node, unittest.TestSuite):
                pending.extend(node)
            else:
                collected.add(type(node).__module__.split(".")[0])
        expected = {name[: -len(".py")] for name in self.found}
        self.assertEqual(
            sorted(expected - collected), [],
            "unittest's own loader does not collect every suite in tests/ "
            "under the configured pattern")


class GateNodeHalfTests(unittest.TestCase):
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
        stage = node_half(stated_gate())
        if re.fullmatch(r"npm (run )?test", stage.strip()):
            return
        missing = [name for name in assignments if name not in stage]
        self.assertEqual(
            missing, [],
            f"the gate's Node stage {stage!r} neither delegates to the npm "
            f"script nor sets {missing}, which that script sets. Without it "
            "the Node suites raise at import, the stage exits non-zero, and "
            "the Python half behind the `&&` never runs")


class GateInterpreterTests(unittest.TestCase):
    """The configured interpreter has to be able to run the suites.

    Every assertion here drives the interpreter the configuration actually
    names, as a process. A bare `python3` is whatever the caller's path
    resolves it to, and the one this repository was configured against could
    not import this repository's own code at all.
    """

    def interpreter(self):
        named = python_half(stated_gate()).split()[0]
        resolved = Path(named)
        if not resolved.is_absolute():
            resolved = FORGE / named
        self.assertTrue(
            resolved.is_file(),
            f"the gate names the interpreter {named!r}, which resolves to no "
            f"file at {resolved}. An interpreter left to PATH instead is "
            "whichever one the caller happens to have first, which is how a "
            "gate ends up configured against one that cannot run the suites")
        return resolved

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
