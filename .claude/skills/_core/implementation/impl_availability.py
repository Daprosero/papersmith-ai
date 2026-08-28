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


def launch_available(*, status: str, unbacked: list, sequence: list,
                     ready: bool | None, job: str) -> dict:
    """Whether a launch may proceed for `job`, and why not when it may not.

    `status`, `unbacked` and `sequence` are a position read's own three
    fields, passed through unchanged by whichever caller already computed
    them once. `ready` is that same caller's own readiness measurement for
    `job` -- `True`, `False`, or `None` when nothing has measured it yet;
    only `True` counts as ready, so a caller that forgets to distinguish
    "measured and failing" from "never measured at all" cannot accidentally
    widen this rule by passing a `False` where a `None` belongs.

    Returns `{"available": bool, "code": str | None, "facts": dict}`.
    `code` is one of `POSITION_ABSENT`, `POSITION_STALE`,
    `POSITION_UNBACKED`, `NOT_READY`, `SEQUENCE_NOT_REACHED`, checked in
    that order -- the same order one caller's own refusal ladder already
    checked them in before this rule existed, preserved here so neither
    caller's answer moves. `facts` carries whichever ordinals a caller's
    own message needs to quote; it is empty wherever no caller needs one.
    """
    if status == "absent":
        return {"available": False, "code": "POSITION_ABSENT", "facts": {}}
    if status == "stale":
        return {"available": False, "code": "POSITION_STALE", "facts": {}}
    if unbacked:
        return {
            "available": False, "code": "POSITION_UNBACKED",
            "facts": {"unbackedOrdinals": [item["ordinal"] for item in unbacked]},
        }
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
