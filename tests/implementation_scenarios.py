#!/usr/bin/env python3
"""Scenario battery for proposal-coding.

Every scenario is a situation a clone can land in. Each one must reach the
final Example-Method validation: structure ok, fidelity ok, suite green, notebook
executed. When the skill refuses or reports something, the resolver plays the
part of the user deciding, and the flow continues — a refusal is a checkpoint,
not an end state.

No LFS blob is ever fetched: clones come from a local mirror with smudging off.
"""

from __future__ import annotations

import json
import os
import tempfile
import shutil
import subprocess
import sys
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
CLI = FORGE / ".claude/skills/proposal-implementation/scripts/implementation_cli.py"
SCRATCH = Path(__file__).resolve().parent
# Intermediate plans are scratch, never repository content.
TMP = Path(tempfile.mkdtemp(prefix="implementation-harness-"))
# A local bare mirror of the target repository, so a full round costs no network
# and no LFS quota. It is not versioned — it is somebody's repository, not the
# forge's. Point IMPLEMENTATION_MIRROR at one, or create it with:
#   GIT_LFS_SKIP_SMUDGE=1 git clone --mirror <url> /tmp/da-mirror.git
MIRROR = Path(os.environ.get("IMPLEMENTATION_MIRROR", "/tmp/da-mirror.git"))
CODING = FORGE / "implementations"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
KIT = FIXTURES / "implementation_kit"
# The harness drives the skill from a neutral fixture, never from proposals/:
# a paper forge must not have its test suite depend on one paper. Naming the
# revision is not enough — the CLI resolves it under IMPLEMENTATION_PROPOSALS,
# which without this default points at the forge's unversioned proposals/.
REVISION = "neutral-concept-r01.md"
os.environ.setdefault("IMPLEMENTATION_PROPOSALS", str(FIXTURES))

CATEGORY_BY_EXT = {
    ".csv": "Results", ".tsv": "Results", ".pdf": "Results", ".png": "Results",
    ".jpg": "Results", ".svg": "Results", ".json": "Data", ".parquet": "Data",
    ".npz": "Data", ".pkl": "Models", ".pth": "Models", ".ckpt": "Models",
    ".ipynb": "Notebooks",
}


def sh(cmd: str, cwd: Path | None = None, check: bool = True) -> str:
    proc = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{cmd}\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def cli(*args: str) -> dict:
    proc = subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, cwd=FORGE)
    return json.loads(proc.stdout or '{"status":"crashed"}')


def git_local(target: Path) -> str:
    return "git -c user.email=t@t -c user.name=t"


def commit_all(target: Path, message: str) -> None:
    sh("git add -A", target)
    sh(f'{git_local(target)} commit -qm "{message}" || true', target)


# --- scenario setups -----------------------------------------------------

def clone(target: Path, extra: str = "") -> None:
    if not MIRROR.exists():
        raise RuntimeError(
            f"no mirror at {MIRROR}. Clone-based scenarios need one; set "
            "IMPLEMENTATION_MIRROR or create it with "
            "`GIT_LFS_SKIP_SMUDGE=1 git clone --mirror <url> /tmp/da-mirror.git`")
    sh(f"GIT_LFS_SKIP_SMUDGE=1 git clone -q {extra} {MIRROR} {target}")
    sh('git config --local filter.lfs.smudge "git-lfs smudge --skip -- %f"', target)
    sh('git config --local filter.lfs.process "git-lfs filter-process --skip"', target)
    sh("git config --local user.email t@t && git config --local user.name t", target)
    sh("git remote set-url --push origin DISABLED_FOR_TEST || true", target, check=False)


def s_empty(t: Path) -> None:
    t.mkdir(parents=True)
    sh("git init -q . && git config user.email t@t && git config user.name t", t)


def s_untracked(t: Path) -> None:
    s_empty(t)
    (t / "notes.md").write_text("# scratch\n")
    (t / "explore.ipynb").write_text('{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}\n')


def s_full_clone(t: Path) -> None:
    clone(t)


def s_shallow(t: Path) -> None:
    clone(t, "--depth 1")


def s_detached(t: Path) -> None:
    clone(t)
    sh("git checkout -q --detach HEAD", t)


def s_branch(t: Path) -> None:
    clone(t)
    sh("git checkout -q -b experiment", t)


def s_flattened(t: Path) -> None:
    clone(t)
    sh("git mv Images/Notebooks/Plots_Generator.ipynb .", t)
    sh("git mv Images/Notebooks/Results_Generator.ipynb .", t)
    sh("git mv Images/Notebooks/Tables_Generator.ipynb .", t)
    sh("mkdir -p Results weights", t)
    for d in ("Resnet18", "Resnet50", "Transformer"):
        sh(f"git mv Images/Results/{d} Results/{d}", t)
    sh("git mv Images/Results/Paper_Results Results/Paper_Results", t)
    sh("git mv Images/Models/resnet50/*.pth weights/", t)
    sh("rm -rf Images", t)
    commit_all(t, "flatten to the root")


def s_ambiguous(t: Path) -> None:
    s_empty(t)
    sh("mkdir -p Alpha/Notebooks Alpha/Results Beta/Models src/old", t)
    (t / "Alpha/Notebooks/a.ipynb").write_text('{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}\n')
    (t / "Alpha/Results/metrics.csv").write_text("x,y\n1,2\n")
    (t / "Beta/Models/net.pkl").write_text("w\n")
    (t / "src/old/io.py").write_text(
        'from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[2]\n'
        'METRICS = ROOT / "Alpha" / "Results" / "metrics.csv"\n'
        'CHECKPOINT = ROOT / "Beta" / "Models" / "net.pkl"\n'
        'DATASET = ROOT / "data" / "SomeExternalSet"\n')
    (t / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["src"]\n')
    commit_all(t, "init")


def s_name_taken(t: Path) -> None:
    clone(t)
    sh("mkdir -p Example-Method", t)
    (t / "Example-Method/unrelated.txt").write_text("something else already lives here\n")
    commit_all(t, "add an unrelated Example-Method folder")


def s_pkg_taken(t: Path) -> None:
    clone(t)
    sh("mkdir -p src/Example_Method", t)
    (t / "src/Example_Method/legacy.py").write_text('"""Foreign code already using the package name."""\n\nVALUE = 1\n')
    commit_all(t, "occupy the package name")


def s_ignored_products(t: Path) -> None:
    clone(t)
    (t / ".gitignore").write_text((t / ".gitignore").read_text() + "\nResults/\n*.log\n")
    (t / "run.log").write_text("noise\n")
    commit_all(t, "ignore Results and logs")


def s_spaces(t: Path) -> None:
    clone(t)
    sh('git mv "Images/Notebooks/Plots_Generator.ipynb" "Images/Notebooks/Plots Generator (final).ipynb"', t)
    sh('git mv "Images/Results/Resnet18/ImageCLEF.csv" "Images/Results/Resnet18/Image CLEF ñ.csv"', t)
    commit_all(t, "names with spaces and accents")


def s_symlink(t: Path) -> None:
    clone(t)
    sh("ln -s Images/Results latest_results", t)
    commit_all(t, "add a symlink to the results")


def s_submodule(t: Path) -> None:
    clone(t)
    nested = t / "vendor"
    nested.mkdir()
    sh("git init -q . && git config user.email t@t && git config user.name t", nested)
    (nested / "tool.py").write_text("VALUE = 1\n")
    commit_all(nested, "vendored tool")
    commit_all(t, "add a nested repository")


SCENARIOS = [
    ("empty", s_empty, "Example-Method", 101),
    ("untracked", s_untracked, "Example-Method", 102),
    ("full-clone", s_full_clone, "Example-Method", 103),
    ("shallow", s_shallow, "Example-Method", 104),
    ("detached", s_detached, "Example-Method", 105),
    ("branch", s_branch, "Example-Method", 106),
    ("flattened", s_flattened, "MILCREDA", 107),
    ("ambiguous", s_ambiguous, "Example-Method", 108),
    ("name-taken", s_name_taken, "Example-Method", 109),
    ("pkg-taken", s_pkg_taken, "Example_Method2", 110),
    ("ignored-products", s_ignored_products, "Example-Method", 111),
    ("spaces", s_spaces, "Example-Method", 112),
    ("symlink", s_symlink, "Example-Method", 113),
    ("submodule", s_submodule, "Example-Method", 114),
]


# --- resolver: what the user would decide --------------------------------

def resolve(target: Path, name: str, plan: dict, log: list[str]) -> bool:
    """Apply one user-style decision. Returns True when something changed."""
    if plan.get("code") == "DIRTY_WORKTREE":
        commit_all(target, "commit pending work before migrating")
        log.append("dirty -> committed")
        return True
    if plan.get("code") == "NOT_A_GIT_REPO":
        sh("git init -q . && git config user.email t@t && git config user.name t", target)
        log.append("not a repo -> git init")
        return True

    if plan.get("unclassified"):
        for rel in plan["unclassified"]:
            category = CATEGORY_BY_EXT.get(Path(rel).suffix.lower(), "Data")
            dest = Path(category) / Path(rel).name
            (target / dest).parent.mkdir(parents=True, exist_ok=True)
            sh(f'git mv "{rel}" "{dest}"', target)
        commit_all(target, "file the unclassified artifacts by category")
        log.append(f"unclassified({len(plan['unclassified'])}) -> filed by category")
        return True

    if plan.get("conflicts"):
        # The target name is already taken by unrelated content: the user moves
        # the pre-existing folder aside instead of merging blindly.
        occupied = [r["to"] for r in plan.get("renames", []) if r["to"] in plan["conflicts"]]
        if occupied:
            for folder in occupied:
                sh(f'git mv "{folder}" "{folder}-preexisting"', target)
            commit_all(target, "move the pre-existing folder aside")
            log.append(f"name taken -> {occupied} moved aside")
            return True

        # Two sources onto one destination: keep the parent folder in the name.
        moved = 0
        for move in plan.get("moves", []):
            if move["to"] in plan["conflicts"]:
                source = Path(move["from"])
                if len(source.parts) > 1:
                    unique = source.parent / f"{source.parent.name}_{source.name}"
                    sh(f'git mv "{source}" "{unique}"', target)
                    moved += 1
        commit_all(target, "disambiguate colliding basenames")
        log.append(f"conflicts({len(plan['conflicts'])}) -> renamed {moved} sources")
        return True
    return False


def resolve_stale(target: Path, name: str, stale: list[dict], log: list[str]) -> bool:
    changed = False
    for entry in stale:
        file = target / entry["file"]
        content = file.read_text(encoding="utf-8")
        for reference in entry["references"]:
            folder = reference.split("/")[0]
            content = content.replace(f"{folder}/", f"{name}/")
            content = content.replace(f'"{folder}"', f'"{name}"')
        file.write_text(content, encoding="utf-8")
        changed = True
    if changed:
        commit_all(target, "point the remaining references at the new layout")
        log.append(f"stale({len(stale)}) -> rewritten")
    return changed


# --- the flow ------------------------------------------------------------

def run(scenario_id: str, setup, name: str, seed: int) -> dict:
    target = CODING / f"sc-{scenario_id}"
    shutil.rmtree(target, ignore_errors=True)
    log: list[str] = []
    setup(target)

    rel = f"implementations/sc-{scenario_id}"
    for _ in range(6):
        plan = cli("plan", "--target", rel, "--name", name)
        if plan.get("status") == "compliant":
            break
        if plan.get("status") == "refused" or plan.get("conflicts") or plan.get("unclassified"):
            if resolve(target, name, plan, log):
                continue
            return {"id": scenario_id, "result": "BLOCKED", "detail": plan, "log": log}
        plan_file = TMP / f"plan-{scenario_id}.json"
        plan_file.write_text(json.dumps(plan))
        applied = cli("apply", "--target", rel, "--name", name, "--plan", str(plan_file))
        if applied.get("status") != "applied":
            return {"id": scenario_id, "result": "APPLY-FAILED", "detail": applied, "log": log}
        log.append(f"apply: {len(applied['renamed'])} rename, {applied['moved']} moves, "
                   f"{len(applied['referencesRewritten'])} refs")
        break

    # Real weights come from the forge's local Models/ folder, cloned with APFS
    # copy-on-write. No LFS blob is fetched at any point.
    models = target / name / "Models" / "resnet50"
    if models.is_dir():
        sh(f'cp -Rc "{FORGE / "Models" / "resnet50"}/." "{models}/"')
        commit_all(target, "bring in the trained weights")
        log.append("weights copied (APFS clone, no LFS)")

    out = subprocess.run(["bash", str(SCRATCH / "implementation_finish.sh"), rel, name, str(seed)],
                         capture_output=True, text=True, cwd=FORGE)
    tail = out.stdout.strip().splitlines()
    suite = next((line for line in tail if "passed" in line or "failed" in line), "no suite output")
    notebook = "executed OK" in out.stdout

    verify = cli("verify", "--target", rel, "--name", name, "--revision", REVISION)
    if verify["structure"]["staleReferences"]:
        resolve_stale(target, name, verify["structure"]["staleReferences"], log)
        verify = cli("verify", "--target", rel, "--name", name,
                     "--revision", REVISION)

    commit_all(target, "materialize the proposal")
    idem = cli("plan", "--target", rel, "--name", name)

    ok = (verify["structure"]["status"] == "ok" and verify["fidelity"]["status"] == "ok"
          and verify["audit"]["status"] in {"ok", "needs-deliberation"}
          and verify["validation"]["status"] == "ok"
          and notebook and "failed" not in suite and idem.get("status") == "compliant")
    return {
        "id": scenario_id, "result": "PASS" if ok else "FAIL", "log": log,
        "suite": suite.strip(), "notebook": notebook,
        "structure": verify["structure"]["status"], "fidelity": verify["fidelity"]["status"],
        "idempotent": idem.get("status"), "audit": verify["audit"]["status"], "nb": verify["validation"]["notebook"]["status"],
        "findings": [f["id"] for f in verify["audit"]["findings"]], "stale": len(verify["structure"]["staleReferences"]),
        "gaps": verify["structure"]["scaffoldGaps"], "verify": verify,
    }


if __name__ == "__main__":
    wanted = sys.argv[1:] or [s[0] for s in SCENARIOS]
    results = []
    for scenario_id, setup, name, seed in SCENARIOS:
        if scenario_id not in wanted:
            continue
        try:
            results.append(run(scenario_id, setup, name, seed))
        except Exception as exc:  # a crashed scenario is a result too
            results.append({"id": scenario_id, "result": "ERROR", "detail": str(exc)[:400]})
        print(json.dumps(results[-1], default=str)[:600], flush=True)

    print("\n=== SUMMARY ===")
    for r in results:
        detail = str(r.get('suite') or r.get('detail') or '')[:70]
        print(f"  {r['id']:<18} {r['result']:<12} {detail}")
