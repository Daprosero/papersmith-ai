"""Declares the experiment this benchmark package runs.

The scaffold step copies this file in once, verbatim, and substitutes nothing
into it — every value below is prefilled empty, and stays that way until a
person fills it in as the work happens.

Each of the seven blocks is prefilled empty on purpose, and only at this level.
Emptiness at the block level is unambiguous: no repository ever means "I
measured that `distribution` is empty" before a single shard has run. One
level down that stops being true — a replication run can measure that
`perEnvironment` is genuinely `[]`, and a template that had already written
`[]` there would be indistinguishable from that measurement. So the shape of
what belongs inside each block is described in a comment beside it, never
written as a value, and nothing here invents a value for `arms`, `search`,
`report` or `distribution` — those are read off the work as it happens, not
guessed at scaffold time.
"""

__benchmark__ = {
    # The managed revision this declaration is bound to, e.g. "r01.md" — a
    # filename under proposals/, asked for by the flow, never invented here.
    "revision": "",

    # What kind of prediction the protocol assumes, over which statistical
    # unit, by which metric and in which direction it is judged, e.g.:
    #     "premises": {
    #         "prediction": "a class label per subject",
    #         "statisticalUnit": "subject",
    #         "metric": "balancedAccuracy",
    #         "direction": "higher",
    #     }
    "premises": {},

    # One entry per arm, naming the sections of the proposal it exercises,
    # e.g.:
    #     "arms": {
    #         "baseline": {"sections": ["3.1"]},
    #         "proposed": {"sections": ["3.1", "3.4"]},
    #     }
    "arms": {},

    # What a declared search has to say about itself before its chosen value
    # means anything, e.g.:
    #     "search": {
    #         "what": "the regularization weight",
    #         "requiredScale": {"epochs": 20, "seeds": 3},
    #         "role": "validation split",
    #         "tieRule": "smallest value within one standard error of the best",
    #     }
    #
    # One further key is OPTIONAL and asked of nobody: `currentWhen`, a
    # dotted path into the record's own file naming where it wrote down the
    # identity of the code that produced it, e.g.:
    #     "currentWhen": "evidence.sourcesDigest"
    # `distribution.currentWhen`'s own idiom, one level up from a shard.
    # Declare it and a found record only counts as evidence while the value
    # there still matches the code as it stands; a record left behind by
    # code this repository has moved past reads as unmeasured rather than as
    # a rung reached. Leave it out -- the default -- and a found record is
    # trusted on arrival alone, exactly as before this key existed. The
    # forge never guesses the field, the same way it never guesses which
    # measurements are poolable: you name it, and it only compares.
    "search": {},

    # Which functions render tables and figures, which produce conclusions,
    # and which way each measured dimension wins, e.g.:
    #     "report": {
    #         "renderers": ["tables.render"],
    #         "conclusions": ["tables.conclusion"],
    #         "figures": ["figures.curves"],
    #         "dimensions": {"accuracy": "higher", "seconds": "lower"},
    #     }
    "report": {},

    # What a run split across shards has to say about itself: the axis a
    # shard is a subset of, and which measurements are poolable, measured
    # per environment, vary per run, or must agree identically across every
    # shard, e.g.:
    #     "distribution": {
    #         "axis": "seed",
    #         "poolable": ["accuracy"],
    #         "perEnvironment": [],
    #         "perRun": [],
    #         "identicalAcrossShards": ["datasetSize"],
    #     }
    #
    # One further key is OPTIONAL and asked of nobody: `currentWhen`, a
    # dotted path into a shard's own `shard.json` stamp naming where that
    # shard wrote down the identity of the code that produced it, e.g.:
    #     "currentWhen": "evidence.sourcesDigest"
    # Declare it and a returned shard only counts as evidence while the
    # value there still matches the code as it stands; a shard that arrived
    # from code this repository has moved past reads as unmeasured rather
    # than as a step reached. Leave it out -- the default -- and a shard is
    # trusted on arrival alone, exactly as before this key existed. The
    # forge never guesses the field, the same way it never guesses which
    # measurements are poolable: you name it, and it only compares.
    #
    # A second, sibling key is likewise OPTIONAL: `shardsRoot`, naming
    # where a split campaign's returned shards land, relative to this
    # repository's own root (an absolute path is honoured as given), e.g.:
    #     "shardsRoot": "campaign-001/shards"
    # Declare it once and every command that reads a position section --
    # not only the ones that carry their own `--shards` flag -- measures a
    # `@shard` witness against that same directory automatically; a `@shard`
    # item ticked on real evidence stays checkable everywhere, not only at
    # the one command that was told where to look for it. An explicit
    # `--shards <dir>`, where the command accepts one, still overrides this
    # for that single invocation. Leave it out -- the default -- and a
    # command with no `--shards` flag of its own reads a `@shard` witness as
    # unmeasured, exactly as before this key existed; the forge never
    # invents a directory a repository never named.
    "distribution": {},

    # The dotted module and function that actually pull the target's runtime
    # in — the same two values `generate-job --run-module`/`--run-function`
    # already require, so nothing new is asked for. `probe`'s harness
    # resolution and `introspect`'s liveness check both read this rather than
    # assuming a filename of the forge's own choosing, e.g.:
    #     "entry": {
    #         "module": "Example_Method_Benchmark.benchmark",
    #         "function": "run",
    #     }
    "entry": {"module": "", "function": ""},
}

# The ordered ladder of rungs a position-section step can reach, entirely in
# this repository's own words -- the forge holds no rung name of its own,
# only the arithmetic that compares two of these names by position (see
# `impl_position.level_index`). A step earns a rung by naming this file's
# own ladder explicitly on its witness (`` `@rehearsal:level <job>` `` in
# `AGREED.md`'s position section); a step with no `:level` marker is
# two-state and never reads this list at all. Left empty until named -- a
# repository whose position items are entirely two-state needs no ladder
# here, and one is never invented on its behalf. A second, independent
# top-level literal, held apart from `__benchmark__` above: see
# `resolve_levels_declaration`'s own docstring for why.
#
# Example (a repository with no remote service at all still has a ladder):
#     __levels__ = ["local", "cluster"]
__levels__: list = []

# A callable this repository's own code can run, isolated, under this
# repository's own venv -- named and resolved statically by the forge
# (module + function, never imported here), then imported and called inside
# the target's own interpreter, never the forge's. A second, independent
# top-level literal, held apart from `__benchmark__` for the identical
# reason `__levels__` is: see `resolve_steps_declaration`'s own docstring.
# Left empty until a step exists -- a repository with nothing local to run
# in isolation needs none, and one is never invented on its behalf.
#
# Example:
#     __steps__ = {
#         "verification": {
#             "module": "Example_Method_Benchmark.steps",
#             "function": "run_verification",
#         },
#     }
__steps__: dict = {}

# A target-chosen name mapped to the record it addresses -- a leveled
# `@record:level <name>` witness in AGREED.md's position section reaches
# exactly one entry here, deriving its rung through the identical arithmetic
# the `search` block's own bare `@record:level` already uses
# (`impl_position._record_scale_level`). A third, independent top-level
# literal, held apart from `__benchmark__` for the identical reason
# `__levels__`/`__steps__` are: see `resolve_records_declaration`'s own
# docstring. Left empty until a record is named -- a repository whose
# leveled `@record` witness stays the bare, operand-less form needs no
# entry here, and one is never invented on its behalf.
#
# Example:
#     __records__ = {
#         "main": {
#             "path": "product/results.json",
#             "requiredScale": {"seeds": 3},
#         },
#     }
__records__: dict = {}
