"""Fail-closed validator for a sota-graph viewer-ready JSON.

Reads one ``<stem>.graph.json`` and refuses every malformed graph. Exit 0
means well-formed, never true: this process reads the graph alone, so a
green run certifies shape against the contract, not fidelity against the
paper. Truth stays the agent's burden.

Exit codes: 0 well-formed, 1 at least one violation (all named), 2 usage
or unreadable input (nothing was judged).

Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MAX_NODES = 20

# slot -> (orbit, min_count, max_count)
SLOTS = {
    "topic_app": (0, 1, 1),
    "topic_ai": (0, 1, 1),
    "problem": (1, 1, 1),
    "family": (2, 3, 5),
    "novelty": (1, 1, 1),
    "result": (3, 1, 3),
    "conclusion": (3, 1, 2),
}

RELS = {"about", "addresses", "extends", "contradicts", "supports", "yields"}

PROVENANCE = {"stated", "grouped"}


def _failures(graph: object, root: Path) -> list[str]:
    """Every violation, so one red run names all of them rather than the
    first — a graph fixed one refusal at a time is a loop nobody budgeted."""
    found: list[str] = []
    if not isinstance(graph, dict):
        return ["GRAPH_NOT_AN_OBJECT"]
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list):
        return ["NODES_NOT_A_LIST"]
    if not isinstance(edges, list):
        found.append("EDGES_NOT_A_LIST")
        edges = []
    if len(nodes) > MAX_NODES:
        found.append(f"NODE_BUDGET_EXCEEDED: {len(nodes)} nodes, ceiling is {MAX_NODES}")

    seen: set[str] = set()
    counts: dict[str, int] = {}
    for position, node in enumerate(nodes):
        where = f"nodes[{position}]"
        if not isinstance(node, dict):
            found.append(f"{where}: NODE_NOT_AN_OBJECT")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            found.append(f"{where}: NODE_ID_MISSING")
            continue
        if node_id in seen:
            found.append(f"DUPLICATE_ID: {node_id!r}")
        seen.add(node_id)
        slot = node.get("slot")
        if slot not in SLOTS:
            found.append(f"{node_id}: SLOT_OUTSIDE_TABLE: {slot!r}")
        else:
            orbit, _, _ = SLOTS[slot]
            if node.get("orbit") != orbit:
                found.append(f"{node_id}: ORBIT_MISMATCH: slot {slot!r} rides orbit {orbit}")
            counts[slot] = counts.get(slot, 0) + 1
        if node.get("provenance") not in PROVENANCE:
            found.append(f"{node_id}: PROVENANCE_UNLABELED")
        for key in ("label", "detail"):
            if not isinstance(node.get(key), str) or not node.get(key).strip():
                found.append(f"{node_id}: {key.upper()}_EMPTY")
        evidence = node.get("evidence")
        if not isinstance(evidence, dict):
            found.append(f"{node_id}: EVIDENCE_MISSING")
            continue
        rel_path = evidence.get("path")
        quote = evidence.get("quote")
        if not isinstance(rel_path, str) or not rel_path.strip():
            found.append(f"{node_id}: EVIDENCE_PATH_EMPTY")
        elif Path(rel_path).is_absolute() or ".." in Path(rel_path).parts:
            found.append(f"{node_id}: EVIDENCE_PATH_ESCAPES_ROOT: {rel_path!r}")
        elif not (root / rel_path).is_file():
            found.append(f"{node_id}: EVIDENCE_PATH_NAMES_NO_FILE: {rel_path!r}")
        if not isinstance(quote, str) or not quote.strip():
            found.append(f"{node_id}: EVIDENCE_QUOTE_EMPTY")

    for slot, (_, minimum, maximum) in SLOTS.items():
        have = counts.get(slot, 0)
        if not minimum <= have <= maximum:
            found.append(f"SLOT_COUNT_OUTSIDE_ROW: {slot!r} has {have}, row allows {minimum}..{maximum}")

    for position, edge in enumerate(edges):
        where = f"edges[{position}]"
        if not isinstance(edge, dict):
            found.append(f"{where}: EDGE_NOT_AN_OBJECT")
            continue
        for endpoint in ("from", "to"):
            if edge.get(endpoint) not in seen:
                found.append(f"{where}: ENDPOINT_WITHOUT_NODE: {endpoint}={edge.get(endpoint)!r}")
        if edge.get("from") == edge.get("to") and edge.get("from") in seen:
            found.append(f"{where}: SELF_LOOP")
        if edge.get("rel") not in RELS:
            found.append(f"{where}: REL_OUTSIDE_CLOSED_SET: {edge.get('rel')!r}")

    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_graph.py <stem>.graph.json", file=sys.stderr)
        return 2
    target = Path(argv[1])
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        print(f"GRAPH_UNREADABLE: {error}", file=sys.stderr)
        return 2
    try:
        graph = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"GRAPH_NOT_JSON: {error}", file=sys.stderr)
        return 2
    root = Path.cwd()
    violations = _failures(graph, root)
    if violations:
        for violation in violations:
            print(violation)
        return 1
    print(f"GRAPH_WELL_FORMED: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
