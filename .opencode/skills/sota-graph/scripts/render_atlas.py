"""Deterministic renderer: a green atlas to one self-contained HTML file.

Reads ``sota-pool/atlas.json`` and writes a single ``atlas.html`` with
inline SVG plus vanilla JavaScript — no CDN, no network at view time.
Clicking a planet shows its detail and abstract quote; a family filter dims
what does not belong; inter-system links highlight across systems.

Exit 0 on a written file, 1 when the atlas fails this module's own shape
read (run the checker first — it names violations, this one only refuses
to draw), 2 on usage or unreadable input.

Stdlib only.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

SLOT_COLORS = {
    "sun": "#e8b339",
    "branch": "#7fb069",
    "topic_app": "#5aa9e6",
    "topic_ai": "#7f6ae6",
    "problem": "#e65a5a",
    "application": "#5ad1e6",
    "family": "#9b7ede",
    "novelty": "#e67e22",
    "result": "#2ecc71",
    "conclusion": "#95a5a6",
}

CX, CY = 400, 300
ORBIT_RADII = {0: 0, 1: 90, 2: 170, 3: 250}
SYSTEM_W, SYSTEM_H = 800, 620


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _layout(system: dict) -> dict[str, tuple[float, float]]:
    """Deterministic positions: orbit radius by slot, evenly spaced angles
    in slot order — the same atlas always draws the same sky."""
    by_orbit: dict[int, list[dict]] = {}
    for planet in system["planets"]:
        by_orbit.setdefault(planet["orbit"], []).append(planet)
    positions: dict[str, tuple[float, float]] = {}
    import math
    for orbit in sorted(by_orbit):
        members = sorted(by_orbit[orbit], key=lambda p: p["id"])
        radius = ORBIT_RADII.get(orbit, 250)
        if radius == 0:
            positions[members[0]["id"]] = (CX, CY)
            continue
        for index, planet in enumerate(members):
            angle = 2 * math.pi * index / len(members) - math.pi / 2
            positions[planet["id"]] = (
                round(CX + radius * math.cos(angle), 1),
                round(CY + radius * math.sin(angle), 1),
            )
    return positions


def _system_svg(index: int, system: dict, positions: dict[str, tuple[float, float]]) -> str:
    parts = [f'<g class="system" data-system="{_escape(system["id"])}">']
    for orbit in sorted({p["orbit"] for p in system["planets"] if p["orbit"] > 0}):
        radius = ORBIT_RADII.get(orbit, 250)
        parts.append(f'<circle cx="{CX}" cy="{CY}" r="{radius}" class="orbit"/>')
    for planet in sorted(system["planets"], key=lambda p: p["id"]):
        x, y = positions[planet["id"]]
        color = SLOT_COLORS.get(planet["slot"], "#cccccc")
        size = 16 if planet["slot"] == "sun" else 9
        parts.append(
            f'<g class="planet" data-system="{_escape(system["id"])}" '
            f'data-planet="{_escape(planet["id"])}" data-slot="{_escape(planet["slot"])}">'
            f'<circle cx="{x}" cy="{y}" r="{size}" fill="{color}"/>'
            f'<text x="{x}" y="{y - size - 4}">{_escape(planet["label"][:28])}</text></g>'
        )
    parts.append("</g>")
    return "\n".join(parts)


def _readable_shape(atlas: object) -> str | None:
    if not isinstance(atlas, dict):
        return "ATLAS_NOT_AN_OBJECT"
    if not isinstance(atlas.get("systems"), list) or not atlas["systems"]:
        return "SYSTEMS_NOT_A_NONEMPTY_LIST"
    if not isinstance(atlas.get("links"), list):
        return "LINKS_NOT_A_LIST"
    for system in atlas["systems"]:
        if not isinstance(system, dict) or not isinstance(system.get("planets"), list):
            return "SYSTEM_MALFORMED"
    return None


def render(atlas: dict) -> str:
    data = json.dumps(atlas).replace("<", "\\u003c")
    svgs, offset = [], 0
    for index, system in enumerate(atlas["systems"]):
        positions = _layout(system)
        intra = [l for l in atlas["links"]
                 if l.get("from_system") == l.get("to_system") == system["id"]]
        seg = [f'<svg class="sky" viewBox="0 0 {SYSTEM_W} {SYSTEM_H}" '
               f'data-system="{_escape(system["id"])}">']
        seg.append(f'<text x="20" y="36" class="sys-title">{_escape(system.get("title", system["id"]))}</text>')
        seg.append(_system_svg(index, system, positions))
        for link in sorted(intra, key=lambda l: (str(l.get("from")), str(l.get("to")))):
            a, b = positions.get(link["from"]), positions.get(link["to"])
            if a and b:
                seg.append(
                    f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" '
                    f'class="link intra" data-rel="{_escape(link.get("rel"))}"/>')
        seg.append("</svg>")
        svgs.append("\n".join(seg))
        offset += 1
    skies = "\n".join(svgs)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SOTA constellation</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0b1020;color:#e8e8e8;margin:0;padding:16px}}
.sky{{background:#111830;border:1px solid #2a3350;border-radius:8px;margin:0 0 24px;width:100%;max-width:840px}}
.orbit{{fill:none;stroke:#2a3350;stroke-width:1}}
.planet text{{fill:#cfd6ea;font-size:11px;text-anchor:middle}}
.planet{{cursor:pointer}}
.link{{stroke:#4a5a80;stroke-width:1.2}}
.sys-title{{fill:#fff;font-size:18px}}
#panel{{position:sticky;top:8px;background:#141b31;border:1px solid #2a3350;border-radius:8px;padding:12px 16px;margin-bottom:16px;max-width:840px}}
#panel .quote{{font-style:italic;color:#b9c4de}}
.dim{{opacity:.15}}
</style>
</head>
<body>
<h1>SOTA constellation</h1>
<div id="panel"><em>Click a planet to read it. Use the family filter to dim the rest.</em></div>
<div><label>Family filter: <input id="famfilter" placeholder="family planet id"></label>
<button id="clear">clear</button></div>
{skies}
<script>
const ATLAS = {data};
const panel = document.getElementById('panel');
function findPlanet(sys, pid) {{
  const s = ATLAS.systems.find(s => s.id === sys);
  return s ? s.planets.find(p => p.id === pid) : null;
}}
document.querySelectorAll('.planet').forEach(g => {{
  g.addEventListener('click', () => {{
    const p = findPlanet(g.dataset.system, g.dataset.planet);
    if (!p) return;
    const ev = p.evidence || {{}};
    panel.innerHTML = '<h3>' + p.label + '</h3>'
      + '<p><b>' + p.slot + '</b> · orbit ' + p.orbit + ' · ' + (p.provenance || '') + '</p>'
      + '<p>' + (p.detail || '') + '</p>'
      + '<p class="quote">' + (ev.quote || '') + '</p>'
      + '<p><small>' + (ev.origin || '') + ' · retrieved ' + (ev.retrieved || '') + '</small></p>';
  }});
}});
function crossLinks(pid) {{
  return ATLAS.links.filter(l =>
    (l.from_system !== l.to_system) &&
    ((l.from_system + '.' + l.from === pid) || (l.to_system + '.' + l.to === pid)));
}}
document.querySelectorAll('.planet').forEach(g => {{
  g.addEventListener('mouseenter', () => {{
    const pid = g.dataset.system + '.' + g.dataset.planet;
    const keep = new Set([pid]);
    crossLinks(pid).forEach(l => {{
      keep.add(l.from_system + '.' + l.from);
      keep.add(l.to_system + '.' + l.to);
    }});
    document.querySelectorAll('.planet').forEach(h => {{
      h.classList.toggle('dim', !keep.has(h.dataset.system + '.' + h.dataset.planet));
    }});
  }});
  g.addEventListener('mouseleave', () => {{
    document.querySelectorAll('.planet').forEach(h => h.classList.remove('dim'));
  }});
}});
document.getElementById('clear').addEventListener('click', () => {{
  document.getElementById('famfilter').value = '';
  document.querySelectorAll('.planet').forEach(h => h.classList.remove('dim'));
}});
document.getElementById('famfilter').addEventListener('input', e => {{
  const q = e.target.value.trim();
  document.querySelectorAll('.planet').forEach(h => {{
    h.classList.toggle('dim', q !== '' && h.dataset.planet !== q && h.dataset.slot !== 'sun');
  }});
}});
</script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    inputs: list[str] = []
    out_path: Path | None = None
    tokens = argv[1:]
    index = 0
    while index < len(tokens):
        if tokens[index] == "--out" and index + 1 < len(tokens):
            out_path = Path(tokens[index + 1])
            index += 2
        else:
            inputs.append(tokens[index])
            index += 1
    if len(inputs) != 1 or out_path is None:
        print("usage: render_atlas.py sota-pool/atlas.json --out sota-pool/atlas.html",
              file=sys.stderr)
        return 2
    try:
        raw = Path(inputs[0]).read_text(encoding="utf-8")
    except OSError as error:
        print(f"ATLAS_UNREADABLE: {error}", file=sys.stderr)
        return 2
    try:
        atlas = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"ATLAS_NOT_JSON: {error}", file=sys.stderr)
        return 2
    shape_error = _readable_shape(atlas)
    if shape_error is not None:
        print(f"{shape_error}: run the checker first", file=sys.stderr)
        return 1
    out_path.write_text(render(atlas), encoding="utf-8")
    systems = len(atlas["systems"])
    print(f"ATLAS_RENDERED: {systems} systems -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
