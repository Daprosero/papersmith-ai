---
name: sota-graph
description: "Trigger: map one ingested paper to a solar-system graph of at most 20 nodes — application topic and AI topic, the problem it faces, 3 to 5 SOTA families, the proposal's novelty, punctual results and conclusions. One viewer-ready JSON beside the paper, every node evidence-quoted. Stdlib checker, no venv, no network."
---

# SOTA Graph

One ingested paper is still a document to read front to back. This skill maps
it to a graph a later session — or an interactive viewer — can navigate
instead: a small solar system per paper, centered on its topics, with the
problem, the SOTA families, the novelty, the results and the conclusions in
fixed orbits. The graph never replaces the `.md`; it indexes it.

## The slots

Every graph carries exactly these slots. Counts are exact where stated, and
the 20-node ceiling is absolute — a paper that needs more is two graphs, not
a bigger one.

| Slot | Nodes | Orbit | What it holds |
| --- | --- | --- | --- |
| `topic_app` | exactly 1 | 0 | The topic as the application domain states it |
| `topic_ai` | exactly 1 | 0 | The same topic framed as an AI problem |
| `problem` | exactly 1 | 1 | The problem the paper faces, in one claim |
| `family` | 3 to 5 | 2 | One SOTA family each: a school of methods the paper positions against |
| `novelty` | exactly 1 | 1 | What the proposal adds over those families |
| `result` | 1 to 3 | 3 | Punctual results, one claim per node |
| `conclusion` | 1 to 2 | 3 | Conclusions, one claim per node |

Typical graphs land at 11–14 nodes. The remaining headroom (up to 20) is for
papers whose results genuinely split — never for commentary nodes, which have
no slot and therefore do not exist.

A family the paper itself names carries `provenance: stated`. A family the
grapher grouped out of scattered methods carries `provenance: grouped`.
Grouping without the label is inventing a school; stating without a quote is
inventing a source.

## Edges

Edges name how the paper itself connects its claims, in this closed set:
`about`, `addresses`, `extends`, `contradicts`, `supports`, `yields`. No
self-loops; every endpoint names a node id that exists. An edge the paper
does not support is a drawing, not a finding.

## The corpus, and what is not in it

Only the ingested Markdown counts: the paper's own `.md` first, and
`guidance/reference-papers/*/*.md` plus `guidance/paper-guide/*/*.md` for
cross-links. A PDF is not evidence. A paper with no `.md` is ingestion's to
finish, not this stretch's to invent.

## Output contract

For a paper folder `<root>/<stem>/` holding `<stem>.md`, write
`<root>/<stem>/<stem>.graph.json` beside it:

```json
{
  "paper": "<stem>",
  "nodes": [
    {"id": "topic-ai", "slot": "topic_ai", "orbit": 0, "label": "…",
     "detail": "…", "provenance": "stated",
     "evidence": {"path": "guidance/reference-papers/<stem>/<stem>.md",
                  "quote": "exact passage, copied verbatim"}}
  ],
  "edges": [{"from": "topic-ai", "to": "problem", "rel": "about"}]
}
```

`evidence.path` is relative to the repository root and must resolve to a
file on disk. `evidence.quote` is copied verbatim from that file — a
paraphrase is not a quote and fails the check.

## The checker

`scripts/check_graph.py` (stdlib-only) is the bound that holds. It refuses,
with exit 1 naming every violation: more than 20 nodes, a duplicated id, an
edge endpoint with no node, a self-loop, a slot outside the table, a slot
count outside its row, a `rel` outside the closed set, a node without a
non-empty `path` and `quote`, an evidence path that does not resolve inside
the repository root or names no file. Exit 2 is usage or unreadable input —
nothing was judged. The checker reads the graph; it never reads the paper,
so a graph that passes is well-formed, not true. Truth stays the agent's
burden under [Measure before you assert](#measure-before-you-assert).

## What this skill delegates, and to whom

Mapping is one stretch, and it runs in an agent of its own rather than in
the conversation that asked for it.

| Stretch | Delegated to | Begins after | Ends at | Measure this before delegating |
| --- | --- | --- | --- | --- |
| Map | this skill delegates to the `sota-grapher` agent | the paper folder holds its `.md` | the viewer-ready graph beside the paper plus the checker's green run | the `.md` exists beside its PDF — a paper with no Markdown is ingestion's to finish, not this stretch's to invent |

What moves is execution, never doctrine: every rule stays here, and the
agent's first instruction is to load this file. The agent writes the graph
and drives the checker in its own loop; the checker is the only shell
command that loop may invoke.

## Activation contract

One paper per run, named by its folder. Never map a paper whose `.md` does
not exist, never map two papers into one graph, and never write outside the
paper's own folder — the graph belongs to the paper the way its figures do.

## Decision gates

| Situation | Action |
| --- | --- |
| Named folder holds no `.md` | Refuse before reading anything; mapping is not ingestion |
| Named folder does not exist | Refuse; nothing was touched |
| The paper names fewer than 3 families | Group methods into families and label each `grouped`; never pad to reach 3 with an unquoted family |
| The paper names more than 5 families | Keep the 5 the paper leans on hardest (by quoted weight) and say which were left out |
| The checker refuses | Fix the graph and re-run, up to 3 repair passes; then stop with the violations quoted in `owed` |
| A claim has no passage to quote | The node does not exist; a quoteless node is a drawing |

## Measure before you assert

Never write a node whose quote was not read in the same pass from the path
its evidence names. An invented quote sounds like a finding and gets acted
on like one.
