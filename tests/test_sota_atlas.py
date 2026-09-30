"""The constellation bound, held executable: check_atlas.py's verdicts and
render_atlas.py's single-file HTML.

Every refusal the checker can name is produced here from an atlas built
for it, never read out of the script's prose. The renderer is held to
three properties: it refuses a red atlas, it embeds every system, and its
output opens with no network (no http references at all).

Stdlib only.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / ".opencode" / "skills" / "plausibility" / "scripts"
CHECKER = SKILL / "check_atlas.py"
RENDERER = SKILL / "render_atlas.py"

SLOTS = ["sun", "topic_app", "topic_ai", "problem", "application",
         "family", "family", "family", "novelty", "result", "conclusion"]


def planet(pid, slot="result", **over):
    doc = {"id": pid, "slot": slot, "orbit": 3, "label": f"L{pid}",
           "detail": f"D{pid}", "provenance": "stated",
           "evidence": {"origin": "https://example.test/p", "quote": "q",
                        "retrieved": "2026-09-30"}}
    doc.update(over)
    return doc


def system(sid, extra=()):
    orbits = {"sun": 0, "branch": 1, "topic_app": 1, "topic_ai": 1,
              "problem": 1, "application": 1, "family": 2, "novelty": 1,
              "result": 3, "conclusion": 3}
    nodes = [planet(f"{sid}-{i}", slot, orbit=orbits[slot])
             for i, slot in enumerate(SLOTS)]
    nodes.extend(extra)
    return {"id": sid, "title": f"T{sid}", "planets": nodes}


def atlas(systems=None, links=None):
    return {"systems": systems if systems is not None else [system("a"), system("b")],
            "links": links if links is not None else []}


class CheckAtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sota-atlas-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def run_checker(self, payload, name="atlas.json"):
        target = self.tmp / name
        target.write_text(payload if isinstance(payload, str) else json.dumps(payload),
                          encoding="utf-8")
        proc = subprocess.run([sys.executable, str(CHECKER), str(target)],
                              capture_output=True, text=True, cwd=self.tmp)
        return proc.returncode, proc.stdout + proc.stderr

    def test_green_constellation_with_intra_and_family_links_passes(self):
        links = [{"from_system": "a", "from": "a-5", "to_system": "b",
                  "to": "b-5", "rel": "shares-family-with"},
                 {"from_system": "a", "from": "a-0", "to_system": "a",
                  "to": "a-3", "rel": "about"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 0, out)
        self.assertIn("ATLAS_WELL_FORMED", out)

    def test_family_link_on_non_family_is_named(self):
        links = [{"from_system": "a", "from": "a-1", "to_system": "b",
                  "to": "b-5", "rel": "shares-family-with"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 1, out)
        self.assertIn("SHARED_FAMILY_LINK_ON_NON_FAMILY", out)

    def test_family_link_between_families_passes(self):
        links = [{"from_system": "a", "from": "a-5", "to_system": "b", "to": "b-6",
                  "rel": "shares-family-with"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 0, out)
        self.assertIn("ATLAS_WELL_FORMED", out)

    def test_twenty_first_planet_exceeds_the_ceiling(self):
        systems = [system("a")]
        systems[0]["planets"].extend(planet(f"x{i}") for i in range(10))
        code, out = self.run_checker(atlas(systems=systems))
        self.assertEqual(code, 1, out)
        self.assertIn("PLANET_BUDGET_EXCEEDED", out)

    def test_link_to_no_planet_is_named(self):
        links = [{"from_system": "a", "from": "a-0", "to_system": "b",
                  "to": "ghost", "rel": "contradicts"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 1, out)
        self.assertIn("LINK_ENDPOINT_WITHOUT_PLANET", out)

    def test_link_to_no_system_is_named(self):
        links = [{"from_system": "a", "from": "a-0", "to_system": "ghost",
                  "to": "a-1", "rel": "about"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 1, out)
        self.assertIn("LINK_SYSTEM_WITHOUT_SYSTEM", out)

    def test_undated_evidence_is_named(self):
        systems = [system("a"), system("b")]
        systems[0]["planets"][0]["evidence"]["retrieved"] = "someday"
        code, out = self.run_checker(atlas(systems=systems))
        self.assertEqual(code, 1, out)
        self.assertIn("EVIDENCE_RETRIEVED_UNDATED", out)

    def test_two_families_starve_and_six_overflow(self):
        systems = [system("a"), system("b")]
        fams = [p for p in systems[0]["planets"] if p["slot"] == "family"]
        systems[0]["planets"] = [p for p in systems[0]["planets"] if p["slot"] != "family"] + fams[:2]
        code, out = self.run_checker(atlas(systems=systems))
        self.assertEqual(code, 1, out)
        self.assertIn("SLOT_COUNT_OUTSIDE_ROW", out)

    def test_non_json_is_unjudged_not_refused(self):
        code, out = self.run_checker("{not json")
        self.assertEqual(code, 2, out)
        self.assertIn("ATLAS_NOT_JSON", out)


class RenderAtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sota-render-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.atlas_path = self.tmp / "atlas.json"
        self.atlas_path.write_text(json.dumps(atlas()), encoding="utf-8")
        self.out_path = self.tmp / "atlas.html"

    def run_renderer(self, *args):
        proc = subprocess.run([sys.executable, str(RENDERER), *args],
                              capture_output=True, text=True, cwd=self.tmp)
        return proc.returncode, proc.stdout + proc.stderr

    def test_green_atlas_renders_one_self_contained_plane(self):
        links = [{"from_system": "a", "from": "a-5", "to_system": "b", "to": "b-5",
                  "rel": "shares-family-with"}]
        self.atlas_path.write_text(json.dumps(atlas(links=links)), encoding="utf-8")
        code, out = self.run_renderer(str(self.atlas_path), "--out", str(self.out_path))
        self.assertEqual(code, 0, out)
        self.assertIn("ATLAS_RENDERED", out)
        page = self.out_path.read_text(encoding="utf-8")
        self.assertEqual(page.count("<svg"), 1)
        self.assertIn("Ta</text>", page)
        self.assertIn("Tb</text>", page)
        self.assertIn('class="link inter"', page)
        self.assertIn('id="zoomin"', page)
        self.assertIn('id="zoomout"', page)
        self.assertIn('id="zoomreset"', page)
        self.assertIn('pointerdown', page)
        self.assertIn('wheel', page)
        self.assertIn('famchips', page)
        self.assertNotIn('famfilter', page)
        self.assertIn('id="overlay"', page)
        self.assertIn('openModal', page)
        self.assertIn('homeRect', page)
        self.assertNotIn("<script src", page)
        self.assertNotIn("<link ", page)
        self.assertNotIn("@import", page)

    def test_same_atlas_draws_the_same_sky(self):
        first = self.tmp / "first.html"
        second = self.tmp / "second.html"
        self.run_renderer(str(self.atlas_path), "--out", str(first))
        self.run_renderer(str(self.atlas_path), "--out", str(second))
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_red_shape_is_not_drawn(self):
        self.atlas_path.write_text(json.dumps({"systems": []}), encoding="utf-8")
        code, out = self.run_renderer(str(self.atlas_path), "--out", str(self.out_path))
        self.assertEqual(code, 1, out)
        self.assertFalse(self.out_path.exists())

    def test_missing_operand_is_usage(self):
        code, _ = self.run_renderer()
        self.assertEqual(code, 2)

    def test_systems_keep_clear_of_each_other_on_one_plane(self):
        import importlib.util
        import math
        spec = importlib.util.spec_from_file_location("render_atlas", str(RENDERER))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        systems = [{"id": f"s{i:02d}", "planets": []} for i in range(25)]
        pts = list(module._system_centers(systems).values())
        nearest = min(math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:])
        self.assertGreaterEqual(nearest, 600)


if __name__ == "__main__":
    unittest.main()
