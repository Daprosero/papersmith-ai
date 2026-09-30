---
name: plausibility
description: "Trigger: explore a research idea before any ingestion — scout ~25 SOTA references from their abstracts, map the pool to one solar-system constellation HTML, then discuss the hypothesis' plausibility against that SOTA with quoted evidence. Three stretches, one command, no ingestion."
---

# Plausibility

Before a single PDF is ingested, an idea needs two things: a map of the
territory, and an honest reading of where the idea stands on it. This skill
does both in three stretches — scout the literature, draw the
constellation, then deliberate the plausibility — and nothing here ingests,
files into `guidance/`, or publishes. Those are later stages with their own
doors.

## The three stretches

| Stretch | Delegated to | Begins after | Ends at | Measure this before delegating |
| --- | --- | --- | --- | --- |
| Scout | this skill delegates to the `sota-scout` agent | the idea is stated in at least two sentences | the pool: 25 candidates with abstracts, 3 to 5 families, and the provisional plausibility note | the stated idea — scouting an unstated idea invents its own question |
| Constellation | this skill delegates to the `sota-grapher` agent | the pool holds its 25 candidates | the single `atlas.html` beside `atlas.json`, plus the checker's green run | the pool file exists with 25 resolved candidates — mapping fewer invents coverage |
| Screen | this skill delegates to the `novelty-screener` agent | the hypothesis is stated and the pool holds its candidates | the plausibility report, each claim evidence-quoted and marked provisional, the top 5 ranked for later ingestion, with what remains owed | the stated hypothesis plus the pool — an empty pool is the scout's to fill, not this stretch's to invent; the borrowed `resolve` runs only to confirm the top 5, and nothing here files into `guidance/` |

What moves is execution, never doctrine: every rule for scouting and
mapping lives below, every rule for screening lives in the agent's own
section, and each agent's first instruction is to load this file. The
grapher drives the checker and the renderer in its own loop; those two
scripts are the only shell commands that loop may invoke, and the
screener's one shell command is the borrowed `resolve` invocation.

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
| `conclusion` | 1 to 2 | 3 | Conclusions, one claim per node |

A family the abstracts themselves name carries `provenance: stated`. A
family grouped out of scattered methods carries `provenance: grouped`.
Families are the only planets two systems may share by name — that sharing
is what the inter-system links are drawn from.

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
Clicking a planet shows its detail and abstract quote; a family filter dims
what does not belong; inter-system links highlight across systems. Exit 2 on a
red atlas — the renderer never draws what the checker refused.

## Screening: the dialogue

The third stretch is a conversation, not a batch job. The screener splits
the hypothesis into claims and grades each one — `provisional-novel`,
`provisional-known`, `provisional-tension`, `provisional-contradicted` —
always quoted, always marked provisional until ingestion. The operator
adjusts the idea mid-dialogue and asks for re-screening; every pass is a
fresh report, because the agent keeps no state between passes beyond the
conversation itself. The stretch ends at the report plus the ranked top 5
for the later ingestion stage — never at a publication, never at a filing.

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
abstract its evidence names, and never grade a claim whose abstract was not
read in the same reply. An invented quote sounds like a finding and gets
acted on like one.
