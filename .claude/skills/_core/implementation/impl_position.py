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
_BLOCK_OPEN_RE = re.compile(
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
#: decides malformed.
_WITNESS_TOKEN_RE = re.compile(r"`@[a-z]+(?: [^`]+)?`")

#: The one true witness: backticked, anchored to end-of-line so item prose is
#: never scanned for a stray `@`. An operand may carry slashes and dots
#: (`some/dir/thing.ipynb`) without needing its own escaping, because the
#: backtick is the only character the grammar treats as a delimiter. The example
#: is deliberately not a real layout name: this module is caller-agnostic, and a
#: comment naming one of the caller's own directories teaches the next reader
#: that the core knows a layout it must always be handed.
WITNESS_RE = re.compile(r"`@(?P<kind>[a-z]+)(?: (?P<operand>[^`]+))?`\s*$")


def locate_block(data: bytes) -> dict | None:
    """Find the position block's byte span in `data`, or say there is none.

    `None` is `absent` — a target whose flow never reached a gate has nothing
    to locate, and that is a state, not a search that failed (the same
    doctrine `agreements_state` states for a repository with no checklist at
    all). More than one opener is never resolved by picking the first: a
    delimiter this module owns appearing twice is an ambiguous document, the
    stricter rule adopted from `proposal-workspace.ts:2488-2501` over the
    first-occurrence rule `lifecycle-service.ts:24-35` uses for text the tool
    does not own.
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
    if header is None:
        raise Refused(
            "POSITION_BLOCK_MALFORMED",
            "the `<!-- position ... -->` opener does not carry revision, "
            "sha256, derivedAt and session in that order.")
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
            "witness": {"kind": kind, "operand": witness_match.group("operand")},
        })
    return items


def _derive_record(evidence: dict) -> tuple[bool | None, str]:
    """`@record` ticks against `search_state()`'s own `recordFound`/`scaleSatisfied`.

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
    """`@notebook <path>` ticks against `notebooks_state()`'s per-report state.

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
    """`@rehearsal <jobName>` ticks against `remote_execution_jobs_state()["smokeReady"]`.

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
    """`@shard <id>` ticks against `verify --shards`'s `shardsArrived`.

    `evidence["shardsArrived"]` is `None` whenever this invocation carries no
    shard evidence at all — `probe` always, and `verify` without `--shards` —
    and `None` here means `unmeasured`, never `False`: the shard may well have
    arrived, this invocation simply was not told to look.
    """
    measured_by = "distribution.shardsArrived"
    arrived = evidence.get("shardsArrived")
    if not operand or arrived is None:
        return None, measured_by
    return operand in arrived, measured_by


_DERIVERS = {
    "notebook": _derive_notebook,
    "rehearsal": _derive_rehearsal,
    "shard": _derive_shard,
}


def derive(items: list[dict], evidence: dict) -> list[dict]:
    """The measured verdict for every item's witness, and nothing else.

    Three-valued per item: `True`/`False` when the evidence class actually
    answers, `None` ("unmeasured") when this invocation's evidence dict
    carries no answer for that witness at all. `None` is never folded into
    `False`: a caller that writes marks back to disk (`splice`'s callers) must
    leave an unmeasured item's byte exactly as found, because untying a step
    that already ran only because this invocation could not check it would be
    a false negative dressed as a measurement — the same rule `_record_scale`
    already applies by returning `{}` rather than guessing.

    Pure: no I/O. `evidence` is a plain dict of already-computed states, so
    two callers (`verify`, `probe`) hand this the same shape and get the same
    answer without either one importing the other's read path.
    """
    results = []
    for item in items:
        witness = item["witness"]
        kind, operand = witness["kind"], witness["operand"]
        if kind == "record":
            derived, measured_by = _derive_record(evidence)
        else:
            derived, measured_by = _DERIVERS[kind](evidence, operand)
        disagrees = derived is not None and derived != (item["mark"] == "x")
        results.append({
            "derived": derived,
            "measuredBy": measured_by,
            "disagrees": disagrees,
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
        f"session={header['session']} -->"
    ]
    for item in items:
        witness = item["witness"]
        operand = witness.get("operand")
        token = f"`@{witness['kind']} {operand}`" if operand else f"`@{witness['kind']}`"
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
