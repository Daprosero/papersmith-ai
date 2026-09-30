---
name: sota-graph
description: "Trigger: explore a research idea before any ingestion — scout ~25 SOTA references from their abstracts, distill 3 to 5 families, and map the pool to one solar-system constellation HTML: one system per paper, at most 20 planets each, with links running between planets of different systems. Stdlib checker and renderer, no venv, no ingestion."
---

# SOTA Graph

Before a single PDF is ingested, an idea needs a map of the territory: who
works on what, which schools exist, and how they touch each other. This
skill builds that map out of abstracts alone — a constellation of small
solar systems, one per reference paper, in a single HTML file a person can
navigate. Nothing here ingests, grades against ingested Markdown, or files
anything into `guidance/`: those are later stages with their own doors.

## The two stretches

| Stretch | Delegated to | Begins after | Ends at | Measure this before delegating |
| --- | --- | --- | --- | --- |
| Scout | this skill delegates to the `sota-scout` agent | the idea is stated in at least two sentences | the pool: 25 candidates with abstracts, 3 to 5 families, and the provisional plausibility note | the stated idea — scouting an unstated idea invents its own question |
| Constellation | this skill delegates to the `sota-grapher` agent | the pool holds its 25 candidates | the single `atlas.html` beside `atlas.json`, plus the checker's green run | the pool file exists with 25 resolved candidates — mapping fewer invents coverage |

What moves is execution, never doctrine: every rule stays here, and each
agent's first instruction is to load this file. The grapher writes the
atlas and drives the checker and the renderer in its own loop; those two
scripts are the only shell commands that loop may invoke.

## The pool

Scouting writes `sota-pool/candidates.json`: at most 25 entries, each with
identifier, resolver, title, year, venue, abstract (quoted verbatim from the
source, never paraphrased), source URL, retrieval date, and its provisional
family. A candidate without an abstract does not exist for the map — a
title is not a territory. The pool is research content: it travels
gitignored, like everything under `sota-pool/`.

## The planets

Every system carries exactly these slots. Counts are exact where stated,
and the 20-planet ceiling per system is absolute.

| Slot | Planets | Orbit | What it holds |
| --- | --- | --- | --- |
| `sun` | exactly 1 | 0 | The paper: title at the center |
| `branch` | 0 to 2 | 1 | Research branches the paper claims |
| `topic_app` | exactly 1 | 1 | The topic as the application domain states it |
| `topic_ai` | exactly 1 | 1 | The same topic framed as an AI problem |
| `problem` | exactly 1 | 1 | The problem the paper faces, in one claim |
| `application` | exactly 1 | 1 | Where it lands in the world |
| `family` | 3 to 5 | 2 | One SOTA family each, shared across systems |
| `novelty` | exactly 1 | 1 | What the paper adds over those families |
| `result` | 1 to 3 | 3 | Punctual results, one claim per planet |
| `conclusion` | 1 to 2 | 3 | Conclusions, one claim per planet |

A family the abstracts themselves name carries `provenance: stated`. A
family the scout grouped carries `provenance: grouped`. Families are the
only planets two systems may share by name — that sharing is what the
inter-system links are drawn from.

## Edges

Two scopes, one closed set of relations (`about`, `addresses`, `extends`,
`contradicts`, `supports`, `yields`, `shares-family-with`): edges inside
one system name how that paper connects its own claims; edges between
systems name how planets of different systems touch — same family, a
citation, a contradiction, an extension. No self-loops; every endpoint
names a planet id that exists in the named system. An edge no abstract
supports is a drawing, not a finding.

## Output contract

Beside the pool, never inside any paper folder (there are no paper folders
yet — nothing is ingested):

- `sota-pool/atlas.json`: systems, planets, edges. Every planet carries
  `evidence: {origin, quote, retrieved}` — origin names the abstract's
  source URL or identifier, quote is copied verbatim, retrieved is the
  date. A paraphrase is not a quote and fails the check.
- `sota-pool/atlas.html`: the single navigable file, rendered
  deterministically from `atlas.json` by `scripts/render_atlas.py`. Never
  hand-edited — a hand touch is regenerated away on the next run.

## The checker and the renderer

`scripts/check_atlas.py` (stdlib-only) is the bound that holds. It refuses,
with exit 1 naming every violation: more than 20 planets in a system, a
duplicated planet id, an edge endpoint with no planet, a self-loop, a slot
outside the table, a slot count outside its row, a `rel` outside the closed
set, a planet without a non-empty `origin` and `quote`, fewer than 25
systems when the pool promises 25. Exit 2 is usage or unreadable input —
nothing was judged. The checker reads the atlas; it never reads the web,
so a green run certifies shape, not truth.

`scripts/render_atlas.py` (stdlib-only) turns a green atlas into the HTML:
inline SVG plus vanilla JavaScript, no CDN, no network at view time.
Clicking a planet shows its detail and abstract; a family filter dims what
does not belong; inter-system links highlight across systems. Exit 2 on a
red atlas — the renderer never draws what the checker refused.

## Decision gates

| Situation | Action |
| --- | --- |
| Idea under two sentences | Refuse before searching; scouting an unstated idea invents its own question |
| Fewer than 25 resolvable candidates | Report the pool short with what was tried; never pad with unquoted entries |
| More than 5 families | Keep the 5 the abstracts lean on hardest and say which were left out |
| The checker refuses | Fix the atlas and re-run, up to 3 repair passes; then stop with the violations quoted in `owed` |
| A claim has no abstract passage | The planet does not exist; a quoteless planet is a drawing |

## Measure before you assert

Never write a planet whose quote was not read in the same pass from the
abstract its evidence names. An invented quote sounds like a finding and
gets acted on like one.
