"""Declares the experiment this benchmark package runs.

`materialize.py` writes this file once, verbatim, at scaffold time. It never
substitutes anything into it — every value below is prefilled empty, and stays
that way until a person fills it in as the work happens.

Each of the six blocks is prefilled empty on purpose, and only at this level.
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
    #         "requiredScale": 30,
    #         "role": "validation split",
    #         "tieRule": "smallest value within one standard error of the best",
    #     }
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
    "distribution": {},
}
