#!/usr/bin/env python3
# This skill's entry point into the shared implementation engine.
#
# The engine under `_core/` serves no domain of its own and refuses to start
# without one, so the only thing this file does is name which domain is asking
# before handing over. Every argument, subcommand and exit code is the engine's.
#
# `setdefault` rather than `=`: an explicit IMPLEMENTATION_DOMAIN_PROFILE in
# the environment is a deliberate override (a test fixture, a sibling domain
# being exercised through this launcher) and must win over the default --
# the same `??=` semantics `proposal-deliberation/cli.mjs` uses, including
# for the empty string, which stays empty and is refused.
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
os.environ.setdefault("IMPLEMENTATION_DOMAIN_PROFILE",
                      str(_HERE.parents[1] / "impl_profile.py"))
sys.path.insert(0, str(_HERE.parents[2] / "_core" / "implementation" / "engine"))
import implementation_engine as _engine  # noqa: E402  (path set above)

if __name__ == "__main__":
    raise SystemExit(_engine.main())
