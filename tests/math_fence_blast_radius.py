"""The M1 measurement harness for the `$$...$$` display-fence blast radius
(design.md, Measurement M1, `the-tripwire-reaches-the-section-that-feeds-it`).

Deliberately not named `test_*.py` — like `paper_mutation.py` and
`forge_vocabulary.py`, this is a non-test helper module under `tests/` so
the configured discovery pattern never collects it as a suite of its own.
It is executable directly (`python tests/math_fence_blast_radius.py`) so
its output can be captured verbatim into the change's own blast-radius
report; no number in that report is ever authored by hand.

For every ordered pair `(styled, sample)` drawn from a text corpus, this
records:

    len(paper_style.normalize_tokens(styled))
    len(paper_leak.tripwire_spans(styled, [sample]))
    paper_leak.overlap_against_set(styled, [sample])

and can compare two such runs (an unmodified-tree "before" run against a
fixed-tree "after" run) to report exactly which files' normalized token
counts changed and which pairs' tripwire hit counts changed.
"""
from __future__ import annotations

import sys
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_style  # noqa: E402
import paper_leak  # noqa: E402

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "math_fence_corpus"

#: Directories an ambient sweep never descends into: this skill's own code,
#: this suite's own fixtures and modules, planning artifacts, and anything
#: version control or tooling keeps out of a fresh clone's working tree.
_AMBIENT_EXCLUDED_DIR_NAMES = frozenset({
    ".git", "node_modules", ".claude", "tests", "openspec", "sections", ".venv",
})


def load_corpus(directory: Path) -> dict[str, str]:
    """Every `.md` file directly under `directory`, keyed by filename, in a
    stable sorted order so a report's line order never depends on the
    filesystem's own directory-listing order."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(directory.glob("*.md"))
    }


def discover_ambient_markdown(forge_root: Path) -> dict[str, str]:
    """Whatever document-sourced `.md` this checkout happens to hold outside
    this skill's and this suite's own directories -- a fresh clone holds
    none of this, which is exactly why it is measured separately and never
    asserted (design.md, Decision A gate table, third row). Keyed by the
    path relative to `forge_root`, in a stable sorted order."""
    found: dict[str, str] = {}
    for path in sorted(forge_root.rglob("*.md")):
        relative = path.relative_to(forge_root)
        if any(part in _AMBIENT_EXCLUDED_DIR_NAMES for part in relative.parts[:-1]):
            continue
        try:
            found[str(relative)] = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return found


def run_m1(corpus: dict[str, str], *, pairwise: bool = True) -> dict:
    """M1 itself: per-file normalized token counts, and -- when `pairwise`
    is true -- per ordered pair `(styled, sample)` drawn from `corpus`, the
    tripwire hit count and the overlap measurement, both computed the exact
    way `check_tripwire` and `relative_overlap_holds` already compute them,
    never re-implemented here.

    `pairwise=False` measures only token counts. `tripwire_spans` and
    `overlap_against_set` are each an unbounded pairwise token scan; the
    committed fixture corpus is six short files, so the full O(pairs) sweep
    is cheap there, but an ambient corpus (task 0.4) can hold real documents
    tens of thousands of tokens long, where every pair costs a full scan --
    infeasible on this machine. The ambient run measures the ONE thing that
    is both cheap and answers the question the ambient sweep exists to ask:
    does this fix change the normalized token count of REAL content on
    disk. That is measured, not skipped; the pairwise half is skipped, and
    said so out loud, rather than silently forecast."""
    names = sorted(corpus)
    token_counts = {name: len(paper_style.normalize_tokens(text)) for name, text in corpus.items()}
    if not pairwise:
        return {"names": names, "token_counts": token_counts, "pair_hits": {}, "pair_overlap": {}}
    pair_hits: dict[tuple[str, str], int] = {}
    pair_overlap: dict[tuple[str, str], int] = {}
    for styled_name in names:
        styled_text = corpus[styled_name]
        for sample_name in names:
            samples = [{"reference": sample_name, "span": corpus[sample_name]}]
            pair_hits[(styled_name, sample_name)] = len(paper_leak.tripwire_spans(styled_text, samples))
            pair_overlap[(styled_name, sample_name)] = paper_leak.overlap_against_set(styled_text, samples)
    return {"names": names, "token_counts": token_counts, "pair_hits": pair_hits, "pair_overlap": pair_overlap}


def format_table(result: dict) -> str:
    names = result["names"]
    lines = ["Token counts (len(normalize_tokens(file))):"]
    for name in names:
        lines.append(f"  {name}: {result['token_counts'][name]}")
    if result["pair_hits"] or result["pair_overlap"]:
        lines.append("")
        lines.append(
            "Pair measurements (styled, sample) -> hits=len(tripwire_spans) overlap=overlap_against_set:"
        )
        for styled in names:
            for sample in names:
                hits = result["pair_hits"][(styled, sample)]
                overlap = result["pair_overlap"][(styled, sample)]
                lines.append(f"  ({styled}, {sample}) -> hits={hits} overlap={overlap}")
    return "\n".join(lines)


def diff_reports(before: dict, after: dict) -> str:
    """Names every file whose normalized token count changed and every pair
    whose tripwire hit count changed between two `run_m1` results over the
    IDENTICAL corpus (design.md, Measurement M1)."""
    names = before["names"]
    if names != after["names"]:
        raise AssertionError("diff_reports requires both runs over the identical corpus")
    lines = ["Token count changes:"]
    changed_files = [n for n in names if before["token_counts"][n] != after["token_counts"][n]]
    if not changed_files:
        lines.append("  none")
    for name in changed_files:
        lines.append(f"  {name}: {before['token_counts'][name]} -> {after['token_counts'][name]}")
    lines.append("")
    lines.append("Tripwire hit-count changes by pair:")
    changed_pairs = [
        (styled, sample) for styled in names for sample in names
        if before["pair_hits"][(styled, sample)] != after["pair_hits"][(styled, sample)]
    ]
    if not changed_pairs:
        lines.append("  none")
    for styled, sample in changed_pairs:
        lines.append(
            f"  ({styled}, {sample}): {before['pair_hits'][(styled, sample)]} -> "
            f"{after['pair_hits'][(styled, sample)]}"
        )
    return "\n".join(lines)


def main() -> None:
    fixture_corpus = load_corpus(CORPUS_DIR)
    fixture_result = run_m1(fixture_corpus)
    print("=== M1 over the committed fixture corpus (asserted) ===")
    print(format_table(fixture_result))

    ambient_corpus = discover_ambient_markdown(FORGE_ROOT)
    print()
    print("=== M1 over ambient document-sourced .md (NOT asserted -- a fresh clone holds none) ===")
    if not ambient_corpus:
        print("  (none found in this checkout)")
    else:
        print(
            f"  ({len(ambient_corpus)} ambient files found; token counts only -- the pairwise "
            "tripwire/overlap scan is skipped here as computationally infeasible over real "
            "documents of this size, stated rather than silently forecast)"
        )
        ambient_result = run_m1(ambient_corpus, pairwise=False)
        print(format_table(ambient_result))


if __name__ == "__main__":
    main()
