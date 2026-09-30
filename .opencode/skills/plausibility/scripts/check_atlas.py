"""Fail-closed validator for a sota-graph constellation atlas.

Reads one ``sota-pool/atlas.json`` and refuses every malformed atlas. Exit
0 means well-formed, never true: this process reads the atlas alone, so a
green run certifies shape against the contract, not fidelity against the
abstracts. Truth stays the agents' burden.

Exit codes: 0 well-formed, 1 at least one violation (all named), 2 usage
or unreadable input (nothing was judged).

Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MAX_PLANETS = 20

# slot -> (orbit, min_count, max_count)
SLOTS = {
    "sun": (0, 1, 1),
    "branch": (1, 0, 2),
    "topic_app": (1, 1, 1),
    "topic_ai": (1, 1, 1),
    "problem": (1, 1, 1),
    "application": (1, 1, 1),
    "family": (2, 3, 5),
    "novelty": (1, 1, 1),
    "result": (3, 1, 3),
    "conclusion": (3, 1, 2),
}

RELS = {"about", "addresses", "extends", "contradicts", "supports",
        "yields", "shares-family-with"}

PROVENANCE = {"stated", "grouped"}

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _failures(atlas: object) -> list[str]:
    """Every violation, so one red run names all of them rather than the
    first — an atlas fixed one refusal at a time is a loop nobody budgeted."""
    found: list[str] = []
    if not isinstance(atlas, dict):
        return ["ATLAS_NOT_AN_OBJECT"]
    systems = atlas.get("systems")
    links = atlas.get("links")
    if not isinstance(systems, list) or not systems:
        return ["SYSTEMS_NOT_A_NONEMPTY_LIST"]
    if not isinstance(links, list):
        found.append("LINKS_NOT_A_LIST")
        links = []

    known: dict[str, set[str]] = {}
    slots_of: dict[tuple[str, str], str] = {}
    for position, system in enumerate(systems):
        where = f"systems[{position}]"
        if not isinstance(system, dict):
            found.append(f"{where}: SYSTEM_NOT_AN_OBJECT")
            continue
        sid = system.get("id")
        if not isinstance(sid, str) or not sid:
            found.append(f"{where}: SYSTEM_ID_MISSING")
            continue
        if sid in known:
            found.append(f"DUPLICATE_SYSTEM_ID: {sid!r}")
            continue
        planets = system.get("planets")
        if not isinstance(planets, list):
            found.append(f"{sid}: PLANETS_NOT_A_LIST")
            known[sid] = set()
            continue
        if len(planets) > MAX_PLANETS:
            found.append(f"{sid}: PLANET_BUDGET_EXCEEDED: {len(planets)} planets, ceiling is {MAX_PLANETS}")
        seen: set[str] = set()
        counts: dict[str, int] = {}
        for index, planet in enumerate(planets):
            plabel = f"{sid}.planets[{index}]"
            if not isinstance(planet, dict):
                found.append(f"{plabel}: PLANET_NOT_AN_OBJECT")
                continue
            pid = planet.get("id")
            if not isinstance(pid, str) or not pid:
                found.append(f"{plabel}: PLANET_ID_MISSING")
                continue
            if pid in seen:
                found.append(f"{sid}: DUPLICATE_PLANET_ID: {pid!r}")
            seen.add(pid)
            slot = planet.get("slot")
            if slot not in SLOTS:
                found.append(f"{sid}.{pid}: SLOT_OUTSIDE_TABLE: {slot!r}")
            else:
                orbit, _, _ = SLOTS[slot]
                if planet.get("orbit") != orbit:
                    found.append(f"{sid}.{pid}: ORBIT_MISMATCH: slot {slot!r} rides orbit {orbit}")
                counts[slot] = counts.get(slot, 0) + 1
                slots_of[(sid, pid)] = slot
            if planet.get("provenance") not in PROVENANCE:
                found.append(f"{sid}.{pid}: PROVENANCE_UNLABELED")
            for key in ("label", "detail"):
                if not isinstance(planet.get(key), str) or not planet.get(key).strip():
                    found.append(f"{sid}.{pid}: {key.upper()}_EMPTY")
            evidence = planet.get("evidence")
            if not isinstance(evidence, dict):
                found.append(f"{sid}.{pid}: EVIDENCE_MISSING")
                continue
            origin = evidence.get("origin")
            quote = evidence.get("quote")
            retrieved = evidence.get("retrieved")
            if not isinstance(origin, str) or not origin.strip():
                found.append(f"{sid}.{pid}: EVIDENCE_ORIGIN_EMPTY")
            if not isinstance(quote, str) or not quote.strip():
                found.append(f"{sid}.{pid}: EVIDENCE_QUOTE_EMPTY")
            if not isinstance(retrieved, str) or not DATE.match(retrieved):
                found.append(f"{sid}.{pid}: EVIDENCE_RETRIEVED_UNDATED")
        for slot, (_, minimum, maximum) in SLOTS.items():
            have = counts.get(slot, 0)
            if not minimum <= have <= maximum:
                found.append(f"{sid}: SLOT_COUNT_OUTSIDE_ROW: {slot!r} has {have}, row allows {minimum}..{maximum}")
        known[sid] = seen

    for position, link in enumerate(links):
        where = f"links[{position}]"
        if not isinstance(link, dict):
            found.append(f"{where}: LINK_NOT_AN_OBJECT")
            continue
        endpoints = []
        for key in ("from_system", "from", "to_system", "to"):
            value = link.get(key)
            if not isinstance(value, str) or not value:
                found.append(f"{where}: LINK_ENDPOINT_MISSING: {key}")
                value = None
            endpoints.append(value)
        from_system, from_pid, to_system, to_pid = endpoints
        if from_system is not None and from_system not in known:
            found.append(f"{where}: LINK_SYSTEM_WITHOUT_SYSTEM: {from_system!r}")
        if to_system is not None and to_system not in known:
            found.append(f"{where}: LINK_SYSTEM_WITHOUT_SYSTEM: {to_system!r}")
        if from_system in known and from_pid is not None and from_pid not in known[from_system]:
            found.append(f"{where}: LINK_ENDPOINT_WITHOUT_PLANET: {from_system}.{from_pid}")
        if to_system in known and to_pid is not None and to_pid not in known[to_system]:
            found.append(f"{where}: LINK_ENDPOINT_WITHOUT_PLANET: {to_system}.{to_pid}")
        if (from_system, from_pid) == (to_system, to_pid) and from_system in known:
            found.append(f"{where}: SELF_LOOP")
        rel = link.get("rel")
        if rel not in RELS:
            found.append(f"{where}: REL_OUTSIDE_CLOSED_SET: {rel!r}")
        elif rel == "shares-family-with":
            ends = [(from_system, from_pid), (to_system, to_pid)]
            if all(e in slots_of for e in ends) and any(slots_of[e] != "family" for e in ends):
                found.append(f"{where}: SHARED_FAMILY_LINK_ON_NON_FAMILY")

    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_atlas.py sota-pool/atlas.json", file=sys.stderr)
        return 2
    target = Path(argv[1])
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        print(f"ATLAS_UNREADABLE: {error}", file=sys.stderr)
        return 2
    try:
        atlas = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"ATLAS_NOT_JSON: {error}", file=sys.stderr)
        return 2
    violations = _failures(atlas)
    if violations:
        for violation in violations:
            print(violation)
        return 1
    systems = len(atlas["systems"])
    planets = sum(len(system["planets"]) for system in atlas["systems"])
    print(f"ATLAS_WELL_FORMED: {systems} systems, {planets} planets, {len(atlas['links'])} links")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
