"""Shared pytest fixtures.

The papersmith CLI uses a src-layout; expose ``src/`` so tests import the
package without an install step.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
