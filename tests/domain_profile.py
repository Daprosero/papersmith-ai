"""Seed a domain profile for one import, then restore the process environment.

The shared implementation engine (`_core/implementation/engine`) reads
``IMPLEMENTATION_DOMAIN_PROFILE`` when it is imported and fails closed without
one, so every test module that loads it in-process must seed the variable. A
bare module-level ``os.environ.setdefault(...)`` never restores, and the
override then leaks into every later subprocess in the same test process: a
suite that drives the *shipped* default silently exercises the first module's
fixture profile instead.

Measured, not theorized: `tests/test_workspace_skills_e2e.py` passed in
isolation and failed only in the full run, because
`test_implementation_domain_mutation.py` had seeded the proposal profile at
import time; the experimental implementation launcher's own `setdefault`
deliberately respects an explicit override, so it resolved to the sibling's
profile and printed the wrong front door.

`setdefault` semantics are preserved exactly: an override already present wins
during the block, and the environment is restored to what it was afterwards.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

ENV_VAR = "IMPLEMENTATION_DOMAIN_PROFILE"


@contextmanager
def seeded_profile(profile_path):
    """``setdefault`` the engine profile for one import, restore afterwards."""
    previous = os.environ.get(ENV_VAR)
    os.environ.setdefault(ENV_VAR, str(profile_path))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = previous
