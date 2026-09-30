"""Deterministic renderer: a green atlas to one self-contained HTML file.

Reads ``sota-pool/atlas.json`` and writes a single ``atlas.html``: every
system laid out on ONE shared 2D plane (golden-angle spiral, systems sorted
by id — the same atlas always draws the same sky), intra-system links as
straight segments, inter-system links as curves running planet to planet
across systems. Inline SVG plus vanilla JavaScript — no CDN, no network at
view time. Clicking a planet shows its detail and abstract quote; a family
filter dims what does not belong; hovering a planet highlights its
cross-system links.

Exit 0 on a written file, 1 when the atlas fails this module's own shape
read (run the checker first — it names violations, this one only refuses
to draw), 2 on usage or unreadable input.

Stdlib only.
"""

from __future__ import annotations

import html
import json
import math
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

ORBIT_RADII = {0: 0, 1: 90, 2: 170, 3: 250}
SYSTEM_RADIUS = 280
SPIRAL_STEP = 640
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))
MARGIN = 120


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _system_centers(systems: list[dict]) -> dict[str, tuple[float, float]]:
    """One shared plane: systems sorted by id along a golden-angle spiral.
    Pure function of the sorted ids — deterministic by construction."""
    centers: dict[str, tuple[float, float]] = {}
    for index, system in enumerate(sorted(systems, key=lambda s: s["id"])):
        radius = SPIRAL_STEP * math.sqrt(index)
        angle = index * GOLDEN_ANGLE
        centers[system["id"]] = (
            round(radius * math.cos(angle), 1),
            round(radius * math.sin(angle), 1),
        )
    return centers


def _local_positions(planets: list[dict]) -> dict[str, tuple[float, float]]:
    """System-local layout: orbit radius by slot, evenly spaced angles in id
    order — the same planets always draw the same system."""
    by_orbit: dict[int, list[dict]] = {}
    for planet in planets:
        by_orbit.setdefault(planet["orbit"], []).append(planet)
    positions: dict[str, tuple[float, float]] = {}
    for orbit in sorted(by_orbit):
        members = sorted(by_orbit[orbit], key=lambda p: p["id"])
        radius = ORBIT_RADII.get(orbit, 250)
        if radius == 0:
            positions[members[0]["id"]] = (0.0, 0.0)
            continue
        for index, planet in enumerate(members):
            angle = 2 * math.pi * index / len(members) - math.pi / 2
            positions[planet["id"]] = (
                round(radius * math.cos(angle), 1),
                round(radius * math.sin(angle), 1),
            )
    return positions


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
    centers = _system_centers(atlas["systems"])
    absolute: dict[tuple[str, str], tuple[float, float]] = {}
    for system in atlas["systems"]:
        cx, cy = centers[system["id"]]
        for pid, (lx, ly) in _local_positions(system["planets"]).items():
            absolute[(system["id"], pid)] = (cx + lx, cy + ly)

    xs = [x for x, _ in absolute.values()]
    ys = [y for _, y in absolute.values()]
    min_x, max_x = min(xs) - SYSTEM_RADIUS - MARGIN, max(xs) + SYSTEM_RADIUS + MARGIN
    min_y, max_y = min(ys) - SYSTEM_RADIUS - MARGIN, max(ys) + SYSTEM_RADIUS + MARGIN
    width, height = round(max_x - min_x), round(max_y - min_y)

    parts = [f'<svg id="sky" class="sky" viewBox="{min_x} {min_y} {width} {height}">']
    for system in sorted(atlas["systems"], key=lambda s: s["id"]):
        cx, cy = centers[system["id"]]
        parts.append(f'<g class="system" data-system="{_escape(system["id"])}">')
        parts.append(f'<text x="{cx}" y="{cy - SYSTEM_RADIUS - 16}" class="sys-title">'
                     f'{_escape(str(system.get("title", system["id"]))[:64])}</text>')
        parts.append(f'<title>{_escape(system.get("title", system["id"]))}</title>')
        for orbit in sorted({p["orbit"] for p in system["planets"] if p["orbit"] > 0}):
            radius = ORBIT_RADII.get(orbit, 250)
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" class="orbit"/>')
        for planet in sorted(system["planets"], key=lambda p: p["id"]):
            x, y = absolute[(system["id"], planet["id"])]
            color = SLOT_COLORS.get(planet["slot"], "#cccccc")
            size = 20 if planet["slot"] == "sun" else 11
            full_label = _escape(planet["label"])
            short_label = _escape(planet["label"][:28])
            parts.append(
                f'<g class="planet" data-system="{_escape(system["id"])}" '
                f'data-planet="{_escape(planet["id"])}" data-slot="{_escape(planet["slot"])}">'
                f'<title>{full_label} [{_escape(planet["slot"])}]</title>'
                f'<circle cx="{x}" cy="{y}" r="{size}" fill="{color}"/>'
                f'<text x="{x}" y="{y - size - 5}">{short_label}</text></g>')
        parts.append("</g>")
    for link in sorted(atlas["links"],
                       key=lambda l: (str(l.get("from_system")), str(l.get("from")),
                                      str(l.get("to_system")), str(l.get("to")))):
        a = absolute.get((link.get("from_system"), link.get("from")))
        b = absolute.get((link.get("to_system"), link.get("to")))
        if not a or not b:
            continue
        intra = link.get("from_system") == link.get("to_system")
        if intra:
            parts.append(
                f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" '
                f'class="link intra" data-rel="{_escape(link.get("rel"))}"/>')
        else:
            mx, my = round((a[0] + b[0]) / 2), round((a[1] + b[1]) / 2 - 120, 1)
            parts.append(
                f'<path d="M {a[0]} {a[1]} Q {mx} {my} {b[0]} {b[1]}" '
                f'class="link inter" data-rel="{_escape(link.get("rel"))}" '
                f'data-from="{_escape(link.get("from_system"))}.{_escape(link.get("from"))}" '
                f'data-to="{_escape(link.get("to_system"))}.{_escape(link.get("to"))}"/>')
    parts.append("</svg>")
    sky = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SOTA constellation</title>
<style>
html,body{{height:100%}}
body{{font-family:system-ui,sans-serif;background:#0b1020;color:#e8e8e8;margin:0;padding:12px 16px;box-sizing:border-box;display:flex;flex-direction:column}}
.sky{{flex:1 1 auto;min-height:0;width:100%;background:#111830;border:1px solid #2a3350;border-radius:8px;cursor:grab}}
.sky:active{{cursor:grabbing}}
.orbit{{fill:none;stroke:#2a3350;stroke-width:1}}
.planet text{{fill:#cfd6ea;font-size:15px;text-anchor:middle}}
.planet{{cursor:pointer}}
.link{{stroke:#4a5a80;stroke-width:1.4;fill:none}}
.link.inter{{stroke:#9b7ede;stroke-width:2}}
.sys-title{{fill:#fff;font-size:30px}}
#toolbar button{{font-size:15px;margin-right:6px;padding:4px 12px;cursor:pointer}}
#panel{{background:#141b31;border:1px solid #2a3350;border-radius:8px;padding:10px 16px;margin:0 0 10px;max-width:900px}}
#overlay{{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:10}}
#overlay.open{{display:flex}}
#modal{{background:#141b31;border:1px solid #9b7ede;border-radius:10px;padding:16px 20px;max-width:580px;max-height:82vh;overflow:auto}}
#modal .quote{{font-style:italic;color:#b9c4de}}
#modalclose{{float:right;cursor:pointer;font-size:16px;padding:2px 10px}}
#famlegend{{margin:0 0 8px}}
.famchip{{margin:2px;padding:3px 12px;cursor:pointer;border-radius:12px;border:1px solid #9b7ede;background:#1a2140;color:#e8e8e8;font-size:13px}}
.famchip.on{{background:#9b7ede;color:#0b1020}}
#toolbar{{margin:0 0 8px}}
.dim{{opacity:.15}}
</style>
</head>
<body>
<h1>SOTA constellation — one plane</h1>
<div id="panel"><em>Click a planet to read it in a popup. Drag to pan, wheel to zoom.</em></div>
<div id="overlay"><div id="modal"><button id="modalclose">close</button><div id="modalbody"></div></div></div>
<div id="famlegend"><em>Families:</em> <span id="famchips"></span></div>
<div id="toolbar"><button id="zoomin">zoom +</button><button id="zoomout">zoom −</button><button id="zoomreset">reset view</button></div>
{sky}
<script>
const ATLAS = {data};
const svg = document.getElementById('sky');
const homeRect = svg.viewBox.baseVal;
const home = {{x: homeRect.x, y: homeRect.y, w: homeRect.width, h: homeRect.height}};
let vb = {{x: home.x, y: home.y, w: home.w, h: home.h}};
function apply() {{
  svg.setAttribute('viewBox', vb.x + ' ' + vb.y + ' ' + vb.w + ' ' + vb.h);
}}
function toSvg(clientX, clientY) {{
  const rect = svg.getBoundingClientRect();
  return {{
    x: vb.x + (clientX - rect.left) / rect.width * vb.w,
    y: vb.y + (clientY - rect.top) / rect.height * vb.h
  }};
}}
function zoomAt(clientX, clientY, factor) {{
  const m = toSvg(clientX, clientY);
  vb.x = m.x - (m.x - vb.x) / factor;
  vb.y = m.y - (m.y - vb.y) / factor;
  vb.w /= factor;
  vb.h /= factor;
  apply();
}}
function zoomCenter(factor) {{
  const rect = svg.getBoundingClientRect();
  zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor);
}}
svg.addEventListener('wheel', e => {{
  e.preventDefault();
  zoomAt(e.clientX, e.clientY, e.deltaY > 0 ? 1 / 1.2 : 1.2);
}}, {{passive: false}});
document.getElementById('zoomin').addEventListener('click', () => zoomCenter(1.5));
document.getElementById('zoomout').addEventListener('click', () => zoomCenter(1 / 1.5));
document.getElementById('zoomreset').addEventListener('click', () => {{
  vb = {{x: home.x, y: home.y, w: home.width, h: home.height}};
  apply();
}});
let drag = null;
svg.addEventListener('pointerdown', e => {{
  drag = {{x: e.clientX, y: e.clientY, moved: false}};
}});
svg.addEventListener('pointermove', e => {{
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (!drag.moved) {{
    if (Math.hypot(dx, dy) < 5) return;
    drag.moved = true;
    try {{ svg.setPointerCapture(e.pointerId); }} catch (_) {{}}
  }}
  const rect = svg.getBoundingClientRect();
  vb.x -= dx / rect.width * vb.w;
  vb.y -= dy / rect.height * vb.h;
  drag = {{x: e.clientX, y: e.clientY, moved: true}};
  apply();
}});
function endDrag() {{ drag = null; }}
svg.addEventListener('pointerup', endDrag);
svg.addEventListener('pointercancel', endDrag);
const panel = document.getElementById('modalbody');
const overlay = document.getElementById('overlay');
function closeModal() {{ overlay.classList.remove('open'); }}
document.getElementById('modalclose').addEventListener('click', closeModal);
overlay.addEventListener('click', e => {{ if (e.target === overlay) closeModal(); }});
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeModal(); }});
function openModal(titleHtml) {{
  panel.innerHTML = titleHtml;
  overlay.classList.add('open');
}}
function findPlanet(sys, pid) {{
  const s = ATLAS.systems.find(s => s.id === sys);
  return s ? s.planets.find(p => p.id === pid) : null;
}}
document.querySelectorAll('.planet').forEach(g => {{
  g.addEventListener('click', () => {{
    const p = findPlanet(g.dataset.system, g.dataset.planet);
    if (!p) return;
    const ev = p.evidence || {{}};
    openModal('<h3>' + p.label + '</h3>'
      + '<p><b>' + p.slot + '</b> · orbit ' + p.orbit + ' · ' + (p.provenance || '') + '</p>'
      + '<p>' + (p.detail || '') + '</p>'
      + '<p class="quote">' + (ev.quote || '') + '</p>'
      + '<p><small>' + (ev.origin || '') + ' · retrieved ' + (ev.retrieved || '') + '</small></p>');
  }});
}});
document.querySelectorAll('.planet').forEach(g => {{
  g.addEventListener('mouseenter', () => {{
    const pid = g.dataset.system + '.' + g.dataset.planet;
    const keep = new Set([pid]);
    ATLAS.links.forEach(l => {{
      if (l.from_system !== l.to_system &&
          ((l.from_system + '.' + l.from === pid) || (l.to_system + '.' + l.to === pid))) {{
        keep.add(l.from_system + '.' + l.from);
        keep.add(l.to_system + '.' + l.to);
      }}
    }});
    document.querySelectorAll('.planet').forEach(h => {{
      h.classList.toggle('dim', !keep.has(h.dataset.system + '.' + h.dataset.planet));
    }});
  }});
  g.addEventListener('mouseleave', () => {{
    document.querySelectorAll('.planet').forEach(h => h.classList.remove('dim'));
  }});
}});
function planetLabel(h) {{
  const p = findPlanet(h.dataset.system, h.dataset.planet);
  return p ? p.label : '';
}}
const chips = document.getElementById('famchips');
const fams = {{}};
ATLAS.systems.forEach(s => s.planets.forEach(p => {{
  if (p.slot === 'family') fams[p.label] = (fams[p.label] || 0) + 1;
}}));
let activeFam = null;
Object.keys(fams).sort().forEach(label => {{
  const b = document.createElement('button');
  b.textContent = label + ' (' + fams[label] + ')';
  b.className = 'famchip';
  b.addEventListener('click', () => {{
    activeFam = (activeFam === label) ? null : label;
    document.querySelectorAll('.famchip').forEach(c => {{
      c.classList.toggle('on', c.textContent.startsWith(label + ' (') && activeFam === label);
    }});
    document.querySelectorAll('.planet').forEach(h => {{
      const hit = h.dataset.slot === 'family' && planetLabel(h) === activeFam;
      h.classList.toggle('dim', activeFam !== null && !hit);
    }});
  }});
  chips.appendChild(b);
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
    print(f"ATLAS_RENDERED: {systems} systems on one plane -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
