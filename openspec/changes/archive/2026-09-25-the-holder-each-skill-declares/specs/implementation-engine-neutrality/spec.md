# Delta for implementation-engine-neutrality

## MODIFIED Requirements

### Requirement: Engine Refuses To Start Without A Domain Profile

The engine MUST fail closed, with a named refusal, when `IMPLEMENTATION_DOMAIN_PROFILE`
is unset, non-absolute, or resolves to a module missing a required field — now including
the ten Cut-2 domain fields and the declared holder leaf (filename plus heading
scaffold), alongside Cut 1's `kit.root`, `cli.path`, `objective`. It
MUST NOT default to any domain, and MUST NOT default to any holder filename
of its own.
(Previously: validated Cut 1's three fields and the ten Cut-2 domain fields,
with no holder leaf.)

#### Scenario: Unset variable refuses
- GIVEN `IMPLEMENTATION_DOMAIN_PROFILE` is unset
- WHEN the engine is imported
- THEN it raises a named refusal before any command runs

#### Scenario: Malformed profile refuses
- GIVEN the variable is relative, or the module omits a required field
- WHEN the engine loads it
- THEN it raises a refusal named for that exact case

#### Scenario: A missing Cut-2 leaf refuses by its own dotted name
- GIVEN a profile carrying Cut 1's three fields but omitting `vocabulary.artifact_noun`
- WHEN the engine loads it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming that leaf

#### Scenario: A missing holder leaf refuses by its own name
- GIVEN a profile carrying every other required field but omitting the
  declared holder leaf
- WHEN the engine loads it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming the
  holder leaf exactly

## ADDED Requirements

### Requirement: The Engine's Own Prose Stops Asserting A Literal Holder Filename As Fact

The four docstring assertions of fact that the holder *is* `<Name>/AGREED.md`
(`implementation_engine.py:575`, `:12005`, `:18946`, `:18992`) MUST instead
name the declared holder leaf, not a literal filename, since the holder is
now a per-skill declared value rather than an engine-asserted constant. Every
other prose mention of the literal `AGREED.md` in `implementation_engine.py`
(15 total) and `impl_position.py` (3 total) that reads as the engine's own
naming — rather than quoting a specific skill's own artifact as an example —
MUST receive the same treatment.

#### Scenario: The four fact-asserting docstrings name the declared leaf
- GIVEN the four docstring sites listed above
- WHEN they are read after this capability lands
- THEN none of them asserts a literal filename as the engine's own fact —
  each instead refers to the declared holder leaf

#### Scenario: A literal filename in engine prose is caught for the engine's own claims
- GIVEN a hypothetical reintroduced docstring asserting the holder is a
  specific literal filename as the engine's own default
- WHEN the doctrine-verification check for this capability runs
- THEN it is caught and named, distinguishing it from a comment merely
  illustrating one skill's own declared example value
