from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from impl_refusals import Refused

#: The section's delimiters. Both are HTML comments — neither starts with
#: `[-*]`, so `BULLET_LINE`/`AGREEMENT_LINE` (implementation_cli.py:149,155)
#: never mistake either one for a checklist item, and the position section can
#: sit inside a hand-curated AGREED.md without inflating `agreements_state`'s
#: counts by a byte.
BLOCK_CLOSE = b"<!-- /position -->"

#: A loose opener, used only to COUNT how many blocks exist in the document.
#: Counting has to survive a header that is itself malformed in some other
#: way — undercounting here would let a second, broken block hide behind the
#: first one's well-formed refusal instead of raising its own.
_BLOCK_OPEN_MARKER = rb"<!--\s*position\b"

#: The one true opener: every header field, in this exact order. A match
#: whose start does not coincide with `_BLOCK_OPEN_MARKER`'s only hit means
#: the opener exists but its header does not parse — a malformed artifact,
#: not an absent one.
#:
#: `target` is new in the level-grammar revision (PR10, `the-position-
#: nobody-holds`): the ordered rung this pass is aiming at, in the target's
#: own vocabulary (see `derive`'s docstring). A block written by the prior,
#: boolean-only grammar carries no `target=` field, so its header no longer
#: matches this pattern at all — **refused, not migrated, not silently
#: reinterpreted**. That is the deliberate choice: a bare byte-shift of an
#: old block's marks onto a new tick meaning ("reached this pass's rung")
#: would be asserting a rung nobody ever measured. The refusal is the same
#: `POSITION_BLOCK_MALFORMED` class the opener already raised for any other
#: unparsable header, and `position --reconcile --target-level <level>`
#: (implementation_cli.py) is the migration path: a fresh header, sequence
#: items preserved by witness identity, ticks re-derived from scratch under
#: the new grammar.
_BLOCK_OPEN_RE = re.compile(
    rb"<!--\s*position\s+revision=(?P<revision>\S+)\s+"
    rb"sha256=(?P<sha256>[0-9a-f]{64})\s+derivedAt=(?P<derivedAt>\S+)\s+"
    rb"session=(?P<session>\S+)\s+target=(?P<target>\S+)\s*-->"
)

#: The exact opener the grammar's first revision wrote, kept only so
#: `locate_block(..., allow_legacy=True)` can tell "an old block, migratable"
#: apart from "a document neither grammar recognizes". Never matched unless
#: the caller opts in: `cmd_position` is the one place migration happens, and
#: `verify`/`probe`/`position_state`'s read side never passes `allow_legacy`,
#: so an unmigrated block still exits 2 for them exactly as documented.
_LEGACY_BLOCK_OPEN_RE = re.compile(
    rb"<!--\s*position\s+revision=(?P<revision>\S+)\s+"
    rb"sha256=(?P<sha256>[0-9a-f]{64})\s+derivedAt=(?P<derivedAt>\S+)\s+"
    rb"session=(?P<session>\S+)\s*-->"
)

#: A sequence item line: `- [x] 1. <prose ending in a witness token>`. Modeled
#: on `AGREEMENT_LINE` (implementation_cli.py:149), with an ordinal added: the
#: sequence's numbering is part of what a human reads and is kept as its own
#: field so a renumbered sequence never has to touch the item's prose.
ITEM_LINE = re.compile(r"^\s*-\s*\[(?P<mark>[ xX])\]\s*(?P<ordinal>\d+)\.\s*(?P<text>.+)$")

#: The four evidence classes named by the domain — forge words, identical for
#: every target and learned from none of them. See `_record_scale`'s
#: docstring (implementation_cli.py:309-341) for why the forge recognizes no
#: target's vocabulary; this is the same discipline one level up.
WITNESS_KINDS = frozenset({"record", "notebook", "rehearsal", "shard"})

#: Every witness-shaped token on a line, used only to COUNT them. Exactly one
#: is required per item; a prose sentence that happens to mention another
#: backticked `@word` is exactly the false positive `BULLET_LINE` already had
#: to guard against one file over, so the count — not a bare search — is what
#: decides malformed. `(?::level)?` mirrors `WITNESS_RE`'s own optional
#: leveled marker so a marked token is still counted as exactly one.
_WITNESS_TOKEN_RE = re.compile(r"`@[a-z]+(?::level)?(?: [^`]+)?`")

#: The one true witness: backticked, anchored to end-of-line so item prose is
#: never scanned for a stray `@`. An operand may carry slashes and dots
#: (`some/dir/thing.ipynb`) without needing its own escaping, because the
#: backtick is the only character the grammar treats as a delimiter. The example
#: is deliberately not a real layout name: this module is caller-agnostic, and a
#: comment naming one of the caller's own directories teaches the next reader
#: that the core knows a layout it must always be handed.
#:
#: `:level` (PR10) is the grammar's way for a single item to opt INTO the
#: ordered ladder. **Omitted, an item is two-state** — satisfied or not, with
#: nothing in between — exactly the grammar's first revision, unchanged, so
#: every block written before PR10's ordered-level revision keeps meaning
#: exactly what it always meant once migrated onto the new header (see
#: `_BLOCK_OPEN_RE`'s docstring for why the header itself still refuses an
#: unmigrated block). Two-state is the default because that is what a
#: witness already meant before this revision; a step earns a rung by saying
#: so, explicitly, right where a reader already looks — never inferred from
#: its kind, because two targets may both write a `@notebook` witness and
#: mean different things by it (one step reads a record tied to a rung,
#: another is a local check that only ever holds or does not). The forge
#: does not decide which a kind means; the artifact declares it.
WITNESS_RE = re.compile(
    r"`@(?P<kind>[a-z]+)(?P<leveled>:level)?(?: (?P<operand>[^`]+))?`\s*$")


def locate_block(data: bytes, allow_legacy: bool = False) -> dict | None:
    """Find the position block's byte span in `data`, or say there is none.

    `None` is `absent` — a target whose flow never reached a gate has nothing
    to locate, and that is a state, not a search that failed (the same
    doctrine `agreements_state` states for a repository with no checklist at
    all). More than one opener is never resolved by picking the first: a
    delimiter this module owns appearing twice is an ambiguous document, the
    stricter rule adopted from `proposal-workspace.ts:2488-2501` over the
    first-occurrence rule `lifecycle-service.ts:24-35` uses for text the tool
    does not own.

    `allow_legacy=True` (PR10) additionally recognizes the exact header the
    grammar's first revision wrote (no `target=` field) and returns it with
    `"target": None, "legacy": True` instead of refusing — the one admission
    that makes migration reachable at all: `cmd_position` has to be able to
    *see* an old block before it can rewrite it. Every other caller (`verify`,
    `probe`, `position_state`'s read side) passes the default `False` and
    keeps refusing an unmigrated block exactly as documented — reading was
    never where migration was promised to happen, only `position` was.
    """
    markers = [m.start() for m in re.finditer(_BLOCK_OPEN_MARKER, data)]
    if not markers:
        return None
    if len(markers) > 1:
        raise Refused(
            "POSITION_BLOCK_NOT_UNIQUE",
            f"{len(markers)} `<!-- position ... -->` openers found in one "
            "document; a delimiter this module owns must occur exactly once.")

    header = _BLOCK_OPEN_RE.match(data, markers[0])
    legacy = False
    if header is None and allow_legacy:
        header = _LEGACY_BLOCK_OPEN_RE.match(data, markers[0])
        legacy = header is not None
    if header is None:
        raise Refused(
            "POSITION_BLOCK_MALFORMED",
            "the `<!-- position ... -->` opener does not carry revision, "
            "sha256, derivedAt, session and target in that order. A block "
            "written by the prior boolean-only grammar has no `target=` "
            "field and is refused here, not silently reinterpreted -- see "
            "`_BLOCK_OPEN_RE`'s docstring for the migration path.")
    close = data.find(BLOCK_CLOSE, header.end())
    if close == -1:
        raise Refused(
            "POSITION_BLOCK_MALFORMED",
            "no matching `<!-- /position -->` closer was found for the opener.")

    return {
        "start": header.start(),
        "end": close + len(BLOCK_CLOSE),
        "body": data[header.end():close].decode("utf-8"),
        "revision": header.group("revision").decode("ascii"),
        "revisionSha256": header.group("sha256").decode("ascii"),
        "derivedAt": header.group("derivedAt").decode("ascii"),
        "session": header.group("session").decode("ascii"),
        "target": None if legacy else header.group("target").decode("ascii"),
        "legacy": legacy,
    }


def parse_items(body: str) -> list[dict]:
    """Every sequence item in a located block's body, witness resolved.

    Raises rather than reports: this section is entirely tool-owned, so a
    line that does not parse, an item without exactly one witness, or a
    witness naming a kind this module does not recognize are all the same
    class `MALFORMED_FINDINGS` already is for `read_findings`
    (implementation_cli.py:2151) — a broken artifact, not a not-yet-ready
    target. `main()`'s existing `except Refused` turns this into exit 2 from
    any command that reads a position block, `verify`/`probe` included, with
    no extra wiring at either call site.
    """
    items: list[dict] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = ITEM_LINE.match(line)
        if not match:
            raise Refused(
                "POSITION_ITEM_MALFORMED",
                f"line in the position block does not parse as a sequence "
                f"item: {line!r}")
        ordinal = int(match.group("ordinal"))
        mark = "x" if match.group("mark") in "xX" else " "
        text = match.group("text")

        tokens = _WITNESS_TOKEN_RE.findall(text)
        witness_match = WITNESS_RE.search(text)
        if len(tokens) != 1 or witness_match is None:
            raise Refused(
                "POSITION_ITEM_WITHOUT_WITNESS",
                f"item {ordinal} must carry exactly one witness token "
                f"anchored to end of line; found {len(tokens)}: {text!r}")

        kind = witness_match.group("kind")
        if kind not in WITNESS_KINDS:
            raise Refused(
                "POSITION_WITNESS_UNKNOWN_KIND",
                f"item {ordinal} names unknown witness kind {kind!r}; "
                f"expected one of {sorted(WITNESS_KINDS)}")

        items.append({
            "ordinal": ordinal,
            "mark": mark,
            "text": text[:witness_match.start()].rstrip(),
            "witness": {
                "kind": kind,
                "operand": witness_match.group("operand"),
                # See `WITNESS_RE`'s docstring: a per-item declaration, not a
                # per-kind one. Absent the `:level` marker, an item is
                # two-state (the default, unchanged from the grammar's first
                # revision); marked, `derive` reports which declared rung it
                # reaches instead of a bare pass/fail.
                "twostate": witness_match.group("leveled") is None,
            },
        })
    return items


def _derive_record(evidence: dict) -> tuple[bool | None, str]:
    """`@record` (two-state, the default) ticks against `search_state()`'s own `recordFound`/`scaleSatisfied`.

    `evidence["search"]` is that function's return, verbatim.
    `evidence["requiredScale"]` is the caller's own `declared_required_scale(search)`
    — computed once by the caller rather than re-derived here, so this stays a
    plain dict reader and never learns `search_state`'s internal shape.
    """
    search = evidence.get("search")
    if not isinstance(search, dict) or "recordFound" not in search:
        return None, "search.recordFound"
    found = search.get("recordFound")
    if found is None:
        return None, "search.recordFound"
    if found is False:
        return False, "search.recordFound"
    if evidence.get("requiredScale"):
        return search.get("scaleSatisfied") is True, "search.scaleSatisfied"
    return True, "search.recordFound"


def _derive_notebook(evidence: dict, operand: str | None) -> tuple[bool | None, str]:
    """`@notebook <path>` (two-state, the default) ticks against `notebooks_state()`'s per-report state.

    `operand` is matched against `report["notebook"]` both exactly and by
    suffix (`.../<operand>`), because `notebooks_state` stamps a path relative
    to the target while the witness names only the tail relative to the
    product — the same pair the design's grammar table declares. Neither
    directory is named here: the caller owns its layout and hands it in, and a
    core that spelled one out would be holding a fact it is supposed to receive.
    """
    measured_by = f"notebooks.reports[{operand}].sourcesMatch"
    notebooks = evidence.get("notebooks")
    if not operand or not isinstance(notebooks, dict):
        return None, measured_by
    report = next(
        (r for r in notebooks.get("reports", [])
         if r.get("notebook") == operand
         or r.get("notebook", "").endswith(f"/{operand}")),
        None)
    if report is None:
        return None, measured_by
    return (report.get("status") == "executed"
            and report.get("sourcesMatch") is True), measured_by


def _derive_rehearsal(evidence: dict, operand: str | None) -> tuple[bool | None, str]:
    """`@rehearsal <jobName>` (two-state, the default) ticks against `remote_execution_jobs_state()["smokeReady"]`.

    The un-forgeable half of the whole change (design §4.3): `smokeReady` is
    only ever `True` once a rehearsal actually ran and was recorded at the
    job's current pin, so a hand-edited mark can never make this branch agree
    with a rehearsal that did not happen.
    """
    measured_by = f"remoteExecution.smokeReady[{operand}]"
    smoke_ready = evidence.get("smokeReady")
    if not operand or not isinstance(smoke_ready, dict) or operand not in smoke_ready:
        return None, measured_by
    return smoke_ready.get(operand) is True, measured_by


def _derive_shard(evidence: dict, operand: str | None) -> tuple[bool | None, str]:
    """`@shard <id>` (two-state, the default) ticks against `verify --shards`'s `shardsArrived`.

    `evidence["shardsArrived"]` is `None` whenever this invocation carries no
    shard evidence at all — `probe` always, and `verify` without `--shards` —
    and `None` here means `unmeasured`, never `False`: the shard may well have
    arrived, this invocation simply was not told to look.

    **Arrival alone is not evidence that a shard reports on the code running
    now.** A shard folder is a file left behind by whatever ran; nothing about
    its presence says which code produced it, and reading a rung off it is the
    same unbacked attribution `_derive_notebook_level` already refuses ("we
    have not looked with current eyes"). `evidence["shardsCurrent"]` is the
    subset of arrived shards whose own stamp says otherwise — measured by the
    caller, which is the only layer that knows both the stamp field a target
    declared and the digest of the code as it stands. An arrived shard that is
    NOT in that subset reads `None` (unmeasured), never `False`: the shard
    exists, we simply cannot say it speaks for this code.

    **`shardsCurrent is None` restores the behaviour that predates it, exactly.**
    A target that never declared which stamp field carries its code identity
    has said nothing this could check, and inventing a field name on its behalf
    is the one thing the forge must not do — so arrival alone decides, as it
    always did, and no target that never opted in changes verdict.
    """
    arrived = evidence.get("shardsArrived")
    current = evidence.get("shardsCurrent")
    measured_by = ("distribution.shardsArrived" if current is None
                   else "distribution.shardsArrived+shardsCurrent")
    if not operand or arrived is None:
        return None, measured_by
    if operand not in arrived:
        return False, measured_by
    if current is not None and operand not in current:
        return None, measured_by
    return True, measured_by


_DERIVERS = {
    "notebook": _derive_notebook,
    "rehearsal": _derive_rehearsal,
    "shard": _derive_shard,
}


def level_index(levels: list[str], level: str | None) -> int | None:
    """`level`'s position on the declared ladder, or `None` off it (unknown
    or `level is None`).

    This is the whole of what the forge knows about a ladder: an ordered
    list, and how to compare two positions in it. The names on that list are
    entirely the target's own vocabulary — this module holds none of its
    own, the same discipline `WITNESS_KINDS` already keeps for evidence
    classes one level up. A repository with a three-rung remote-execution
    ladder and one with none at all (`levels == []`) both run this same
    arithmetic; only the list differs.
    """
    if level is None:
        return None
    try:
        return levels.index(level)
    except ValueError:
        return None


def _record_scale_level(evidence: dict, levels: list[str]) -> tuple[str | None, str]:
    """The rung a record's own scale reaches, composed from exactly the two
    facts `search_state()` already computes — `recordFound` and, when a
    scale is declared, `scaleSatisfied` — never a new measurement.

    This is the mechanism behind PR10's motivating defect: a record found on
    disk but short of the declared scale (sixty runs beside a declared
    eighteen hundred) used to satisfy the same boolean `@record` witness a
    full record did. Composed as a rung instead, it reads as the *second*
    rung on a ladder with room for one, not the top — visible on the item
    itself, not something a reader has to already remember to doubt.

    - not found → the floor rung: nothing has run yet.
    - found, and either no scale is declared or the declared scale is met →
      the top rung: nothing further was asked of this record.
    - found, short of a declared scale → one rung under the top when the
      ladder has room for that distinction (three rungs or more); the floor
      otherwise — a two-rung ladder has nowhere honest to place "something
      ran, but not enough of it" except "not yet there".
    - `scaleSatisfied` itself unmeasured (a scale is declared but nothing
      could check it) → unmeasured, not guessed at.
    """
    measured_by = "search.recordFound+scaleSatisfied"
    if not levels:
        return None, measured_by
    search = evidence.get("search")
    if not isinstance(search, dict) or "recordFound" not in search:
        return None, measured_by
    found = search.get("recordFound")
    if found is None:
        return None, measured_by
    if found is False:
        return levels[0], measured_by
    if not evidence.get("requiredScale") or search.get("scaleSatisfied") is True:
        return levels[-1], measured_by
    if search.get("scaleSatisfied") is False:
        return levels[max(0, len(levels) - 2)], measured_by
    return None, measured_by


def _derive_notebook_level(
        evidence: dict, operand: str | None, levels: list[str]) -> tuple[str | None, str]:
    """`@notebook <path>` (leveled): the rung the record behind this report
    reaches — but only once the report itself is honestly current.

    A notebook that has not run, or whose sources no longer match, cannot
    attribute a rung to anything it printed: unmeasured, not the floor,
    because the fact is "we have not looked with current eyes", not "we
    looked and it has not started" — the distinction `derive`'s own
    docstring keeps for the same reason one level up. Once the report is
    current, its rung is the record's own (`_record_scale_level`): a report
    is only ever as trustworthy about scale as the record it read.
    """
    measured_by = f"notebooks.reports[{operand}].sourcesMatch+search.scaleSatisfied"
    notebooks = evidence.get("notebooks")
    if not operand or not isinstance(notebooks, dict):
        return None, measured_by
    report = next(
        (r for r in notebooks.get("reports", [])
         if r.get("notebook") == operand
         or r.get("notebook", "").endswith(f"/{operand}")),
        None)
    if report is None:
        return None, measured_by
    if not (report.get("status") == "executed" and report.get("sourcesMatch") is True):
        return None, measured_by
    level, _ = _record_scale_level(evidence, levels)
    return level, measured_by


def _derive_rehearsal_level(
        evidence: dict, operand: str | None, levels: list[str]) -> tuple[str | None, str]:
    """`@rehearsal <jobName>` (leveled): `smokeReady` is itself a two-valued
    fact (a rehearsal ran and passed, or it did not), so it can only ever
    place a job at the floor rung or the one just above it — reaching
    further than that is `@record`'s or `@shard`'s evidence to speak to, a
    rehearsal never claims full scale on its own.
    """
    measured_by = f"remoteExecution.smokeReady[{operand}]"
    if not levels:
        return None, measured_by
    smoke_ready = evidence.get("smokeReady")
    if not operand or not isinstance(smoke_ready, dict) or operand not in smoke_ready:
        return None, measured_by
    if smoke_ready.get(operand) is True:
        return levels[min(1, len(levels) - 1)], measured_by
    return levels[0], measured_by


def _derive_shard_level(
        evidence: dict, operand: str | None, levels: list[str]) -> tuple[str | None, str]:
    """`@shard <id>` (leveled): an arrived shard that reports on the code
    running now is full-scale evidence in its own right, so it places its
    item at the top rung; one that has not arrived, at the floor — both
    definite, because `shardsArrived` being present at all (not `None`)
    means this invocation was told to look.

    A shard that arrived but is not `evidence["shardsCurrent"]` reads
    `None` (unmeasured), never the floor, for the identical reason
    `_derive_notebook_level` gives: the fact is "we have not looked with
    current eyes", not "it has not started". And `shardsCurrent is None`
    — the target declared no way to tell — leaves arrival alone deciding,
    exactly as it did before that key existed. See `_derive_shard`'s own
    docstring for both halves in full.
    """
    arrived = evidence.get("shardsArrived")
    current = evidence.get("shardsCurrent")
    measured_by = ("distribution.shardsArrived" if current is None
                   else "distribution.shardsArrived+shardsCurrent")
    if not levels:
        return None, measured_by
    if not operand or arrived is None:
        return None, measured_by
    if operand not in arrived:
        return levels[0], measured_by
    if current is not None and operand not in current:
        return None, measured_by
    return levels[-1], measured_by


_LEVEL_DERIVERS = {
    "notebook": _derive_notebook_level,
    "rehearsal": _derive_rehearsal_level,
    "shard": _derive_shard_level,
}


def derive(items: list[dict], evidence: dict) -> list[dict]:
    """The measured verdict for every item's witness, and nothing else.

    **A level, not a bool (PR10) — except where an item declared itself
    two-state.** Per item, `derived` is:

    - for a two-state item (no `:level` marker, the default): `True`/`False`
      when the evidence class actually
      answers, `None` ("unmeasured") when it does not — unchanged from the
      grammar's first revision, because a two-state item has no rung to be
      assigned and never has one invented for it.
    - for a leveled item (the default): one of `evidence["levels"]`'s own
      names when the evidence resolves to a rung, `None` when it does not.
      **A leveled item is never assigned `False`; only `None` or one of the
      declared names.** `None` is never folded into the floor rung: "we did
      not look" and "it has not started" stay two different facts, the same
      rule `_record_scale` already keeps by returning `{}` rather than
      guessing.

    `unbacked` is the one asymmetry a blank box and a ticked box do not
    share. `disagrees` compares a mark against a measurement, so it is
    necessarily silent when there is no measurement — an `x` over an
    unmeasured witness contradicts nothing, because nothing was said. But
    the two marks are not equally honest there: a blank box over an
    unmeasured witness claims nothing and is exactly right to; a ticked one
    asserts a step was reached while the only thing that could confirm it
    was never looked at. Without this key those two items are byte-identical
    in every report the position produces, so the assertion nobody measured
    reads as the settled fact everybody did. `unbacked` is that, and only
    that: `satisfied is None and mark == "x"`. It is deliberately NOT folded
    into `disagrees` — a disagreement names a measurement that says
    otherwise, and there is none here to name.

    `satisfied` is the tick-worthy verdict every caller writing a mark
    should read, never `derived` directly: for a two-state item it is
    `derived` itself; for a leveled item it is whether `derived`'s rung is
    at or above `evidence["targetLevel"]` — the pass this call is deriving
    against — computed via `level_index` and `None` whenever either side is
    `None` or unknown. `disagrees` compares `satisfied` against the item's
    existing mark, not `derived`, so a two-state item and a leveled item are
    graded by the identical rule once `satisfied` exists.

    Pure: no I/O. `evidence` is a plain dict of already-computed states plus
    the declared ladder (`evidence["levels"]`, absent or `[]` for a target
    that names none) and this pass's own target (`evidence["targetLevel"]`),
    so two callers (`verify`, `probe`) hand this the same shape and get the
    same answer without either one importing the other's read path.
    """
    levels = evidence.get("levels") or []
    target_level = evidence.get("targetLevel")
    results = []
    for item in items:
        witness = item["witness"]
        kind, operand = witness["kind"], witness["operand"]
        # Two-state is the default when a hand-built item dict carries no
        # `twostate` key at all (`.get(..., True)`, not `.get(...)`), the
        # same default `WITNESS_RE`'s docstring states for the markdown
        # grammar itself -- a caller that never opted into levels keeps
        # getting exactly the boolean derivation it always got.
        twostate = witness.get("twostate", True)
        if twostate:
            if kind == "record":
                derived, measured_by = _derive_record(evidence)
            else:
                derived, measured_by = _DERIVERS[kind](evidence, operand)
            satisfied = derived
        else:
            if kind == "record":
                derived, measured_by = _record_scale_level(evidence, levels)
            else:
                derived, measured_by = _LEVEL_DERIVERS[kind](evidence, operand, levels)
            # `derived is None` must short-circuit straight to `satisfied =
            # None`: an `and`-chain that starts `derived_index is not None`
            # collapses to the bool `False` the moment that first condition
            # is `False`, which would silently turn "unmeasured" into a
            # definite "not satisfied" -- exactly the collapse this whole
            # revision exists to keep from happening.
            if derived is None:
                satisfied = None
            else:
                derived_index = level_index(levels, derived)
                target_index = level_index(levels, target_level)
                satisfied = (None if derived_index is None or target_index is None
                            else derived_index >= target_index)
        disagrees = satisfied is not None and satisfied != (item["mark"] == "x")
        # See the docstring: a tick over a witness nothing measured is an
        # assertion, and it has to be told apart from the blank box beside
        # it, which asserts nothing and is honest for it.
        unbacked = satisfied is None and item["mark"] == "x"
        results.append({
            "derived": derived,
            "twostate": twostate,
            "satisfied": satisfied,
            "measuredBy": measured_by,
            "disagrees": disagrees,
            "unbacked": unbacked,
        })
    return results


def render(header: dict, items: list[dict]) -> str:
    """The block's complete markdown text, opener through closer.

    The inverse of `locate_block` + `parse_items`: splicing this back in is
    how a refresh or an install writes. Item order, marks and text are the
    caller's; this only lays out the fixed grammar around them, so a caller
    that wants marks left untouched for an unmeasured witness passes items
    whose `mark` it never changed.
    """
    lines = [
        f"<!-- position revision={header['revision']} "
        f"sha256={header['revisionSha256']} derivedAt={header['derivedAt']} "
        f"session={header['session']} target={header['target']} -->"
    ]
    for item in items:
        witness = item["witness"]
        operand = witness.get("operand")
        suffix = "" if witness.get("twostate", True) else ":level"
        token = (f"`@{witness['kind']}{suffix} {operand}`" if operand
                else f"`@{witness['kind']}{suffix}`")
        lines.append(f"- [{item['mark']}] {item['ordinal']}. {item['text']} {token}")
    lines.append("<!-- /position -->")
    return "\n".join(lines) + "\n"


def splice(data: bytes, new_block: bytes, block: dict | None) -> bytes:
    """The document's complete new bytes, with only the located span replaced.

    Pure: slicing and concatenation on `bytes`, never `re.sub` or
    `str.replace`. Both interpret characters in a replacement argument —
    `re.sub` treats a leading backslash in the replacement as an escape
    (`\\t`, `\\g<0>`...) — and `AGREED.md` already carries `\\tag{}` and other
    backslash sequences the design cites (lines 197-261 of a real target).
    Slicing at the exact located offsets sidesteps replacement-string
    semantics entirely: `new_block`'s bytes are only ever concatenated, never
    interpreted.

    `block is None` means the document holds no position section yet: the new
    block is appended, preceded by exactly enough blank line(s) to separate it
    from whatever the document already ends with, and everything before that
    point — the file's other 90 hand-curated items, its `Reversed` section —
    is untouched down to the byte.
    """
    if block is None:
        if not data or data.endswith(b"\n\n"):
            return data + new_block
        if data.endswith(b"\n"):
            return data + b"\n" + new_block
        return data + b"\n\n" + new_block
    return data[:block["start"]] + new_block + data[block["end"]:]


def write_spliced(path: Path, data: bytes) -> None:
    """Write `data` to `path` by temp file + `os.replace`, same directory.

    Same-directory temp file so the replace is one filesystem rename rather
    than a cross-device copy, and so a crash mid-write never leaves the
    original truncated: the old file stays exactly as it was until the new
    one is fully written and renamed over it.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def read_events(path: Path) -> list[dict]:
    """Every event `.implementation/position.jsonl` holds, oldest first.

    Modeled on the remote-execution ledger's own fold
    (`_load_remote_execution_ledger`, implementation_cli.py:4826-4844): an
    absent file is zero events, not an error, because a target that never
    reached a gate has nothing appended yet. A line that fails to parse is
    skipped rather than raising — the ledger this mirrors already treats a
    corrupt line as silently absent evidence rather than a reason to refuse
    every read that follows it.
    """
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def append_event(path: Path, event: dict) -> None:
    """Append one JSON line to `.implementation/position.jsonl`, creating it.

    Append-only, on purpose: `remote-execution/SKILL.md`'s own rationale for
    its ledger ("Why append, not a status record") applies unchanged here — a
    lost append is detectable (the newest `gate` a caller expects is simply
    missing), and a lost in-place mutation is not.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True))
        handle.write("\n")
