"""Cut 3 (`a-revision-is-two-documents`, Phase 6, design.md D1d): the
re-derivation test lands FIRST, before the binding-shape work it protects.

**The trap this file exists to catch** (design.md D1c). The gate
authorization token is `sha256(json.dumps({**own_binding, "session": …,
"at": …, "mintOrdinal": …}, sort_keys=True))`, and `own_binding` is built by
iterating a key tuple over a committed ledger record. If that tuple ever
grows to nine keys UNCONDITIONALLY, every existing one-document record on
disk -- which never carried a ninth key -- re-digests over a `None` it never
had, and every already-minted token in every clone stops verifying. This
file's job is to prove that the *helper* the production code routes through
(`_authorization_binding_keys`) reads key PRESENCE from the record itself,
never assumes a fixed width.

`test_committed_token_rederives` is the load-bearing test: the expected
digest is a **literal committed in this file**, computed once, offline,
against the exact fixture below -- never recomputed from the fixture's own
`token` field on both sides of the assertion (the "green because nothing
happened" shape a prior cut's retrospective already named). A mutation that
breaks re-digestion turns this red without touching the fixture at all.

Fixture: `tests/fixtures/authorization/position.jsonl`, two committed
`authorization` events --

1. A genuine POST-change (8-key) event: carries `proposalDigest` (here
   `null`, a legitimate value for a token minted before any campaign
   proposal existed) and re-digests under the CURRENT 8-key shape.
2. A genuine PRE-change (7-key) event: carries no `proposalDigest` key AT
   ALL and re-digests only under the shape that predates it -- the exact
   case `GATE_AUTHORIZATION_SUPERSEDED` exists to recognise as legitimate,
   never tampered.

Both were minted by this same production hash formula, offline, with the
resulting `token` committed into the fixture alongside the facts that
produced it -- not hand-typed.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
ENGINE = FORGE / "skills/_core/implementation/engine/implementation_engine.py"
sys.path.insert(0, str(ENGINE.parent))
from domain_profile import seeded_profile  # noqa: E402  (path set above)
with seeded_profile(FORGE / "skills/proposal-implementation/impl_profile.py"):
    import implementation_engine as impl  # noqa: E402  (path set above)

FIXTURE_PATH = FORGE / "tests" / "fixtures" / "authorization" / "position.jsonl"

#: The digest `test_committed_token_rederives` asserts against -- a literal,
#: computed once offline against the exact 8-key fixture event below, never
#: recomputed from the fixture's own `token` field. See the module
#: docstring's "never recomputed... on both sides" note.
EXPECTED_EIGHT_KEY_TOKEN = (
    "999f0ca30e11d39b463d635e44fe036a1771a992a06758aea35e972541c05c7a")


def _load_fixture_events() -> list[dict]:
    events = []
    for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


class TokenRederivationTests(unittest.TestCase):
    """D1d's headline guard: the production re-digest path, run over a
    committed fixture, reaches a committed literal digest."""

    def test_committed_token_rederives(self):
        events = _load_fixture_events()
        record = next(e for e in events if e["jobName"] == "job1")
        # `binding` mirrors the SAME eight facts this invocation would have
        # freshly re-derived at `gate` time -- read straight off the
        # committed record via the helper the production `own_binding`
        # comprehension itself must route through (design.md D1c): a raw
        # `_AUTHORIZATION_BINDING_KEYS` read would pass today for the wrong
        # reason (the helper does not exist yet, but this fixture is a
        # one-document, 8-key record the OLD unconditional tuple already
        # handled) and prove nothing about the helper this phase adds.
        binding = {key: record[key]
                   for key in impl._authorization_binding_keys(record)}
        result = impl._verify_gate_authorization(
            events, EXPECTED_EIGHT_KEY_TOKEN, binding)
        self.assertEqual(result, record)


class VerifyAcceptsCommittedTokenTests(unittest.TestCase):
    """`_verify_gate_authorization` over the fixture returns the record and
    raises nothing -- the full function's happy path, exercised end to end,
    reading the token straight off the committed record rather than the
    hardcoded literal above (a second, independent path to the same
    conclusion)."""

    def test_verify_accepts_the_committed_token(self):
        events = _load_fixture_events()
        record = next(e for e in events if e["jobName"] == "job1")
        binding = {key: record[key]
                   for key in impl._authorization_binding_keys(record)}
        result = impl._verify_gate_authorization(events, record["token"], binding)
        self.assertEqual(result, record)


class SupersededStillFiresTests(unittest.TestCase):
    """A legitimate PRE-change (7-key, no `proposalDigest` at all) fixture
    still yields `GATE_AUTHORIZATION_SUPERSEDED`, never `UNKNOWN` -- the
    existing migration mechanism (M3) is not collateral damage from this
    cut's own binding-shape work."""

    def test_superseded_still_fires(self):
        events = _load_fixture_events()
        record = next(e for e in events if e["jobName"] == "job2")
        self.assertNotIn("proposalDigest", record)
        # This invocation's own freshly re-derived binding, built the same
        # helper-routed way `own_binding` is (D1c): for a record naming no
        # `documentRevisions` at all, the helper answers exactly the eight
        # base keys, so this stays behaviourally identical to a raw
        # `_AUTHORIZATION_BINDING_KEYS` read while still exercising the new
        # symbol -- proving Phase 7's helper does not disturb the existing
        # migration mechanism.
        binding = {key: record.get(key)
                   for key in impl._authorization_binding_keys(record)}
        with self.assertRaises(impl.Refused) as ctx:
            impl._verify_gate_authorization(events, record["token"], binding)
        self.assertEqual(ctx.exception.code, "GATE_AUTHORIZATION_SUPERSEDED")


if __name__ == "__main__":
    unittest.main()
