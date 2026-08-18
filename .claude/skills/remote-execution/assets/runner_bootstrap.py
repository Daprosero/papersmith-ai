#!/usr/bin/env python3
"""PLACEHOLDER — cell 0 of the generated runner notebook.

This is a provisional stand-in, not the real bootstrap cell. It exists
only so `jobfolder.generate_job()`'s default asset path resolves to a real
file today; a later slice (design #744 section 2, "T7b") replaces this
content in place with the real, service-blind bootstrap: reading
`run-config.json`, sparse-cloning the pinned commit, verifying declared
imports resolve under the clone's own `src/`, detecting hardware, writing
`bootstrap.json`, and raising `SystemExit` before cell 1 on any of
code/config/hardware being missing. Nothing above this file (`jobfolder.py`,
`remote_cli.py`) interpolates into this cell's bytes; it is copied
byte-for-byte, whatever this file's own content is at generation time.

No service is named here, and none may be added later either — this file
stays service-blind for every job it will ever serve.
"""
from __future__ import annotations

raise NotImplementedError(
    "runner_bootstrap.py is a placeholder; a later slice replaces this "
    "with the real bootstrap implementation"
)
