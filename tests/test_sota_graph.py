"""The sota-graph bound, held executable: check_graph.py's verdicts.

Every refusal the checker can name is produced here from a graph built for
it, never read out of the script's prose. A refusal the script names and no
test produces is a sentence nobody proved; a test that produces one the
script never names is a test of nothing.

Stdlib only.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parent.parent / ".opencode" / "skills" \
    / "sota-graph" / "scripts" / "check_graph.py"

SLOTS = ["topic_app", "topic_ai", "problem", "family", "family",
         "family", "novelty", "result", "conclusion"]


def node(i, slot="result", **over):
    doc = {"id": f"n{i}", "slot": slot, "orbit": 3, "label": f"L{i}",
           "detail": f"D{i}", "provenance": "stated",
           "evidence": {"path": "p.md", "quote": "q"}}
    doc.update(over)
    return doc


def base_nodes():
    orbits = {"topic_app": 0, "topic_ai": 0, "problem": 1, "family": 2,
              "novelty": 1, "result": 3, "conclusion": 3}
    return [node(i, slot, orbit=orbits[slot])
            for i, slot in enumerate(SLOTS)]


def graph(nodes=None, edges=None):
    return {"paper": "s", "nodes": nodes if nodes is not None else base_nodes(),
            "edges": edges if edges is not None else []}


class CheckGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sota-graph-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "p.md").write_text("q\n", encoding="utf-8")

    def run_checker(self, payload, name="s.graph.json"):
        target = self.tmp / name
        if isinstance(payload, str):
            target.write_text(payload, encoding="utf-8")
        else:
            target.write_text(json.dumps(payload), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(CHECKER), str(target)],
            capture_output=True, text=True, cwd=self.tmp)
        return proc.returncode, proc.stdout + proc.stderr

    def test_well_formed_graph_passes_naming_its_counts(self):
        code, out = self.run_checker(graph())
        self.assertEqual(code, 0, out)
        self.assertIn("GRAPH_WELL_FORMED", out)

    def test_twenty_first_node_exceeds_the_absolute_ceiling(self):
        nodes = base_nodes() + [node(100 + i) for i in range(12)]
        code, out = self.run_checker(graph(nodes=nodes))
        self.assertEqual(code, 1, out)
        self.assertIn("NODE_BUDGET_EXCEEDED", out)

    def test_duplicated_id_is_named(self):
        nodes = base_nodes()
        nodes.append(node(0))
        code, out = self.run_checker(graph(nodes=nodes))
        self.assertEqual(code, 1, out)
        self.assertIn("DUPLICATE_ID", out)

    def test_edge_endpoint_without_node_is_named(self):
        code, out = self.run_checker(
            graph(edges=[{"from": "n0", "to": "ghost", "rel": "about"}]))
        self.assertEqual(code, 1, out)
        self.assertIn("ENDPOINT_WITHOUT_NODE", out)

    def test_self_loop_is_named(self):
        code, out = self.run_checker(
            graph(edges=[{"from": "n0", "to": "n0", "rel": "about"}]))
        self.assertEqual(code, 1, out)
        self.assertIn("SELF_LOOP", out)

    def test_rel_outside_the_closed_set_is_named(self):
        code, out = self.run_checker(
            graph(edges=[{"from": "n0", "to": "n1", "rel": "orbiting"}]))
        self.assertEqual(code, 1, out)
        self.assertIn("REL_OUTSIDE_CLOSED_SET", out)

    def test_two_families_starve_the_row_and_six_overflow_it(self):
        thin = [n for n in base_nodes() if n["slot"] != "family"][:6] \
            + [n for n in base_nodes() if n["slot"] == "family"][:2]
        code, out = self.run_checker(graph(nodes=thin))
        self.assertEqual(code, 1, out)
        self.assertIn("SLOT_COUNT_OUTSIDE_ROW", out)
        fat = base_nodes() + [node(50 + i, "family", orbit=2) for i in range(3)]
        code, out = self.run_checker(graph(nodes=fat))
        self.assertEqual(code, 1, out)
        self.assertIn("SLOT_COUNT_OUTSIDE_ROW", out)

    def test_slot_outside_the_table_is_named(self):
        nodes = base_nodes()
        nodes[0] = node(0, "commentary", orbit=9)
        code, out = self.run_checker(graph(nodes=nodes))
        self.assertEqual(code, 1, out)
        self.assertIn("SLOT_OUTSIDE_TABLE", out)

    def test_orbit_mismatch_is_named(self):
        nodes = base_nodes()
        nodes[0]["orbit"] = 3
        code, out = self.run_checker(graph(nodes=nodes))
        self.assertEqual(code, 1, out)
        self.assertIn("ORBIT_MISMATCH", out)

    def test_empty_quote_and_missing_file_are_named(self):
        nodes = base_nodes()
        nodes[0]["evidence"]["quote"] = "  "
        nodes[1]["evidence"]["path"] = "absent.md"
        code, out = self.run_checker(graph(nodes=nodes))
        self.assertEqual(code, 1, out)
        self.assertIn("EVIDENCE_QUOTE_EMPTY", out)
        self.assertIn("EVIDENCE_PATH_NAMES_NO_FILE", out)

    def test_path_escaping_the_root_is_named(self):
        nodes = base_nodes()
        nodes[0]["evidence"]["path"] = "../outside.md"
        code, out = self.run_checker(graph(nodes=nodes))
        self.assertEqual(code, 1, out)
        self.assertIn("EVIDENCE_PATH_ESCAPES_ROOT", out)

    def test_non_json_is_unjudged_not_refused(self):
        code, out = self.run_checker("{not json")
        self.assertEqual(code, 2, out)
        self.assertIn("GRAPH_NOT_JSON", out)

    def test_missing_operand_is_usage(self):
        proc = subprocess.run([sys.executable, str(CHECKER)],
                              capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
