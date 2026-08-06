#!/usr/bin/env python3
"""Guard suite: every refusal and every detector the skill claims to have.

The scenario battery exercises the successful path fourteen times. It says
nothing about the refusals, and a guard that silently stopped working would
leave every scenario green. This suite drives each one to its failure state and
checks the skill notices.

Discipline: every case that mutates a fixture asserts the mutation took effect
before believing the result. A negative test whose mutation quietly failed
reports success while testing nothing.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
CLI = FORGE / ".claude/skills/proposal-implementation/scripts/implementation_cli.py"
SCRATCH = Path(__file__).resolve().parent
# Intermediate plans are scratch, never repository content.
TMP = Path(tempfile.mkdtemp(prefix="implementation-harness-"))
WORK = FORGE / "implementations"
REVISION = "neutral-concept-r01.md"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
KIT = FIXTURES / "implementation_kit"

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))


def sh(cmd: str, cwd: Path | None = None, check: bool = True) -> str:
    proc = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{cmd}\n{proc.stderr}")
    return proc.stdout


def cli(*args: str, interpreter: str = sys.executable) -> dict:
    proc = subprocess.run([interpreter, str(CLI), *args],
                          capture_output=True, text=True, cwd=FORGE)
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"status": "crashed", "stderr": proc.stderr[-400:]}


def fresh(name: str) -> Path:
    target = WORK / f"g-{name}"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    sh("git init -q . && git config user.email t@t && git config user.name t", target)
    return target


def commit(target: Path, message: str = "x") -> None:
    sh("git add -A", target)
    sh(f'git -c user.email=t@t -c user.name=t commit -qm "{message}" || true', target)


def scaffolded(name: str, materialize: bool = True, admit: bool = True) -> Path:
    """A target taken through the normal flow, ready to be broken."""
    target = fresh(name)
    rel = f"implementations/{target.name}"
    plan = TMP / f"plan-{name}.json"
    plan.write_text(json.dumps(cli("plan", "--target", rel, "--name", "MIL-CREDA")))
    cli("apply", "--target", rel, "--name", "MIL-CREDA", "--plan", str(plan))
    if materialize:
        subprocess.run([sys.executable, str(FORGE / ".claude/skills/proposal-implementation/scripts/materialize.py"), rel, "MIL-CREDA", "9", str(KIT)],
                       capture_output=True, cwd=FORGE)
    if admit:
        cli("admit", "--target", rel, "--name", "MIL-CREDA", "--revision", REVISION)
    return target


def mutated(path: Path, old: str, new: str) -> None:
    """Rewrite and prove the rewrite happened. Silence here is the whole trap."""
    text = path.read_text(encoding="utf-8")
    replaced = text.replace(old, new, 1)
    if replaced == text:
        raise AssertionError(f"fixture unchanged in {path.name}: {old!r} never matched")
    path.write_text(replaced, encoding="utf-8")


# --- refusals -------------------------------------------------------------

def guard_outside_workspace() -> None:
    out = cli("plan", "--target", "/tmp", "--name", "X")
    record("OUTSIDE_WORKSPACE", out.get("code") == "OUTSIDE_WORKSPACE", str(out.get("code")))


def guard_not_a_git_repo() -> None:
    target = WORK / "g-nogit"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    out = cli("plan", "--target", f"implementations/{target.name}", "--name", "X")
    record("NOT_A_GIT_REPO", out.get("code") == "NOT_A_GIT_REPO", str(out.get("code")))


def guard_invalid_name() -> None:
    target = fresh("badname")
    out = cli("plan", "--target", f"implementations/{target.name}", "--name", "bad name!")
    record("INVALID_NAME", out.get("code") == "INVALID_NAME", str(out.get("code")))


def guard_dirty_worktree() -> None:
    target = fresh("dirty")
    (target / "loose.txt").write_text("uncommitted\n")
    out = cli("plan", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA")
    record("DIRTY_WORKTREE", out.get("code") == "DIRTY_WORKTREE", str(out.get("code")))


def guard_plan_stale() -> None:
    target = fresh("stale")
    (target / "a.ipynb").write_text("{}\n")
    commit(target)
    rel = f"implementations/{target.name}"
    plan = TMP / "plan-stale.json"
    plan.write_text(json.dumps(cli("plan", "--target", rel, "--name", "MIL-CREDA")))
    (target / "b.ipynb").write_text("{}\n")   # the repository moves under the plan
    commit(target)
    out = cli("apply", "--target", rel, "--name", "MIL-CREDA", "--plan", str(plan))
    record("PLAN_STALE", out.get("code") == "PLAN_STALE", str(out.get("code")))


def guard_destination_conflict_rename() -> None:
    target = fresh("occupied")
    for sub in ("Notebooks", "Results"):
        (target / "Legacy" / sub).mkdir(parents=True)
        (target / "Legacy" / sub / "f.csv").write_text("a,b\n")
    (target / "MIL-CREDA").mkdir()
    (target / "MIL-CREDA" / "unrelated.txt").write_text("taken\n")
    commit(target)
    rel = f"implementations/{target.name}"
    plan = TMP / "plan-occupied.json"
    plan.write_text(json.dumps(cli("plan", "--target", rel, "--name", "MIL-CREDA")))
    out = cli("apply", "--target", rel, "--name", "MIL-CREDA", "--plan", str(plan))
    record("DESTINATION_CONFLICT (rename onto existing)",
           out.get("code") == "DESTINATION_CONFLICT", str(out.get("code")))


def guard_destination_collision_moves() -> None:
    target = fresh("collision")
    for sub in ("A", "B"):
        (target / sub).mkdir()
        (target / sub / "same.csv").write_text("a,b\n")
    commit(target)
    plan = cli("plan", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA")
    record("DESTINATION_CONFLICT (two sources, one path)",
           bool(plan.get("conflicts")), str(plan.get("conflicts")))


def guard_unclassified() -> None:
    target = fresh("unclassified")
    (target / "notes.docx").write_text("binary-ish\n")
    commit(target)
    rel = f"implementations/{target.name}"
    plan = TMP / "plan-unclassified.json"
    plan.write_text(json.dumps(cli("plan", "--target", rel, "--name", "MIL-CREDA")))
    out = cli("apply", "--target", rel, "--name", "MIL-CREDA", "--plan", str(plan))
    record("UNCLASSIFIED_FILES", out.get("code") == "UNCLASSIFIED_FILES", str(out.get("code")))


def guard_forge_interpreter() -> None:
    forge_python = FORGE / ".claude/skills/paper-ingestion/.venv/bin/python"
    if not forge_python.exists():
        record("FORGE_INTERPRETER", True, "skipped: forge venv absent")
        return
    target = fresh("forgepy")
    out = cli("env", "--target", f"implementations/{target.name}",
              interpreter=str(forge_python))
    record("FORGE_INTERPRETER", out.get("code") == "FORGE_INTERPRETER", str(out.get("code")))


def guard_revision_unreadable() -> None:
    target = scaffolded("norev", admit=False)
    out = cli("admit", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", "research-concept-r99.md")
    record("REVISION_UNREADABLE", out.get("code") == "REVISION_UNREADABLE", str(out.get("code")))


def guard_no_findings() -> None:
    target = scaffolded("nofindings", materialize=False, admit=False)
    out = cli("admit", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    record("NO_FINDINGS", out.get("code") == "NO_FINDINGS", str(out.get("code")))


# --- detectors ------------------------------------------------------------

def guard_admissibility_missing() -> None:
    target = scaffolded("noruling", admit=False)
    out = cli("verify", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    audit = out.get("audit", {})
    record("admissibility missing -> audit incomplete",
           audit.get("status") == "incomplete"
           and audit.get("admissibility", {}).get("status") == "missing",
           f"{audit.get('status')}/{audit.get('admissibility', {}).get('status')}")


def guard_admissibility_stale() -> None:
    target = scaffolded("staleruling")
    ruling = target / "tests" / "admissibility.json"
    mutated(ruling, '"revisionSha256": "', '"revisionSha256": "0000')
    out = cli("verify", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    audit = out.get("audit", {})
    record("admissibility stale -> audit incomplete",
           audit.get("admissibility", {}).get("status") == "stale",
           str(audit.get("admissibility", {}).get("status")))


def guard_inadmissible_not_measured() -> None:
    target = scaffolded("inadmissible", admit=False)
    mutated(target / "tests" / "findings.py", '"equations": ["4", "5"]',
            '"equations": ["4", "77"]')
    out = cli("admit", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    flagged = "discrepancy_constant_is_unattainable" in out.get("inadmissible", {})
    record("inadmissible finding is refused", out.get("status") == "inadmissible" and flagged,
           str(out.get("status")))


def guard_trivial_assertion() -> None:
    target = scaffolded("trivial")
    mutated(target / "tests" / "test_smoke.py", "def test_package_imports() -> None:",
            "def test_bogus() -> None:\n    assert True\n\n\ndef test_package_imports() -> None:")
    out = cli("verify", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    trivial = out.get("validation", {}).get("trivialAssertions", [])
    record("trivial assertion detected", bool(trivial), str(trivial[:1]))


def guard_self_comparison() -> None:
    target = scaffolded("selfcmp")
    mutated(target / "tests" / "test_smoke.py", "def test_package_imports() -> None:",
            "def test_counter() -> None:\n    hits = 0\n    hits += len(MODULES) == len(MODULES)\n"
            "    assert hits == 1\n\n\ndef test_package_imports() -> None:")
    out = cli("verify", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    trivial = out.get("validation", {}).get("trivialAssertions", [])
    record("self-comparison in a counter detected", bool(trivial), str(trivial[:1]))


def guard_remedy_without_control() -> None:
    target = scaffolded("nocontrol")
    path = target / "tests" / "test_remedies.py"
    text = path.read_text()
    for old, new in (("declared_full = weighted_mean(discrepancies, confidences)", "declared_full = full"),
                     ("declared_half = weighted_mean(discrepancies, 0.5 * confidences)", "declared_half = full")):
        if old not in text:
            raise AssertionError(f"fixture unchanged: {old!r} never matched")
        text = text.replace(old, new)
    path.write_text(text)
    out = cli("verify", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    uncontrolled = out.get("audit", {}).get("remediesWithoutControl", [])
    record("remedy without control detected", bool(uncontrolled), str(uncontrolled))


def guard_notebook_states() -> None:
    target = scaffolded("notebook")
    out = cli("verify", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    notebook = out.get("validation", {}).get("notebook", {})
    record("notebook never executed -> stale", notebook.get("status") == "stale",
           str(notebook.get("status")))

    path = target / "MIL-CREDA" / "Notebooks" / "verification.ipynb"
    notebook_json = json.loads(path.read_text())
    for cell in notebook_json["cells"]:
        if cell["cell_type"] == "code":
            cell["execution_count"] = 1
            cell["outputs"] = []
    notebook_json["cells"].append({
        "cell_type": "code", "execution_count": 2, "id": "boom", "metadata": {},
        "outputs": [{"output_type": "error", "ename": "ValueError",
                     "evalue": "x", "traceback": []}],
        "source": ["raise ValueError('x')"]})
    path.write_text(json.dumps(notebook_json))
    out = cli("verify", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    notebook = out.get("validation", {}).get("notebook", {})
    record("notebook with a raised cell -> errored", notebook.get("status") == "errored",
           str(notebook.get("status")))


def guard_venv_never_committed() -> None:
    target = scaffolded("venvleak", materialize=False, admit=False)
    cli("env", "--target", f"implementations/{target.name}")
    commit(target, "everything")
    tracked = sh("git ls-files", target).splitlines()
    leaked = [p for p in tracked if p.startswith(".venv/")]
    record("target virtualenv stays out of the index", not leaked, f"{len(leaked)} paths")


def guard_stale_references() -> None:
    target = fresh("staleref")
    for sub in ("Notebooks", "Results"):
        (target / "Alpha" / sub).mkdir(parents=True)
    (target / "Alpha" / "Results" / "m.csv").write_text("a,b\n")
    (target / "Alpha" / "Notebooks" / "n.ipynb").write_text("{}\n")
    (target / "docs").mkdir()
    (target / "docs" / "guide.md").write_text("results live in Beta/Results\n")
    commit(target)
    rel = f"implementations/{target.name}"
    plan = TMP / "plan-staleref.json"
    plan.write_text(json.dumps(cli("plan", "--target", rel, "--name", "MIL-CREDA")))
    cli("apply", "--target", rel, "--name", "MIL-CREDA", "--plan", str(plan))
    out = cli("verify", "--target", rel, "--name", "MIL-CREDA", "--revision", REVISION)
    stale = out.get("structure", {}).get("staleReferences", [])
    record("reference to a vanished product folder detected", bool(stale), str(stale[:1]))


def guard_apply_aborts_atomically() -> None:
    """A failure mid-migration must leave the reviewed starting point intact.

    The blocker is a gitignored FILE where a product directory has to go: git
    neither tracks it nor calls the tree dirty, so the plan cannot see it and
    `apply` only discovers it while creating directories — after the migration
    has already begun.
    """
    target = fresh("abort")
    (target / ".gitignore").write_text("blocker\nMIL-CREDA\n")
    (target / "a.ipynb").write_text("{}\n")
    commit(target)
    (target / "MIL-CREDA").write_text("a file where the product folder must go\n")
    assert (target / "MIL-CREDA").is_file(), "the blocker was not created"
    assert not sh("git status --porcelain", target).strip(), "the blocker must stay invisible"

    head_before = sh("git rev-parse HEAD", target).strip()
    rel = f"implementations/{target.name}"
    plan = TMP / "plan-abort.json"
    plan.write_text(json.dumps(cli("plan", "--target", rel, "--name", "MIL-CREDA")))
    out = cli("apply", "--target", rel, "--name", "MIL-CREDA", "--plan", str(plan))

    head_after = sh("git rev-parse HEAD", target).strip()
    dirty = sh("git status --porcelain", target).strip()
    record("APPLY_ABORTED leaves the repository untouched",
           out.get("code") == "APPLY_ABORTED" and head_after == head_before and not dirty,
           f"{out.get('code')} head_unchanged={head_after == head_before} clean={not dirty}")


def guard_handoff_sizes_by_reach() -> None:
    """Local remedies settle inline; a structural one gets a session of its own."""
    target = scaffolded("handoff", admit=False)
    out = cli("handoff", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    inline = {i["id"] for i in out.get("settleInline", [])}
    deferred = {i["id"] for i in out.get("deferToOwnSession", [])}
    structural = "confidence_is_an_unconstrained_decision_variable"
    prompt = (out.get("deferToOwnSession") or [{}])[0].get("prompt", "")
    record("handoff defers the structural remedy to its own session",
           structural in deferred and structural not in inline
           and len(inline) == 2 and "sesión propia" in prompt,
           f"inline={len(inline)} deferred={len(deferred)}")


def guard_handoff_needs_a_revision() -> None:
    target = scaffolded("handoffrev", materialize=False, admit=False)
    out = cli("handoff", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", "research-concept-r99.md")
    record("handoff refuses without a readable revision",
           out.get("code") == "REVISION_UNREADABLE", str(out.get("code")))


def guard_adoption_inference() -> None:
    """Adoption is read from the revision, and fails toward `open`."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("cli_mod", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    target = scaffolded("adoption", admit=False)
    sys.path.insert(0, str(target / "tests"))
    for name in ("findings",):
        sys.modules.pop(name, None)
    from findings import FINDINGS  # noqa: E402
    sys.path.pop(0)

    source = (FIXTURES / REVISION).read_text()
    finding = next(f for f in FINDINGS if f["id"] == "discrepancy_constant_is_unattainable")
    marker = finding["adoption"]["absent"]

    taken = source.replace(marker, finding["adoption"]["expect"][0])
    other = source.replace(marker, marker.replace("= 4", "= 9"))
    if taken == source or other == source:
        raise AssertionError("the simulated revisions did not change")

    states = (mod.adoption_state(finding, source)["state"],
              mod.adoption_state(finding, taken)["state"],
              mod.adoption_state(finding, other)["state"])
    record("adoption inferred, and unrecognised change is not adoption",
           states == ("open", "adopted", "changed-unrecognized"), str(states))


def guard_invalid_adoption_marker() -> None:
    """A marker that does not describe today's revision is refused.

    This is the check that was missing: one finding shipped a marker that never
    matched, so an untouched revision read as `changed-unrecognized` instead of
    `open` — absence indistinguishable from adoption.
    """
    target = scaffolded("badmarker", admit=False)
    mutated(target / "tests" / "findings.py", '"absent": r"\\kappa = 4"',
            '"absent": r"\\kappa = 47"')
    out = cli("admit", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    flagged = out.get("inadmissible", {}).get("discrepancy_constant_is_unattainable", [])
    record("adoption marker absent from the revision is inadmissible",
           out.get("status") == "inadmissible" and any("marker" in r for r in flagged),
           str(out.get("status")))


def guard_every_marker_matches_today() -> None:
    """Every declared marker must be found in the bound revision, right now."""
    target = scaffolded("markers", admit=False)
    out = cli("admit", "--target", f"implementations/{target.name}", "--name", "MIL-CREDA",
              "--revision", REVISION)
    record("every finding's marker describes the current revision",
           out.get("status") == "admitted" and not out.get("inadmissible"),
           str(out.get("inadmissible") or "all four match"))


def guard_adopted_remedy_must_migrate() -> None:
    """An adopted remedy owes its claim to the invariant suite.

    Exercised against a synthetic revision rather than the real one: the
    proposal belongs to the deliberation and is never written from here.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("cli_migr", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    target = scaffolded("migration", admit=False)
    sys.path.insert(0, str(target / "tests"))
    sys.modules.pop("findings", None)
    from findings import FINDINGS  # noqa: E402
    sys.path.pop(0)

    finding = next(f for f in FINDINGS
                   if f["id"] == "discrepancy_constant_is_unattainable")
    source = (FIXTURES / REVISION).read_text()
    adopted = source.replace(finding["adoption"]["absent"], finding["adoption"]["expect"][0])
    if adopted == source:
        raise AssertionError("the simulated adoption changed nothing")

    before = mod.migration_state(target, [finding], adopted, "MIL_CREDA")
    owed = before["pending"][0] if before["pending"] else ""
    still_open = mod.migration_state(target, [finding], source, "MIL_CREDA")

    # now do what the agent would: retire the remedy, land the invariant
    invariant = finding["becomes_invariant"]
    remedies = target / "tests" / "test_remedies.py"
    text = remedies.read_text().replace(
        f"def test_remedy_{finding['id']}(", f"def _retired_remedy_{finding['id']}(")
    if text == remedies.read_text():
        raise AssertionError("the remedy test was not retired")
    remedies.write_text(text)
    (target / "tests" / "test_invariants.py").write_text(
        (target / "tests" / "test_invariants.py").read_text()
        + f"\n\ndef test_{invariant}() -> None:\n    assert 2.0 > 0.0\n")
    module = target / "src" / "MIL_CREDA" / "discrepancy.py"
    module.write_text(module.read_text().replace(
        '"weighted_mean_lies_in_the_unit_interval",',
        f'"weighted_mean_lies_in_the_unit_interval",\n        "{invariant}",'))

    after = mod.migration_state(target, [finding], adopted, "MIL_CREDA")
    record("adopted remedy must migrate, and clears once it has",
           still_open["status"] == "clear" and before["status"] == "pending"
           and after["status"] == "clear" and "remedy test is still in place" in owed,
           f"open={still_open['status']} adopted={before['status']} migrated={after['status']}")


GUARDS = [
    guard_outside_workspace, guard_not_a_git_repo, guard_invalid_name,
    guard_dirty_worktree, guard_plan_stale, guard_destination_conflict_rename,
    guard_destination_collision_moves, guard_unclassified, guard_forge_interpreter,
    guard_revision_unreadable, guard_no_findings, guard_admissibility_missing,
    guard_admissibility_stale, guard_inadmissible_not_measured, guard_trivial_assertion,
    guard_self_comparison, guard_remedy_without_control, guard_notebook_states,
    guard_venv_never_committed, guard_stale_references,
    guard_apply_aborts_atomically, guard_handoff_sizes_by_reach,
    guard_handoff_needs_a_revision, guard_adoption_inference,
    guard_invalid_adoption_marker, guard_every_marker_matches_today,
    guard_adopted_remedy_must_migrate,
]


if __name__ == "__main__":
    for guard in GUARDS:
        try:
            guard()
        except Exception as exc:  # noqa: BLE001 - a broken probe is a result too
            record(guard.__name__, False, f"probe error: {str(exc)[:160]}")

    print("\n=== GUARDS ===")
    for name, ok, detail in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL':<5} {name:<48} {detail}")
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n  {len(RESULTS) - len(failed)}/{len(RESULTS)} guards hold")
    for path in WORK.glob("g-*"):
        shutil.rmtree(path, ignore_errors=True)
    sys.exit(1 if failed else 0)
