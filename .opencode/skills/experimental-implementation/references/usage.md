# Experimental Implementation — holder obligations

See [SKILL.md](../SKILL.md) for the full contract. This file documents only
this skill's own checklist-holder obligations — the declared filename, what
happens when it is absent, and what happens when a checklist already exists
under a different name. It does not mirror the sibling's full
`references/usage.md`: this skill ships no `assets/kit/`, so the kit-asset
sections there (`materialize --stage scaffold`/`objects`/`harness`, the
placeholder token table, adoption) do not apply here (see SKILL.md's "Which
commands are not available yet, and why").

## The declared holder: `Experimental_AGREED.md`

This skill declares its own checklist holder in
`impl_profile.py`'s `PROFILE["holder"]`:

```python
"holder": {
    "filename": "Experimental_AGREED.md",
    "headings": ("# Agreed", "## Ladder"),
    "scaffold": "# Agreed\n\n## Ladder\n",
},
```

`Experimental_AGREED.md` is a deliberately distinct name from the sibling's
own `AGREED.md` — the two skills share the same engine and the same
per-product-folder shape, so a fixed shared name would let one skill's write
land inside the other's checklist. Nothing else about a file makes it the
holder: not its item count, not whether it carries a position block, not its
size. A file is this skill's declared holder iff its name is exactly
`Experimental_AGREED.md` and it is a regular file under `<Name>/`.

Reading is unaffected by this declaration: `verify` still finds a checklist
by shape (any `*.md` under `<Name>/` holding checklist items), exactly as it
always has. Only a WRITE — `position`'s fresh install/reconcile, or any of
`settle`'s five modes — resolves through the declared name first.

## Create-on-absent

When `Experimental_AGREED.md` does not exist and no other markdown file
under `<Name>/` holds checklist items yet, a write (`position --sequence`,
`position --reconcile`, or `settle`'s create path) writes the declared
scaffold to `<Name>/Experimental_AGREED.md` **before** anything else runs:

```
# Agreed

## Ladder
```

That is `HOLDER_SCAFFOLD`, written verbatim — no name interpolation, no
title composed from `--name`, zero checklist items. The file is created only
when `<Name>/` already exists as a directory; this skill never runs
`mkdir()` to bring the product folder itself into existence. If `<Name>/`
does not exist at all, the write instead refuses `POSITION_HOLDER_ABSENT`
(`position`) or `SETTLE_HOLDER_ABSENT` (`settle`) — "no product folder to
create a holder in," never a filename problem.

Once created, the file carries both declared headings
(`# Agreed`, `## Ladder`), so the very next `settle --under "## Ladder"`
places its line without also having to fix a missing heading.

## Write-refusal into an undeclared holder: `HOLDER_UNDECLARED`

When some other markdown file under `<Name>/` — one this skill did not
declare — already holds checklist items, and `Experimental_AGREED.md`
itself does not exist, a WRITE refuses `HOLDER_UNDECLARED` rather than
silently adopting that file or silently creating a second one beside it:

```json
{
  "status": "refused",
  "code": "HOLDER_UNDECLARED",
  "detail": "Method/TASKS.md holds checklist items under Method/, but this skill declares its own holder as Experimental_AGREED.md; rename Method/TASKS.md to Experimental_AGREED.md in the target repository, or declare 'TASKS.md' in this skill's own PROFILE[\"holder\"][\"filename\"] if that name should become this skill's convention for every target."
}
```

Both exits are named in the refusal and neither is chosen for you:

1. rename the found file to `Experimental_AGREED.md` in the target
   repository, or
2. declare the found file's own name in this skill's own
   `PROFILE["holder"]["filename"]`.

Exit 2 is a decision that reaches every target this skill is ever run
against, not only this one — it changes the skill's own convention, not
this target's file. Take it only when the found name really should become
that convention; otherwise rename the file in the target repository
instead. `verify` continues to read the found file by shape either way —
`HOLDER_UNDECLARED` blocks writes, never reads.

When more than one candidate markdown file exists and neither is the
declared name, the write instead refuses the unchanged
`POSITION_HOLDER_AMBIGUOUS` — a human, not a flag, has to choose which file
receives the section.
