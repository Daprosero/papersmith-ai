#!/usr/bin/env python3
"""End to end: from a repository on disk to a new revision of the proposal.

The scenario battery stops at `verify`: it proves the skill can carry a
repository to a materialized, validated implementation. It says nothing about
what the whole point of that work is — that an audited finding comes back as a
published revision of the proposal. This closes that loop.

Isolation is the design, not a precaution. Each scenario gets a box holding its
own `proposals/` and its own engine state, and the box is removed in a `finally`
whether the scenario passed, failed or raised. Nothing a scenario writes can
reach the forge or the scenario after it.

    python3 tests/implementation_e2e.py [scenario-id ...]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import implementation_scenarios as battery  # noqa: E402  (path set above)

FORGE = Path(__file__).resolve().parents[1]
IMPL_CLI = FORGE / ".claude/skills/proposal-implementation/scripts/implementation_cli.py"
DELIB_CLI = FORGE / ".claude/skills/proposal-deliberation/engine/cli.mjs"
FIXTURE = FORGE / "tests" / "fixtures" / "research-concept-neutral-r01.md"
REVISION = FIXTURE.name
SUCCESSOR = REVISION.replace("-r01.md", "-r02.md")


class Deliberation:
    """One `--serve` process, bound to a box. Speaks NDJSON, dies with the box."""

    def __init__(self, box: Path) -> None:
        self.proc = subprocess.Popen(
            ["node", str(DELIB_CLI), "--serve"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=str(FORGE),
            env={**os.environ, "PROPOSAL_DELIBERATION_PROJECT_ROOT": str(box)},
        )

    def send(self, request: dict) -> dict:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            stderr = (self.proc.stderr.read() if self.proc.stderr else "")[-400:]
            return {"status": "no-response", "stderr": stderr}
        return json.loads(line)

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def impl(*args: str) -> dict:
    """The implementation CLI, reading whatever proposals/ the box installed."""
    proc = subprocess.run([sys.executable, str(IMPL_CLI), *args],
                          capture_output=True, text=True, cwd=FORGE)
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"status": "crashed", "stderr": proc.stderr[-400:]}


def materialize(target_rel: str, name: str, seed: int, box: Path) -> str:
    """Everything the scenario tail does, with the box's proposals/ in scope."""
    out = subprocess.run(
        ["bash", str(FORGE / "tests" / "implementation_finish.sh"),
         target_rel, name, str(seed)],
        capture_output=True, text=True, cwd=FORGE,
        env={**os.environ, "IMPLEMENTATION_PROPOSALS": str(box / "proposals")},
    )
    return out.stdout + out.stderr


def carry_to_verified(scenario_id: str, setup, name: str, seed: int,
                      box: Path, log: list[str]) -> tuple[Path, dict] | tuple[Path, None]:
    """Reuse the battery's own decisions to reach a materialized implementation."""
    target = FORGE / "implementations" / f"e2e-{scenario_id}"
    shutil.rmtree(target, ignore_errors=True)
    setup(target)
    rel = f"implementations/e2e-{scenario_id}"

    for _ in range(6):
        plan = impl("plan", "--target", rel, "--name", name)
        if plan.get("status") == "compliant":
            break
        if plan.get("status") == "refused" or plan.get("conflicts") or plan.get("unclassified"):
            if battery.resolve(target, name, plan, log):
                continue
            log.append(f"blocked at plan: {plan.get('code')}")
            return target, None
        plan_file = box / "plan.json"
        plan_file.write_text(json.dumps(plan))
        applied = impl("apply", "--target", rel, "--name", name, "--plan", str(plan_file))
        if applied.get("status") != "applied":
            log.append(f"apply failed: {applied.get('code')}")
            return target, None
        break

    models = target / name / "Models" / "resnet50"
    if models.is_dir() and (FORGE / "Models" / "resnet50").is_dir():
        battery.sh(f'cp -Rc "{FORGE / "Models" / "resnet50"}/." "{models}/"')
        battery.commit_all(target, "bring in the trained weights")

    tail = materialize(rel, name, seed, box)
    if "passed" not in tail:
        log.append(f"suite never ran: {tail.strip().splitlines()[-1:] or ['no output']}")
        return target, None

    verify = impl("verify", "--target", rel, "--name", name, "--revision", REVISION)
    if verify.get("structure", {}).get("staleReferences"):
        battery.resolve_stale(target, name, verify["structure"]["staleReferences"], log)
        verify = impl("verify", "--target", rel, "--name", name, "--revision", REVISION)
    battery.commit_all(target, "materialize the proposal")
    return target, verify


def publish_successor(box: Path, item: dict, source: str, target_rel: str,
                      log: list[str]) -> dict:
    """Drive the deliberation with what the handoff hands over — nothing else.

    The harness deliberately refuses to compose the request itself. If the
    bridge is incomplete, that must surface as a failure here rather than be
    papered over by a test that knows the answer.
    """
    payload = item.get("deliberation")
    if not payload:
        return {"status": "no-bridge",
                "detail": f"handoff item {item['id']} carries no deliberation payload"}

    engine = Deliberation(box)
    try:
        status = engine.send({"operation": "STATUS"})
        if status.get("status") == "no-response":
            return {"status": "engine-dead", "detail": status.get("stderr", "")}
        log.append(f"STATUS: latest={status.get('latest')}")

        query = payload.get("selectedEntryId")
        resolved = engine.send({"operation": "RESOLVE_TARGET",
                                "sourceFilename": source, "query": query})
        if resolved.get("blocked") or not resolved.get("entryId"):
            return {"status": "locus-unresolved",
                    "detail": resolved.get("question") or resolved}
        if not resolved.get("text"):
            return {"status": "entry-unreadable",
                    "detail": "RESOLVE_TARGET returned no text for the entry"}

        # The skill composes the new entry; the harness never edits mathematics.
        composed = subprocess.run(
            [sys.executable, str(IMPL_CLI), "compose", "--target", target_rel,
             "--finding", item["id"], "--entry-text", "-"],
            input=resolved["text"], capture_output=True, text=True, cwd=FORGE)
        try:
            composition = json.loads(composed.stdout or "{}")
        except json.JSONDecodeError:
            return {"status": "compose-crashed", "detail": composed.stderr[-300:]}
        if composition.get("status") == "refused":
            return {"status": "compose-refused",
                    "detail": f"{composition.get('code')}: {composition.get('detail')}"}

        decisions = [{"kind": "replace", "targetEntryId": resolved["entryId"],
                      "replacementText": composition["replacementText"]}]
        request = {"operation": "CREATE_SUCCESSOR", "sourceFilename": source,
                   "instruction": payload.get("instruction"),
                   "selectedEntryId": query, "resolvedDecisions": decisions}
        first = engine.send(request)
        if first.get("status") == "awaiting_acceptance":
            first = engine.send({**request, "acceptSuccessor": True,
                                 "successorAcceptanceToken": first.get("acceptanceToken")})
        return first
    finally:
        engine.close()


def run(scenario_id: str, setup, name: str, seed: int) -> dict:
    box = Path(tempfile.mkdtemp(prefix=f"e2e-{scenario_id}-"))
    target = FORGE / "implementations" / f"e2e-{scenario_id}"
    log: list[str] = []
    previous = os.environ.get("IMPLEMENTATION_PROPOSALS")
    try:
        (box / "proposals").mkdir(parents=True)
        shutil.copy(FIXTURE, box / "proposals" / REVISION)
        original = (box / "proposals" / REVISION).read_bytes()
        os.environ["IMPLEMENTATION_PROPOSALS"] = str(box / "proposals")

        target, verify = carry_to_verified(scenario_id, setup, name, seed, box, log)
        if verify is None:
            return {"id": scenario_id, "stage": "implementation", "result": "FAIL", "log": log}

        rel = f"implementations/e2e-{scenario_id}"
        handoff = impl("handoff", "--target", rel, "--name", name, "--revision", REVISION)
        inline = handoff.get("settleInline", [])
        if not inline:
            return {"id": scenario_id, "stage": "handoff", "result": "FAIL",
                    "log": log, "detail": "no local remedy to settle inline",
                    "handoff": {k: handoff.get(k) for k in ("status", "deferToOwnSession")}}

        # Every local remedy travels, each onto the revision the last one made.
        source, problems, published_files = REVISION, [], []
        for item in inline:
            published = publish_successor(box, item, source, rel, log)
            if published.get("status") != "published":
                return {"id": scenario_id, "stage": "deliberation", "result": "FAIL",
                        "log": log, "finding": item["id"],
                        "detail": published.get("detail") or published.get("status"),
                        # The engine reports refusals in several shapes; keep the
                        # whole answer or the next run debugs a null.
                        "engine": json.dumps(published)[:600]}

            written = (published.get("targetFilename")
                       or published.get("published", {}).get("targetFilename"))
            successor = box / "proposals" / (written or "")
            if not written or not successor.exists():
                return {"id": scenario_id, "stage": "publish", "result": "FAIL",
                        "log": log, "detail": f"nothing was written for {item['id']}",
                        "engine": json.dumps(published)[:600]}
            published_files.append(written)

            text = successor.read_text(encoding="utf-8")
            markers = item.get("adoption", {})
            if markers.get("absent") and markers["absent"] in text:
                problems.append(f"{item['id']}: still carries {markers['absent']!r}")
            for token in markers.get("expect", []):
                if token not in text:
                    problems.append(f"{item['id']}: never introduced {token!r}")
            source = written

        if (box / "proposals" / REVISION).read_bytes() != original:
            problems.append("the source revision was modified in place")

        return {"id": scenario_id, "stage": "complete",
                "result": "FAIL" if problems else "PASS", "log": log,
                "detail": "; ".join(problems) or f"published {' -> '.join(published_files)}"}
    except Exception as error:  # a raising scenario must still clean up
        return {"id": scenario_id, "stage": "raised", "result": "FAIL",
                "log": log, "detail": f"{type(error).__name__}: {error}"}
    finally:
        shutil.rmtree(box, ignore_errors=True)
        shutil.rmtree(target, ignore_errors=True)
        if previous is None:
            os.environ.pop("IMPLEMENTATION_PROPOSALS", None)
        else:
            os.environ["IMPLEMENTATION_PROPOSALS"] = previous


def main(argv: list[str]) -> int:
    wanted = set(argv) or None
    results = []
    for scenario_id, setup, name, seed in battery.SCENARIOS:
        if wanted and scenario_id not in wanted:
            continue
        result = run(scenario_id, setup, name, seed)
        results.append(result)
        print(json.dumps(result), flush=True)

    print("\n=== SUMMARY ===")
    for result in results:
        print(f"  {result['id']:<18} {result['result']:<6} "
              f"{result['stage']:<15} {str(result.get('detail', ''))[:90]}")
    failed = [r for r in results if r["result"] != "PASS"]
    print(f"\n  {len(results) - len(failed)}/{len(results)} scenarios close the loop")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
