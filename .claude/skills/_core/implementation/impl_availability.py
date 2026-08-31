"""One pure rule for whether a launch may proceed, shared by two callers.

Two commands ask the identical question about the identical facts: may a
launch proceed for this job, given the position ladder's current state and
its readiness measurement? Before this module existed, the answer lived
inside one command's own refusal ladder, and a second command computing its
own version of the same five checks is exactly how the two would quietly
drift apart from each other -- one accepting a launch the other refuses on
identical facts, discovered only when somebody compared them by hand.

This module answers `available: bool` and, when the answer is `False`,
which of five reasons it is -- nothing more. It never raises, and it never
composes a sentence a caller reads aloud: a launch verb's own prose names
its sibling commands and their own vocabulary, and this module is shared by
more than one such verb, so it may not commit to either one's words. A
caller that must refuse loudly wraps this verdict in whatever exception
shape it already raises; a caller that must merely omit an option from a
menu reads `available` alone and never raises anything at all.

Every fact this rule needs arrives as a keyword argument, already computed
by whichever caller is asking. This module opens no file, reads no
argument list, and knows nothing about where a position ledger lives or
what a caller's own flags are spelled -- that is layout, and layout belongs
one level up, in the command that has a directory to walk.
"""
from __future__ import annotations


def position_honest(*, status: str, unbacked: list, disagreements: list,
                    shards_declared: bool) -> dict:
    """Whether the position section, as recorded, says only what was
    measured -- the honesty prefix both `launch_available` (below) and a
    caller that never asks about readiness at all share, so neither one
    computes its own version of the identical four questions.

    `status`, `unbacked` and `disagreements` are a position read's own
    fields, passed through unchanged by whichever caller already computed
    them once. `unbacked` and `disagreements` carry no default: a caller
    that forgets one fails the call itself, loudly, rather than being read
    as an empty list and letting a contradicted or an unmeasured item
    through as if it agreed.

    `shards_declared` also carries no default. It answers one question
    only: did THIS invocation resolve any directory at all to measure a
    `@shard` witness against -- an explicit override, or the repository's
    own declared location? A ticked `@shard` item that stays unmeasured
    because nothing ever named where its evidence lives is a different
    fact from one whose declared location was consulted and still came back
    silent, and the two must not read as the identical claim: the first is
    "nobody was told where to look", the second is "somebody looked, and
    found nothing that speaks for this mark". Folding them into one code
    would keep asserting the general one is true even for a target that has
    since named its shard directory correctly and simply never re-measured.

    Returns `{"honest": bool, "code": str | None, "facts": dict}`. `code`
    is one of `POSITION_ABSENT`, `POSITION_STALE`, `POSITION_UNBACKED`,
    `POSITION_SHARDS_UNDECLARED`, `POSITION_DISAGREES`, checked in that
    order. `POSITION_SHARDS_UNDECLARED` only ever fires for a ticked
    `@shard` item whose unbacked-ness is fully explained by
    `shards_declared` being false; any other unbacked item -- of any
    witness kind, `@shard` included, once a location was actually consulted
    -- still reads `POSITION_UNBACKED`, checked first, exactly as before
    this code existed. `facts` carries whichever ordinals a caller's own
    message needs to quote; it is empty wherever no caller needs one.
    """
    if status == "absent":
        return {"honest": False, "code": "POSITION_ABSENT", "facts": {}}
    if status == "stale":
        return {"honest": False, "code": "POSITION_STALE", "facts": {}}
    undeclared = ([item for item in unbacked if item["witness"]["kind"] == "shard"]
                 if not shards_declared else [])
    real_unbacked = [item for item in unbacked if item not in undeclared]
    if real_unbacked:
        return {
            "honest": False, "code": "POSITION_UNBACKED",
            "facts": {"unbackedOrdinals": [item["ordinal"] for item in real_unbacked]},
        }
    if undeclared:
        return {
            "honest": False, "code": "POSITION_SHARDS_UNDECLARED",
            "facts": {"undeclaredOrdinals": [item["ordinal"] for item in undeclared]},
        }
    if disagreements:
        return {
            "honest": False, "code": "POSITION_DISAGREES",
            "facts": {"disagreeingOrdinals": [item["ordinal"] for item in disagreements]},
        }
    return {"honest": True, "code": None, "facts": {}}


def launch_available(*, status: str, unbacked: list, disagreements: list,
                     sequence: list, ready: bool | None, job: str,
                     shards_declared: bool) -> dict:
    """Whether a launch may proceed for `job`, and why not when it may not.

    `status`, `unbacked`, `disagreements`, `shards_declared` and `sequence`
    are a position read's own fields, passed through unchanged by whichever
    caller already computed them once. `ready` is that same caller's own
    readiness measurement for `job` -- `True`, `False`, or `None` when
    nothing has measured it yet; only `True` counts as ready, so a caller
    that forgets to distinguish "measured and failing" from "never measured
    at all" cannot accidentally widen this rule by passing a `False` where
    a `None` belongs.

    `disagreements` names every item whose recorded mark contradicts its
    own fresh re-measurement -- ticked but not actually reached, or the
    reverse. It carries no default: a caller that forgets to pass it fails
    the call itself, loudly, rather than being read as an empty list and
    letting a contradicted item through as if it agreed. Two callers ask
    this one rule the identical question over the identical facts, and a
    forgotten keyword is exactly the kind of drift this module exists to
    make impossible between them.

    The first four questions -- is there a position at all, is it current,
    does every tick say only what was measured, does every measurement
    agree with its mark -- are answered by `position_honest` above, called
    first and unchanged in what it checks; this function only continues
    past it. `position_honest`'s own `shards_declared` doctrine applies
    here identically: see that function's docstring for why a ticked
    `@shard` item with nowhere declared to look is a different fact from
    one whose declared location simply had nothing to report.

    Returns `{"available": bool, "code": str | None, "facts": dict}`.
    `code` is one of `POSITION_ABSENT`, `POSITION_STALE`,
    `POSITION_UNBACKED`, `POSITION_SHARDS_UNDECLARED`, `POSITION_DISAGREES`,
    `NOT_READY`, `SEQUENCE_NOT_REACHED`, checked in that order -- the same
    order one caller's own refusal ladder already checked the first five
    (now six) in before this rule existed, preserved here so neither
    caller's answer moves. `facts` carries whichever ordinals a caller's
    own message needs to quote; it is empty wherever no caller needs one.
    """
    honesty = position_honest(status=status, unbacked=unbacked,
                              disagreements=disagreements,
                              shards_declared=shards_declared)
    if not honesty["honest"]:
        return {"available": False, "code": honesty["code"], "facts": honesty["facts"]}
    if ready is not True:
        return {"available": False, "code": "NOT_READY", "facts": {}}

    job_item = next(
        (item for item in sequence
         if item["witness"]["kind"] == "rehearsal"
         and item["witness"]["operand"] == job),
        None)
    if job_item is None:
        return {
            "available": False, "code": "SEQUENCE_NOT_REACHED",
            "facts": {"reason": "no_witness"},
        }
    earlier_open = [item["ordinal"] for item in sequence
                    if item["ordinal"] < job_item["ordinal"] and item["mark"] != "x"]
    if earlier_open:
        return {
            "available": False, "code": "SEQUENCE_NOT_REACHED",
            "facts": {"reason": "earlier_open",
                      "earliestOpenOrdinal": min(earlier_open),
                      "jobOrdinal": job_item["ordinal"]},
        }
    return {"available": True, "code": None,
            "facts": {"jobOrdinal": job_item["ordinal"]}}
