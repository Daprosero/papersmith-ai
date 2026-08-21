"""Focused unit tests for the remote-execution ledger and adapter seam.

Covers `ledger.py`'s write-integrity guarantees (the short-write check, the
per-event size cap, `errored.reason` truncation, concurrent appenders never
tearing or losing a line), its fold: deriving per-entrypoint state from the
log and the currency rule that tells a fresh result from a stale one, and
`adapter.py`'s seam: the ABC's structural refusal of an incomplete
implementation, the frozen data shapes, the name-to-class registry, and that
a fake adapter's output plugs into the ledger's own event builders with zero
translation.

Run with any Python 3.10+ (the modules are stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import ast
import builtins
import concurrent.futures
import contextlib
import dataclasses
import hashlib
import importlib.util
import io
import inspect
import json
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import uuid
from pathlib import Path
from types import SimpleNamespace


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Doctrine, as a path the suite can read. `PinConditionDoctrineTests`
# holds `SKILL.md`'s pin-condition table to `jobfolder.PIN_CONDITIONS`;
# prose cannot be held to code, a table can.
SKILL_MD = REPOSITORY_ROOT / ".claude/skills/remote-execution/SKILL.md"

SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/ledger.py"
SPEC = importlib.util.spec_from_file_location("remote_execution_ledger", SCRIPT)
assert SPEC and SPEC.loader
LEDGER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LEDGER
SPEC.loader.exec_module(LEDGER)

ADAPTER_SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/adapter.py"
ADAPTER_SPEC = importlib.util.spec_from_file_location("remote_execution_adapter", ADAPTER_SCRIPT)
assert ADAPTER_SPEC and ADAPTER_SPEC.loader
ADAPTER = importlib.util.module_from_spec(ADAPTER_SPEC)
sys.modules[ADAPTER_SPEC.name] = ADAPTER
ADAPTER_SPEC.loader.exec_module(ADAPTER)

# Loaded AFTER ledger.py and adapter.py above, and under the exact module
# names packer.py's own sibling-loader looks for first: packer.py's
# `_load_sibling` checks `sys.modules` before loading anything itself, so by
# the time its top-level code runs here, it reuses these exact LEDGER/ADAPTER
# module objects rather than exec'ing either file a second time. That reuse
# is what lets `isinstance(fake_adapter, ADAPTER.Adapter)` and
# `isinstance(fake_adapter, PACKER.ADAPTER.Adapter)` agree below — two
# separately exec'd copies of adapter.py would otherwise define two distinct
# `Adapter` classes with the same name.
PACKER_SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/packer.py"
PACKER_SPEC = importlib.util.spec_from_file_location("remote_execution_packer", PACKER_SCRIPT)
assert PACKER_SPEC and PACKER_SPEC.loader
PACKER = importlib.util.module_from_spec(PACKER_SPEC)
sys.modules[PACKER_SPEC.name] = PACKER
PACKER_SPEC.loader.exec_module(PACKER)

# Loaded AFTER ledger.py, adapter.py and packer.py above, for the same
# sys.modules-reuse reason documented next to PACKER's own load above:
# remote_cli.py's `_load_sibling` reuses these exact LEDGER/ADAPTER/PACKER
# module objects rather than exec'ing any of the three a second time.
REMOTE_CLI_SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/remote_cli.py"
REMOTE_CLI_SPEC = importlib.util.spec_from_file_location("remote_execution_cli", REMOTE_CLI_SCRIPT)
assert REMOTE_CLI_SPEC and REMOTE_CLI_SPEC.loader
REMOTE_CLI = importlib.util.module_from_spec(REMOTE_CLI_SPEC)
sys.modules[REMOTE_CLI_SPEC.name] = REMOTE_CLI
REMOTE_CLI_SPEC.loader.exec_module(REMOTE_CLI)

# Loaded AFTER adapter.py above, for the same sys.modules-reuse reason: this
# module's own `isinstance(kaggle_adapter, ADAPTER.Adapter)` checks below
# have to agree with the exact `Adapter` class every other module in this
# chain already loaded.
KAGGLE_SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/adapters/kaggle.py"
KAGGLE_SPEC = importlib.util.spec_from_file_location(
    "remote_execution_kaggle_adapter", KAGGLE_SCRIPT
)
assert KAGGLE_SPEC and KAGGLE_SPEC.loader
KAGGLE = importlib.util.module_from_spec(KAGGLE_SPEC)
sys.modules[KAGGLE_SPEC.name] = KAGGLE
KAGGLE_SPEC.loader.exec_module(KAGGLE)

# Loaded AFTER remote_cli.py above, which already path-imports this exact
# module under this exact name via its own `_load_sibling` — reused here
# rather than exec'd a second time, the same idiom every other module in
# this chain follows.
JOBFOLDER_SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/jobfolder.py"
JOBFOLDER = sys.modules["remote_execution_jobfolder"]

# The two runner assets — loaded fresh (nothing above the seam execs
# them; `jobfolder.py` only reads their bytes to copy verbatim). Each
# guards its orchestrating call behind `if __name__ == "__main__":`, and
# `__name__` here is the module name below, never `"__main__"`, so this
# import fires nothing and lets the suite drive `RUNNER_BOOTSTRAP.bootstrap()`
# / `RUNNER_INVOKE.invoke()` directly against fake configs.
RUNNER_BOOTSTRAP_SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/assets/runner_bootstrap.py"
RUNNER_BOOTSTRAP_SPEC = importlib.util.spec_from_file_location(
    "remote_execution_runner_bootstrap", RUNNER_BOOTSTRAP_SCRIPT
)
assert RUNNER_BOOTSTRAP_SPEC and RUNNER_BOOTSTRAP_SPEC.loader
RUNNER_BOOTSTRAP = importlib.util.module_from_spec(RUNNER_BOOTSTRAP_SPEC)
sys.modules[RUNNER_BOOTSTRAP_SPEC.name] = RUNNER_BOOTSTRAP
RUNNER_BOOTSTRAP_SPEC.loader.exec_module(RUNNER_BOOTSTRAP)

RUNNER_INVOKE_SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/assets/runner_invoke.py"
RUNNER_INVOKE_SPEC = importlib.util.spec_from_file_location(
    "remote_execution_runner_invoke", RUNNER_INVOKE_SCRIPT
)
assert RUNNER_INVOKE_SPEC and RUNNER_INVOKE_SPEC.loader
RUNNER_INVOKE = importlib.util.module_from_spec(RUNNER_INVOKE_SPEC)
sys.modules[RUNNER_INVOKE_SPEC.name] = RUNNER_INVOKE
RUNNER_INVOKE_SPEC.loader.exec_module(RUNNER_INVOKE)

SHARD_IO_SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/shard_io.py"
SHARD_IO_SPEC = importlib.util.spec_from_file_location(
    "remote_execution_shard_io", SHARD_IO_SCRIPT
)
assert SHARD_IO_SPEC and SHARD_IO_SPEC.loader
SHARD_IO = importlib.util.module_from_spec(SHARD_IO_SPEC)
sys.modules[SHARD_IO_SPEC.name] = SHARD_IO
SHARD_IO_SPEC.loader.exec_module(SHARD_IO)


def _sample_submitted_event(**overrides: object) -> dict:
    fields = dict(
        entrypoint="Notebooks/a.ipynb",
        source_digest="a" * 64,
        submission_id="s1",
        worker="acct-1",
        requested_capacity=1,
        granted_capacity=1,
        ts="2026-08-17T00:00:00Z",
    )
    fields.update(overrides)
    return LEDGER.submitted_event(**fields)


def _append_worker(script_path: str, ledger_path: str, worker_id: int, count: int) -> None:
    # A fresh module load per process rather than relying on fork-inherited
    # state, so this test proves the same thing regardless of the platform's
    # default multiprocessing start method.
    spec = importlib.util.spec_from_file_location(f"remote_execution_ledger_w{worker_id}", script_path)
    module = importlib.util.module_from_spec(spec)
    # Registered before exec, matching the module-level load above: with
    # `from __future__ import annotations` in effect, a dataclass's
    # annotations resolve by looking the defining module up in
    # `sys.modules` by name. An unregistered module makes that lookup fail
    # (observed on Python 3.9), unrelated to anything this test is
    # actually exercising.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    for i in range(count):
        event = module.submitted_event(
            entrypoint=f"Notebooks/worker-{worker_id}.ipynb",
            source_digest="b" * 64,
            submission_id=f"w{worker_id}-{i}",
            worker=f"acct-{worker_id}",
            requested_capacity=1,
            granted_capacity=1,
        )
        module.append(ledger_path, event)


class EventBuildersTests(unittest.TestCase):
    def test_submitted_event_uses_entrypoint_field_not_notebook(self) -> None:
        event = _sample_submitted_event()
        self.assertIn("entrypoint", event)
        self.assertEqual(event["entrypoint"], "Notebooks/a.ipynb")
        self.assertNotIn("notebook", event)

    def test_errored_reason_truncated_to_512_chars(self) -> None:
        event = LEDGER.errored_event(submission_id="s1", reason="x" * 1000)
        self.assertEqual(len(event["reason"]), 512)

    def test_errored_reason_under_the_cap_is_left_untouched(self) -> None:
        event = LEDGER.errored_event(submission_id="s1", reason="disk full")
        self.assertEqual(event["reason"], "disk full")

    def test_a_real_event_stays_well_under_the_4096_byte_cap(self) -> None:
        event = LEDGER.errored_event(submission_id="s1", reason="x" * 1000)
        line = json.dumps(event, sort_keys=True) + "\n"
        self.assertLess(len(line.encode("utf-8")), LEDGER.MAX_EVENT_BYTES)


class AppendTests(unittest.TestCase):
    def test_append_writes_one_json_line_per_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            submitted = _sample_submitted_event()
            returned = LEDGER.returned_event(
                submission_id="s1", artifact_path="/out/s1", observed_concurrency=1
            )
            LEDGER.append(path, submitted)
            LEDGER.append(path, returned)

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            first, second = (json.loads(line) for line in lines)
            self.assertEqual(first["kind"], "submitted")
            self.assertEqual(first["entrypoint"], "Notebooks/a.ipynb")
            self.assertEqual(second["kind"], "returned")
            self.assertEqual(second["submissionId"], "s1")

    def test_append_accepts_an_errored_event_with_a_long_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            event = LEDGER.errored_event(submission_id="s1", reason="boom " * 500)
            LEDGER.append(path, event)

            (line,) = path.read_text(encoding="utf-8").splitlines()
            recorded = json.loads(line)
            self.assertEqual(len(recorded["reason"]), 512)

    def test_append_raises_above_4096_byte_cap_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            oversized = dict(_sample_submitted_event(), extra="x" * 5000)

            with self.assertRaises(LEDGER.LedgerError):
                LEDGER.append(path, oversized)

            self.assertFalse(path.exists())

    def test_append_raises_on_short_write_and_claims_no_recorded_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            event = _sample_submitted_event()
            full_line = json.dumps(event, sort_keys=True) + "\n"
            full_payload = full_line.encode("utf-8")

            real_write = os.write

            def short_write(fd: int, data: bytes) -> int:
                # A physically short write, not just a faked return value: the
                # bytes actually landed on disk are the same ones the
                # short-write check has to react to.
                torn = data[: len(data) - 5]
                return real_write(fd, torn)

            with unittest.mock.patch.object(LEDGER.os, "write", side_effect=short_write):
                with self.assertRaises(LEDGER.LedgerError):
                    LEDGER.append(path, event)

            raw = path.read_bytes()
            self.assertEqual(len(raw), len(full_payload) - 5)
            # The bytes on disk are a torn prefix of the event, not the event
            # itself: no complete state was recorded.
            with self.assertRaises(json.JSONDecodeError):
                json.loads(raw.decode("utf-8"))

    def test_concurrent_appends_from_multiple_processes_lose_no_line_and_tear_no_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            worker_count = 8
            events_per_worker = 25

            processes = [
                multiprocessing.Process(
                    target=_append_worker,
                    args=(str(SCRIPT), str(path), worker_id, events_per_worker),
                )
                for worker_id in range(worker_count)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join()
            for process in processes:
                self.assertEqual(process.exitcode, 0)

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), worker_count * events_per_worker)

            # json.loads raising on any single line would mean that line was
            # torn or fused with a neighbour; a lost line would already have
            # failed the count assertion above, so this proves the second,
            # distinct half of the guarantee.
            submission_ids = {json.loads(line)["submissionId"] for line in lines}
            self.assertEqual(len(submission_ids), worker_count * events_per_worker)


class FoldCurrencyTests(unittest.TestCase):
    """The full currency matrix: `fold()`'s verdict for a returned event.

    Every case below is its own test on purpose, even where two cover
    closely related ground, because each one pins a distinct way a
    superseded result could otherwise misread as current.
    """

    @staticmethod
    def _lines(*events: dict) -> list[str]:
        return [json.dumps(event, sort_keys=True) for event in events]

    def test_current_when_latest_submission_matches_and_source_unchanged(self) -> None:
        s1 = LEDGER.submitted_event(
            entrypoint="Notebooks/a.ipynb",
            source_digest="digest-1",
            submission_id="s1",
            worker="acct-1",
            requested_capacity=1,
            granted_capacity=1,
            ts="2026-08-17T00:00:00Z",
        )
        r1 = LEDGER.returned_event(
            submission_id="s1",
            artifact_path="/out/s1",
            observed_concurrency=1,
            ts="2026-08-17T00:05:00Z",
        )

        state = LEDGER.fold(self._lines(s1, r1), live_digest="digest-1")

        self.assertEqual(state.verdicts["s1"], "current")
        self.assertEqual(state.entrypoints["Notebooks/a.ipynb"].state, "returned")
        self.assertEqual(state.from_stale_submission, ())

    def test_from_stale_submission_when_result_belongs_to_superseded_submission(self) -> None:
        s1 = LEDGER.submitted_event(
            entrypoint="Notebooks/a.ipynb",
            source_digest="digest-1",
            submission_id="s1",
            worker="acct-1",
            requested_capacity=1,
            granted_capacity=1,
            ts="2026-08-17T00:00:00Z",
        )
        s2 = LEDGER.submitted_event(  # resubmission after a source edit
            entrypoint="Notebooks/a.ipynb",
            source_digest="digest-2",
            submission_id="s2",
            worker="acct-1",
            requested_capacity=1,
            granted_capacity=1,
            ts="2026-08-17T00:10:00Z",
        )
        r1 = LEDGER.returned_event(  # the OLD submission's result, arriving late
            submission_id="s1",
            artifact_path="/out/s1",
            observed_concurrency=1,
            ts="2026-08-17T00:20:00Z",
        )

        state = LEDGER.fold(self._lines(s1, s2, r1), live_digest="digest-2")

        self.assertEqual(state.verdicts["s1"], "fromStaleSubmission")
        self.assertIn("Notebooks/a.ipynb", state.from_stale_submission)

    def test_from_stale_submission_when_latest_submission_id_matches_but_source_moved_since(
        self,
    ) -> None:
        """Also proves digest-equality is load-bearing on its own.

        With a single submission and no resubmission at all, id-equality
        trivially holds (the latest id IS this submission's id), so only
        the digest check can catch the staleness here. The task brief lists
        "result's submission IS the latest but the source moved again
        since" and "source moved with no resubmission" as separate bullets;
        they describe the same fold input, so this one test covers both
        framings instead of duplicating an identical case under a second
        name.
        """
        s1 = LEDGER.submitted_event(
            entrypoint="Notebooks/a.ipynb",
            source_digest="digest-1",
            submission_id="s1",
            worker="acct-1",
            requested_capacity=1,
            granted_capacity=1,
            ts="2026-08-17T00:00:00Z",
        )
        r1 = LEDGER.returned_event(
            submission_id="s1",
            artifact_path="/out/s1",
            observed_concurrency=1,
            ts="2026-08-17T00:05:00Z",
        )

        # The source moved again AFTER submission, with no resubmission.
        state = LEDGER.fold(self._lines(s1, r1), live_digest="digest-2")

        self.assertEqual(state.verdicts["s1"], "fromStaleSubmission")

    def test_resubmission_at_unchanged_digest_still_marks_earlier_result_stale(self) -> None:
        """Proves id-equality is load-bearing on its own.

        A retry after a service failure resubmits at the SAME digest — the
        source never moved. A digest-only rule would call the old result
        current because its recorded digest still matches; only checking
        the id against the latest submission catches that it is stale.
        """
        s1 = LEDGER.submitted_event(
            entrypoint="Notebooks/a.ipynb",
            source_digest="digest-1",
            submission_id="s1",
            worker="acct-1",
            requested_capacity=1,
            granted_capacity=1,
            ts="2026-08-17T00:00:00Z",
        )
        s2 = LEDGER.submitted_event(
            entrypoint="Notebooks/a.ipynb",
            source_digest="digest-1",  # unchanged: a retry, not an edit
            submission_id="s2",
            worker="acct-1",
            requested_capacity=1,
            granted_capacity=1,
            ts="2026-08-17T00:01:00Z",
        )
        r1 = LEDGER.returned_event(
            submission_id="s1",
            artifact_path="/out/s1",
            observed_concurrency=1,
            ts="2026-08-17T00:05:00Z",
        )

        state = LEDGER.fold(self._lines(s1, s2, r1), live_digest="digest-1")

        self.assertEqual(state.verdicts["s1"], "fromStaleSubmission")

    def test_stale_in_flight_reported_without_calling_cancel(self) -> None:
        s1 = LEDGER.submitted_event(
            entrypoint="Notebooks/a.ipynb",
            source_digest="digest-1",
            submission_id="s1",
            worker="acct-1",
            requested_capacity=1,
            granted_capacity=1,
            ts="2026-08-17T00:00:00Z",
        )

        state = LEDGER.fold(self._lines(s1), live_digest="digest-2")

        self.assertEqual(state.entrypoints["Notebooks/a.ipynb"].state, "pending")
        self.assertIn("Notebooks/a.ipynb", state.stale_in_flight)
        # The stronger guarantee than "nothing called cancel() in this test":
        # fold() takes no adapter and no cancel callable at all, so there is
        # no cancel() reachable from here for it to call even by accident.
        self.assertNotIn("cancel", inspect.signature(LEDGER.fold).parameters)
        self.assertFalse(hasattr(LEDGER, "cancel"))

    def test_resubmission_appends_and_superseded_line_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            s1 = LEDGER.submitted_event(
                entrypoint="Notebooks/a.ipynb",
                source_digest="digest-1",
                submission_id="s1",
                worker="acct-1",
                requested_capacity=1,
                granted_capacity=1,
            )
            LEDGER.append(path, s1)
            original_first_line = path.read_text(encoding="utf-8").splitlines()[0]

            s2 = LEDGER.submitted_event(
                entrypoint="Notebooks/a.ipynb",
                source_digest="digest-2",
                submission_id="s2",
                worker="acct-1",
                requested_capacity=1,
                granted_capacity=1,
            )
            LEDGER.append(path, s2)

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], original_first_line)

            state = LEDGER.fold(lines, live_digest="digest-2")
            self.assertEqual(state.by_id["s1"]["sourceDigest"], "digest-1")
            self.assertEqual(state.latest["Notebooks/a.ipynb"]["submissionId"], "s2")

    def test_corrupted_line_counted_skipped_and_file_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            s1 = LEDGER.submitted_event(
                entrypoint="Notebooks/a.ipynb",
                source_digest="digest-1",
                submission_id="s1",
                worker="acct-1",
                requested_capacity=1,
                granted_capacity=1,
            )
            LEDGER.append(path, s1)
            # A truncated tail: exactly what a short write or a process
            # killed mid-append leaves behind. Not valid JSON.
            with open(path, "a", encoding="utf-8") as handle:
                handle.write('{"kind": "submitted", "entrypoint": "Note')

            before = path.read_bytes()
            lines = path.read_text(encoding="utf-8").splitlines()
            state = LEDGER.fold(lines, live_digest="digest-1")
            after = path.read_bytes()

            self.assertEqual(state.unreadable_lines, 1)
            self.assertEqual(state.entrypoints["Notebooks/a.ipynb"].state, "pending")
            # fold() only reads `lines`; it never opens the ledger file
            # itself, so nothing about this call could rewrite it. This
            # assertion is what pins that, rather than trusting the claim.
            self.assertEqual(before, after)

    def test_ts_is_not_a_sort_key_fold_follows_append_order(self) -> None:
        s1 = LEDGER.submitted_event(
            entrypoint="Notebooks/a.ipynb",
            source_digest="digest-1",
            submission_id="s1",
            worker="acct-1",
            requested_capacity=1,
            granted_capacity=1,
            ts="2026-08-17T23:00:00Z",  # a LATER clock reading...
        )
        s2 = LEDGER.submitted_event(  # ...appended AFTER s1 regardless
            entrypoint="Notebooks/a.ipynb",
            source_digest="digest-2",
            submission_id="s2",
            worker="acct-1",
            requested_capacity=1,
            granted_capacity=1,
            ts="2026-08-17T01:00:00Z",  # a machine with a skewed clock
        )
        r_s2 = LEDGER.returned_event(
            submission_id="s2", artifact_path="/out/s2", observed_concurrency=1
        )
        r_s1 = LEDGER.returned_event(
            submission_id="s1", artifact_path="/out/s1", observed_concurrency=1
        )

        state = LEDGER.fold(self._lines(s1, s2, r_s2, r_s1), live_digest="digest-2")

        # If `ts` had been used to order events, s1 (the later timestamp)
        # would have been treated as the latest submission and both
        # assertions below would flip.
        self.assertEqual(state.latest["Notebooks/a.ipynb"]["submissionId"], "s2")
        self.assertEqual(state.verdicts["s2"], "current")
        self.assertEqual(state.verdicts["s1"], "fromStaleSubmission")


class FakeAdapter(ADAPTER.Adapter):
    """A complete, in-memory stand-in for a real backend adapter.

    Exists to prove the seam is genuinely swappable, not merely typed that
    way: everything that consumes an adapter today — only the ledger's event
    builders, since the packer does not exist until Task 4 — reads and
    writes nothing but these six operations' return shapes.
    """

    def __init__(self, worker_id: str = "fake-1", capacity: int = 2) -> None:
        self._worker = ADAPTER.Worker(id=worker_id, capacity=capacity)
        self._next_id = 0
        self._states: dict[str, str] = {}

    def workers(self) -> list:
        return [self._worker]

    def submit(self, job) -> "ADAPTER.Submission":
        self._next_id += 1
        submission_id = f"fake-{self._next_id}"
        self._states[submission_id] = "complete"
        return ADAPTER.Submission(id=submission_id, worker=job.worker)

    def poll(self, submission_id: str) -> "ADAPTER.Status":
        return ADAPTER.Status(state=self._states[submission_id], detail="fake backend")

    def fetch(self, submission_id: str, into: Path) -> "ADAPTER.Fetched":
        into.mkdir(parents=True, exist_ok=True)
        (into / "result.txt").write_text("ok", encoding="utf-8")
        return ADAPTER.Fetched(path=into, complete=True, files=("result.txt",))

    def cancel(self, submission_id: str) -> None:
        self._states[submission_id] = "failed"

    def list_active(self, worker: str) -> list:
        return [sid for sid, state in self._states.items() if state in ("queued", "running")]


class AdapterSeamTests(unittest.TestCase):
    def test_adapter_abc_rejects_direct_instantiation(self) -> None:
        with self.assertRaises(TypeError):
            ADAPTER.Adapter()

    def test_an_incomplete_subclass_cannot_be_instantiated(self) -> None:
        """The ABC is a structural guarantee, not a suggestion.

        Leaving out even one of the six operations must make the subclass
        itself uninstantiable, not merely undocumented — this is the test
        that makes the seam a seam rather than a convention a future
        contributor could quietly ignore.
        """

        class MissingCancel(ADAPTER.Adapter):
            def workers(self):
                return []

            def submit(self, job):
                raise NotImplementedError

            def poll(self, submission_id):
                raise NotImplementedError

            def fetch(self, submission_id, into):
                raise NotImplementedError

            def list_active(self, worker):
                return []

            # cancel() deliberately omitted.

        with self.assertRaises(TypeError):
            MissingCancel()

    def test_fake_adapter_satisfies_all_six_operations(self) -> None:
        adapter = FakeAdapter()
        self.assertIsInstance(adapter, ADAPTER.Adapter)  # instantiation itself proves completeness
        workers = adapter.workers()
        self.assertEqual(len(workers), 1)

        job = ADAPTER.Job(
            entrypoint=Path("Notebooks/a.ipynb"), run_config={}, worker=workers[0].id
        )
        submission = adapter.submit(job)
        status = adapter.poll(submission.id)
        self.assertIn(status.state, ADAPTER.STATES)

        with tempfile.TemporaryDirectory() as tmp:
            fetched = adapter.fetch(submission.id, Path(tmp) / "out")
            self.assertTrue(fetched.complete)

        adapter.cancel(submission.id)
        self.assertEqual(adapter.list_active(workers[0].id), [])

    def test_registry_resolves_adapter_class_by_name(self) -> None:
        ADAPTER.register("fake-for-test", FakeAdapter)
        self.assertIs(ADAPTER.resolve("fake-for-test"), FakeAdapter)
        with self.assertRaises(KeyError):
            ADAPTER.resolve("no-backend-registered-under-this-name")

    def test_registry_refuses_a_class_that_does_not_subclass_adapter(self) -> None:
        class NotAnAdapter:
            pass

        with self.assertRaises(TypeError):
            ADAPTER.register("not-an-adapter", NotAnAdapter)

    def test_job_exposes_entrypoint_field_not_notebook(self) -> None:
        """Pins the naming decision the ledger's own schema already made."""
        job = ADAPTER.Job(
            entrypoint=Path("Notebooks/a.ipynb"), run_config={"x": True}, worker="w1"
        )
        self.assertEqual(job.entrypoint, Path("Notebooks/a.ipynb"))
        with self.assertRaises(TypeError):
            ADAPTER.Job(notebook=Path("a.ipynb"), run_config={}, worker="w1")

    def test_status_rejects_a_value_outside_the_five_state_vocabulary(self) -> None:
        with self.assertRaises(ValueError):
            ADAPTER.Status(state="succeeded", detail="a backend's own word, not the seam's")

    def test_frozen_shapes_refuse_assignment(self) -> None:
        worker = ADAPTER.Worker(id="w1", capacity=2)
        job = ADAPTER.Job(entrypoint=Path("a.ipynb"), run_config={}, worker="w1")
        submission = ADAPTER.Submission(id="s1", worker="w1")
        status = ADAPTER.Status(state="queued", detail="")
        fetched = ADAPTER.Fetched(path=Path("/tmp/out"), complete=False, files=())

        for instance, field, value in (
            (worker, "capacity", 99),
            (job, "worker", "w2"),
            (submission, "id", "s2"),
            (status, "state", "running"),
            (fetched, "complete", True),
        ):
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(instance, field, value)

    def test_adapter_module_names_no_service(self) -> None:
        """The leak guard for this new module — asserted over the raw file

        text, which covers the module source and every docstring in it: a
        docstring naming a backend to explain an example would be exactly
        the kind of leak the seam exists to prevent, so it is checked the
        same as executable code.
        """
        source = ADAPTER_SCRIPT.read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)

    def test_job_carries_run_config_as_an_opaque_mapping(self) -> None:
        """`Job.run_config` replaces the old `inputs` tuple: an opaque
        mapping the packer and ledger never interpret. Construction accepts
        an ordinary dict; the seam itself is what freezes it (see the
        immutability test below).
        """
        job = ADAPTER.Job(
            entrypoint=Path("Notebooks/a.ipynb"),
            run_config={"mode": "smoke", "seeds": [0, 1]},
            worker="w1",
        )
        self.assertEqual(dict(job.run_config), {"mode": "smoke", "seeds": [0, 1]})

    def test_job_run_config_is_immutable_even_against_direct_mutation(self) -> None:
        """`__post_init__` normalizes `run_config` to a `MappingProxyType`
        over a private copy, so mutating the mapping a caller gets back is
        structurally refused — not merely a documented convention.
        """
        original = {"a": 1}
        job = ADAPTER.Job(entrypoint=Path("a.ipynb"), run_config=original, worker="w1")
        with self.assertRaises(TypeError):
            job.run_config["a"] = 2

        # Mutating the caller's own dict after construction must not leak
        # into the job either — the seam copies, it does not merely wrap.
        original["a"] = 99
        self.assertEqual(job.run_config["a"], 1)

    def test_run_config_is_opaque_to_packer_and_ledger(self) -> None:
        """RED-provable opacity: the substring `run_config` never occurs
        anywhere in `packer.py` or `ledger.py` — not in code, not in a
        docstring, not in a comment. Those two modules depend on `Job` only
        through the fields they already use (`entrypoint`, `worker`); this
        field must never become a third.
        """
        for script in (PACKER_SCRIPT, SCRIPT):
            source = script.read_text(encoding="utf-8")
            self.assertNotIn("run_config", source, str(script))

    def test_metadata_registry_resolves_by_name(self) -> None:
        """A second, separate registry from the adapter class registry
        above: `register_metadata`/`resolve_metadata` map a name to a
        callable `fn(run_config) -> (filename, text)`. This keeps metadata
        assembly off the `Adapter` ABC entirely — the spec pins that ABC at
        exactly six operations, so a seventh method is not an option.
        """
        def fake_assembler(run_config):
            return "meta.json", json.dumps(dict(run_config))

        ADAPTER.register_metadata("fake-for-test", fake_assembler)
        resolved = ADAPTER.resolve_metadata("fake-for-test")
        filename, text = resolved({"a": 1})
        self.assertEqual(filename, "meta.json")
        self.assertEqual(json.loads(text), {"a": 1})

    def test_metadata_registry_refuses_an_unregistered_name(self) -> None:
        with self.assertRaises(KeyError):
            ADAPTER.resolve_metadata("no-metadata-registered-under-this-name")

    def test_adapter_abc_still_exposes_exactly_six_operations(self) -> None:
        """Structural proof, not a count copied from prose: the metadata
        registry above must never grow into a seventh ABC method.
        """
        self.assertEqual(len(ADAPTER.Adapter.__abstractmethods__), 6)

    def test_fake_adapter_output_plugs_into_ledger_events_unchanged(self) -> None:
        """What exists today — `fold()` and the event builders — accepts a
        fake adapter's output with zero translation, proving the seam
        instead of merely asserting it.

        The packer (Task 4) does not exist yet, so `plan()`'s clamp/grant
        arithmetic is deliberately NOT exercised here. This covers only the
        ledger integration that exists at this point in the chain; claiming
        packer coverage here would be a proxy, not a test.
        """
        adapter = FakeAdapter(worker_id="w1", capacity=2)
        job = ADAPTER.Job(entrypoint=Path("Notebooks/a.ipynb"), run_config={}, worker="w1")
        submission = adapter.submit(job)

        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.jsonl"
            LEDGER.append(
                ledger_path,
                LEDGER.submitted_event(
                    entrypoint=str(job.entrypoint),
                    source_digest="digest-1",
                    submission_id=submission.id,
                    worker=submission.worker,
                    requested_capacity=1,
                    granted_capacity=1,
                ),
            )

            status = adapter.poll(submission.id)
            self.assertEqual(status.state, "complete")
            fetched = adapter.fetch(submission.id, Path(tmp) / "out")
            self.assertTrue(fetched.complete)

            LEDGER.append(
                ledger_path,
                LEDGER.returned_event(
                    submission_id=submission.id,
                    artifact_path=str(fetched.path),
                    observed_concurrency=1,
                ),
            )

            lines = ledger_path.read_text(encoding="utf-8").splitlines()
            state = LEDGER.fold(lines, live_digest="digest-1")
            self.assertEqual(state.entrypoints[str(job.entrypoint)].state, "returned")
            self.assertEqual(state.verdicts[submission.id], "current")


class UnreachableAdapter(FakeAdapter):
    """A `FakeAdapter` whose `list_active()` simulates the service being
    unreachable, so `plan()`'s ledger-fallback path is exercised on
    purpose rather than only ever taking the `list_active` branch.
    """

    def list_active(self, worker: str) -> list:
        raise ConnectionError("service unreachable (test double)")


def _pending_submission_line(*, entrypoint: str, submission_id: str, worker: str) -> str:
    """One `submitted` line with no terminal event — still pending."""
    return json.dumps(
        LEDGER.submitted_event(
            entrypoint=entrypoint,
            source_digest="digest-1",
            submission_id=submission_id,
            worker=worker,
            requested_capacity=1,
            granted_capacity=1,
        ),
        sort_keys=True,
    )


class PackerTests(unittest.TestCase):
    """Clamp arithmetic and its visibility.

    `FakeAdapter`'s `submit()` marks a submission `complete` immediately, so
    it never populates its own `list_active()` on its own — that is
    deliberate here, not a gap: the in-flight numbers below come from the
    ledger's own pending submissions (built directly with
    `LEDGER.submitted_event`, no terminal event appended), which is exactly
    the case `plan()`'s `pending_for()` call exists to cover, and
    `UnreachableAdapter` exercises the `list_active`-raises fallback
    separately from that.
    """

    def test_plan_clamps_requested_above_the_adapter_cap(self) -> None:
        adapter = FakeAdapter(worker_id="w1", capacity=2)
        result = PACKER.plan(
            adapter=adapter,
            worker_id="w1",
            requested=5,
            ledger_lines=[],
            live_digest="digest-1",
        )
        self.assertEqual(result.requested, 5)
        self.assertEqual(result.cap, 2)
        self.assertEqual(result.in_flight, 0)
        self.assertEqual(result.granted, 2)

    def test_plan_grants_the_full_request_when_cap_exceeds_it(self) -> None:
        adapter = FakeAdapter(worker_id="w1", capacity=5)
        result = PACKER.plan(
            adapter=adapter,
            worker_id="w1",
            requested=2,
            ledger_lines=[],
            live_digest="digest-1",
        )
        self.assertEqual(result.requested, 2)
        self.assertEqual(result.cap, 5)
        self.assertEqual(result.granted, 2)

    def test_plan_saturates_grant_to_zero_when_in_flight_meets_the_cap(self) -> None:
        adapter = UnreachableAdapter(worker_id="w1", capacity=2)
        lines = [
            _pending_submission_line(entrypoint="Notebooks/a.ipynb", submission_id="s1", worker="w1"),
            _pending_submission_line(entrypoint="Notebooks/b.ipynb", submission_id="s2", worker="w1"),
        ]
        result = PACKER.plan(
            adapter=adapter,
            worker_id="w1",
            requested=5,
            ledger_lines=lines,
            live_digest="digest-1",
        )
        self.assertEqual(result.cap, 2)
        self.assertEqual(result.in_flight, 2)
        self.assertEqual(result.granted, 0)
        self.assertEqual(result.in_flight_source, "ledger")

    def test_granted_never_goes_negative_when_in_flight_exceeds_the_cap(self) -> None:
        # An edge case that should not arise in ordinary operation (more
        # pending submissions than the cap allows), but the clamp still has
        # to answer it without a negative "grant" leaking downstream.
        adapter = UnreachableAdapter(worker_id="w1", capacity=2)
        lines = [
            _pending_submission_line(entrypoint="Notebooks/a.ipynb", submission_id="s1", worker="w1"),
            _pending_submission_line(entrypoint="Notebooks/b.ipynb", submission_id="s2", worker="w1"),
            _pending_submission_line(entrypoint="Notebooks/c.ipynb", submission_id="s3", worker="w1"),
        ]
        result = PACKER.plan(
            adapter=adapter,
            worker_id="w1",
            requested=5,
            ledger_lines=lines,
            live_digest="digest-1",
        )
        self.assertEqual(result.in_flight, 3)
        self.assertEqual(result.granted, 0)
        self.assertGreaterEqual(result.granted, 0)

    def test_plan_reports_four_numbers_not_a_silent_minimum(self) -> None:
        """The test that would fail if `plan()` returned only `granted`.

        Two plans below share the exact same `granted` value (2) for
        opposite reasons — one asked for less than the cap and got all of
        it, the other asked for more than the cap and got clamped to it.
        `granted` alone cannot tell these apart; `requested` and `cap`
        together are what make the difference a visible fact instead of a
        silent minimum.
        """
        unclamped_adapter = FakeAdapter(worker_id="w1", capacity=5)
        unclamped = PACKER.plan(
            adapter=unclamped_adapter,
            worker_id="w1",
            requested=2,
            ledger_lines=[],
            live_digest="digest-1",
        )

        clamped_adapter = FakeAdapter(worker_id="w1", capacity=2)
        clamped = PACKER.plan(
            adapter=clamped_adapter,
            worker_id="w1",
            requested=5,
            ledger_lines=[],
            live_digest="digest-1",
        )

        self.assertEqual(unclamped.granted, clamped.granted)  # same granted...
        # ...yet the two plans are not the same claim, and `requested`/`cap`
        # are what prove it:
        self.assertEqual(unclamped.requested, unclamped.granted)  # got what it asked for
        self.assertNotEqual(clamped.requested, clamped.granted)  # got less than it asked for
        self.assertNotEqual(unclamped.cap, clamped.cap)
        self.assertNotEqual(unclamped.requested, clamped.requested)

    def test_plan_prefers_list_active_over_the_ledger_estimate_when_reachable(self) -> None:
        """`list_active()` REFINES `inFlight`, it does not merely duplicate
        the ledger's own count — proven here by a ledger that reports one
        pending submission while the reachable adapter's `list_active()`
        reports none, and the adapter's answer is the one that wins.
        """
        adapter = FakeAdapter(worker_id="w1", capacity=2)  # list_active() answers []
        lines = [
            _pending_submission_line(entrypoint="Notebooks/a.ipynb", submission_id="s1", worker="w1"),
        ]
        result = PACKER.plan(
            adapter=adapter,
            worker_id="w1",
            requested=2,
            ledger_lines=lines,
            live_digest="digest-1",
        )
        self.assertEqual(result.in_flight, 0)
        self.assertEqual(result.in_flight_source, "list_active")

    def test_plan_falls_back_to_the_ledger_when_the_adapter_is_unreachable(self) -> None:
        adapter = UnreachableAdapter(worker_id="w1", capacity=2)
        lines = [
            _pending_submission_line(entrypoint="Notebooks/a.ipynb", submission_id="s1", worker="w1"),
        ]
        result = PACKER.plan(
            adapter=adapter,
            worker_id="w1",
            requested=2,
            ledger_lines=lines,
            live_digest="digest-1",
        )
        self.assertEqual(result.in_flight, 1)
        self.assertEqual(result.in_flight_source, "ledger")

    def test_plan_refuses_an_object_that_is_not_a_real_adapter(self) -> None:
        class NotAnAdapter:
            def workers(self):
                return []

        with self.assertRaises(PACKER.PackerError):
            PACKER.plan(
                adapter=NotAnAdapter(),
                worker_id="w1",
                requested=1,
                ledger_lines=[],
                live_digest="digest-1",
            )

    def test_plan_refuses_a_worker_id_the_adapter_does_not_report(self) -> None:
        adapter = FakeAdapter(worker_id="w1", capacity=2)
        with self.assertRaises(PACKER.PackerError):
            PACKER.plan(
                adapter=adapter,
                worker_id="no-such-worker",
                requested=1,
                ledger_lines=[],
                live_digest="digest-1",
            )

    def test_packer_module_names_no_service_and_hardcodes_no_capacity(self) -> None:
        source = PACKER_SCRIPT.read_text(encoding="utf-8")
        lowered = source.lower()
        for leaked in ("kaggle", "t4"):
            self.assertNotIn(leaked, lowered, leaked)

        # No module-level ALL_CAPS numeric constant (the shape a hardcoded
        # capacity would take, mirroring how ledger.py's own real constants
        # like MAX_EVENT_BYTES are declared) anywhere in this file.
        for line in source.splitlines():
            stripped = line.strip()
            match = re.match(r"^[A-Z][A-Z0-9_]*\s*=\s*-?\d+\s*(#.*)?$", stripped)
            self.assertIsNone(match, f"looks like a hardcoded constant: {line!r}")

    def test_packer_only_discovers_capacity_through_adapter_workers(self) -> None:
        """`plan()` accepts no `cap`/`capacity` keyword at all — the only
        route to a capacity number in this module's public signature is
        `adapter.workers()`.
        """
        signature = inspect.signature(PACKER.plan)
        for leaked in ("cap", "capacity"):
            self.assertNotIn(leaked, signature.parameters)

    def test_plan_works_against_fake_adapter_with_no_real_backend(self) -> None:
        """No import of any concrete backend module anywhere in this test,
        and none exists yet in this skill — `FakeAdapter` is the only
        `Adapter` this whole test module ever constructs.
        """
        adapter = FakeAdapter(worker_id="w1", capacity=3)
        result = PACKER.plan(
            adapter=adapter,
            worker_id="w1",
            requested=3,
            ledger_lines=[],
            live_digest="digest-1",
        )
        self.assertIsInstance(result, PACKER.Plan)
        self.assertEqual(result.granted, 3)


def _make_product(target: Path, name: str) -> Path:
    """Build `<target>/<name>/Notebooks/` and return the Notebooks dir."""
    notebooks = target / name / "Notebooks"
    notebooks.mkdir(parents=True)
    return notebooks


def _make_job_folder(target: Path, service: str, job_name: str) -> Path:
    """Build `<target>/tools/<service>/<job-name>/` and return that dir."""
    job_dir = target / "tools" / service / job_name
    job_dir.mkdir(parents=True)
    return job_dir


def _write_job_folder_run_config(job_dir: Path, **overrides: object) -> dict:
    """A COMPLETE `run-config.json` beside a job-folder-shaped fixture.

    Several `cmd_submit` fixtures used to write `{"product": "..."}` alone
    — enough for `product_for()`, which tolerates an incomplete config on
    purpose, and nowhere near what a real generated job folder contains.
    Once `submit` gates on the job folder's own declared pin, an
    incomplete config stops being a shortcut and becomes a malformed job
    folder, which now refuses. Completing the fixture is a fidelity
    repair: it makes these tests describe the artifact `generate-job`
    actually writes. Their own subjects — product resolution, ledger
    placement, smoke isolation — are untouched, and `product_for()`'s
    tolerance of an incomplete config keeps its own coverage in
    `ProductForTests`, which does not submit.
    """
    run_config = {
        "schemaVersion": 1,
        "product": "MIL-CREDA",
        "service": "kaggle",
        "jobName": job_dir.name,
        "commit": "a" * 40,
        "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
        "clonePaths": ["src/MIL_CREDA_Benchmark"],
        "run": {"module": "MIL_CREDA_Benchmark.harness", "function": "campaign"},
        "runnerTemplate": [],
    }
    run_config.update(overrides)
    (job_dir / "run-config.json").write_text(
        json.dumps(run_config), encoding="utf-8"
    )
    return run_config


class PathGuardTests(unittest.TestCase):
    """`remote_cli.guard_entrypoint()` — the sole holder of file-kind policy.

    Every case here has a reachable red: `remote_cli.py` does not exist
    before this task, so the whole module fails to import and every test in
    this file fails to collect.
    """

    def test_symlink_escaping_the_product_notebooks_dir_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            outside = Path(tmp) / "outside.ipynb"
            outside.write_text("{}", encoding="utf-8")

            link = notebooks / "evil.ipynb"
            os.symlink(outside, link)

            # The fixture itself must actually escape — a negative test
            # whose escape silently failed would report success while
            # testing nothing.
            self.assertNotIn("Notebooks", link.resolve().parts)
            self.assertEqual(link.resolve(), outside.resolve())

            with self.assertRaises(REMOTE_CLI.PathGuardError):
                REMOTE_CLI.guard_entrypoint(target.resolve(), link)

    def test_non_ipynb_path_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            not_a_notebook = notebooks / "notes.txt"
            not_a_notebook.write_text("plain text", encoding="utf-8")

            with self.assertRaises(REMOTE_CLI.PathGuardError):
                REMOTE_CLI.guard_entrypoint(target.resolve(), not_a_notebook)

    def test_path_legitimately_under_notebooks_dir_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            resolved = REMOTE_CLI.guard_entrypoint(target.resolve(), notebook)
            self.assertEqual(resolved, notebook.resolve())

    def test_path_outside_target_entirely_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            elsewhere = Path(tmp) / "elsewhere.ipynb"
            elsewhere.write_text("{}", encoding="utf-8")

            with self.assertRaises(REMOTE_CLI.PathGuardError):
                REMOTE_CLI.guard_entrypoint(target.resolve(), elsewhere)

    def test_job_folder_shaped_path_is_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            resolved = REMOTE_CLI.guard_entrypoint(target.resolve(), notebook)
            self.assertEqual(resolved, notebook.resolve())

    def test_symlink_escaping_job_folder_shape_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            outside = Path(tmp) / "outside.ipynb"
            outside.write_text("{}", encoding="utf-8")

            link = job_dir / "evil.ipynb"
            os.symlink(outside, link)

            # Same escape-proof requirement the legacy-shape fixture check
            # above already applies: prove the fixture itself escapes
            # before trusting a refusal to mean anything.
            self.assertNotIn("tools", link.resolve().parts)
            self.assertEqual(link.resolve(), outside.resolve())

            with self.assertRaises(REMOTE_CLI.PathGuardError):
                REMOTE_CLI.guard_entrypoint(target.resolve(), link)

    def test_five_deep_tools_path_is_refused(self) -> None:
        """The job-folder shape is exactly four components past `target`,
        not "at least four" — a fifth component, one level deeper than a
        job folder ever legitimately goes, is refused rather than admitted
        the way a `>=` check would admit it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            too_deep = target / "tools" / "kaggle" / "search-a" / "extra"
            too_deep.mkdir(parents=True)
            notebook = too_deep / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            with self.assertRaises(REMOTE_CLI.PathGuardError):
                REMOTE_CLI.guard_entrypoint(target.resolve(), notebook)

    def test_three_deep_tools_path_is_refused(self) -> None:
        """The opposite boundary: a path one component too SHALLOW to be a
        genuine job folder (no `<job-name>` level at all) is refused the
        same way — there is no service-level entrypoint, only a job-level
        one.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            service_dir = target / "tools" / "kaggle"
            service_dir.mkdir(parents=True)
            notebook = service_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            with self.assertRaises(REMOTE_CLI.PathGuardError):
                REMOTE_CLI.guard_entrypoint(target.resolve(), notebook)


class ProductForTests(unittest.TestCase):
    """`remote_cli.product_for()` — replaces `name_for()`. Same resolve-first
    discipline `name_for()` always had, plus the four-step resolution order
    design #744 section 5 pins: an explicit `--product` wins outright, then
    a job folder's own declared `product`, then the legacy shape's
    `<Name>`, then refusal — never a guess.
    """

    def test_explicit_product_wins_over_a_declared_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "MIL-CREDA").mkdir(parents=True)
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            (job_dir / "run-config.json").write_text(
                json.dumps({"product": "SomeOtherProduct"}), encoding="utf-8"
            )

            product = REMOTE_CLI.product_for(
                target.resolve(), notebook, explicit="MIL-CREDA"
            )
            self.assertEqual(product, "MIL-CREDA")

    def test_job_folder_shape_reads_the_declared_product_from_run_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "MIL-CREDA").mkdir(parents=True)
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            (job_dir / "run-config.json").write_text(
                json.dumps({"product": "MIL-CREDA"}), encoding="utf-8"
            )

            product = REMOTE_CLI.product_for(target.resolve(), notebook)
            self.assertEqual(product, "MIL-CREDA")

    def test_legacy_shape_falls_back_to_the_first_path_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            product = REMOTE_CLI.product_for(target.resolve(), notebook)
            self.assertEqual(product, "MIL-CREDA")

    def test_job_folder_shape_with_no_run_config_at_all_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            # No run-config.json at all: T7 is the task that ever writes
            # one. This step must fall through cleanly, never guess "tools".

            with self.assertRaises(REMOTE_CLI.RemoteCLIError):
                REMOTE_CLI.product_for(target.resolve(), notebook)

    def test_job_folder_shape_with_run_config_present_but_no_product_field_is_refused(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            (job_dir / "run-config.json").write_text(
                json.dumps({"commit": "abc123"}), encoding="utf-8"
            )

            with self.assertRaises(REMOTE_CLI.RemoteCLIError):
                REMOTE_CLI.product_for(target.resolve(), notebook)

    def test_resolved_product_must_be_an_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            # No `NoSuchProduct/` directory exists under target at all.

            with self.assertRaises(REMOTE_CLI.RemoteCLIError):
                REMOTE_CLI.product_for(
                    target.resolve(), notebook, explicit="NoSuchProduct"
                )

    def test_resolved_product_must_not_be_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            # `tools/` genuinely exists as a directory under target — the
            # refusal has to come from the name itself, not a missing dir.
            self.assertTrue((target / "tools").is_dir())

            with self.assertRaises(REMOTE_CLI.RemoteCLIError):
                REMOTE_CLI.product_for(target.resolve(), notebook, explicit="tools")

    def test_path_outside_target_entirely_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            elsewhere = Path(tmp) / "elsewhere.ipynb"
            elsewhere.write_text("{}", encoding="utf-8")

            with self.assertRaises(REMOTE_CLI.RemoteCLIError):
                REMOTE_CLI.product_for(target.resolve(), elsewhere)


class AdapterErrorAtTheSeamTests(unittest.TestCase):
    """A backend fails, and the CLI has to survive a backend it never heard of.

    `main()` is the one path in this skill nothing else exercises: every other
    test calls `cmd_*` directly, so argparse, the exit codes and the error
    handling were wired and never run. That is where this hole was hiding.

    The hole itself is the seam's, not any backend's. Code above the seam has
    to catch a backend's failures somehow, and the only two options without a
    common base are both wrong: importing the concrete adapter to name its
    error type is the leak this whole seam exists to prevent, and catching
    bare `Exception` swallows the real defects a traceback is for. So
    `AdapterError` is what lets the CLI handle a backend it has never heard
    of, and these tests are what keep it that way.
    """

    class _Boom(ADAPTER.AdapterError):
        pass

    class _FailingAdapter(ADAPTER.Adapter):
        def workers(self):
            return []

        def submit(self, job):
            raise AdapterErrorAtTheSeamTests._Boom("the service refused")

        def poll(self, submission_id):
            raise AdapterErrorAtTheSeamTests._Boom("the service refused")

        def fetch(self, submission_id, into):
            raise AdapterErrorAtTheSeamTests._Boom("the service refused")

        def cancel(self, submission_id):
            raise AdapterErrorAtTheSeamTests._Boom("the service refused")

        def list_active(self, worker):
            raise AdapterErrorAtTheSeamTests._Boom("the service refused")

    def setUp(self) -> None:
        ADAPTER.register("failing-test-backend", self._FailingAdapter)

    def test_a_failing_backend_becomes_an_error_line_and_not_a_traceback(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = REMOTE_CLI.main(
                ["poll", "--submission-id", "s1", "--backend", "failing-test-backend"]
            )
        self.assertEqual(code, 1)
        self.assertIn("the service refused", stderr.getvalue())

    def test_the_concrete_adapter_s_error_descends_from_the_seam_s(self) -> None:
        """Otherwise the handler above catches nothing that matters: the base
        exists and the one backend that ships does not use it."""
        self.assertTrue(issubclass(KAGGLE.KaggleAdapterError, ADAPTER.AdapterError))

    def test_a_genuine_defect_still_reaches_the_caller(self) -> None:
        """Reachable red in the other direction. Widening the handler to bare
        `Exception` would make the first test pass and this one fail, and that
        trade is the whole reason the base type exists."""

        class Broken(self._FailingAdapter):
            def poll(self, submission_id):
                raise ZeroDivisionError("a real bug, not a backend refusing")

        ADAPTER.register("broken-test-backend", Broken)
        with self.assertRaises(ZeroDivisionError):
            REMOTE_CLI.main(
                ["poll", "--submission-id", "s1", "--backend", "broken-test-backend"]
            )


class RealDigestLoaderTests(unittest.TestCase):
    """The one path in `submit` every other test replaces with a stub.

    Injecting a digest is what keeps the submit tests fast and independent of
    any repository's source tree, but it means the real loader — a path
    reaching out of this skill into `proposal-implementation`'s kit — is wired
    and never exercised. A path nothing runs is a path that breaks when the
    file it points at moves, and the break surfaces at submit time, on the one
    run that was about to spend an afternoon of somebody's machine.
    """

    def test_the_real_loader_returns_a_working_digest_function(self) -> None:
        digest = REMOTE_CLI._load_source_digest()
        self.assertTrue(callable(digest))
        computed = digest(REPOSITORY_ROOT, "MIL_CREDA_Benchmark")
        self.assertRegex(computed, r"^[0-9a-f]{64}$")

    def test_the_loader_fails_loudly_when_its_target_is_gone(self) -> None:
        """Reachable red for the test above: it passes only because the file is
        where the loader expects it, so the failure has to be reachable by
        moving it. A loader that quietly returned something on a missing file
        would make the parity it depends on unverifiable."""
        kit = (REPOSITORY_ROOT / ".claude/skills/proposal-implementation"
               / "assets/kit/nb/report_digest.py")
        self.assertTrue(kit.exists(), "the loader's target moved; update the loader")
        hidden = kit.with_suffix(".py.hidden")
        kit.rename(hidden)
        try:
            with self.assertRaises(Exception):
                REMOTE_CLI._load_source_digest()
        finally:
            hidden.rename(kit)


class SubmitTests(unittest.TestCase):
    """`remote_cli.cmd_submit()` — the whole submit path, FakeAdapter only.

    No live account and no concrete backend are involved anywhere in this
    class; `adapters/kaggle.py` does not exist yet (a later task).
    """

    def setUp(self) -> None:
        # `submit` now gates a job-folder submission on the three pin
        # conditions. This class's subject is the submit path itself —
        # product resolution, ledger placement, capacity — and its
        # fixtures are plain directories rather than git repositories, so
        # the whole-precondition seam is stubbed to keep the class offline
        # and deterministic. `SubmitPinGateTests` drives the gate against
        # real git repositories.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "verify_pin_preconditions", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_submit_appends_exactly_one_submitted_event_with_a_fresh_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            digest_calls: list[tuple[Path, str]] = []

            def fake_source_digest(resolved_target: Path, name: str) -> str:
                digest_calls.append((resolved_target, name))
                return "d" * 64

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            result = REMOTE_CLI.cmd_submit(
                target=target,
                entrypoint=notebook,
                worker="w1",
                requested=1,
                adapter=adapter,
                source_digest=fake_source_digest,
            )

            # target.resolve(), not the raw tmp path: on darwin, tempfile's
            # own /var/folders path is itself a symlink to /private/var, so
            # only the resolved form matches what cmd_submit actually wrote.
            ledger_path = target.resolve() / "MIL-CREDA" / ".remote-execution" / "ledger.jsonl"
            self.assertEqual(result["ledgerPath"], ledger_path)
            lines = ledger_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

            event = json.loads(lines[0])
            self.assertEqual(event["kind"], "submitted")
            self.assertEqual(event["entrypoint"], "Notebooks/a.ipynb")
            self.assertEqual(event["sourceDigest"], "d" * 64)
            self.assertEqual(event["submissionId"], result["submission"].id)

            # Computed fresh at submit time — called exactly once, with the
            # resolved target this call actually used.
            self.assertEqual(len(digest_calls), 1)
            self.assertEqual(digest_calls[0], (target.resolve(), "MIL-CREDA"))

    def test_submit_refuses_a_symlink_escaping_notebooks_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            outside = Path(tmp) / "outside.ipynb"
            outside.write_text("{}", encoding="utf-8")
            link = notebooks / "evil.ipynb"
            os.symlink(outside, link)

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            with self.assertRaises(REMOTE_CLI.PathGuardError):
                REMOTE_CLI.cmd_submit(
                    target=target,
                    entrypoint=link,
                    worker="w1",
                    requested=1,
                    adapter=adapter,
                    source_digest=lambda t, n: "d" * 64,
                )

            ledger_path = target / "MIL-CREDA" / ".remote-execution" / "ledger.jsonl"
            self.assertFalse(ledger_path.exists())

    def test_target_must_resolve_to_an_existing_dir_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_target = Path(tmp) / "does-not-exist"
            adapter = FakeAdapter(worker_id="w1", capacity=2)

            with self.assertRaises(REMOTE_CLI.RemoteCLIError):
                REMOTE_CLI.cmd_submit(
                    target=missing_target,
                    entrypoint=missing_target / "MIL-CREDA" / "Notebooks" / "a.ipynb",
                    worker="w1",
                    requested=1,
                    adapter=adapter,
                    source_digest=lambda t, n: "d" * 64,
                )

            self.assertFalse(missing_target.exists())

    def test_relative_target_is_resolved_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            original_cwd = Path.cwd()
            os.chdir(tmp)
            try:
                adapter = FakeAdapter(worker_id="w1", capacity=2)
                result = REMOTE_CLI.cmd_submit(
                    target=Path("repo"),  # relative to the tmp dir just chdir'd into
                    entrypoint=Path("repo/MIL-CREDA/Notebooks/a.ipynb"),
                    worker="w1",
                    requested=1,
                    adapter=adapter,
                    source_digest=lambda t, n: "d" * 64,
                )
            finally:
                os.chdir(original_cwd)

            # Written under the resolved absolute target...
            expected_ledger = (target / "MIL-CREDA" / ".remote-execution" / "ledger.jsonl").resolve()
            self.assertEqual(result["ledgerPath"], expected_ledger)
            self.assertTrue(expected_ledger.exists())

            # ...and nothing leaked into the real process cwd this test
            # started from (the repository checkout itself), which is what
            # a relative `--target` resolved against the wrong directory at
            # write time would otherwise have produced.
            self.assertFalse((original_cwd / "repo").exists())

    def test_relative_target_is_resolved_before_any_write_for_job_folder_shape(
        self,
    ) -> None:
        """The same resolve-first guarantee the legacy-shape test above
        proves, exercised against the job-folder shape too — `cmd_submit`'s
        own `target = Path(target).resolve()` runs before
        `guard_entrypoint()` ever sees either shape, not just the legacy
        one.

        A `run-config.json` declaring a product is part of this fixture
        (T6b): before, `cmd_submit` never resolved a product for this
        shape at all, so this test only proved resolve-first mechanics
        without asserting where the ledger actually landed. Now that
        `cmd_submit` genuinely resolves a product via `product_for()`, this
        test also proves it lands under that declared product rather than
        under `tools` — the two guarantees are exercised together, not
        conflated: `SubmitTests` above already covers the product-not-
        resolvable-is-refused case on its own.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "MIL-CREDA").mkdir(parents=True)
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            _write_job_folder_run_config(job_dir)

            original_cwd = Path.cwd()
            os.chdir(tmp)
            try:
                adapter = FakeAdapter(worker_id="w1", capacity=2)
                result = REMOTE_CLI.cmd_submit(
                    target=Path("repo"),
                    entrypoint=Path("repo/tools/kaggle/search-a/runner.ipynb"),
                    worker="w1",
                    requested=1,
                    adapter=adapter,
                    source_digest=lambda t, n: "d" * 64,
                )
            finally:
                os.chdir(original_cwd)

            # The guard admitted the job-folder shape and resolved the
            # entrypoint under the resolved (not relative) target, proven
            # by the ledger existing at an absolute path with nothing
            # leaking into the real process cwd this test started from.
            self.assertTrue(Path(result["ledgerPath"]).is_absolute())
            self.assertTrue(Path(result["ledgerPath"]).exists())
            self.assertFalse((original_cwd / "repo").exists())

            # And it landed under the declared product, not under "tools".
            self.assertEqual(
                Path(result["ledgerPath"]),
                (target.resolve() / "MIL-CREDA" / ".remote-execution" / "ledger.jsonl"),
            )

    def test_job_folder_submit_with_declared_product_lands_under_that_product_not_tools(
        self,
    ) -> None:
        """The T6b defect, reproduced then corrected: a job-folder
        submission whose `run-config.json` names a product must land its
        ledger under THAT product, never under `tools` (the inline
        `parts[0]` derivation this replaces would have produced `"tools"`
        here, since that is the entrypoint's own first path component).
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "MIL-CREDA").mkdir(parents=True)
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            _write_job_folder_run_config(job_dir)

            digest_calls: list[tuple[Path, str]] = []

            def fake_source_digest(resolved_target: Path, name: str) -> str:
                digest_calls.append((resolved_target, name))
                return "d" * 64

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            result = REMOTE_CLI.cmd_submit(
                target=target,
                entrypoint=notebook,
                worker="w1",
                requested=1,
                adapter=adapter,
                source_digest=fake_source_digest,
            )

            ledger_path = (
                target.resolve() / "MIL-CREDA" / ".remote-execution" / "ledger.jsonl"
            )
            self.assertEqual(result["ledgerPath"], ledger_path)
            self.assertTrue(ledger_path.exists())

            # Never under "tools" -- the exact defect this test corrects.
            tools_ledger = (
                target.resolve() / "tools" / ".remote-execution" / "ledger.jsonl"
            )
            self.assertFalse(tools_ledger.exists())

            lines = ledger_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[0])
            self.assertEqual(event["kind"], "submitted")
            self.assertEqual(event["entrypoint"], "tools/kaggle/search-a/runner.ipynb")

            # The digest is computed over the resolved product's own tree,
            # never over "tools".
            self.assertEqual(digest_calls, [(target.resolve(), "MIL-CREDA")])

    def test_submit_explicit_product_override_wins_over_the_declared_one(self) -> None:
        """Triangulates the job-folder case above with a DIFFERENT product,
        proving `cmd_submit` actually wires an explicit override through to
        `product_for`, not merely that `product_for` itself supports one.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "OverrideProduct").mkdir(parents=True)
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            _write_job_folder_run_config(job_dir)
            # "MIL-CREDA" is deliberately never created under target: if the
            # declared value were used instead of the override, product_for
            # would refuse for a not-existing-directory reason, not silently
            # succeed under the wrong product.

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            result = REMOTE_CLI.cmd_submit(
                target=target,
                entrypoint=notebook,
                worker="w1",
                requested=1,
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
                product="OverrideProduct",
            )

            ledger_path = (
                target.resolve() / "OverrideProduct" / ".remote-execution" / "ledger.jsonl"
            )
            self.assertEqual(result["ledgerPath"], ledger_path)
            self.assertTrue(ledger_path.exists())

    def test_job_folder_submit_with_no_resolvable_product_is_refused_not_recorded(
        self,
    ) -> None:
        """A job-folder submission with no declared product and no explicit
        override must be REFUSED -- never silently recorded under a guessed
        product (`tools` or otherwise), and never allowed to reach the
        adapter at all.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            # No run-config.json at all, no --product override.

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            with self.assertRaises(REMOTE_CLI.RemoteCLIError):
                REMOTE_CLI.cmd_submit(
                    target=target,
                    entrypoint=notebook,
                    worker="w1",
                    requested=1,
                    adapter=adapter,
                    source_digest=lambda t, n: "d" * 64,
                )

            # Nothing reached the adapter, and nothing was written anywhere:
            # a refusal, not a mis-recorded submission.
            self.assertEqual(adapter._next_id, 0)
            tools_ledger = (
                target.resolve() / "tools" / ".remote-execution" / "ledger.jsonl"
            )
            self.assertFalse(tools_ledger.exists())

    def test_submit_parser_exposes_a_product_override_flag(self) -> None:
        """Step 1 of `product_for`'s four-step order -- an explicit
        `--product` -- has to actually be reachable from the command line,
        not merely accepted by `product_for` itself.
        """
        parser = REMOTE_CLI._build_parser()
        args = parser.parse_args(
            [
                "submit",
                "--target", "/tmp/does-not-need-to-exist",
                "--entrypoint", "/tmp/does-not-need-to-exist/a.ipynb",
                "--worker", "w1",
                "--backend", "fake",
                "--product", "MIL-CREDA",
            ]
        )
        self.assertEqual(args.product, "MIL-CREDA")

    def test_submit_parser_product_flag_defaults_to_none(self) -> None:
        parser = REMOTE_CLI._build_parser()
        args = parser.parse_args(
            [
                "submit",
                "--target", "/tmp/does-not-need-to-exist",
                "--entrypoint", "/tmp/does-not-need-to-exist/a.ipynb",
                "--worker", "w1",
                "--backend", "fake",
            ]
        )
        self.assertIsNone(args.product)

    def test_remote_cli_module_names_no_service(self) -> None:
        """The leak guard for this module, over the raw file text — a
        docstring naming a backend to explain an example would be exactly
        the leak this skill's seam exists to prevent everywhere above the
        adapter, and this CLI sits at the very top of that chain.
        """
        source = REMOTE_CLI_SCRIPT.read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)


def _append_pending_submission(
    ledger_path: Path, *, entrypoint: str, submission_id: str, worker: str, source_digest: str
) -> None:
    """Write a real `submitted` event to `ledger_path` through `LEDGER.append()`
    — never a hand-built file — so every fetch/reconcile test below starts
    from the exact same write path `cmd_submit` itself uses.
    """
    LEDGER.append(
        ledger_path,
        LEDGER.submitted_event(
            entrypoint=entrypoint,
            source_digest=source_digest,
            submission_id=submission_id,
            worker=worker,
            requested_capacity=1,
            granted_capacity=1,
        ),
    )


class CrashingFetchAdapter(FakeAdapter):
    """Simulates a process killed partway through `fetch()`: some bytes land
    under `into`, then the call raises before returning anything — the exact
    shape a real crash mid-download leaves behind.
    """

    def fetch(self, submission_id: str, into: Path) -> "ADAPTER.Fetched":
        into.mkdir(parents=True, exist_ok=True)
        (into / "partial.bin").write_text("only-partial-bytes", encoding="utf-8")
        raise ConnectionError("simulated crash mid-fetch (test double)")


class IncompleteFetchAdapter(FakeAdapter):
    """`fetch()` returns normally but reports `complete=False` — the
    backend's own signal that the result is not finished yet, distinct from
    a crash: nothing raised, but there is nothing to rename either.
    """

    def fetch(self, submission_id: str, into: Path) -> "ADAPTER.Fetched":
        into.mkdir(parents=True, exist_ok=True)
        (into / "still-running.bin").write_text("not done yet", encoding="utf-8")
        return ADAPTER.Fetched(path=into, complete=False, files=())


class ScriptedListActiveAdapter(FakeAdapter):
    """A `FakeAdapter` whose `list_active()` answers with a fixed,
    test-controlled set of ids, independent of anything `submit()`/
    `cancel()` did on this same instance.

    `reconcile` tests need to control exactly what "the service" claims is
    active without first driving every submission through this fake's own
    `submit()` — the ledger lines those tests build directly already stand
    in for "what was submitted"; this adapter only needs to stand in for
    "what the service currently says is active".
    """

    def __init__(
        self, worker_id: str = "w1", capacity: int = 2, active: tuple[str, ...] = ()
    ) -> None:
        super().__init__(worker_id=worker_id, capacity=capacity)
        self._active = tuple(active)

    def list_active(self, worker: str) -> list:
        return list(self._active)


class _SpySubmitAdapter(FakeAdapter):
    """A `FakeAdapter` that records the exact `Job` it was handed, so a
    test can assert what `cmd_submit()` actually constructed."""

    def __init__(self, worker_id: str = "w1", capacity: int = 2) -> None:
        super().__init__(worker_id=worker_id, capacity=capacity)
        self.last_job = None

    def submit(self, job) -> "ADAPTER.Submission":
        self.last_job = job
        return super().submit(job)


class PollTests(unittest.TestCase):
    def test_poll_refuses_a_status_outside_the_five_state_vocabulary(self) -> None:
        class MisbehavingAdapter(FakeAdapter):
            def poll(self, submission_id: str):
                # Bypasses `ADAPTER.Status.__post_init__`'s own vocabulary
                # check entirely — a raw namespace, not a genuine `Status`
                # instance. This is exactly the "adapter's fault" case
                # `cmd_poll`'s own refusal has to catch itself, rather than
                # trusting every adapter to have gone through the
                # dataclass's own constructor.
                return SimpleNamespace(state="succeeded", detail="not this seam's word")

        adapter = MisbehavingAdapter(worker_id="w1", capacity=2)
        job = ADAPTER.Job(entrypoint=Path("Notebooks/a.ipynb"), run_config={}, worker="w1")
        submission = adapter.submit(job)

        with self.assertRaises(REMOTE_CLI.RemoteCLIError):
            REMOTE_CLI.cmd_poll(submission_id=submission.id, adapter=adapter)

    def test_poll_accepts_a_genuinely_valid_status(self) -> None:
        adapter = FakeAdapter(worker_id="w1", capacity=2)
        job = ADAPTER.Job(entrypoint=Path("Notebooks/a.ipynb"), run_config={}, worker="w1")
        submission = adapter.submit(job)

        status = REMOTE_CLI.cmd_poll(submission_id=submission.id, adapter=adapter)
        self.assertIn(status.state, ADAPTER.STATES)


class StatusTests(unittest.TestCase):
    def test_status_reports_pending_stale_in_flight_and_unreadable_lines_and_calls_no_adapter(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME / REMOTE_CLI.LEDGER_FILENAME
            )
            _append_pending_submission(
                ledger_path,
                entrypoint="Notebooks/a.ipynb",
                submission_id="s1",
                worker="w1",
                source_digest="digest-old",
            )
            with open(ledger_path, "a", encoding="utf-8") as handle:
                handle.write('{"kind": "submitted", "entrypoint": "Note')  # a torn tail

            result = REMOTE_CLI.cmd_status(
                target=target, entrypoint=notebook, source_digest=lambda t, n: "digest-new"
            )

            self.assertEqual(result["entrypoints"]["Notebooks/a.ipynb"]["state"], "pending")
            self.assertIn("Notebooks/a.ipynb", result["staleInFlight"])
            self.assertEqual(result["unreadableLines"], 1)
            self.assertEqual(result["quarantined"], ())

            # `cmd_status`'s own signature accepts no adapter at all — this
            # is what makes "status reports; it never resolves" a structural
            # fact rather than a rule its body would otherwise have to be
            # trusted to follow.
            self.assertNotIn("adapter", inspect.signature(REMOTE_CLI.cmd_status).parameters)


class FetchTests(unittest.TestCase):
    """`remote_cli.cmd_fetch()` — materialize-then-rename, and the
    quarantine placement, FakeAdapter only.
    """

    def test_fetch_renames_into_place_and_appends_returned_only_on_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME / REMOTE_CLI.LEDGER_FILENAME
            )
            _append_pending_submission(
                ledger_path,
                entrypoint="Notebooks/a.ipynb",
                submission_id="s1",
                worker="w1",
                source_digest="d" * 64,
            )

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            # target.resolve(), not the raw tmp path — see the darwin
            # /var/folders-is-a-symlink gotcha noted elsewhere in this file.
            dest = target.resolve() / "MIL-CREDA" / "Results" / "shards" / "a"

            result = REMOTE_CLI.cmd_fetch(
                target=target,
                entrypoint=notebook,
                submission_id="s1",
                dest=dest,
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )

            self.assertTrue(result["complete"])
            self.assertEqual(result["verdict"], "current")
            self.assertEqual(result["path"], dest)
            self.assertTrue((dest / "result.txt").exists())

            partial_dest = dest.with_name(dest.name + REMOTE_CLI.PARTIAL_SUFFIX)
            self.assertFalse(partial_dest.exists())

            lines = ledger_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            appended = json.loads(lines[-1])
            self.assertEqual(appended["kind"], "returned")
            self.assertEqual(appended["submissionId"], "s1")
            self.assertEqual(appended["artifactPath"], str(dest))

    def test_crash_mid_fetch_leaves_pending_and_appends_no_returned_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME / REMOTE_CLI.LEDGER_FILENAME
            )
            _append_pending_submission(
                ledger_path,
                entrypoint="Notebooks/a.ipynb",
                submission_id="s1",
                worker="w1",
                source_digest="d" * 64,
            )
            lines_before = ledger_path.read_text(encoding="utf-8")

            adapter = CrashingFetchAdapter(worker_id="w1", capacity=2)
            dest = target.resolve() / "MIL-CREDA" / "Results" / "shards" / "a"

            with self.assertRaises(ConnectionError):
                REMOTE_CLI.cmd_fetch(
                    target=target,
                    entrypoint=notebook,
                    submission_id="s1",
                    dest=dest,
                    adapter=adapter,
                    source_digest=lambda t, n: "d" * 64,
                )

            # No returned event: the ledger is byte-identical, and the
            # submission still folds to pending.
            self.assertEqual(ledger_path.read_text(encoding="utf-8"), lines_before)
            state = LEDGER.fold(
                ledger_path.read_text(encoding="utf-8").splitlines(), live_digest="d" * 64
            )
            self.assertEqual(state.entrypoints["Notebooks/a.ipynb"].state, "pending")

            # The .partial/ directory holds exactly the crash's partial
            # bytes and was never renamed into `dest`.
            partial_dest = dest.with_name(dest.name + REMOTE_CLI.PARTIAL_SUFFIX)
            self.assertTrue((partial_dest / "partial.bin").exists())
            self.assertFalse(dest.exists())

    def test_incomplete_fetch_renames_nothing_and_appends_no_returned_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME / REMOTE_CLI.LEDGER_FILENAME
            )
            _append_pending_submission(
                ledger_path,
                entrypoint="Notebooks/a.ipynb",
                submission_id="s1",
                worker="w1",
                source_digest="d" * 64,
            )
            lines_before = ledger_path.read_text(encoding="utf-8")

            adapter = IncompleteFetchAdapter(worker_id="w1", capacity=2)
            dest = target.resolve() / "MIL-CREDA" / "Results" / "shards" / "a"

            result = REMOTE_CLI.cmd_fetch(
                target=target,
                entrypoint=notebook,
                submission_id="s1",
                dest=dest,
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )

            self.assertFalse(result["complete"])
            self.assertIsNone(result["event"])
            self.assertEqual(ledger_path.read_text(encoding="utf-8"), lines_before)
            self.assertFalse(dest.exists())

    def test_observed_concurrency_reflects_actual_pending_not_the_grant(self) -> None:
        """(packer attempts 2, service actually runs 1 → recorded 1):
        `plan()` grants capacity for two concurrent jobs on this worker, but
        only one is ever actually submitted and pending when its result
        comes back — the service throttled below the grant, and
        `observedConcurrency` is what makes that visible instead of assumed.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            plan = PACKER.plan(
                adapter=adapter,
                worker_id="w1",
                requested=2,
                ledger_lines=[],
                live_digest="d" * 64,
            )
            self.assertEqual(plan.granted, 2)

            ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME / REMOTE_CLI.LEDGER_FILENAME
            )
            _append_pending_submission(
                ledger_path,
                entrypoint="Notebooks/a.ipynb",
                submission_id="s1",
                worker="w1",
                source_digest="d" * 64,
            )

            dest = target.resolve() / "MIL-CREDA" / "Results" / "shards" / "a"
            result = REMOTE_CLI.cmd_fetch(
                target=target,
                entrypoint=notebook,
                submission_id="s1",
                dest=dest,
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )

            self.assertEqual(result["event"]["observedConcurrency"], 1)
            self.assertNotEqual(result["event"]["observedConcurrency"], plan.granted)

    def test_stale_result_is_quarantined_and_never_enumerable_under_results_shards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME / REMOTE_CLI.LEDGER_FILENAME
            )
            _append_pending_submission(
                ledger_path,
                entrypoint="Notebooks/a.ipynb",
                submission_id="s1",
                worker="w1",
                source_digest="digest-1",
            )
            _append_pending_submission(  # a resubmission after a source edit
                ledger_path,
                entrypoint="Notebooks/a.ipynb",
                submission_id="s2",
                worker="w1",
                source_digest="digest-2",
            )

            # A real, enumerable tree standing in for what a shard reader
            # walks in the actual target repository.
            shards_dir = target.resolve() / "MIL-CREDA" / "Results" / "shards"
            shards_dir.mkdir(parents=True)

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            # s1's own late result naively requests a path INSIDE
            # Results/shards/ — exactly what an unaware caller might ask
            # for; the point of this test is that fetch overrides it anyway.
            requested_dest = shards_dir / "a"

            result = REMOTE_CLI.cmd_fetch(
                target=target,
                entrypoint=notebook,
                submission_id="s1",
                dest=requested_dest,
                adapter=adapter,
                source_digest=lambda t, n: "digest-2",
            )

            self.assertEqual(result["verdict"], "fromStaleSubmission")
            quarantine_path = result["path"]
            self.assertTrue((quarantine_path / "result.txt").exists())

            # Fetched and parked, never discarded — but never at the path
            # the caller asked for either.
            self.assertFalse(requested_dest.exists())
            self.assertNotIn(shards_dir, quarantine_path.parents)

            # The placement is the guarantee, not a filter: walking the
            # exact tree a shard reader enumerates finds nothing at all.
            enumerated = list(shards_dir.rglob("*"))
            self.assertEqual(enumerated, [])


class ReconcileTests(unittest.TestCase):
    def test_reconcile_reports_orphan_remote_without_fabricating_a_submitted_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME / REMOTE_CLI.LEDGER_FILENAME
            )
            _append_pending_submission(
                ledger_path,
                entrypoint="Notebooks/a.ipynb",
                submission_id="s1",
                worker="w1",
                source_digest="d" * 64,
            )
            before = ledger_path.read_bytes()

            # The service reports an id (s2) this ledger never recorded.
            adapter = ScriptedListActiveAdapter(worker_id="w1", active=("s1", "s2"))

            result = REMOTE_CLI.cmd_reconcile(
                target=target,
                entrypoint=notebook,
                worker="w1",
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )

            self.assertEqual(result["orphanRemote"], ("s2",))
            self.assertEqual(result["orphanLocal"], ())
            self.assertEqual(result["resolved"], ())

            # No submitted line was fabricated for s2 — never auto-adopted.
            after = ledger_path.read_bytes()
            self.assertEqual(before, after)

    def test_reconcile_reports_orphan_local_and_resolve_appends_exactly_one_errored_event(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME / REMOTE_CLI.LEDGER_FILENAME
            )
            _append_pending_submission(
                ledger_path,
                entrypoint="Notebooks/a.ipynb",
                submission_id="s1",
                worker="w1",
                source_digest="d" * 64,
            )

            # The service no longer lists s1 at all.
            adapter = ScriptedListActiveAdapter(worker_id="w1", active=())

            reported = REMOTE_CLI.cmd_reconcile(
                target=target,
                entrypoint=notebook,
                worker="w1",
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )
            self.assertEqual(reported["orphanLocal"], ("s1",))
            # Merely reporting (the default, resolve=False) appends nothing.
            self.assertEqual(
                len(ledger_path.read_text(encoding="utf-8").splitlines()), 1
            )

            resolved = REMOTE_CLI.cmd_reconcile(
                target=target,
                entrypoint=notebook,
                worker="w1",
                adapter=adapter,
                resolve=True,
                source_digest=lambda t, n: "d" * 64,
            )
            self.assertEqual(len(resolved["resolved"]), 1)
            self.assertEqual(resolved["resolved"][0]["kind"], "errored")
            self.assertEqual(resolved["resolved"][0]["submissionId"], "s1")
            self.assertEqual(resolved["resolved"][0]["reason"], "not-found-at-service")

            lines_after_resolve = ledger_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines_after_resolve), 2)
            appended = json.loads(lines_after_resolve[-1])
            self.assertEqual(appended["kind"], "errored")
            self.assertEqual(appended["reason"], "not-found-at-service")


# A stand-in credential in the shape kaggle-accounts actually materializes
# — the `KGAT_` prefix plus 32 hex characters, as a plain-text file — with
# an obviously fake body no real account could ever hold. Deliberately NOT
# a value any assertion in this module also matches by accident: a fixture
# whose own name satisfies the assertion made of it is how a test in this
# suite already went falsely green once.
FIXTURE_TOKEN = "KGAT_" + "0123456789abcdef" * 2


def _write_fake_token(directory: Path, value: str = FIXTURE_TOKEN) -> Path:
    """Write a credential file the way `cmd_materialize` writes one — the
    token itself and a single trailing newline, nothing else — and answer
    with its path.

    The trailing newline is not decoration: it is the byte
    `accounts_cli.py`'s `cmd_materialize` genuinely appends, and a fixture
    without it could not tell a consumer that strips from one that does
    not.
    """
    directory.mkdir(parents=True, exist_ok=True)
    token_path = directory / "token"
    token_path.write_text(value + "\n", encoding="utf-8")
    return token_path


def _write_fake_kaggle(
    bin_dir: Path,
    *,
    status_text: str = "complete",
    exit_code: int = 0,
    sleep_seconds: float | None = None,
) -> Path:
    """A minimal stand-in for the real `kaggle` executable.

    Never touches a network, never reads whatever `KAGGLE_API_TOKEN`
    points to (real or fake), and answers `kernels push|status|output|list`
    just well enough to drive `KaggleAdapter` through its own pipeline.
    Placed on disk with an executable bit and a shebang so it can be
    invoked directly by `subprocess.run(shell=False, ...)`, the same way
    the genuine `kaggle` executable would be.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "kaggle"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, time\n"
        "from pathlib import Path\n"
        f"SLEEP = {sleep_seconds!r}\n"
        "if SLEEP:\n"
        "    time.sleep(SLEEP)\n"
        f"EXIT_CODE = {exit_code!r}\n"
        "if EXIT_CODE != 0:\n"
        "    print('simulated failure', file=sys.stderr)\n"
        "    sys.exit(EXIT_CODE)\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['kernels', 'push']:\n"
        "    print('kernel version 1 successfully pushed')\n"
        "    sys.exit(0)\n"
        "if args[:2] == ['kernels', 'status']:\n"
        "    ref = args[2] if len(args) > 2 else 'unknown-ref'\n"
        f"    print(ref + ' has status \"{status_text}\"')\n"
        "    sys.exit(0)\n"
        "if args[:2] == ['kernels', 'output']:\n"
        "    idx = args.index('-p')\n"
        "    outdir = Path(args[idx + 1])\n"
        "    outdir.mkdir(parents=True, exist_ok=True)\n"
        "    (outdir / 'result.txt').write_text('ok', encoding='utf-8')\n"
        "    print('output downloaded')\n"
        "    sys.exit(0)\n"
        "if args[:2] == ['kernels', 'list']:\n"
        "    print('ref,status')\n"
        "    sys.exit(0)\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


class KaggleAdapterTests(unittest.TestCase):
    """`adapters/kaggle.py` — the one file in this skill allowed to name a
    service. No test in this class reaches the network or a real Kaggle
    account: every subprocess call goes to a fake `kaggle` executable this
    class writes to a temp `PATH` entry, or to a fake `accounts_cli.py`
    stub passed in by path.

    Every test here has a reachable red: `adapters/kaggle.py` did not exist
    before this task, so the whole module fails to import and every test
    in this class fails to collect.
    """

    def test_adapter_source_contains_no_accounts_json_or_store_literal(self) -> None:
        """The leak guard specific to this module: a static scan over the
        raw file text (source and every docstring alike) for the two
        literals that would tie this adapter's own code to reading
        `kaggle-accounts`' credential file directly, rather than only ever
        running its sanctioned `list --json` command as a subprocess.
        """
        source = KAGGLE_SCRIPT.read_text(encoding="utf-8").lower()
        for leaked in ("accounts.json", "store"):
            self.assertNotIn(leaked, source, leaked)

    def test_kaggle_adapter_satisfies_the_abc(self) -> None:
        self.assertIsInstance(KAGGLE.KaggleAdapter(), ADAPTER.Adapter)

    def test_a_kaggle_adapter_missing_one_method_cannot_instantiate(self) -> None:
        """The ABC's structural guarantee holds for a concrete subclass
        too, not only for `adapter.py`'s own generic incomplete-subclass
        case (`AdapterSeamTests`): re-marking one already-implemented
        method abstract on a subclass of `KaggleAdapter` itself must make
        that subclass uninstantiable.
        """
        from abc import abstractmethod

        class BrokenKaggleAdapter(KAGGLE.KaggleAdapter):
            cancel = abstractmethod(lambda self, submission_id: None)

        with self.assertRaises(TypeError):
            BrokenKaggleAdapter()

    def test_the_accelerator_request_is_declared_here_as_a_request_not_a_receipt(
        self,
    ) -> None:
        """A boolean, because that is the only accelerator vocabulary the
        installed client can express — see `AcceleratorRequestDoctrineTests`
        for the measurement behind that, and for why a named accelerator is
        not requestable here at all.
        """
        self.assertIs(KAGGLE.REQUEST_GPU, True)
        self.assertFalse(hasattr(KAGGLE, "REQUESTED_ACCELERATOR"))

    def test_kaggle_worker_capacity_is_two_documented_as_the_batch_session_figure(self) -> None:
        """`KAGGLE_WORKER_CAPACITY` states Kaggle's own concurrent-kernel
        allowance as observed against `kernels push` batch sessions — not
        as a universal property of the service. This pins both the value
        and the fact that its comment says so, so a future revision of the
        number cannot silently drop the caveat that makes revising it safe.
        """
        self.assertEqual(KAGGLE.KAGGLE_WORKER_CAPACITY, 2)

        source_lines = KAGGLE_SCRIPT.read_text(encoding="utf-8").splitlines()
        constant_index = next(
            i
            for i, line in enumerate(source_lines)
            if line.startswith("KAGGLE_WORKER_CAPACITY = ")
        )
        comment_lines: list[str] = []
        i = constant_index - 1
        while i >= 0 and source_lines[i].lstrip().startswith("#"):
            comment_lines.append(source_lines[i])
            i -= 1
        comment = "\n".join(reversed(comment_lines)).lower()

        self.assertIn("batch-session", comment)
        self.assertIn("kernels push", comment)
        self.assertIn("revis", comment)
        self.assertIn("never", comment)
        self.assertIn("universal", comment)

    def test_workers_still_answers_when_the_credential_file_is_unreadable(self) -> None:
        """Proves `workers()` never opens the credential file itself: a
        genuinely unreadable decoy file named the way that file is named
        sits on disk throughout this test, and `workers()` still answers
        normally, because the only thing it ever does is run the sanctioned
        `list --json` command as a subprocess — never open anything by
        path on its own.

        The fixture's own brokenness is asserted BEFORE trusting the
        result: a negative test whose fixture silently failed to break
        would report success while testing nothing.
        """
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root ignores file permission bits; this check needs a non-root run")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            decoy = tmp_path / "accounts.json"
            decoy.write_text('{"accounts": []}', encoding="utf-8")
            decoy.chmod(0o000)
            try:
                with self.assertRaises(PermissionError):
                    decoy.read_text(encoding="utf-8")

                fake_accounts_cli = tmp_path / "fake_accounts_cli.py"
                fake_accounts_cli.write_text(
                    "import json\n"
                    "print(json.dumps({'accounts': [{'username': 'acct-1'}]}))\n",
                    encoding="utf-8",
                )

                adapter = KAGGLE.KaggleAdapter(accounts_cli=fake_accounts_cli)
                workers = adapter.workers()
            finally:
                decoy.chmod(0o644)

            self.assertEqual([w.id for w in workers], ["acct-1"])
            self.assertEqual(workers[0].capacity, KAGGLE.KAGGLE_WORKER_CAPACITY)

    def test_a_service_status_outside_the_five_value_vocabulary_is_translated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir, status_text="cancelAcknowledged")
            token_path = _write_fake_token(tmp_path / "creds")

            handle = KAGGLE.CredentialHandle(worker_id="acct-1", token_path=token_path)
            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"acct-1": handle})
                status = adapter.poll("acct-1/kernel-1")

            self.assertEqual(status.state, "unknown")
            self.assertIn("cancelAcknowledged", status.detail)

    def test_a_genuinely_valid_status_translates_straight_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir, status_text="running")
            token_path = _write_fake_token(tmp_path / "creds")

            handle = KAGGLE.CredentialHandle(worker_id="acct-1", token_path=token_path)
            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"acct-1": handle})
                status = adapter.poll("acct-1/kernel-1")

            self.assertEqual(status.state, "running")

    def test_kaggle_cli_2_2_4s_enum_repr_status_translates_correctly(self) -> None:
        """Kaggle CLI 2.2.4 was confirmed, against a real running kernel,
        to print `has status "KernelWorkerStatus.RUNNING"` -- the enum's
        own `str()` repr, quoted whole -- rather than the bare word
        `"running"` earlier versions apparently used. Lowercasing that
        whole repr produces `"kernelworkerstatus.running"`, which matches
        no key in `_KAGGLE_STATUS_TO_SEAM` and silently fell through to
        `"unknown"` even though the kernel was, in fact, running.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir, status_text="KernelWorkerStatus.RUNNING")
            token_path = _write_fake_token(tmp_path / "creds")

            handle = KAGGLE.CredentialHandle(worker_id="acct-1", token_path=token_path)
            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"acct-1": handle})
                status = adapter.poll("acct-1/kernel-1")

            self.assertEqual(status.state, "running")
            self.assertIn("KernelWorkerStatus.RUNNING", status.detail)

    def test_non_zero_exit_from_the_service_cli_produces_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir, exit_code=7)
            token_path = _write_fake_token(tmp_path / "creds")

            handle = KAGGLE.CredentialHandle(worker_id="acct-1", token_path=token_path)
            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"acct-1": handle})
                with self.assertRaises(KAGGLE.KaggleAdapterError):
                    adapter.poll("acct-1/kernel-1")

    def test_subprocess_timeout_yields_a_refusal_not_a_fabricated_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir, sleep_seconds=5)
            token_path = _write_fake_token(tmp_path / "creds")

            handle = KAGGLE.CredentialHandle(worker_id="acct-1", token_path=token_path)
            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"acct-1": handle}, timeout=0.3)
                with self.assertRaises(KAGGLE.KaggleAdapterError):
                    adapter.poll("acct-1/kernel-1")

    def test_worker_id_with_shell_metacharacters_reaches_argv_verbatim_executes_nothing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir)
            token_path = _write_fake_token(tmp_path / "creds")
            # No "/" anywhere in this string: `poll()` derives a worker id
            # from a submission id by splitting on the FIRST "/", and this
            # test's own `/kernel-1` suffix is what that split is meant to
            # find — a malicious segment containing its own "/" would
            # confuse this test's own arithmetic, not the adapter's.
            marker_name = "pwned-marker"
            malicious_worker = (
                f"acct-1$(touch {marker_name})`touch {marker_name}`;touch {marker_name}"
            )
            handle = KAGGLE.CredentialHandle(worker_id=malicious_worker, token_path=token_path)

            recorded_argv: list[list[str]] = []
            real_run = subprocess.run

            def recording_run(argv, **kwargs):
                recorded_argv.append(list(argv))
                return real_run(argv, **kwargs)

            marker_path = Path.cwd() / marker_name
            try:
                with unittest.mock.patch.dict(
                    os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
                ), unittest.mock.patch.object(
                    KAGGLE.subprocess, "run", side_effect=recording_run
                ):
                    adapter = KAGGLE.KaggleAdapter(credentials={malicious_worker: handle})
                    status = adapter.poll(f"{malicious_worker}/kernel-1")

                # Never executed: shell=False plus a list argv means the
                # whole malicious string travels as ONE argv element, never
                # evaluated by a shell.
                self.assertFalse(marker_path.exists())
                self.assertEqual(status.state, "complete")
                self.assertEqual(
                    recorded_argv[-1][-1], f"{malicious_worker}/kernel-1"
                )
            finally:
                if marker_path.exists():
                    marker_path.unlink()

    def test_kaggle_registers_assemble_metadata_requesting_the_pinned_accelerator(
        self,
    ) -> None:
        """`adapters/kaggle.py` registers `assemble_metadata` under the
        metadata registry, and calling it produces `kernel-metadata.json`
        carrying the accelerator request under `enable_gpu` — the key
        `kernels_push` actually reads. `machine_shape`, which this template
        used to carry instead, is read by nothing in the installed client
        and never transmitted; `AcceleratorRequestDoctrineTests` holds that
        against the installed source directly. The template also carries
        every field a push needs at minimum: `enable_internet` (the runner clones over git
        inside the kernel, and Kaggle disables internet by default),
        `language`, `kernel_type`, and `is_private`. `id` and `code_file`
        are present but deliberately blank here — this call runs before a
        worker is assigned, so neither can be known yet; `submit()`
        completes both in a staged copy (see below).
        """
        assembler = ADAPTER.resolve_metadata("kaggle")
        filename, text = assembler({"jobName": "domain-adaptation-2ep"})
        self.assertEqual(filename, "kernel-metadata.json")
        payload = json.loads(text)
        self.assertIs(payload["enable_gpu"], True)
        self.assertEqual(payload["language"], "python")
        self.assertEqual(payload["kernel_type"], "notebook")
        self.assertIs(payload["is_private"], True)
        self.assertIs(payload["enable_internet"], True)
        self.assertIn("id", payload)
        self.assertIn("code_file", payload)
        self.assertIn("title", payload)
        self.assertGreaterEqual(len(payload["title"]), 5)

    def test_submit_refuses_when_run_config_is_non_empty_and_metadata_file_is_absent(
        self,
    ) -> None:
        """A generated job (non-empty `run_config`) must ship its own
        metadata file beside the entrypoint before `submit()` ever shells
        out — pushing a folder the service will reject is worse than
        refusing here, before any subprocess runs. The patched
        `subprocess.run` below raises if invoked at all, proving the
        refusal happens without a real (or fake) service call.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            job_dir = tmp_path / "job"
            job_dir.mkdir()
            entrypoint = job_dir / "runner.ipynb"
            entrypoint.write_text("{}", encoding="utf-8")
            # Deliberately no kernel-metadata.json beside it.

            token_path = _write_fake_token(tmp_path / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)
            adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
            job = ADAPTER.Job(entrypoint=entrypoint, run_config={"mode": "full"}, worker="w1")

            with unittest.mock.patch.object(
                KAGGLE.subprocess,
                "run",
                side_effect=AssertionError("submit must refuse before shelling out"),
            ):
                with self.assertRaises(KAGGLE.KaggleAdapterError):
                    adapter.submit(job)

    def test_submit_proceeds_when_run_config_is_non_empty_and_metadata_file_is_present(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            job_dir = tmp_path / "job"
            job_dir.mkdir()
            entrypoint = job_dir / "runner.ipynb"
            entrypoint.write_text("{}", encoding="utf-8")
            (job_dir / "kernel-metadata.json").write_text("{}", encoding="utf-8")

            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir)
            token_path = _write_fake_token(tmp_path / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)

            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
                job = ADAPTER.Job(
                    entrypoint=entrypoint, run_config={"mode": "full"}, worker="w1"
                )
                submission = adapter.submit(job)

            self.assertEqual(submission.worker, "w1")

    def test_submit_with_empty_run_config_behaves_exactly_as_before_even_without_metadata(
        self,
    ) -> None:
        """Empty `run_config` is the legacy shape: submit proceeds even
        with no metadata file present, which is what keeps the credential
        sentinel test (a legacy-shaped `cmd_submit` call) green.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            notebooks = _make_product(tmp_path / "repo", "MIL-CREDA")
            entrypoint = notebooks / "a.ipynb"
            entrypoint.write_text("{}", encoding="utf-8")
            # No metadata file beside it, and none is required.

            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir)
            token_path = _write_fake_token(tmp_path / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)

            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
                job = ADAPTER.Job(entrypoint=entrypoint, run_config={}, worker="w1")
                submission = adapter.submit(job)

            self.assertEqual(submission.worker, "w1")

    def test_submit_completes_id_and_code_file_in_a_staged_copy_never_touching_the_job_folder(
        self,
    ) -> None:
        """`id` is `<owner>/<slug>` — it names the account, which is only
        known at submit time, not at `generate-job` time. `cmd_submit`
        only ever sets `run_config["mode"] = "smoke"` for a smoke run; an
        ordinary (non-smoke) job-folder submission carries an EMPTY
        `run_config`, exactly like the legacy shape. So the signal that
        must drive metadata completion is the metadata file's own
        presence beside the entrypoint, not `run_config` truthiness — this
        is the actual real-world path `generate-job` + `submit` takes.

        `submit()` must complete `id` and `code_file` in a STAGED COPY of
        the job folder and push that copy, leaving the versioned
        `kernel-metadata.json` inside the job folder itself byte-for-byte
        unchanged — the same folder pushed to a second worker must be able
        to receive a second, different `id` later.

        The slug in `id` is derived from the metadata's own `title`
        (`"papersmith-domain-adaptation"` here), never from the
        entrypoint's filename: confirmed against a real Kaggle account
        that a newly-created kernel's actual slug is the one the service
        derives from `title`, and every generated job folder's entrypoint
        is named `runner.ipynb` regardless of job — deriving the slug
        from that constant filename made every job-folder submission to
        the same worker collide on the identical ref `<worker>/runner`.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            job_dir = tmp_path / "job"
            job_dir.mkdir()
            entrypoint = job_dir / "runner.ipynb"
            entrypoint.write_text("{}", encoding="utf-8")
            original_metadata = json.dumps(
                {
                    "id": "",
                    "title": "papersmith-domain-adaptation",
                    "code_file": "",
                    "language": "python",
                    "kernel_type": "notebook",
                    "is_private": True,
                    "enable_internet": True,
                    "enable_gpu": True,
                }
            )
            (job_dir / "kernel-metadata.json").write_text(
                original_metadata, encoding="utf-8"
            )

            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            captured_metadata = tmp_path / "captured-kernel-metadata.json"
            fake_kaggle = bin_dir / "kaggle"
            fake_kaggle.write_text(
                "#!/usr/bin/env python3\n"
                "import shutil, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "if args[:2] == ['kernels', 'push']:\n"
                "    idx = args.index('-p')\n"
                "    src = Path(args[idx + 1]) / 'kernel-metadata.json'\n"
                f"    shutil.copyfile(src, {str(captured_metadata)!r})\n"
                "    print('kernel version 1 successfully pushed')\n"
                "    sys.exit(0)\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )
            fake_kaggle.chmod(0o755)

            token_path = _write_fake_token(tmp_path / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)

            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
                job = ADAPTER.Job(entrypoint=entrypoint, run_config={}, worker="w1")
                submission = adapter.submit(job)

            self.assertEqual(submission.id, "w1/papersmith-domain-adaptation")
            self.assertTrue(captured_metadata.is_file())
            pushed = json.loads(captured_metadata.read_text(encoding="utf-8"))
            self.assertEqual(pushed["id"], "w1/papersmith-domain-adaptation")
            self.assertEqual(pushed["code_file"], "runner.ipynb")
            self.assertIs(pushed["enable_gpu"], True)

            self.assertEqual(
                (job_dir / "kernel-metadata.json").read_text(encoding="utf-8"),
                original_metadata,
            )

    def test_submit_slug_comes_from_title_not_the_constant_entrypoint_filename(
        self,
    ) -> None:
        """Every generated job folder's entrypoint is named `runner.ipynb`
        — `jobfolder.py`'s own `RUNNER_FILENAME` constant, the same for
        every job. A slug derived from that filename alone is therefore
        the same string for every job-folder submission to a given
        worker, so two different jobs would silently collide on the
        identical kernel ref. `title` (`"papersmith-<job-name>"`) is what
        actually varies per job, and it is also what a real Kaggle
        account gives the created kernel as its slug — reached here by
        two different job names producing two different refs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir)
            token_path = _write_fake_token(tmp_path / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)

            refs = {}
            for job_name in ("phase1-run-e2e", "phase2-run-e2e"):
                job_dir = tmp_path / job_name
                job_dir.mkdir()
                entrypoint = job_dir / "runner.ipynb"
                entrypoint.write_text("{}", encoding="utf-8")
                (job_dir / "kernel-metadata.json").write_text(
                    json.dumps({
                        "id": "", "title": f"papersmith-{job_name}", "code_file": "",
                        "language": "python", "kernel_type": "notebook",
                        "is_private": True, "enable_internet": True,
                        "enable_gpu": True,
                    }),
                    encoding="utf-8",
                )
                with unittest.mock.patch.dict(
                    os.environ,
                    {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"},
                ):
                    adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
                    job = ADAPTER.Job(entrypoint=entrypoint, run_config={}, worker="w1")
                    refs[job_name] = adapter.submit(job).id

            assert refs["phase1-run-e2e"] != refs["phase2-run-e2e"], (
                f"both jobs collided on the same ref: {refs}"
            )
            self.assertEqual(refs["phase1-run-e2e"], "w1/papersmith-phase1-run-e2e")
            self.assertEqual(refs["phase2-run-e2e"], "w1/papersmith-phase2-run-e2e")

    def test_submit_slug_falls_back_to_entrypoint_when_metadata_has_no_title(
        self,
    ) -> None:
        """A degenerate/malformed metadata file with no `title` at all
        must never crash `submit()` — it falls back to the same
        entrypoint-derived slug the legacy shape already uses, rather
        than raising on a missing key.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            job_dir = tmp_path / "job"
            job_dir.mkdir()
            entrypoint = job_dir / "runner.ipynb"
            entrypoint.write_text("{}", encoding="utf-8")
            (job_dir / "kernel-metadata.json").write_text("{}", encoding="utf-8")

            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir)
            token_path = _write_fake_token(tmp_path / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)

            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
                job = ADAPTER.Job(entrypoint=entrypoint, run_config={}, worker="w1")
                submission = adapter.submit(job)

            self.assertEqual(submission.id, "w1/runner")

    def test_submit_prepends_a_run_config_cell_without_touching_the_runner_logic_cells(
        self,
    ) -> None:
        """`kernels push` uploads only `code_file` — confirmed against the
        installed `kaggle` 2.2.4 CLI's own `kernels_push()` — so a job
        folder's sibling `run-config.json` never reaches the worker on its
        own. `submit()` must inject a THIRD cell, prepended ahead of the
        two real runner cells, that materializes that file back onto disk
        before cell 0 (now cell 1) ever reads it.

        This must never touch the two existing cells' own bytes: they stay
        exactly what `jobfolder.build_notebook()` wrote, byte for byte,
        both in the staged/pushed copy and in the job folder's own
        versioned `runner.ipynb` — the same "never touching the job
        folder" guarantee `kernel-metadata.json` already gets.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            job_dir = tmp_path / "job"
            job_dir.mkdir()
            entrypoint = job_dir / "runner.ipynb"

            bootstrap_cell = {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": ["print('bootstrap')\n"],
            }
            invoke_cell = {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": ["print('invoke')\n"],
            }
            original_notebook = {
                "cells": [bootstrap_cell, invoke_cell],
                "metadata": {
                    "kernelspec": {
                        "display_name": "Python 3",
                        "language": "python",
                        "name": "python3",
                    },
                    "language_info": {"name": "python"},
                },
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            original_notebook_text = json.dumps(original_notebook, indent=1)
            entrypoint.write_text(original_notebook_text, encoding="utf-8")

            run_config_text = json.dumps(
                {"schemaVersion": 1, "jobName": "cell-injection", "commit": "c" * 40}
            )
            (job_dir / "run-config.json").write_text(run_config_text, encoding="utf-8")
            (job_dir / "kernel-metadata.json").write_text(
                json.dumps({"id": "", "title": "papersmith-cell-injection", "code_file": ""}),
                encoding="utf-8",
            )

            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            captured_notebook = tmp_path / "captured-runner.ipynb"
            fake_kaggle = bin_dir / "kaggle"
            fake_kaggle.write_text(
                "#!/usr/bin/env python3\n"
                "import shutil, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "if args[:2] == ['kernels', 'push']:\n"
                "    idx = args.index('-p')\n"
                "    src = Path(args[idx + 1]) / 'runner.ipynb'\n"
                f"    shutil.copyfile(src, {str(captured_notebook)!r})\n"
                "    print('kernel version 1 successfully pushed')\n"
                "    sys.exit(0)\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )
            fake_kaggle.chmod(0o755)

            token_path = _write_fake_token(tmp_path / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)

            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
                job = ADAPTER.Job(entrypoint=entrypoint, run_config={}, worker="w1")
                adapter.submit(job)

            self.assertTrue(captured_notebook.is_file())
            pushed = json.loads(captured_notebook.read_text(encoding="utf-8"))
            self.assertEqual(len(pushed["cells"]), 3)

            # The two runner-logic cells stay exactly where they were,
            # byte for byte — only a new cell was prepended ahead of them.
            self.assertEqual(pushed["cells"][1], bootstrap_cell)
            self.assertEqual(pushed["cells"][2], invoke_cell)

            injected_source = "".join(pushed["cells"][0]["source"])
            self.assertIn("run-config.json", injected_source)
            self.assertIn(run_config_text, injected_source)

            # The job folder's own versioned runner.ipynb is never mutated.
            self.assertEqual(
                entrypoint.read_text(encoding="utf-8"), original_notebook_text
            )

    def test_injected_run_config_cell_writes_the_configs_own_bytes_at_runtime(
        self,
    ) -> None:
        """Structural proof (the cell contains the right text) is not
        functional proof. This actually executes the injected cell's
        source, in a fresh working directory, and confirms the file it
        writes is byte-for-byte identical to the job folder's own
        `run-config.json` — the exact file cell 0's `load_run_config()`
        resolves via `Path.cwd() / "run-config.json"` when no `base_dir`
        is given, which is how the real notebook cell runs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            job_dir = tmp_path / "job"
            job_dir.mkdir()
            entrypoint = job_dir / "runner.ipynb"
            entrypoint.write_text(
                json.dumps(
                    {
                        "cells": [
                            {
                                "cell_type": "code",
                                "metadata": {},
                                "execution_count": None,
                                "outputs": [],
                                "source": ["print('bootstrap')\n"],
                            }
                        ],
                        "metadata": {},
                        "nbformat": 4,
                        "nbformat_minor": 5,
                    }
                ),
                encoding="utf-8",
            )

            run_config_text = json.dumps(
                {"schemaVersion": 1, "jobName": "cell-injection", "commit": "d" * 40},
                indent=2,
            )
            (job_dir / "run-config.json").write_text(run_config_text, encoding="utf-8")
            (job_dir / "kernel-metadata.json").write_text(
                json.dumps({"id": "", "title": "papersmith-cell-injection", "code_file": ""}),
                encoding="utf-8",
            )

            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            captured_notebook = tmp_path / "captured-runner.ipynb"
            fake_kaggle = bin_dir / "kaggle"
            fake_kaggle.write_text(
                "#!/usr/bin/env python3\n"
                "import shutil, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "if args[:2] == ['kernels', 'push']:\n"
                "    idx = args.index('-p')\n"
                "    src = Path(args[idx + 1]) / 'runner.ipynb'\n"
                f"    shutil.copyfile(src, {str(captured_notebook)!r})\n"
                "    print('kernel version 1 successfully pushed')\n"
                "    sys.exit(0)\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )
            fake_kaggle.chmod(0o755)

            token_path = _write_fake_token(tmp_path / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)

            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
                job = ADAPTER.Job(entrypoint=entrypoint, run_config={}, worker="w1")
                adapter.submit(job)

            pushed = json.loads(captured_notebook.read_text(encoding="utf-8"))
            injected_source = "".join(pushed["cells"][0]["source"])

            with tempfile.TemporaryDirectory() as runtime_cwd:
                previous_cwd = os.getcwd()
                os.chdir(runtime_cwd)
                try:
                    exec(compile(injected_source, "<injected-cell>", "exec"), {})
                finally:
                    os.chdir(previous_cwd)

                written = Path(runtime_cwd) / "run-config.json"
                self.assertTrue(written.is_file())
                self.assertEqual(
                    written.read_bytes(),
                    (job_dir / "run-config.json").read_bytes(),
                )

    def test_submit_smoke_override_reaches_select_block_in_the_staged_run_config(
        self,
    ) -> None:
        """The seam nobody was asserting: `cmd_submit --smoke` sets
        `job.run_config["mode"] = "smoke"` on the in-memory `Job`, but
        `submit()` used to stage `run-config.json`'s own bytes verbatim —
        that file never carries a `mode` key, so `select_block()` in the
        pushed kernel always saw the normal `run` block, never `smoke`.
        Confirmed on real hardware: six `--smoke` submissions ran the full
        `run` block instead of the one-transfer rehearsal.

        This test spans the two pieces every prior test proved separately
        while the bug stayed live: that `cmd_submit` sets the field on the
        `Job` (never checking what `submit()` does with it), and that the
        file's own bytes arrive at the kernel intact (never checking
        whether `job.run_config` also arrives). It actually executes the
        injected cell, reads back the file it writes, and feeds that
        exact mapping to `runner_invoke.select_block()` — the same call
        the real kernel makes — to prove `mode` is really there.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            job_dir = tmp_path / "job"
            job_dir.mkdir()
            entrypoint = job_dir / "runner.ipynb"
            entrypoint.write_text(
                json.dumps(
                    {
                        "cells": [
                            {
                                "cell_type": "code",
                                "metadata": {},
                                "execution_count": None,
                                "outputs": [],
                                "source": ["print('bootstrap')\n"],
                            }
                        ],
                        "metadata": {},
                        "nbformat": 4,
                        "nbformat_minor": 5,
                    }
                ),
                encoding="utf-8",
            )

            # The versioned file: exactly what `generate-job` writes, with
            # no `mode` key — `mode` is only ever set at submit time, on
            # the in-memory `Job`, never written to disk.
            versioned_run_config = {
                "schemaVersion": 1,
                "jobName": "smoke-seam",
                "commit": "e" * 40,
                "run": {"module": "pkg.entry", "function": "run"},
            }
            versioned_run_config["run"]["smoke"] = {
                "module": "pkg.entry",
                "function": "smoke",
            }
            (job_dir / "run-config.json").write_text(
                json.dumps(versioned_run_config), encoding="utf-8"
            )
            (job_dir / "kernel-metadata.json").write_text(
                json.dumps({"id": "", "title": "papersmith-smoke-seam", "code_file": ""}),
                encoding="utf-8",
            )

            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            captured_notebook = tmp_path / "captured-runner.ipynb"
            fake_kaggle = bin_dir / "kaggle"
            fake_kaggle.write_text(
                "#!/usr/bin/env python3\n"
                "import shutil, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "if args[:2] == ['kernels', 'push']:\n"
                "    idx = args.index('-p')\n"
                "    src = Path(args[idx + 1]) / 'runner.ipynb'\n"
                f"    shutil.copyfile(src, {str(captured_notebook)!r})\n"
                "    print('kernel version 1 successfully pushed')\n"
                "    sys.exit(0)\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )
            fake_kaggle.chmod(0o755)

            token_path = _write_fake_token(tmp_path / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)

            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
                # Exactly what `cmd_submit --smoke` hands the adapter.
                job = ADAPTER.Job(
                    entrypoint=entrypoint,
                    run_config={"mode": "smoke"},
                    worker="w1",
                )
                adapter.submit(job)

            pushed = json.loads(captured_notebook.read_text(encoding="utf-8"))
            injected_source = "".join(pushed["cells"][0]["source"])

            with tempfile.TemporaryDirectory() as runtime_cwd:
                previous_cwd = os.getcwd()
                os.chdir(runtime_cwd)
                try:
                    exec(compile(injected_source, "<injected-cell>", "exec"), {})
                finally:
                    os.chdir(previous_cwd)

                written = Path(runtime_cwd) / "run-config.json"
                self.assertTrue(written.is_file())
                staged_run_config = json.loads(written.read_text(encoding="utf-8"))

            # The override reached the staged file...
            self.assertEqual(staged_run_config["mode"], "smoke")
            # ...without losing the file's own content.
            self.assertEqual(staged_run_config["jobName"], "smoke-seam")
            self.assertEqual(staged_run_config["commit"], "e" * 40)

            # And the exact call the real kernel makes now resolves to the
            # smoke block, not the full `run` block.
            self.assertEqual(
                RUNNER_INVOKE.select_block(staged_run_config),
                {"module": "pkg.entry", "function": "smoke"},
            )

    def test_credential_sentinel_absent_from_argv_stdout_stderr_ledger_and_quarantine(
        self,
    ) -> None:
        """The sentinel test: the whole point of `CredentialHandle` is that
        a key VALUE never becomes a value this process holds. A fake
        credential file, holding a unique sentinel as its whole content,
        sits at the path this adapter is handed by PATH only — and after a
        real `submit()` followed by a `fetch()` that lands in quarantine
        (so both the ledger AND a quarantine file are exercised), the
        sentinel must appear in none of: every subprocess call's argv, its
        stdout, its stderr, the ledger file, or the quarantine file.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            sentinel = "SENTINEL-" + uuid.uuid4().hex
            token_dir = tmp_path / "creds" / "w1"
            token_dir.mkdir(parents=True)
            token_path = token_dir / "token"
            token_path.write_text(sentinel, encoding="utf-8")

            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir)

            fake_accounts_cli = tmp_path / "fake_accounts_cli.py"
            fake_accounts_cli.write_text(
                "import json\n"
                "print(json.dumps({'accounts': [{'username': 'w1'}]}))\n",
                encoding="utf-8",
            )

            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)

            calls: list[dict[str, object]] = []
            real_run = subprocess.run

            def recording_run(argv, **kwargs):
                result = real_run(argv, **kwargs)
                calls.append(
                    {"argv": list(argv), "stdout": result.stdout, "stderr": result.stderr}
                )
                return result

            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ), unittest.mock.patch.object(KAGGLE.subprocess, "run", side_effect=recording_run):
                adapter = KAGGLE.KaggleAdapter(
                    credentials={"w1": handle}, accounts_cli=fake_accounts_cli
                )

                submit_result = REMOTE_CLI.cmd_submit(
                    target=target,
                    entrypoint=notebook,
                    worker="w1",
                    requested=1,
                    adapter=adapter,
                    source_digest=lambda t, n: "d" * 64,
                )

                submission_id = submit_result["submission"].id
                ledger_path = submit_result["ledgerPath"]
                dest = target.resolve() / "MIL-CREDA" / "Results" / "shards" / "a"

                # A different live digest at fetch time than at submit time
                # forces `fromStaleSubmission`, exercising the quarantine
                # path, not only the ledger.
                fetch_result = REMOTE_CLI.cmd_fetch(
                    target=target,
                    entrypoint=notebook,
                    submission_id=submission_id,
                    dest=dest,
                    adapter=adapter,
                    source_digest=lambda t, n: "e" * 64,
                )

            self.assertEqual(fetch_result["verdict"], "fromStaleSubmission")
            quarantine_dir = fetch_result["path"]
            self.assertTrue(quarantine_dir.exists())

            self.assertGreater(len(calls), 0)
            for call in calls:
                self.assertNotIn(sentinel, json.dumps(call["argv"]))
                if call["stdout"]:
                    self.assertNotIn(sentinel, call["stdout"])
                if call["stderr"]:
                    self.assertNotIn(sentinel, call["stderr"])

            self.assertNotIn(sentinel, ledger_path.read_text(encoding="utf-8"))
            for artifact in quarantine_dir.rglob("*"):
                if artifact.is_file():
                    self.assertNotIn(
                        sentinel, artifact.read_text(encoding="utf-8", errors="ignore")
                    )


def _write_fake_materialize_cli(
    script_path: Path, materialized_root: Path, key: str, *, worker: str = "w1"
) -> Path:
    """A stand-in for kaggle-accounts' own CLI that answers exactly the two
    sanctioned commands `KaggleAdapter`/`credentials.py` ever run as a
    subprocess: `list --json` (worker identity) and `materialize` (the ONE
    process in the tests below sanctioned to write a real credential
    file). `materialize` is invoked exactly the way
    `credentials.materialize()` invokes the real command — `<cli>
    materialize --worker <id> --json` — and prints back a destination
    only, never the key, mirroring `cmd_materialize`'s own contract: a
    plain-text token file, no JSON wrapper, and a `tokenPath` field
    naming it.
    """
    script_path.write_text(
        "import argparse, json, os\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "sub = parser.add_subparsers(dest='command', required=True)\n"
        "p_list = sub.add_parser('list')\n"
        "p_list.add_argument('--json', action='store_true')\n"
        "p = sub.add_parser('materialize')\n"
        "p.add_argument('--worker', required=True)\n"
        "p.add_argument('--json', action='store_true')\n"
        "args = parser.parse_args()\n"
        "if args.command == 'list':\n"
        f"    print(json.dumps({{'accounts': [{{'username': {worker!r}}}]}}))\n"
        "    raise SystemExit(0)\n"
        f"dest = Path({str(materialized_root)!r}) / args.worker\n"
        "dest.mkdir(parents=True, exist_ok=True)\n"
        f"key = {key!r}\n"
        "token_path = dest / 'token'\n"
        "token_path.write_text(key + chr(10))\n"
        "os.chmod(token_path, 0o600)\n"
        "print(json.dumps({'worker': args.worker, 'tokenPath': str(token_path)}))\n",
        encoding="utf-8",
    )
    return script_path


def _is_under(candidate: object, root: Path) -> bool:
    """Whether `candidate` resolves under `root` — used only to detect a
    forbidden file-read INSIDE this test process; a child subprocess doing
    its own file I/O is a separate OS process and is never seen by this
    check, which is exactly the boundary the security contract draws.
    """
    try:
        resolved = Path(candidate).resolve()
    except (TypeError, OSError, ValueError):
        return False
    try:
        return resolved.is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


@contextlib.contextmanager
def _interposition_guard(guarded_root: Path):
    """Interpose `Path.read_text`, `Path.read_bytes` and `builtins.open`
    for the duration of the `with` block, recording every call whose
    argument resolves under `guarded_root` — how it read, what it read,
    and the file the calling code lives in. Every call is still forwarded
    to the real implementation — this only OBSERVES, it never blocks —
    so the guarded code path keeps running exactly as it would otherwise.
    """
    hits: list[dict] = []
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_open = builtins.open

    def _record(how: str, target: object) -> None:
        # The immediate caller's own file, so a hit names WHICH module read
        # the credential — the whole invariant now that the value, not the
        # path, is what a client is handed.
        hits.append(
            {"how": how, "path": str(target), "caller": sys._getframe(2).f_code.co_filename}
        )

    def guarded_read_text(path_self, *a, **kw):
        if _is_under(path_self, guarded_root):
            _record("Path.read_text", path_self)
        return real_read_text(path_self, *a, **kw)

    def guarded_read_bytes(path_self, *a, **kw):
        if _is_under(path_self, guarded_root):
            _record("Path.read_bytes", path_self)
        return real_read_bytes(path_self, *a, **kw)

    def guarded_open(file, *a, **kw):
        if _is_under(file, guarded_root):
            _record("open", file)
        return real_open(file, *a, **kw)

    with unittest.mock.patch.object(Path, "read_text", guarded_read_text), \
            unittest.mock.patch.object(Path, "read_bytes", guarded_read_bytes), \
            unittest.mock.patch("builtins.open", guarded_open):
        yield hits


class CredentialSecurityTests(unittest.TestCase):
    """T1's hard security constraints (C2-C6): no component above the
    adapter seam may open, read, print, or parse the credential store or
    any credential file. Credentials move BY PATH only; the sole sink is
    `KAGGLE_API_TOKEN` on a child process's own environment.

    Every full-cycle test here drives `submit -> poll -> fetch -> status`
    through `CREDENTIALS.provider()` and a FAKE `materialize` command (see
    `_write_fake_materialize_cli`) that genuinely writes a credential file
    to disk, as a separate OS process — the one process in these tests
    sanctioned to touch it. Nothing else here ever reads that file.
    """

    def _run_full_cycle(self, tmp_path: Path, *, worker: str = "w1", key: str = "K1"):
        materialized_root = tmp_path / "materialized"
        fake_accounts_cli = _write_fake_materialize_cli(
            tmp_path / "fake_accounts_cli.py", materialized_root, key, worker=worker
        )
        bin_dir = tmp_path / "bin"
        _write_fake_kaggle(bin_dir)

        target = tmp_path / "repo"
        notebooks = _make_product(target, "MIL-CREDA")
        notebook = notebooks / "a.ipynb"
        notebook.write_text("{}", encoding="utf-8")

        calls: list[dict[str, object]] = []
        real_run = subprocess.run

        def recording_run(argv, **kwargs):
            result = real_run(argv, **kwargs)
            calls.append(
                {"argv": list(argv), "stdout": result.stdout, "stderr": result.stderr}
            )
            return result

        with unittest.mock.patch.dict(
            os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
        ), unittest.mock.patch.object(
            subprocess, "run", side_effect=recording_run
        ), _interposition_guard(materialized_root) as hits:
            provider = REMOTE_CLI.CREDENTIALS.provider(accounts_cli=fake_accounts_cli)
            adapter = KAGGLE.KaggleAdapter(
                credentials=provider, accounts_cli=fake_accounts_cli
            )

            submit_result = REMOTE_CLI.cmd_submit(
                target=target, entrypoint=notebook, worker=worker, requested=1,
                adapter=adapter, source_digest=lambda t, n: "d" * 64,
            )
            submission_id = submit_result["submission"].id
            ledger_path = submit_result["ledgerPath"]

            REMOTE_CLI.cmd_poll(submission_id=submission_id, adapter=adapter)

            dest = target.resolve() / "MIL-CREDA" / "Results" / "shards" / "a"
            # A different live digest at fetch time than at submit time
            # forces `fromStaleSubmission`, exercising the quarantine path
            # too, not only the ledger.
            fetch_result = REMOTE_CLI.cmd_fetch(
                target=target, entrypoint=notebook, submission_id=submission_id,
                dest=dest, adapter=adapter, source_digest=lambda t, n: "e" * 64,
            )

            status_result = REMOTE_CLI.cmd_status(
                target=target, entrypoint=notebook, source_digest=lambda t, n: "e" * 64,
            )

        return {
            "calls": calls,
            "ledger_path": ledger_path,
            "fetch_result": fetch_result,
            "status_result": status_result,
            "materialized_root": materialized_root,
            "interposition_hits": hits,
        }

    def test_only_the_adapter_reads_the_credential_across_a_full_submit_poll_fetch_status_run(
        self,
    ) -> None:
        """C2. The credential file IS read inside this process now — a
        client that authenticates only by value left no other route — so
        the invariant is no longer "nobody reads it" but "exactly one file
        reads it, and it is the one file allowed to name a service".

        Every hit's caller is checked, not just its count: a read from
        `remote_cli.py`, `ledger.py` or `credentials.py` is the failure
        this guards against, and those would otherwise be invisible behind
        a passing count.
        """
        with tempfile.TemporaryDirectory() as tmp:
            cycle = self._run_full_cycle(Path(tmp))
            self.assertGreater(len(cycle["calls"]), 0)

            hits = cycle["interposition_hits"]
            self.assertGreater(len(hits), 0, "the credential was never read at all")
            for hit in hits:
                self.assertEqual(hit["how"], "Path.read_text", hit)
                self.assertTrue(hit["path"].endswith("/token"), hit)
                self.assertEqual(hit["caller"], str(KAGGLE_SCRIPT), hit)

    def test_planted_sentinel_leaks_nowhere_including_materializes_own_stdout(
        self,
    ) -> None:
        """C3."""
        sentinel = "SENTINEL-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as tmp:
            cycle = self._run_full_cycle(Path(tmp), key=sentinel)

            self.assertGreater(len(cycle["calls"]), 0)
            for call in cycle["calls"]:
                self.assertNotIn(sentinel, json.dumps(call["argv"]))
                if call["stdout"]:
                    self.assertNotIn(sentinel, call["stdout"])
                if call["stderr"]:
                    self.assertNotIn(sentinel, call["stderr"])

            self.assertNotIn(sentinel, cycle["ledger_path"].read_text(encoding="utf-8"))

            self.assertEqual(cycle["fetch_result"]["verdict"], "fromStaleSubmission")
            quarantine_dir = cycle["fetch_result"]["path"]
            self.assertTrue(quarantine_dir.exists())
            for artifact in quarantine_dir.rglob("*"):
                if artifact.is_file():
                    self.assertNotIn(
                        sentinel, artifact.read_text(encoding="utf-8", errors="ignore")
                    )

    def test_no_forge_component_contains_credential_store_literals_or_imports_accounts_cli(
        self,
    ) -> None:
        """C4."""
        scanned = (
            REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/credentials.py",
            REMOTE_CLI_SCRIPT,
            PACKER_SCRIPT,
            SCRIPT,
            ADAPTER_SCRIPT,
            KAGGLE_SCRIPT,
            JOBFOLDER_SCRIPT,
        )
        forbidden = ("accounts.json", "STORE_PATH", "STORE_DIR", "import accounts_cli")
        for path in scanned:
            source = path.read_text(encoding="utf-8")
            for literal in forbidden:
                self.assertNotIn(literal, source, f"{literal!r} found in {path}")

    def test_credentials_module_names_no_service(self) -> None:
        """The leak guard this module was missing until now, in the same
        family as `test_adapter_module_names_no_service`,
        `test_packer_module_names_no_service_and_hardcodes_no_capacity`,
        `test_remote_cli_module_names_no_service` and
        `test_shard_io_source_names_no_service_and_no_domain_term`: a static
        scan over the raw file text (source and every docstring alike),
        because a docstring naming a backend to explain an example is
        exactly the leak this skill's seam exists to prevent, and
        `credentials.py` is the only producer of a `CredentialHandle`
        anywhere above the adapter.
        """
        source = (
            REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/credentials.py"
        ).read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)

    def test_credential_handle_carries_exactly_worker_id_and_token_path(self) -> None:
        """C5."""
        fields = tuple(f.name for f in dataclasses.fields(ADAPTER.CredentialHandle))
        self.assertEqual(fields, ("worker_id", "token_path"))

        # `.token_path` is accessed exactly once in `adapters/kaggle.py`'s
        # actual CODE — the single sink documented at the top of this
        # module. Parsed as an AST rather than scanned as raw text, so a
        # docstring that quotes the same expression in prose (as this
        # module's own module docstring does, to document the sink) is not
        # mistaken for a second real access.
        tree = ast.parse(KAGGLE_SCRIPT.read_text(encoding="utf-8"))
        accesses = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "token_path"
        ]
        self.assertEqual(len(accesses), 1)

    def test_the_only_sink_is_kaggle_api_token_on_the_child_environment(self) -> None:
        """C6. The sink is still exactly one variable on exactly one child
        environment; what changed is what that variable carries. The client
        this adapter shells out to reads `KAGGLE_API_TOKEN` as a token
        VALUE with no path check of any kind, so a path here authenticates
        nothing — see `CredentialValueDeliveryTests` for that contract in
        full.
        """
        with tempfile.TemporaryDirectory() as tmp:
            token_path = _write_fake_token(Path(tmp) / "creds")
            handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)
            adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})

            env = adapter._env_for(handle)
            self.assertEqual(env.get("KAGGLE_API_TOKEN"), FIXTURE_TOKEN)
            self.assertEqual(sorted(env), ["KAGGLE_API_TOKEN", "PATH"])

            env_without_handle = adapter._env_for(None)
            self.assertEqual(sorted(env_without_handle), ["PATH"])


def _write_recording_kaggle(
    bin_dir: Path, record_dir: Path, *, sleep_seconds: float
) -> Path:
    """A fake `kaggle` that records the credential IT ACTUALLY RECEIVED,
    plus when it started and finished, and nothing else.

    The record directory is baked into the script's own source rather than
    passed through the environment, because the environment is exactly what
    this fixture exists to observe: `_env_for` builds the child's whole env
    from an allowlist (`PATH` plus `KAGGLE_API_TOKEN`), so a second variable
    naming the record directory could not reach this process anyway.

    Never touches a network and never reads any file: it answers
    `kernels push` well enough to drive `submit()` and writes one JSON
    record per invocation, under a unique name, so two concurrent
    invocations cannot overwrite each other's record.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    record_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "kaggle"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time, uuid\n"
        "from pathlib import Path\n"
        f"RECORD_DIR = Path({str(record_dir)!r})\n"
        f"SLEEP = {sleep_seconds!r}\n"
        "started = time.time()\n"
        "time.sleep(SLEEP)\n"
        "record = {\n"
        "    'argv': sys.argv[1:],\n"
        "    'credential': os.environ.get('KAGGLE_API_TOKEN'),\n"
        "    'started': started,\n"
        "    'finished': time.time(),\n"
        "}\n"
        "(RECORD_DIR / (uuid.uuid4().hex + '.json')).write_text(\n"
        "    json.dumps(record), encoding='utf-8')\n"
        "print('kernel version 1 successfully pushed')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


class CredentialValueDeliveryTests(unittest.TestCase):
    """`_env_for` hands the service client the token's VALUE, because the
    client this adapter shells out to reads `KAGGLE_API_TOKEN` as a value
    and as nothing else.

    Reachable red: `_env_for` assigned `str(handle.token_path)` before this
    change, so a submission sent `Authorization: Bearer /path/to/token` and
    every assertion below that names the file's stripped CONTENT failed
    against a path.

    What still holds, and is asserted here rather than assumed: no module
    above the adapter can reach the credential file at all — the value is
    read in exactly one file, at exactly one expression, and reaches
    exactly one child process's own environment.
    """

    def _env_for(self, token_path: Path) -> dict:
        handle = KAGGLE.CredentialHandle(worker_id="w1", token_path=token_path)
        return KAGGLE.KaggleAdapter(credentials={"w1": handle})._env_for(handle)

    def test_the_env_value_is_the_files_stripped_content_and_never_its_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = _write_fake_token(Path(tmp) / "creds")

            env = self._env_for(token_path)

            self.assertEqual(env["KAGGLE_API_TOKEN"], FIXTURE_TOKEN)
            self.assertNotEqual(env["KAGGLE_API_TOKEN"], str(token_path))
            self.assertNotIn(str(token_path), env["KAGGLE_API_TOKEN"])
            self.assertEqual(sorted(env), ["KAGGLE_API_TOKEN", "PATH"])

    def test_the_newline_materialize_writes_never_reaches_the_header(self) -> None:
        """`cmd_materialize` writes the key followed by `\\n`. A bearer
        header carrying that newline is a malformed header, not a
        credential — so the surrounding whitespace is stripped here, at the
        one place the value is read.
        """
        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "token"
            token_path.write_text(f"\n {FIXTURE_TOKEN} \n", encoding="utf-8")

            value = self._env_for(token_path)["KAGGLE_API_TOKEN"]

            self.assertEqual(value, FIXTURE_TOKEN)
            self.assertNotIn("\n", value)
            self.assertEqual(value, value.strip())

    def test_a_credential_file_that_cannot_be_read_is_a_refusal(self) -> None:
        """Fails closed, the same way every other unusable answer in this
        module does: a missing token file is a `KaggleAdapterError` naming
        the path, never a request sent with no credential at all.
        """
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "creds" / "token"

            with self.assertRaises(KAGGLE.KaggleAdapterError) as caught:
                self._env_for(missing)

            self.assertIn(str(missing), str(caught.exception))

    def test_an_empty_credential_file_is_refused_rather_than_sent_as_a_bare_bearer(
        self,
    ) -> None:
        """The refusal names the worker, not the path: naming the path
        would need a second `handle.token_path` access, and the single-
        access lock in `CredentialSecurityTests` is worth more than a
        friendlier message. The worker id is enough to re-materialize.
        """
        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "token"
            token_path.write_text("\n", encoding="utf-8")

            with self.assertRaises(KAGGLE.KaggleAdapterError) as caught:
                self._env_for(token_path)

            self.assertIn("w1", str(caught.exception))
            self.assertNotIn(FIXTURE_TOKEN, str(caught.exception))

    def test_no_module_above_the_adapter_can_reach_the_credential_file(self) -> None:
        """The structural half of the trade this change makes: the adapter
        now reads a VALUE, so what keeps a value out of everything else is
        that nothing else ever touches `token_path` at all.

        Parsed as an AST rather than scanned as raw text, exactly like the
        single-access lock in `CredentialSecurityTests`, so a docstring
        naming the attribute in prose (as `adapter.py`'s own
        `CredentialHandle` docstring does) is not mistaken for a real
        access. `credentials.py` names `token_path` only as a local
        variable and a keyword argument, neither of which is an attribute
        access on a handle.
        """
        scripts = (
            REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/credentials.py",
            REMOTE_CLI_SCRIPT,
            PACKER_SCRIPT,
            SCRIPT,
            ADAPTER_SCRIPT,
            JOBFOLDER_SCRIPT,
        )
        for path in scripts:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            accesses = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr == "token_path"
            ]
            self.assertEqual(
                accesses, [], f"{path} reaches a credential handle's own path"
            )


class ParallelCredentialIsolationTests(unittest.TestCase):
    """Two concurrent submissions for two workers carry two distinct,
    uncrossed credentials — the requirement this whole change exists to
    serve, locked rather than assumed.

    True by construction (`_run` builds a fresh env dict per call and hands
    it to one `subprocess.run`), which is exactly why it needs a falsifier:
    a shared credential, a crossed one, or one written into a place a
    second call could read back would all still look like working code.
    The fake `kaggle` on `PATH` records the credential it was actually
    handed, so the claim dies if the two recorded values are equal, crossed,
    or path-shaped.

    No network: the fake executable is the only thing either submission
    ever reaches.
    """

    SLEEP_SECONDS = 0.5

    def _two_concurrent_submissions(self, tmp_path: Path) -> tuple:
        tokens = {
            "worker-alpha": "KGAT_" + "a" * 32,
            "worker-beta": "KGAT_" + "b" * 32,
        }
        record_dir = tmp_path / "records"
        bin_dir = tmp_path / "bin"
        _write_recording_kaggle(bin_dir, record_dir, sleep_seconds=self.SLEEP_SECONDS)

        credentials = {}
        jobs = {}
        for worker, value in tokens.items():
            token_path = _write_fake_token(tmp_path / "creds" / worker, value)
            credentials[worker] = KAGGLE.CredentialHandle(
                worker_id=worker, token_path=token_path
            )
            job_dir = tmp_path / f"job-for-{worker}"
            job_dir.mkdir()
            entrypoint = job_dir / "a.ipynb"
            entrypoint.write_text("{}", encoding="utf-8")
            jobs[worker] = ADAPTER.Job(
                entrypoint=entrypoint, run_config={}, worker=worker
            )

        adapter = KAGGLE.KaggleAdapter(credentials=credentials)
        with unittest.mock.patch.dict(
            os.environ,
            {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"},
        ):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = {
                    worker: pool.submit(adapter.submit, job)
                    for worker, job in jobs.items()
                }
                submissions = {
                    worker: future.result() for worker, future in futures.items()
                }

        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(record_dir.iterdir())
        ]
        return tokens, records, submissions

    @staticmethod
    def _worker_of(record: dict) -> str:
        argv = record["argv"]
        push_dir = Path(argv[argv.index("-p") + 1])
        return push_dir.name.replace("job-for-", "")

    def test_two_concurrent_submissions_carry_two_distinct_uncrossed_credentials(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tokens, records, submissions = self._two_concurrent_submissions(Path(tmp))

        self.assertEqual(len(records), 2)
        received = {self._worker_of(record): record["credential"] for record in records}
        # One assertion kills all three ways this can be wrong: a shared
        # credential, a crossed one, and a path where a value belongs.
        self.assertEqual(received, tokens)
        self.assertEqual(
            sorted(submissions), ["worker-alpha", "worker-beta"]
        )
        for worker, value in received.items():
            self.assertNotIn(os.sep, value, worker)

    def test_the_two_submissions_genuinely_overlapped_in_time(self) -> None:
        """Without this, the isolation test above would pass just as well
        against two submissions that never ran at the same time — and
        "parallel" is the requirement, not "twice".
        """
        with tempfile.TemporaryDirectory() as tmp:
            _, records, _ = self._two_concurrent_submissions(Path(tmp))

        self.assertEqual(len(records), 2)
        first, second = sorted(records, key=lambda record: record["started"])
        self.assertLess(
            second["started"],
            first["finished"],
            "the two pushes never overlapped: this run proves nothing about "
            "credential isolation under concurrency",
        )


class CredentialTransportDoctrineTests(unittest.TestCase):
    """`SKILL.md` must state how a credential actually travels, and the
    suite holds that statement to the tests that enforce it.

    The same parseable-table idiom `PinConditionDoctrineTests` established,
    for the same reason and against a defect of the same family: the skill
    documented a by-path contract, the client had no by-path behavior to
    hold it to, and no test could contradict a paragraph. The binding here
    runs both ways — a lock with no row is undocumented, a row naming no
    test is a claim nothing enforces — so the two cannot drift apart again
    without a red test.

    The parser is deliberately small and local, exactly as it is in
    `PinConditionDoctrineTests`: this suite does not import across test
    modules.
    """

    HEADER = "| # | id | Guarantee | Enforced by | Proven by |"

    # Every test in these classes is a credential-transport lock, so every
    # one of them must appear in the table. A lock added here with no row
    # is a guarantee an operator cannot look up.
    LOCK_CLASSES = ("CredentialValueDeliveryTests", "ParallelCredentialIsolationTests")

    def _table_rows(self, text: str, header: str) -> list:
        lines = text.split("\n")
        try:
            start = next(i for i, line in enumerate(lines) if line.strip() == header)
        except StopIteration:
            self.fail(
                f"SKILL.md has no credential-transport table: the exact header "
                f"{header!r} was not found"
            )
        rows = []
        for line in lines[start + 1:]:
            stripped = line.strip()
            if not stripped.startswith("|"):
                break
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= {"-", ":"} and cell for cell in cells):
                continue  # the separator row
            rows.append(cells)
        return rows

    def _rows(self) -> list:
        return self._table_rows(SKILL_MD.read_text(encoding="utf-8"), self.HEADER)

    def test_every_row_is_complete_and_every_id_is_named_once(self) -> None:
        rows = self._rows()
        self.assertGreater(len(rows), 0, "the table documents nothing")
        ids = []
        for row in rows:
            self.assertEqual(len(row), 5, row)
            for cell in row:
                self.assertTrue(cell, row)
            ids.append(row[1])
        self.assertEqual(sorted(ids), sorted(set(ids)), f"a row id is repeated: {ids}")

    def test_every_row_names_a_test_this_suite_actually_runs(self) -> None:
        """A row whose `Proven by` cell names nothing real is exactly the
        claim this change exists to end.
        """
        module_tests = {
            node.name
            for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        }
        for row in self._rows():
            named = row[4].strip("`")
            self.assertIn(named, module_tests, f"row {row[1]!r} names no real test")

    def test_every_credential_transport_lock_is_documented(self) -> None:
        documented = {row[4].strip("`") for row in self._rows()}
        for class_name in self.LOCK_CLASSES:
            cls = globals()[class_name]
            for name in dir(cls):
                if name.startswith("test_"):
                    self.assertIn(
                        name,
                        documented,
                        f"{class_name}.{name} enforces a guarantee SKILL.md's "
                        f"credential-transport table does not document",
                    )

    def test_the_retracted_by_path_claim_survives_nowhere(self) -> None:
        """The old doctrine said the client "checks it exists" before
        treating `KAGGLE_API_TOKEN` as a literal. It does not, and never
        did in the installed version. Rewording that sentence would have
        left the same claim in softer words, so this asserts its absence
        outright — in the skill's own surface, in the adapter, and in the
        seam that must not name a service at all.
        """
        retracted = (
            "checks `Path(...).exists()`",
            "Path(KAGGLE_API_TOKEN).exists()",
            "checks it exists",
            "carried by PATH only",
            "move BY PATH, never by value",
        )
        for path in (
            SKILL_MD,
            KAGGLE_SCRIPT,
            ADAPTER_SCRIPT,
            REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/credentials.py",
        ):
            text = path.read_text(encoding="utf-8")
            for claim in retracted:
                self.assertNotIn(claim, text, f"{claim!r} still stated in {path}")


def _installed_kaggle_client_source() -> str | None:
    """The installed `kaggle` client's own `kernels_push` module, read as
    TEXT and never imported.

    Importing `kaggle` runs `api.authenticate()` at package import time,
    which raises without credentials on this machine and would reach the
    filesystem looking for them — neither of which belongs in this suite.
    `find_spec` locates the package without executing a line of it.
    """
    spec = importlib.util.find_spec("kaggle")
    if spec is None or not spec.origin:
        return None
    source = Path(spec.origin).parent / "api" / "kaggle_api_extended.py"
    if not source.is_file():
        return None
    return source.read_text(encoding="utf-8", errors="replace")


class AcceleratorRequestDoctrineTests(unittest.TestCase):
    """`assemble_metadata` must emit the accelerator key the installed
    client actually reads.

    Reachable red: it emitted `machine_shape: "NvidiaTeslaT4"` and
    deliberately omitted `enable_gpu` as "documented DEPRECATED in favor of
    it". The installed `kernels_push` reads `enable_gpu`/`enable_tpu` and
    builds its request field by field; `machine_shape` appears nowhere in
    that client at all, so the key was never even transmitted and every
    submission this skill ever pushed ran on CPU.

    Two of the tests below read the INSTALLED client's own source rather
    than trusting a docstring about it. That is the whole lesson of this
    change: every claim in this adapter that named a version was checked
    against a version that is not installed, and no test could contradict
    it. They skip, loudly, on a machine where the client is absent — a
    pass here is never proof on a machine that has nothing to check.
    """

    def test_assemble_metadata_emits_the_key_the_installed_client_reads(self) -> None:
        _, text = ADAPTER.resolve_metadata("kaggle")({"jobName": "domain-adaptation-2ep"})
        payload = json.loads(text)

        self.assertIs(payload["enable_gpu"], True)
        self.assertNotIn(
            "machine_shape",
            payload,
            "a key the installed client never reads and never transmits",
        )

    def test_the_installed_client_reads_enable_gpu_and_knows_no_machine_shape(
        self,
    ) -> None:
        source = _installed_kaggle_client_source()
        if source is None:
            self.skipTest(
                "the `kaggle` client is not installed here — nothing to hold "
                "this adapter's accelerator claim to, which is not the same as "
                "holding it and finding it true"
            )
        self.assertIn("'enable_gpu'", source)
        self.assertNotIn("machine_shape", source)

    def test_every_version_this_adapter_claims_is_the_version_installed(self) -> None:
        """The root cause, as a lock. Five docstrings claimed confirmation
        against `kaggle` 2.2.4 while `KaggleApi.__version__` is something
        else entirely, so every claim resting on that reading was unchecked
        against what actually runs here.
        """
        source = _installed_kaggle_client_source()
        if source is None:
            self.skipTest("the `kaggle` client is not installed here")
        match = re.search(r"__version__ = '([^']+)'", source)
        self.assertIsNotNone(match, "the installed client states no version")
        installed = match.group(1)

        claimed = set(
            re.findall(r"\b\d+\.\d+\.\d+(?:\.\d+)*\b", KAGGLE_SCRIPT.read_text(encoding="utf-8"))
        )
        self.assertEqual(
            claimed - {installed},
            set(),
            f"this adapter names a version it was not checked against; "
            f"installed is {installed}",
        )

    def test_the_request_is_never_reported_as_a_receipt(self) -> None:
        """Emitting the right key is a request. What a submission actually
        ran on is a fact the service states, and this skill has exactly one
        place for it.
        """
        for path in (KAGGLE_SCRIPT, SKILL_MD):
            # Whitespace-normalized, so the claim can wrap across lines the
            # way prose in both files already does.
            text = " ".join(path.read_text(encoding="utf-8").lower().split())
            self.assertIn("a request, not a receipt", text, str(path))
            self.assertIn("detail", text, str(path))


class JobFolderTests(unittest.TestCase):
    """`jobfolder.generate_job()` — this slice's whole surface: the
    `generate-job` CLI command, `run-config.json`'s schema, and atomic,
    refusal-guarded writes into a foreign checkout.

    The two runner assets' own real content (the eight-responsibility
    bootstrap cell, the invoke cell) is exercised directly in
    `RunnerBootstrapTests`/`RunnerInvokeTests` below; every test here either
    supplies its own fixture asset files or exercises `jobfolder.py`'s
    default asset paths only to prove they resolve to *a* file, never that
    file's real behavior. `resolve_clone_paths()`'s own dedicated coverage
    lives in `ResolveClonePathsTests`; the tests here only cover its wiring
    into `generate_job()`.

    Every test in this class has a reachable red: `jobfolder.py` did not
    exist before this task, so the module import above would fail and
    every test here would fail to collect.
    """

    FAKE_SERVICE = "jobfolder-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def setUp(self) -> None:
        # This class is not exercising the pin preconditions themselves
        # (`CleanWorkingTreeTests`, `PinIsHeadTests` and
        # `CommitReachabilityTests` below each own one) — every `commit`/
        # `repo_url` pair here is a syntactic fixture pointed at
        # `example.invalid`, and the fixtures are plain directories rather
        # than git repositories at all. `verify_pin_preconditions()` is
        # the WHOLE-precondition seam, so stubbing that one name is what
        # keeps this class offline and deterministic; stubbing only the
        # probe would leave the two local conditions refusing every
        # generation here.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "verify_pin_preconditions", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fixture_assets(self, tmp: str) -> tuple[Path, Path]:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# fixture bootstrap cell\nprint('cell-0')\n", encoding="utf-8")
        invoke.write_text("# fixture invoke cell\nprint('cell-1')\n", encoding="utf-8")
        return bootstrap, invoke

    def _ensure_default_source_tree(self, target: Path) -> None:
        """`_generate()`'s default `clone_paths=["src/MIL_CREDA_Benchmark"]`
        and `run_module="MIL_CREDA_Benchmark.harness"` now have to resolve
        to a real file on disk under `target`, since `generate_job()` runs
        `resolve_clone_paths()`. A no-further-imports module is enough:
        exactly what makes the declared clone path match the computed one
        with nothing left over.
        """
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        if not harness.exists():
            harness.parent.mkdir(parents=True, exist_ok=True)
            harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")

    def _generate(self, tmp: str, target: Path, *, assets=None, **overrides) -> Path:
        bootstrap, invoke = assets or self._fixture_assets(tmp)
        self._ensure_default_source_tree(target)
        kwargs = dict(
            target=target,
            service=self.FAKE_SERVICE,
            job_name="search-a",
            product="MIL-CREDA",
            commit="a" * 40,
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            clone_paths=["src/MIL_CREDA_Benchmark"],
            run_module="MIL_CREDA_Benchmark.harness",
            run_function="campaign",
            bootstrap_asset=bootstrap,
            invoke_asset=invoke,
        )
        kwargs.update(overrides)
        return JOBFOLDER.generate_job(**kwargs)

    def test_generate_job_writes_three_files_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()

            job_dir = self._generate(tmp, target)

            self.assertEqual(
                job_dir, (target / "tools" / self.FAKE_SERVICE / "search-a").resolve()
            )
            names = sorted(p.name for p in job_dir.iterdir())
            self.assertEqual(names, ["fake-metadata.json", "run-config.json", "runner.ipynb"])
            self.assertFalse(job_dir.with_name(job_dir.name + ".partial").exists())

            run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
            self.assertEqual(run_config["schemaVersion"], 1)
            self.assertEqual(run_config["product"], "MIL-CREDA")
            self.assertEqual(run_config["run"]["module"], "MIL_CREDA_Benchmark.harness")

    def test_generated_notebook_declares_a_kernelspec_papermill_can_resolve(self) -> None:
        """Confirmed against a real Kaggle kernel run: with no `kernelspec`
        at all, the service's own runner (`papermill`) refuses before a
        single cell executes — `ValueError: No kernel name found in
        notebook and no override provided` — a failure that surfaces only
        after a real push, with quota already spent, for a notebook that
        was never going to run regardless of which target it clones.

        Every generated notebook needs this, unconditionally — it is
        notebook-format correctness, not a fact about any one target
        repository or benchmark, which is why it belongs in
        `build_notebook()` rather than anywhere target-side.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()

            job_dir = self._generate(tmp, target)

            notebook = json.loads((job_dir / "runner.ipynb").read_text(encoding="utf-8"))
            kernelspec = notebook["metadata"]["kernelspec"]
            self.assertEqual(kernelspec["name"], "python3")
            self.assertEqual(kernelspec["language"], "python")

    def test_regeneration_refused_without_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            self._generate(tmp, target)

            with self.assertRaises(JOBFOLDER.JobFolderError):
                self._generate(tmp, target)

    def test_regeneration_with_the_flag_replaces_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            self._generate(tmp, target, commit="a" * 40)

            job_dir = self._generate(tmp, target, commit="b" * 40, regenerate=True)

            run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
            self.assertEqual(run_config["commit"], "b" * 40)
            self.assertFalse(job_dir.with_name(job_dir.name + ".partial").exists())
            leftovers = [
                p for p in job_dir.parent.iterdir() if p.name.startswith("search-a.stale-")
            ]
            self.assertEqual(leftovers, [])

    def test_leftover_partial_dir_is_reported_and_never_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            job_dir = target / "tools" / self.FAKE_SERVICE / "search-a"
            partial = job_dir.with_name(job_dir.name + ".partial")
            partial.mkdir(parents=True)
            (partial / "sentinel").write_text("do-not-read-me", encoding="utf-8")

            with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                self._generate(tmp, target)

            self.assertIn(".partial", str(ctx.exception))
            # Never read as a job folder: the real destination was never
            # created from it, and the sentinel is exactly where it was
            # left — nothing here opened the leftover directory's contents.
            self.assertFalse(job_dir.exists())
            self.assertEqual(
                (partial / "sentinel").read_text(encoding="utf-8"), "do-not-read-me"
            )

    def test_destination_derived_from_service_and_job_name_cannot_escape_target(self) -> None:
        """The one check standing between a crafted `--service`/`--job-name`
        and a write landing outside the resolved target entirely.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()

            with self.assertRaises(JOBFOLDER.JobFolderError):
                self._generate(tmp, target, service="../../escaped", job_name="x")

    def test_relative_target_is_resolved_before_the_destination_is_derived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                job_dir = self._generate(tmp, Path("repo"))
            finally:
                os.chdir(cwd)

            self.assertTrue(job_dir.is_absolute())
            self.assertEqual(
                job_dir, (target / "tools" / self.FAKE_SERVICE / "search-a").resolve()
            )

    def test_empty_clone_paths_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            with self.assertRaises(JOBFOLDER.JobFolderError):
                self._generate(tmp, target, clone_paths=[])

    def test_absolute_clone_path_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            with self.assertRaises(JOBFOLDER.JobFolderError):
                self._generate(tmp, target, clone_paths=["/etc/passwd"])

    def test_dotdot_clone_path_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            with self.assertRaises(JOBFOLDER.JobFolderError):
                self._generate(tmp, target, clone_paths=["src/../../../etc"])

    def test_validate_run_config_refuses_a_missing_required_field(self) -> None:
        with self.assertRaises(JOBFOLDER.JobFolderError):
            JOBFOLDER.validate_run_config({"schemaVersion": 1})

    def test_validate_run_config_refuses_an_unknown_schema_version(self) -> None:
        run_config = {
            "schemaVersion": 99, "product": "P", "service": "s", "jobName": "j",
            "commit": "a" * 40, "repo": {"url": "u", "ref": "main"},
            "clonePaths": ["src/A"], "run": {"module": "A.b", "function": "f"},
            "runnerTemplate": [{"path": "x", "sha256": "y"}],
        }
        with self.assertRaises(JOBFOLDER.JobFolderError):
            JOBFOLDER.validate_run_config(run_config)

    def test_validate_run_config_refuses_a_run_block_missing_function(self) -> None:
        run_config = {
            "schemaVersion": 1, "product": "P", "service": "s", "jobName": "j",
            "commit": "a" * 40, "repo": {"url": "u", "ref": "main"},
            "clonePaths": ["src/A"], "run": {"module": "A.b"},
            "runnerTemplate": [{"path": "x", "sha256": "y"}],
        }
        with self.assertRaises(JOBFOLDER.JobFolderError):
            JOBFOLDER.validate_run_config(run_config)

    def test_runner_template_provenance_records_real_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            bootstrap, invoke = self._fixture_assets(tmp)

            job_dir = self._generate(tmp, target, assets=(bootstrap, invoke))

            run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
            template = run_config["runnerTemplate"]
            self.assertEqual(len(template), 2)
            self.assertEqual(
                template[0]["sha256"], hashlib.sha256(bootstrap.read_bytes()).hexdigest()
            )
            self.assertEqual(
                template[1]["sha256"], hashlib.sha256(invoke.read_bytes()).hexdigest()
            )

    def test_generated_cell_zero_equals_the_asset_byte_for_byte_across_two_different_jobs(
        self,
    ) -> None:
        """The executable-file-classification threat-matrix RED test: the
        notebook's own bytes carry no per-job interpolation at all.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            bootstrap, invoke = self._fixture_assets(tmp)

            job_a = self._generate(
                tmp, target, job_name="job-a", commit="a" * 40, assets=(bootstrap, invoke)
            )
            job_b = self._generate(
                tmp, target, job_name="job-b", commit="b" * 40, assets=(bootstrap, invoke)
            )

            notebook_a = json.loads((job_a / "runner.ipynb").read_text(encoding="utf-8"))
            notebook_b = json.loads((job_b / "runner.ipynb").read_text(encoding="utf-8"))

            self.assertEqual(notebook_a["cells"][0]["source"], notebook_b["cells"][0]["source"])
            self.assertEqual(
                "".join(notebook_a["cells"][0]["source"]), bootstrap.read_text(encoding="utf-8")
            )

    def test_metadata_file_is_written_verbatim_from_the_registered_assembler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()

            job_dir = self._generate(tmp, target)

            content = (job_dir / "fake-metadata.json").read_text(encoding="utf-8")
            self.assertEqual(json.loads(content), {"ok": True})

    def test_jobfolder_module_names_no_service(self) -> None:
        """The no-service guard this new sibling module needs of its own —
        in the same family as `test_adapter_module_names_no_service`,
        `test_remote_cli_module_names_no_service` and
        `test_credentials_module_names_no_service`.
        """
        source = JOBFOLDER_SCRIPT.read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)

    def test_generate_job_cli_wired_through_remote_cli_main_with_fixture_assets(self) -> None:
        """Runtime harness: the real `remote_cli.main()` entry point, not
        `generate_job()` called directly — proves the CLI wiring itself,
        including the fixture-asset override this command does not expose
        as a flag (patched onto the module instead, the way a test doubles
        any other default this skill resolves lazily).
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            self._ensure_default_source_tree(target)
            bootstrap, invoke = self._fixture_assets(tmp)

            with unittest.mock.patch.object(
                JOBFOLDER, "DEFAULT_BOOTSTRAP_ASSET", bootstrap
            ), unittest.mock.patch.object(JOBFOLDER, "DEFAULT_INVOKE_ASSET", invoke):
                exit_code = REMOTE_CLI.main([
                    "generate-job",
                    "--target", str(target),
                    "--service", self.FAKE_SERVICE,
                    "--job-name", "cli-job",
                    "--product", "MIL-CREDA",
                    "--commit", "a" * 40,
                    "--repo-url", "https://example.invalid/repo.git",
                    "--repo-ref", "main",
                    "--clone-path", "src/MIL_CREDA_Benchmark",
                    "--run-module", "MIL_CREDA_Benchmark.harness",
                    "--run-function", "campaign",
                ])

            self.assertEqual(exit_code, 0)
            job_dir = target / "tools" / self.FAKE_SERVICE / "cli-job"
            self.assertTrue((job_dir / "run-config.json").is_file())
            self.assertTrue((job_dir / "runner.ipynb").is_file())

    def test_generate_job_cli_reaches_the_real_default_asset_paths_today(self) -> None:
        """Without an override, `generate-job` reaches THIS repository's own
        real `assets/runner_bootstrap.py` and `assets/runner_invoke.py` —
        proving the CLI's default wiring points at the real location, not a
        fixture. Their content is a placeholder until a later slice, but
        the path resolution and the atomic write around it are real today,
        and this is the one test in this class that proves it end to end.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            self._ensure_default_source_tree(target)

            exit_code = REMOTE_CLI.main([
                "generate-job",
                "--target", str(target),
                "--service", self.FAKE_SERVICE,
                "--job-name", "cli-job",
                "--product", "MIL-CREDA",
                "--commit", "a" * 40,
                "--repo-url", "https://example.invalid/repo.git",
                "--repo-ref", "main",
                "--clone-path", "src/MIL_CREDA_Benchmark",
                "--run-module", "MIL_CREDA_Benchmark.harness",
                "--run-function", "campaign",
            ])

            self.assertEqual(exit_code, 0)
            job_dir = target / "tools" / self.FAKE_SERVICE / "cli-job"
            notebook = json.loads((job_dir / "runner.ipynb").read_text(encoding="utf-8"))
            self.assertEqual(
                "".join(notebook["cells"][0]["source"]),
                JOBFOLDER.DEFAULT_BOOTSTRAP_ASSET.read_text(encoding="utf-8"),
            )

    def test_generate_job_refuses_when_a_transitive_import_is_not_declared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            self._ensure_default_source_tree(target)
            (target / "src" / "MIL_CREDA_Benchmark" / "harness.py").write_text(
                "import Extra.helper\n\n\ndef campaign(*args, **kwargs):\n    pass\n",
                encoding="utf-8",
            )
            extra = target / "src" / "Extra"
            extra.mkdir()
            (extra / "helper.py").write_text("value = 1\n", encoding="utf-8")

            with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                self._generate(tmp, target)

            self.assertIn("src/Extra", str(ctx.exception))

    def test_generate_job_refuses_uncertain_imports_without_accept_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            self._ensure_default_source_tree(target)
            (target / "src" / "MIL_CREDA_Benchmark" / "harness.py").write_text(
                "import sys\nsys.path.append('/tmp/extra')\n\n\n"
                "def campaign(*args, **kwargs):\n    pass\n",
                encoding="utf-8",
            )

            with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                self._generate(tmp, target)

            self.assertIn("sys.path", str(ctx.exception))

    def test_generate_job_accept_unresolved_records_the_decision_in_run_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            self._ensure_default_source_tree(target)
            (target / "src" / "MIL_CREDA_Benchmark" / "harness.py").write_text(
                "import sys\nsys.path.append('/tmp/extra')\n\n\n"
                "def campaign(*args, **kwargs):\n    pass\n",
                encoding="utf-8",
            )

            job_dir = self._generate(tmp, target, accept_unresolved=True)

            run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
            self.assertEqual(len(run_config["unresolvedImports"]), 1)
            self.assertIn("sys.path", run_config["unresolvedImports"][0])

    def test_generate_job_cli_accept_unresolved_flag_reaches_run_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            self._ensure_default_source_tree(target)
            (target / "src" / "MIL_CREDA_Benchmark" / "harness.py").write_text(
                "mod = __import__('MIL_CREDA_Benchmark.harness')\n\n\n"
                "def campaign(*args, **kwargs):\n    pass\n",
                encoding="utf-8",
            )
            bootstrap, invoke = self._fixture_assets(tmp)

            with unittest.mock.patch.object(
                JOBFOLDER, "DEFAULT_BOOTSTRAP_ASSET", bootstrap
            ), unittest.mock.patch.object(JOBFOLDER, "DEFAULT_INVOKE_ASSET", invoke):
                exit_code = REMOTE_CLI.main([
                    "generate-job",
                    "--target", str(target),
                    "--service", self.FAKE_SERVICE,
                    "--job-name", "cli-accept",
                    "--product", "MIL-CREDA",
                    "--commit", "a" * 40,
                    "--repo-url", "https://example.invalid/repo.git",
                    "--repo-ref", "main",
                    "--clone-path", "src/MIL_CREDA_Benchmark",
                    "--run-module", "MIL_CREDA_Benchmark.harness",
                    "--run-function", "campaign",
                    "--accept-unresolved",
                ])

            self.assertEqual(exit_code, 0)
            job_dir = target / "tools" / self.FAKE_SERVICE / "cli-accept"
            run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
            self.assertEqual(len(run_config["unresolvedImports"]), 1)
            self.assertIn("__import__", run_config["unresolvedImports"][0])


class CommitShapeTests(unittest.TestCase):
    """`jobfolder.validate_run_config()` — a pin must be a commit, not a
    name.

    Nothing checked `commit`'s shape at all before this class existed, and
    the consequence was not cosmetic: `--commit main` passed every guard
    downstream of it. The reachability probe succeeds because `main` IS a
    ref name the remote can serve; `_staleness_for()`'s `cat-file -e
    main^{commit}` succeeds because `main` resolves locally; `readiness`
    compares the recorded string `"main"` against itself forever. The
    runner then checks out whatever `main` pointed at on the day it ran.
    A pin that moves was being recorded as if it were immutable, and every
    later check agreed with it.

    Shape validation lives in `validate_run_config()` rather than beside
    the CLI flag deliberately: that function is re-run on every `read()`,
    so a job folder that acquired a name-shaped pin any other way is
    refused when it is read, not only when it is written.
    """

    FAKE_SERVICE = "commit-shape-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def setUp(self) -> None:
        # Shape validation is what this class exercises. The whole-
        # precondition seam is stubbed so this class stays offline and so
        # a refusal reaching a generation here can only be the shape one —
        # these fixtures are plain directories, not git repositories.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "verify_pin_preconditions", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run_config(self, commit: str) -> dict:
        return {
            "schemaVersion": 1,
            "product": "MIL-CREDA",
            "service": self.FAKE_SERVICE,
            "jobName": "search-a",
            "commit": commit,
            "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
            "clonePaths": ["src/MIL_CREDA_Benchmark"],
            "run": {"module": "MIL_CREDA_Benchmark.harness", "function": "campaign"},
            "runnerTemplate": [],
        }

    def _generate(self, tmp: str, target: Path, *, commit: str) -> Path:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# cell-0\n", encoding="utf-8")
        invoke.write_text("# cell-1\n", encoding="utf-8")
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        harness.parent.mkdir(parents=True, exist_ok=True)
        harness.write_text("def campaign(*a, **k):\n    pass\n", encoding="utf-8")
        return JOBFOLDER.generate_job(
            target=target,
            service=self.FAKE_SERVICE,
            job_name="search-a",
            product="MIL-CREDA",
            commit=commit,
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            clone_paths=["src/MIL_CREDA_Benchmark"],
            run_module="MIL_CREDA_Benchmark.harness",
            run_function="campaign",
            bootstrap_asset=bootstrap,
            invoke_asset=invoke,
        )

    def test_a_branch_name_is_refused_and_the_message_names_it(self) -> None:
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            JOBFOLDER.validate_run_config(self._run_config("main"))
        self.assertIn("main", str(caught.exception))

    def test_a_branch_name_refuses_generation_and_writes_no_job_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._generate(tmp, target, commit="main")

            self.assertIn("main", str(caught.exception))
            self.assertFalse((target / "tools").exists())

    def test_the_refusal_says_a_branch_or_tag_name_is_not_a_pin(self) -> None:
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            JOBFOLDER.validate_run_config(self._run_config("v1.2.0"))
        message = str(caught.exception).lower()
        self.assertIn("branch", message)
        self.assertIn("tag", message)

    def test_uppercase_hex_is_refused(self) -> None:
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            JOBFOLDER.validate_run_config(self._run_config("D903D14" + "a" * 33))
        self.assertIn("D903D14", str(caught.exception))

    def test_an_abbreviated_hex_pin_is_refused(self) -> None:
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            JOBFOLDER.validate_run_config(self._run_config("d903d14"))
        self.assertIn("d903d14", str(caught.exception))

    def test_a_lowercase_forty_hex_pin_is_accepted(self) -> None:
        JOBFOLDER.validate_run_config(self._run_config("a1b2c3d4" + "e" * 32))

    def test_a_lowercase_sixty_four_hex_pin_is_accepted(self) -> None:
        """sha256 object names are 64 hex; refusing them would make this
        guard the thing that breaks when git's transition lands.
        """
        JOBFOLDER.validate_run_config(self._run_config("f" * 64))

    def test_a_forty_hex_pin_generates_a_job_folder_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()

            job_dir = self._generate(tmp, target, commit="b" * 40)

            written = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
            self.assertEqual(written["commit"], "b" * 40)

    def test_a_commit_carrying_shell_metacharacters_is_refused_by_shape(self) -> None:
        """The companion to `StalenessTests`'s argv-verbatim lock. That one
        proves `_run_git()` never lets such a value reach a shell; this one
        proves it can no longer reach a job folder at all. Two layers, and
        the outer one is not a reason to remove the inner one.
        """
        malicious = "a$(touch pwned)`touch pwned`;touch pwned"
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            JOBFOLDER.validate_run_config(self._run_config(malicious))
        self.assertIn("touch pwned", str(caught.exception))

    def test_a_non_string_commit_is_refused_rather_than_crashing(self) -> None:
        with self.assertRaises(JOBFOLDER.JobFolderError):
            JOBFOLDER.validate_run_config(self._run_config(None))

    def test_reading_a_job_folder_whose_pin_is_a_name_refuses(self) -> None:
        """`validate_run_config()` runs on every read, so a job folder that
        acquired a name-shaped pin by hand is refused when it is read.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            job_dir = self._generate(tmp, target, commit="c" * 40)
            config_path = job_dir / "run-config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["commit"] = "main"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                JOBFOLDER.read(job_dir)

            self.assertIn("main", str(caught.exception))


class CommitReachabilityTests(unittest.TestCase):
    """`jobfolder._verify_commit_reachable()` — generation refuses when
    the pinned `--commit` cannot be confirmed reachable on the declared
    `--repo-url`, exactly like the existing `computedNotDeclared` refusal:
    fail-closed, never a warning.

    `git cat-file -e <pinned>^{commit}` (used elsewhere in this module,
    for staleness) only proves the pin exists in the LOCAL checkout — it
    says nothing about whether the declared remote can serve it, which is
    what a Kaggle runner actually needs when it clones `--repo-url` and
    checks out the pin inside the kernel. A pin that only exists on the
    author's laptop currently surfaces as a failure inside the kernel,
    after quota is already spent; this is the check that catches it here
    instead, locally, before a single byte is written.

    `git ls-remote <repo_url> <commit>` cannot do this for a bare 40-hex
    commit SHA — proven directly against a real GitHub repository while
    building this check: `ls-remote` matches ref *names*, and a commit
    hash that is not literally a branch/tag name comes back empty with
    exit 0 whether or not the remote actually has the commit. `git fetch
    --dry-run <repo_url> <commit>` is the equivalent that actually answers
    the question — verified the same way: the remote's own upload-pack
    either serves the commit (exit 0) or refuses it with "not our ref"
    (non-zero) — and `--dry-run` means no ref or `FETCH_HEAD` is ever
    written locally.

    Every test in this class has a reachable red: before this task,
    `jobfolder` exposed no `_verify_commit_reachable` attribute at all, so
    every test here that references it fails with `AttributeError`, and
    `generate_job()` wrote a job folder unconditionally regardless of
    whether the pin was reachable anywhere but locally.
    """

    FAKE_SERVICE = "commit-reachability-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def _fixture_assets(self, tmp: str) -> tuple[Path, Path]:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# fixture bootstrap cell\n", encoding="utf-8")
        invoke.write_text("# fixture invoke cell\n", encoding="utf-8")
        return bootstrap, invoke

    def _ensure_default_source_tree(self, target: Path) -> None:
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        if not harness.exists():
            harness.parent.mkdir(parents=True, exist_ok=True)
            harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")

    def _generate(self, tmp: str, target: Path, **overrides) -> Path:
        bootstrap, invoke = self._fixture_assets(tmp)
        self._ensure_default_source_tree(target)
        kwargs = dict(
            target=target,
            service=self.FAKE_SERVICE,
            job_name="search-a",
            product="MIL-CREDA",
            commit="c" * 40,
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            clone_paths=["src/MIL_CREDA_Benchmark"],
            run_module="MIL_CREDA_Benchmark.harness",
            run_function="campaign",
            bootstrap_asset=bootstrap,
            invoke_asset=invoke,
        )
        kwargs.update(overrides)
        return JOBFOLDER.generate_job(**kwargs)

    # -- `_verify_commit_reachable()` in isolation, `_run_git` mocked so no
    # real network call is ever made -------------------------------------

    def test_probes_from_a_scratch_repository_and_never_from_the_target(self) -> None:
        """The argv and the cwd, which are one fact and not two.

        `--depth 1` is not decoration: it is the exact depth
        `assets/runner_bootstrap.py:169` fetches at (`fetch --depth 1
        origin <commit>`), which is what makes this class's own claim —
        that the probe is the operation the runner performs — true rather
        than approximately true. Asserting a full-depth argv while
        claiming to emulate a shallow clone was the assertion describing
        a different operation from the one it named.

        The cwd assertion is the one this class previously got backwards.
        It used to require `cwd == target`; a target that holds the pin
        is the one repository that cannot ask the question, so that
        assertion pinned the defect in place as a requirement. What
        replaces it is the negative that actually matters: the probe's
        cwd is a scratch directory, it is not the target, it is not
        anywhere under the target, and it does not survive the call.
        """
        recorded = []

        def fake_run_git(args, *, cwd, timeout=None):
            recorded.append({"args": list(args), "cwd": Path(cwd)})
            return unittest.mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            with unittest.mock.patch.object(JOBFOLDER, "_run_git", side_effect=fake_run_git):
                JOBFOLDER._verify_commit_reachable(
                    "c" * 40, "https://example.invalid/repo.git", "main"
                )

            self.assertEqual(
                [entry["args"] for entry in recorded],
                [
                    ["init", "-q"],
                    [
                        "fetch",
                        "--dry-run",
                        "--depth",
                        "1",
                        "https://example.invalid/repo.git",
                        "c" * 40,
                    ],
                ],
            )
            # Both calls run in ONE directory: creating the scratch
            # repository somewhere the fetch does not then run is the
            # same defect wearing a different hat.
            cwds = {entry["cwd"] for entry in recorded}
            self.assertEqual(len(cwds), 1, f"probe used more than one cwd: {cwds}")
            probe_cwd = cwds.pop()
            self.assertNotEqual(probe_cwd, target)
            self.assertNotIn(target, probe_cwd.parents)
            self.assertFalse(
                probe_cwd.exists(), "the scratch repository outlived the probe"
            )

    def test_succeeds_silently_when_fetch_dry_run_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            with unittest.mock.patch.object(
                JOBFOLDER, "_run_git", return_value=unittest.mock.Mock(returncode=0)
            ):
                self.assertIsNone(
                    JOBFOLDER._verify_commit_reachable(
                        "c" * 40, "https://example.invalid/repo.git", "main"
                    )
                )

    def test_refuses_when_remote_reports_not_our_ref(self) -> None:
        """The real failure shape `git fetch --dry-run` produces for a
        commit the remote cannot serve — reproduced verbatim from a real
        GitHub repository while building this check.
        """

        def fake_run_git(args, *, cwd, timeout=None):
            raise JOBFOLDER.JobFolderError(
                "git fetch --dry-run exited 128: fatal: remote error: "
                f"upload-pack: not our ref {'d' * 40}"
            )

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            with unittest.mock.patch.object(JOBFOLDER, "_run_git", side_effect=fake_run_git):
                with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                    JOBFOLDER._verify_commit_reachable(
                        "d" * 40, "https://example.invalid/repo.git", "main"
                    )

            self.assertIn("d" * 40, str(ctx.exception))
            self.assertIn("https://example.invalid/repo.git", str(ctx.exception))

    def test_refuses_when_network_is_unavailable_not_a_silent_pass(self) -> None:
        """`_staleness_for()` already refuses to render an unanswerable
        question as `fresh` — `unknown` is a separate branch, never a
        fallback to the clean verdict. The same discipline applies here:
        a network failure cannot confirm reachability any more than it can
        deny it, and generation costs nothing to re-run once connectivity
        is back — a wrong PASS here costs a spent Kaggle quota discovered
        only after the push, which is exactly what this check exists to
        avoid. So an unresolved DNS lookup refuses generation exactly like
        a confirmed-absent commit does, not a warning either way.
        """

        def fake_run_git(args, *, cwd, timeout=None):
            raise JOBFOLDER.JobFolderError(
                "could not run git: [Errno 8] nodename nor servname provided, "
                "or not known"
            )

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            with unittest.mock.patch.object(JOBFOLDER, "_run_git", side_effect=fake_run_git):
                with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                    JOBFOLDER._verify_commit_reachable(
                        "c" * 40, "https://example.invalid/repo.git", "main"
                    )

            self.assertIn("nodename nor servname", str(ctx.exception))

    def test_refuses_when_the_scratch_repository_cannot_be_initialised(self) -> None:
        """A scratch repository that cannot be created is an unanswerable
        question, and this module already has a settled answer for those:
        refuse, the same way a confirmed-absent commit refuses, because
        `unknown` is never rendered as `fresh` anywhere in it. The
        `git init` therefore lives inside the same `try` as the fetch —
        not beside it, where its failure would surface as a bare
        `JobFolderError` naming neither the commit nor the remote the
        operator has to act on.
        """

        def fake_run_git(args, *, cwd, timeout=None):
            if list(args)[:1] == ["init"]:
                raise JOBFOLDER.JobFolderError(
                    "git init -q exited 128: fatal: cannot mkdir .git: Read-only file system"
                )
            raise AssertionError("the fetch ran after the scratch repository failed")

        with unittest.mock.patch.object(JOBFOLDER, "_run_git", side_effect=fake_run_git):
            with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                JOBFOLDER._verify_commit_reachable(
                    "c" * 40, "https://example.invalid/repo.git", "main"
                )

        self.assertIn("c" * 40, str(ctx.exception))
        self.assertIn("https://example.invalid/repo.git", str(ctx.exception))
        self.assertIn("Read-only file system", str(ctx.exception))

    def test_refuses_when_the_scratch_directory_itself_cannot_be_made(self) -> None:
        """The failure one level below `git init`: the temporary
        directory. It arrives as `OSError`, not `JobFolderError`, so it
        reaches the caller as an unhandled `OSError` unless the refusal
        path is written to catch it — and an unhandled `OSError` out of
        `generate_job()` is a crash rather than a refusal, which is the
        one distinction this module's whole error discipline rests on.
        """
        with unittest.mock.patch.object(
            JOBFOLDER.tempfile,
            "TemporaryDirectory",
            side_effect=OSError("[Errno 28] No space left on device"),
        ):
            with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                JOBFOLDER._verify_commit_reachable(
                    "c" * 40, "https://example.invalid/repo.git", "main"
                )

        self.assertIn("c" * 40, str(ctx.exception))
        self.assertIn("https://example.invalid/repo.git", str(ctx.exception))
        self.assertIn("No space left on device", str(ctx.exception))

    # -- against real git repositories: the two facts a mock cannot hold --

    def _real_repositories(self, tmp: str) -> SimpleNamespace:
        """One origin and one target, real git, arranged so that each
        holds a commit the other does not.

        `origin` is what a `--repo-url` points at. `target` is a clone of
        it taken at `shared`, then advanced by a local commit that was
        never pushed, while `origin` was advanced by a commit the clone
        never fetched. That gives the two commits this class needs and a
        mock cannot supply:

          `unpushed`  — in `target`, absent from `origin`. The pin an
                        operator writes after committing and before
                        pushing. It is the case the guard exists for.
          `origin_only` — in `origin`, absent from `target`. A pin the
                        remote can serve and the local checkout has never
                        seen, which is how the probe's own side effects
                        on `target` become observable at all.

        A local path is a real git remote: `fetch` runs `upload-pack`
        against it and answers `not our ref` exactly as a GitHub HTTPS
        remote does — verified directly while writing this class, against
        both a local path and `github.com`, rather than assumed.
        """
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "commit-reachability-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "reachability@example.invalid"

        def git(cwd: Path, *args: str) -> str:
            return subprocess.run(
                ["git", *args],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

        origin = Path(tmp) / "origin"
        origin.mkdir()
        git(origin, "init", "-q")
        (origin / "shared.py").write_text("SHARED = 1\n", encoding="utf-8")
        git(origin, "add", "-A")
        git(origin, "commit", "-q", "-m", "shared")
        shared = git(origin, "rev-parse", "HEAD")

        target = Path(tmp) / "target"
        git(Path(tmp), "clone", "-q", str(origin), str(target))

        (target / "local.py").write_text("LOCAL = 1\n", encoding="utf-8")
        git(target, "add", "-A")
        git(target, "commit", "-q", "-m", "committed but never pushed")
        unpushed = git(target, "rev-parse", "HEAD")

        (origin / "later.py").write_text("LATER = 1\n", encoding="utf-8")
        git(origin, "add", "-A")
        git(origin, "commit", "-q", "-m", "pushed by somebody else")
        origin_only = git(origin, "rev-parse", "HEAD")

        return SimpleNamespace(
            origin=origin,
            target=target,
            shared=shared,
            unpushed=unpushed,
            origin_only=origin_only,
        )

    def test_refuses_a_commit_that_exists_locally_and_was_never_pushed(self) -> None:
        """The whole defect, stated as one assertion against real git.

        Committed, not pushed, then pinned: the local checkout holds the
        object, the declared remote has never heard of it, and a runner
        cloning that remote dies on the checkout after quota is spent.
        The old probe asked this question from inside the very repository
        that holds the object, so git answered it out of the local store
        without ever contacting `upload-pack` and the guard returned
        clean for every pin anyone could write.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repos = self._real_repositories(tmp)

            with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                JOBFOLDER._verify_commit_reachable(
                    repos.unpushed, str(repos.origin), "main"
                )

        message = str(ctx.exception)
        self.assertIn(repos.unpushed, message)
        self.assertIn(str(repos.origin), message)
        # Git's own words, not a second and coarser sentence written
        # over them — `test_reachability_refusal_precedes_clone_path_resolution`
        # below asserts on this same substring surviving the whole way out.
        self.assertIn("not our ref", message)

    def test_a_published_commit_passes_without_depositing_objects_in_the_target(self) -> None:
        """`--dry-run` suppresses ref updates. It does not suppress
        object transfer — measured against the live remote this skill
        targets: one `fetch --dry-run --depth 1` wrote 12.8 MiB of
        objects into the repository it ran in while writing no ref and no
        `FETCH_HEAD` at all.

        So "the probe must not run in the target" is not only about the
        answer being wrong. A probe run there also silently grows the
        operator's object store by the remote's whole shallow tree on
        every single generation. This test pins a commit the target has
        never seen, so a probe running in the target would leave its
        objects behind and be caught here, even in the case where it
        happens to return the right answer.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repos = self._real_repositories(tmp)
            objects = repos.target / ".git" / "objects"
            before = sorted(p.relative_to(objects) for p in objects.rglob("*") if p.is_file())
            fetch_head = repos.target / ".git" / "FETCH_HEAD"

            self.assertIsNone(
                JOBFOLDER._verify_commit_reachable(
                    repos.origin_only, str(repos.origin), "main"
                )
            )

            after = sorted(p.relative_to(objects) for p in objects.rglob("*") if p.is_file())
            self.assertEqual(before, after, "the probe deposited objects in the target")
            self.assertFalse(fetch_head.exists())

    # -- wired into `generate_job()`: refuses before any file is written --

    @staticmethod
    def _clean_tree_git(fetch_error: str | None):
        """A `_run_git` double that answers the LOCAL questions exactly as
        real git answers them for a clean tree, and fails only the fetch
        (or succeeds everywhere, when `fetch_error` is `None`).

        This is a fidelity repair, not a relaxation, and the distinction
        matters enough to write down. These three tests each have one
        subject: the reachability refusal, and that `generate_job()`
        reaches it. Once generation asks git two further local questions
        first, a double that raised for every argv made condition (1)
        refuse first, and a bare `Mock(returncode=0)` made `result.stdout`
        an auto-`Mock` whose `.splitlines()` is a truthy `Mock`, so a
        clean tree read as dirty. Both outcomes are the double being
        wrong about git, not the guard being wrong about the pin.
        Answering `rev-parse HEAD` with a commit and `status --porcelain`
        with the empty string is what real git does in the fixture these
        tests were always describing. It stays silent about conditions (1)
        and (2), which is exactly why those two are locked against real
        git repositories in `CleanWorkingTreeTests` and `PinIsHeadTests`
        and never through this double.
        """

        def fake_run_git(args, *, cwd, timeout=None):
            if args and args[0] == "fetch" and fetch_error is not None:
                raise JOBFOLDER.JobFolderError(fetch_error)
            if args and args[0] == "rev-parse":
                return unittest.mock.Mock(returncode=0, stdout="f" * 40 + "\n", stderr="")
            return unittest.mock.Mock(returncode=0, stdout="", stderr="")

        return fake_run_git

    def test_generate_job_refuses_when_pin_is_not_reachable_on_declared_remote(self) -> None:
        fake_run_git = self._clean_tree_git(
            f"git fetch --dry-run exited 128: fatal: remote error: "
            f"upload-pack: not our ref {'e' * 40}"
        )

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            with unittest.mock.patch.object(JOBFOLDER, "_run_git", side_effect=fake_run_git):
                with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                    self._generate(tmp, target, commit="e" * 40)

            self.assertIn("e" * 40, str(ctx.exception))
            self.assertIn("https://example.invalid/repo.git", str(ctx.exception))
            # Fail-closed before any write: no job folder, no partial
            # leftover — the same atomicity `computedNotDeclared` already
            # guarantees for its own refusal.
            job_dir = target / "tools" / self.FAKE_SERVICE / "search-a"
            self.assertFalse(job_dir.exists())
            self.assertFalse(job_dir.with_name(job_dir.name + ".partial").exists())

    def test_generate_job_succeeds_when_pin_is_reachable_on_declared_remote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            with unittest.mock.patch.object(
                JOBFOLDER, "_run_git", side_effect=self._clean_tree_git(None)
            ):
                job_dir = self._generate(tmp, target)

            self.assertTrue((job_dir / "run-config.json").is_file())

    def test_reachability_refusal_precedes_clone_path_resolution(self) -> None:
        """The reachability check runs early enough to refuse before
        `resolve_clone_paths()` ever parses a single source file — proven
        by pointing `run_module` at a module that does not exist on disk
        at all (which `resolve_clone_paths()` would itself refuse on, but
        with a different message) and confirming the REMOTE refusal is
        the one that actually surfaces.

        The double answers the two local questions as real git does for a
        clean tree, so the refusal observed here really is condition (3)'s
        and not condition (1)'s wearing the same words — every refusal in
        this module carries git's own text forward, which would otherwise
        make the two indistinguishable by substring.
        """
        fake_run_git = self._clean_tree_git("not our ref")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            # No source tree at all under `target` — resolve_clone_paths()
            # would refuse on a missing entry module if it ever ran.
            with unittest.mock.patch.object(JOBFOLDER, "_run_git", side_effect=fake_run_git):
                with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                    JOBFOLDER.generate_job(
                        target=target,
                        service=self.FAKE_SERVICE,
                        job_name="search-a",
                        product="MIL-CREDA",
                        commit="c" * 40,
                        repo_url="https://example.invalid/repo.git",
                        repo_ref="main",
                        clone_paths=["src/MIL_CREDA_Benchmark"],
                        run_module="MIL_CREDA_Benchmark.harness",
                        run_function="campaign",
                        bootstrap_asset=self._fixture_assets(tmp)[0],
                        invoke_asset=self._fixture_assets(tmp)[1],
                    )

            self.assertIn("not our ref", str(ctx.exception))


class ProbeAuthorityTests(unittest.TestCase):
    """The probe must carry no more authority than the runner it stands in for.

    `assets/runner_bootstrap.py:70` builds its git child's environment
    from `("PATH",)` and nothing else, and `:166-170` clones with no
    credential step anywhere in it. A runner is therefore an anonymous
    client by construction. If this probe authenticates — a credential
    helper, an agent socket, a `HOME` carrying `.gitconfig` and
    `.git-credentials` — then it answers a question about a remote *this
    operator* can read, and generation passes for jobs whose runner can
    never clone the repository at all. That is this change's own defect
    one layer up: a guard asking a question different from the one whose
    answer it reports.

    The widening this class does permit is asker-side transport only —
    proxy configuration and the trust store. Those decide whether the
    probe can reach the host; they decide nothing about who it is. The
    runner inherits its own from the kernel it runs in.

    Two further settings live at `_run_git()`, the single composition
    point, rather than at the probe: `GIT_TERMINAL_PROMPT=0` and
    `stdin=DEVNULL`. A credential-requiring remote must fail fast, and
    "fail fast" is not the default — an interactive session's stdin is a
    terminal, and `ssh` prompts on a channel `GIT_TERMINAL_PROMPT` does
    not govern, so a probe that inherited both would sit holding the
    120-second timeout open waiting for a passphrase nobody is there to
    type. Both are inert for the local `rev-parse`/`cat-file`/`diff`
    calls, which is why they belong at the shared point and not at one
    call site.
    """

    # Names that would make the probe someone rather than anyone. `HOME`
    # is here because it is the whole of git's user-configuration story:
    # `~/.gitconfig` carries `credential.helper`, `url.*.insteadOf` and
    # `http.*.extraHeader`, any one of which re-authenticates the child
    # without an obviously credential-shaped variable ever appearing.
    FORBIDDEN_ENV_NAMES = (
        "HOME",
        "SSH_AUTH_SOCK",
        "SSH_ASKPASS",
        "GIT_ASKPASS",
        "GIT_CONFIG",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_COUNT",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "GIT_TOKEN",
        "USERPROFILE",
        "XDG_CONFIG_HOME",
        "NETRC",
    )

    def test_the_allowlist_admits_no_name_that_confers_authorization(self) -> None:
        admitted = set(JOBFOLDER.GIT_ENV_ALLOWLIST)
        leaked = sorted(admitted.intersection(self.FORBIDDEN_ENV_NAMES))
        self.assertEqual(
            leaked,
            [],
            "the probe may reach a remote the runner cannot: "
            f"{leaked} confer authorization and the runner has none",
        )
        # A name-by-name list cannot anticipate every future variable, so
        # the shape is held too: nothing token-, password-, credential-
        # or auth-shaped, whatever it ends up being called.
        shaped = sorted(
            name
            for name in admitted
            if re.search(r"TOKEN|PASSWORD|CREDENTIAL|SECRET|AUTH|NETRC", name, re.IGNORECASE)
        )
        self.assertEqual(shaped, [], f"authorization-shaped names in the allowlist: {shaped}")

    def test_the_allowlist_widens_for_transport_and_keeps_the_runner_s_own_path(self) -> None:
        admitted = set(JOBFOLDER.GIT_ENV_ALLOWLIST)
        self.assertIn("PATH", admitted, "the runner's own allowlist is `('PATH',)`")
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "GIT_SSL_CAINFO",
        ):
            with self.subTest(name=name):
                self.assertIn(name, admitted)
        # Both cases of every proxy variable, because curl reads the
        # lowercase spelling and a corporate environment commonly sets
        # only that one; admitting one case and not the other produces a
        # refusal that is a local misconfiguration wearing the message of
        # an unpublished commit.
        self.assertEqual(
            sorted(n for n in admitted if n.upper().endswith("_PROXY")),
            sorted(
                [
                    "ALL_PROXY",
                    "HTTPS_PROXY",
                    "HTTP_PROXY",
                    "NO_PROXY",
                    "all_proxy",
                    "http_proxy",
                    "https_proxy",
                    "no_proxy",
                ]
            ),
        )

    def _record_subprocess_call(self) -> dict:
        recorded = {}

        def fake_run(argv, **kwargs):
            recorded["argv"] = list(argv)
            recorded.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with unittest.mock.patch.object(JOBFOLDER.subprocess, "run", side_effect=fake_run):
            JOBFOLDER._run_git(["rev-parse", "HEAD"], cwd=Path(REPOSITORY_ROOT))
        return recorded

    def test_the_child_is_told_never_to_prompt_for_credentials(self) -> None:
        recorded = self._record_subprocess_call()
        self.assertEqual(recorded["env"].get("GIT_TERMINAL_PROMPT"), "0")

    def test_the_child_never_inherits_this_process_s_terminal_on_stdin(self) -> None:
        """`GIT_TERMINAL_PROMPT=0` closes git's own prompt. It does not
        close `ssh`'s, which reads a passphrase from the terminal
        directly. In an interactive session this process's stdin is that
        terminal, so without this the probe against an SSH remote blocks
        until the 120-second timeout instead of refusing at once.
        """
        recorded = self._record_subprocess_call()
        self.assertIs(recorded.get("stdin"), subprocess.DEVNULL)

    def test_an_ssh_remote_refuses_through_the_reachability_path_naming_the_probe(self) -> None:
        def fake_run_git(args, *, cwd, timeout=None):
            if list(args)[:1] == ["init"]:
                return unittest.mock.Mock(returncode=0, stdout="", stderr="")
            raise JOBFOLDER.JobFolderError(
                "git fetch --dry-run --depth 1 exited 128: "
                "git@host: Permission denied (publickey)."
            )

        with unittest.mock.patch.object(JOBFOLDER, "_run_git", side_effect=fake_run_git):
            with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                JOBFOLDER._verify_commit_reachable(
                    "a" * 40, "git@host:owner/repo.git", "main"
                )

        message = str(ctx.exception)
        # The ordinary reachability refusal, enriched — not a second one.
        self.assertIn("could not be confirmed reachable", message)
        self.assertIn("git@host:owner/repo.git", message)
        self.assertIn("Permission denied (publickey)", message)
        self.assertIn("unauthenticated", message)

    def test_an_ssh_remote_is_not_refused_by_a_separate_guard_before_the_fetch(self) -> None:
        """"Enriched message, not a new guard" is a claim with an
        observable consequence, and this is it: an SSH-shaped URL that
        the probe can actually serve is accepted. A guard that rejected
        SSH URLs on sight would be deciding remote policy the runner
        never asked it to decide, and would refuse a working deploy-key
        setup on the strength of a colon in a string.
        """
        calls = []

        def fake_run_git(args, *, cwd, timeout=None):
            calls.append(list(args))
            return unittest.mock.Mock(returncode=0, stdout="", stderr="")

        with unittest.mock.patch.object(JOBFOLDER, "_run_git", side_effect=fake_run_git):
            self.assertIsNone(
                JOBFOLDER._verify_commit_reachable(
                    "a" * 40, "git@host:owner/repo.git", "main"
                )
            )

        self.assertEqual(len(calls), 2, f"the fetch never ran: {calls}")
        self.assertEqual(calls[1][0], "fetch")


class CleanWorkingTreeTests(unittest.TestCase):
    """`jobfolder.verify_pin_preconditions()` and its first condition —
    the working tree must be clean over the declared clone paths.

    Nothing checked this before. `resolve_clone_paths()` walks the WORKING
    TREE (`jobfolder.py`'s `_module_to_relpath` resolves against files on
    disk), so generation validated bytes the runner would never receive:
    a brand-new `run_search.py` that was never `git add`ed satisfied the
    import walk happily and was simply absent from the commit the runner
    clones. The job died in the kernel with `ModuleNotFoundError` after
    quota was already spent.

    The instrument is `git status --porcelain`, never `git diff`, and that
    is not interchangeable. `diff` enumerates changes to TRACKED content;
    an untracked path is outside its domain by construction. Measured in a
    scratch repository with one modified tracked file and one file never
    added: `diff --name-only` reports only the modified one, while
    `status --porcelain` reports `M existente.py` AND `?? run_search.py`.
    The untracked case is exactly the one this condition exists to catch,
    so a `diff`-based version would be blind to its own purpose.

    Real git fixtures throughout: an untracked file is not a state a mocked
    `_run_git` can express without the mock simply asserting the answer.
    """

    FAKE_SERVICE = "clean-worktree-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def setUp(self) -> None:
        # Condition (3) reaches a network. Every `repo_url` here is
        # `example.invalid`; stubbed so this class stays offline and so a
        # refusal here can only be condition (1)'s.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "_verify_commit_reachable", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "clean-worktree-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "clean-worktree-tests@example.invalid"
        return subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check
        )

    def _init_repo(self, target: Path) -> str:
        target.mkdir(parents=True, exist_ok=True)
        self._git(target, "init", "-q")
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        harness.parent.mkdir(parents=True, exist_ok=True)
        harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")
        (target / "README.md").write_text("outside every clone path\n", encoding="utf-8")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", "initial")
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _verify(self, target: Path, commit: str, *, decision: str = "generation") -> None:
        JOBFOLDER.verify_pin_preconditions(
            target=target,
            commit=commit,
            clone_paths=["src/MIL_CREDA_Benchmark"],
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            decision=decision,
        )

    def _tree_fingerprint(self, target: Path) -> list:
        """Every path under `target` with its bytes, `.git` included — the
        instrument for "the repository is byte-identical afterwards".
        """
        entries = []
        for path in sorted(target.rglob("*")):
            if path.is_file():
                entries.append((str(path.relative_to(target)), path.read_bytes()))
        return entries

    # -- the shared seam ------------------------------------------------

    def test_pin_conditions_is_an_ordered_tuple_of_condition_ids(self) -> None:
        self.assertIsInstance(JOBFOLDER.PIN_CONDITIONS, tuple)
        self.assertEqual(JOBFOLDER.PIN_CONDITIONS[0], "clean-worktree")
        self.assertIn("pin-published", JOBFOLDER.PIN_CONDITIONS)

    def test_generate_job_calls_the_shared_seam_and_not_the_probe_directly(self) -> None:
        """The seam is the only thing either decision point calls. Proven
        by stubbing `verify_pin_preconditions` alone and confirming the
        probe never runs — if `generate_job()` still called
        `_verify_commit_reachable()` beside the seam, the probe would fire.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)
            probe_calls = []

            with unittest.mock.patch.object(
                JOBFOLDER, "_verify_commit_reachable",
                side_effect=lambda *a, **k: probe_calls.append((a, k)),
            ), unittest.mock.patch.object(
                JOBFOLDER, "verify_pin_preconditions", return_value=None
            ):
                self._generate(tmp, target, commit="a" * 40)

            self.assertEqual(probe_calls, [], "the probe ran beside the seam")

    def test_the_seam_receives_the_decision_word_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            recorded = {}

            with unittest.mock.patch.object(
                JOBFOLDER, "verify_pin_preconditions",
                side_effect=lambda **kwargs: recorded.update(kwargs),
            ):
                self._generate(tmp, target, commit=head)

            self.assertEqual(recorded["decision"], "generation")
            self.assertEqual(recorded["commit"], head)
            self.assertEqual(list(recorded["clone_paths"]), ["src/MIL_CREDA_Benchmark"])
            self.assertEqual(recorded["repo_url"], "https://example.invalid/repo.git")
            self.assertEqual(recorded["repo_ref"], "main")

    def _fixture_assets(self, tmp: str) -> tuple[Path, Path]:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# cell-0\n", encoding="utf-8")
        invoke.write_text("# cell-1\n", encoding="utf-8")
        return bootstrap, invoke

    def _generate(self, tmp: str, target: Path, *, commit: str) -> Path:
        bootstrap, invoke = self._fixture_assets(tmp)
        return JOBFOLDER.generate_job(
            target=target,
            service=self.FAKE_SERVICE,
            job_name="search-a",
            product="MIL-CREDA",
            commit=commit,
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            clone_paths=["src/MIL_CREDA_Benchmark"],
            run_module="MIL_CREDA_Benchmark.harness",
            run_function="campaign",
            bootstrap_asset=bootstrap,
            invoke_asset=invoke,
        )

    # -- condition (1) ---------------------------------------------------

    def test_a_modified_tracked_file_under_a_clone_path_refuses_naming_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
            harness.write_text("def campaign():\n    return 'edited'\n", encoding="utf-8")

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, head)

            self.assertIn("src/MIL_CREDA_Benchmark/harness.py", str(caught.exception))

    def test_an_untracked_non_ignored_file_under_a_clone_path_refuses_naming_it(self) -> None:
        """The case `git diff` cannot see, and the reason this condition
        exists at all: `resolve_clone_paths()` would validate this file's
        imports happily and the runner would never receive it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            new_module = target / "src" / "MIL_CREDA_Benchmark" / "run_search.py"
            new_module.write_text("def search():\n    pass\n", encoding="utf-8")

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, head)

            self.assertIn("src/MIL_CREDA_Benchmark/run_search.py", str(caught.exception))

    def test_git_diff_would_not_have_seen_the_untracked_file(self) -> None:
        """Not a test of this module — a test of the instrument choice,
        measured against real git so the docstring above is a fact and not
        a recollection. If this ever goes green the wrong way, `status`
        stopped being the stronger instrument and the choice needs
        rethinking, not the assertion relaxing.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)
            harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
            harness.write_text("def campaign():\n    return 'edited'\n", encoding="utf-8")
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "def search():\n    pass\n", encoding="utf-8"
            )

            diffed = self._git(
                target, "diff", "--name-only", "--", "src/MIL_CREDA_Benchmark"
            ).stdout
            statused = self._git(
                target, "status", "--porcelain", "--", "src/MIL_CREDA_Benchmark"
            ).stdout

            self.assertIn("harness.py", diffed)
            self.assertNotIn("run_search.py", diffed)
            self.assertIn("harness.py", statused)
            self.assertIn("run_search.py", statused)

    def test_a_staged_but_uncommitted_file_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            staged = target / "src" / "MIL_CREDA_Benchmark" / "staged.py"
            staged.write_text("STAGED = 1\n", encoding="utf-8")
            self._git(target, "add", "src/MIL_CREDA_Benchmark/staged.py")

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, head)

            self.assertIn("src/MIL_CREDA_Benchmark/staged.py", str(caught.exception))

    def test_an_ignored_file_under_a_clone_path_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target).mkdir(parents=True, exist_ok=True)
            head = self._init_repo(target)
            (target / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
            self._git(target, "add", ".gitignore")
            self._git(target, "commit", "-q", "-m", "ignore pyc")
            head = self._git(target, "rev-parse", "HEAD").stdout.strip()
            (target / "src" / "MIL_CREDA_Benchmark" / "harness.pyc").write_bytes(b"\x00")

            self._verify(target, head)

    def test_dirt_outside_every_clone_path_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            (target / "README.md").write_text("edited outside the clone paths\n", encoding="utf-8")
            (target / "scratch-note.txt").write_text("untracked, outside\n", encoding="utf-8")

            self._verify(target, head)

    def test_a_target_that_is_not_a_repository_refuses_carrying_gits_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "plain"
            (target / "src" / "MIL_CREDA_Benchmark").mkdir(parents=True)

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, "a" * 40)

            self.assertIn("not a git repository", str(caught.exception))

    def test_a_repository_with_no_commits_refuses_carrying_gits_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "src" / "MIL_CREDA_Benchmark").mkdir(parents=True)
            self._git(target, "init", "-q")

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, "a" * 40)

            self.assertIn("HEAD", str(caught.exception))

    def test_the_refusal_names_the_commands_the_operator_can_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "x = 1\n", encoding="utf-8"
            )

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, head)

            message = str(caught.exception)
            self.assertIn("git add", message)
            self.assertIn("git commit", message)

    def test_the_refusal_offers_no_dirty_tree_escape_hatch(self) -> None:
        """Rejected by name by the operator this change was written for. A
        refusal that advertises a bypass is a refusal that will be bypassed.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "x = 1\n", encoding="utf-8"
            )

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, head)

            lowered = str(caught.exception).lower()
            for hatch in ("--accept-dirty", "--force", "--allow-dirty", "--skip"):
                self.assertNotIn(hatch, lowered, hatch)

    def test_the_repository_is_byte_identical_after_every_refusal(self) -> None:
        """The tool never stages, commits, stashes or fetches on the
        operator's behalf. A commit message is a human artifact, and an
        automatic commit poisons the very history later used to say which
        code produced which number.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "x = 1\n", encoding="utf-8"
            )
            harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
            harness.write_text("def campaign():\n    return 'edited'\n", encoding="utf-8")
            before = self._tree_fingerprint(target)

            with self.assertRaises(JOBFOLDER.JobFolderError):
                self._verify(target, head)

            self.assertEqual(self._tree_fingerprint(target), before)

    # -- through generation ----------------------------------------------

    def test_generation_refuses_a_dirty_tree_and_writes_no_job_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "def search():\n    pass\n", encoding="utf-8"
            )

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._generate(tmp, target, commit=head)

            self.assertIn("run_search.py", str(caught.exception))
            self.assertFalse((target / "tools").exists())

    def test_generation_succeeds_on_a_clean_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)

            job_dir = self._generate(tmp, target, commit=head)

            self.assertTrue((job_dir / "run-config.json").is_file())

    def test_generations_own_untracked_output_under_tools_does_not_refuse_it(self) -> None:
        """`generate_job()` writes untracked files under `<target>/tools/`.
        An unscoped cleanliness check would forbid its own output on the
        second run; the `-- <clone_paths…>` pathspec is what prevents that.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)

            self._generate(tmp, target, commit=head)
            self._verify(target, head)


class PinIsHeadTests(unittest.TestCase):
    """`jobfolder`'s second pin condition — the pin must be HEAD, or
    nothing may have changed between them under the declared clone paths.

    The verdict is not computed a second time here. `_staleness_for()`
    already answers exactly this question, and has since the job folder
    existed — it just never did anything but REPORT. Two non-gating layers
    consumed it (a line in `submit`'s return payload, `fromStaleSubmission`
    on the way back) and neither could refuse, so a job folder pinned to a
    commit whose code had already moved on was generated, submitted and
    run, with the drift printed alongside the submission id as though it
    were weather.

    The asymmetry that remains is deliberate and is documented in
    `SKILL.md` and in `jobfolder.py`: the SAME verdict refuses at a
    decision point and only reports at `read()`. `read()` is an
    observation — refusing there would make a drifted job folder
    unreadable, which is the one state where reading it is most useful.

    `unknown` refuses too, and is never rendered as `fresh`. A pin absent
    from local history cannot be shown to be HEAD or to be equivalent to
    it, and this module has one settled answer for questions that cannot
    be asked.
    """

    FAKE_SERVICE = "pin-is-head-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def setUp(self) -> None:
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "_verify_commit_reachable", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "pin-is-head-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "pin-is-head-tests@example.invalid"
        return subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check
        )

    def _init_repo(self, target: Path) -> str:
        target.mkdir(parents=True, exist_ok=True)
        self._git(target, "init", "-q")
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        harness.parent.mkdir(parents=True, exist_ok=True)
        harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")
        (target / "README.md").write_text("outside every clone path\n", encoding="utf-8")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", "initial")
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _commit_all(self, target: Path, message: str) -> str:
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", message)
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _verify(self, target: Path, commit: str, *, decision: str = "generation") -> None:
        JOBFOLDER.verify_pin_preconditions(
            target=target,
            commit=commit,
            clone_paths=["src/MIL_CREDA_Benchmark"],
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            decision=decision,
        )

    def test_every_local_condition_runs_before_the_one_that_reaches_a_network(self) -> None:
        """Order is the contract, and it is cheapest-first: every local,
        instant question before the one that dials out. Named as the property
        rather than by counting, because the count changed once a fourth
        condition arrived and a test that asserts the count has to be edited
        for a reason that is not about order at all.
        """
        conditions = list(JOBFOLDER.PIN_CONDITIONS)
        self.assertEqual(
            conditions,
            ["clean-worktree", "pin-is-head", "declared-paths-exist",
             "pin-published"],
        )
        self.assertEqual(conditions[-1], "pin-published",
                         "the network condition must be last, whatever else "
                         "is added before it")

    def test_a_pin_behind_head_under_the_clone_paths_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            pinned = self._init_repo(target)
            harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
            harness.write_text("def campaign():\n    return 2\n", encoding="utf-8")
            head = self._commit_all(target, "move the harness on")

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, pinned)

            message = str(caught.exception)
            self.assertIn("src/MIL_CREDA_Benchmark/harness.py", message)
            self.assertIn(pinned, message)
            self.assertIn(head, message)

    def test_a_pin_behind_head_only_outside_the_clone_paths_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            pinned = self._init_repo(target)
            (target / "README.md").write_text("docs moved on\n", encoding="utf-8")
            self._commit_all(target, "docs only")

            self._verify(target, pinned)

    def test_a_pin_absent_from_local_history_is_unknown_and_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, "d" * 40)

            message = str(caught.exception)
            self.assertIn("d" * 40, message)
            self.assertIn("unknown", message.lower())

    def test_the_unknown_refusal_carries_gits_own_words_forward(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, "d" * 40)

            self.assertIn("cat-file", str(caught.exception))

    def test_the_pin_being_head_itself_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)

            self._verify(target, head)

    def test_the_refusal_does_not_commit_or_push_on_the_operators_behalf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            pinned = self._init_repo(target)
            harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
            harness.write_text("def campaign():\n    return 2\n", encoding="utf-8")
            self._commit_all(target, "move the harness on")
            before = self._git(target, "rev-parse", "HEAD").stdout.strip()

            with self.assertRaises(JOBFOLDER.JobFolderError):
                self._verify(target, pinned)

            self.assertEqual(
                self._git(target, "rev-parse", "HEAD").stdout.strip(), before
            )
            self.assertEqual(
                self._git(target, "status", "--porcelain").stdout.strip(), ""
            )

    def test_condition_two_runs_after_condition_one(self) -> None:
        """A dirty tree AND a drifted pin: the dirty tree is what the
        operator hears about, because it is the cheaper question and the
        one whose remedy comes first.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            pinned = self._init_repo(target)
            harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
            harness.write_text("def campaign():\n    return 2\n", encoding="utf-8")
            self._commit_all(target, "move the harness on")
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "x = 1\n", encoding="utf-8"
            )

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._verify(target, pinned)

            self.assertIn("run_search.py", str(caught.exception))

    def test_condition_two_uses_the_one_existing_staleness_computation(self) -> None:
        """No second diff. The generation guard and the read-time report
        cannot drift because there is only one of them.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            pinned = self._init_repo(target)
            calls = []

            real = JOBFOLDER._staleness_for

            def recording(target_arg, pinned_commit, clone_paths):
                calls.append((pinned_commit, list(clone_paths)))
                return real(target_arg, pinned_commit, clone_paths)

            with unittest.mock.patch.object(
                JOBFOLDER, "_staleness_for", side_effect=recording
            ):
                self._verify(target, pinned)

            self.assertEqual(calls, [(pinned, ["src/MIL_CREDA_Benchmark"])])

    # -- the asymmetry: refuse at a decision point, report at read() ------

    def _fixture_assets(self, tmp: str) -> tuple[Path, Path]:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# cell-0\n", encoding="utf-8")
        invoke.write_text("# cell-1\n", encoding="utf-8")
        return bootstrap, invoke

    def _generate(self, tmp: str, target: Path, *, commit: str) -> Path:
        bootstrap, invoke = self._fixture_assets(tmp)
        return JOBFOLDER.generate_job(
            target=target,
            service=self.FAKE_SERVICE,
            job_name="search-a",
            product="MIL-CREDA",
            commit=commit,
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            clone_paths=["src/MIL_CREDA_Benchmark"],
            run_module="MIL_CREDA_Benchmark.harness",
            run_function="campaign",
            bootstrap_asset=bootstrap,
            invoke_asset=invoke,
        )

    def test_reading_a_drifted_job_folder_still_only_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)

            harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
            harness.write_text("def campaign():\n    return 2\n", encoding="utf-8")
            self._commit_all(target, "move the harness on")

            job_folder = JOBFOLDER.read(job_dir)

            self.assertEqual(job_folder.staleness["status"], "drift")
            self.assertIn(
                "src/MIL_CREDA_Benchmark/harness.py",
                job_folder.staleness["changedPaths"],
            )

    def test_generation_refuses_a_drifted_pin_and_writes_no_job_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            pinned = self._init_repo(target)
            harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
            harness.write_text("def campaign():\n    return 2\n", encoding="utf-8")
            self._commit_all(target, "move the harness on")

            with self.assertRaises(JOBFOLDER.JobFolderError):
                self._generate(tmp, target, commit=pinned)

            self.assertFalse((target / "tools").exists())


class PinConditionDoctrineTests(unittest.TestCase):
    """`SKILL.md` must document every pin condition, and the suite holds
    the doctrine to the code rather than to a reviewer's memory.

    The lock is a parseable table, not prose, and that is the established
    local idiom for a reason: prose cannot be held to code. A condition
    added to `PIN_CONDITIONS` with no table row is a condition an operator
    hits at a decision point and cannot look up — which is exactly the
    state this whole change started from. `SKILL.md` documented the
    reachability guard NOWHERE (zero hits for `reachab`, `dry-run`,
    `ls-remote`), which is why the defect had no doctrine to contradict
    it for as long as it did.

    `tests/test_proposal_implementation.py` has a `markdown_table_rows`
    helper, but it is local to that module and this suite does not import
    across test modules; the parser below is deliberately small and local
    for the same reason.
    """

    HEADER = "| # | id | Condition | Enforced at | Refusal names |"

    def _table_rows(self, text: str, header: str) -> list:
        """Every data row of the one table introduced by `header`, as a
        list of stripped cell lists. Stops at the first line that is not a
        table row, so a second table further down the file cannot be
        silently absorbed into this one.
        """
        lines = text.split("\n")
        try:
            start = next(
                i for i, line in enumerate(lines) if line.strip() == header
            )
        except StopIteration:
            self.fail(
                f"SKILL.md has no pin-condition table: the exact header "
                f"{header!r} was not found"
            )
        rows = []
        for line in lines[start + 1:]:
            stripped = line.strip()
            if not stripped.startswith("|"):
                break
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= {"-", ":"} and cell for cell in cells):
                continue  # the separator row
            rows.append(cells)
        return rows

    def test_the_table_documents_every_condition_in_pin_conditions_order(self) -> None:
        rows = self._table_rows(SKILL_MD.read_text(encoding="utf-8"), self.HEADER)
        documented = [row[1].strip("`") for row in rows]
        expected = list(JOBFOLDER.PIN_CONDITIONS)

        undocumented = [c for c in expected if c not in documented]
        self.assertEqual(
            undocumented, [],
            f"enforced at a decision point and absent from SKILL.md's table: "
            f"{undocumented}",
        )
        invented = [c for c in documented if c not in expected]
        self.assertEqual(
            invented, [],
            f"documented in SKILL.md's table and enforced nowhere: {invented}",
        )
        self.assertEqual(documented, expected, "the table's order is the contract")

    def test_every_row_names_where_it_is_enforced_and_what_it_names(self) -> None:
        rows = self._table_rows(SKILL_MD.read_text(encoding="utf-8"), self.HEADER)
        for row in rows:
            self.assertEqual(len(row), 5, row)
            for cell in row:
                self.assertTrue(cell, row)

    def test_both_decision_points_are_named_in_every_row(self) -> None:
        """One implementation, two callers. A row that named only
        `generate-job` would describe the code before this change.
        """
        rows = self._table_rows(SKILL_MD.read_text(encoding="utf-8"), self.HEADER)
        for row in rows:
            enforced_at = row[3]
            self.assertIn("generate-job", enforced_at, row)
            self.assertIn("submit", enforced_at, row)

    def test_doctrine_states_the_tool_never_commits_or_pushes(self) -> None:
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("never commits or pushes on your behalf", text)

    def test_doctrine_states_there_is_no_dirty_tree_escape_hatch(self) -> None:
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("no dirty-tree escape hatch", text)

    def test_doctrine_documents_the_refuse_versus_report_asymmetry(self) -> None:
        text = SKILL_MD.read_text(encoding="utf-8").lower()
        self.assertIn("refuses at a decision point", text)
        self.assertIn("only reports", text)


class CommitDefaultTests(unittest.TestCase):
    """`--commit` may be omitted, and then defaults to the target's HEAD.

    This is the only requirement in this change that ADDS convenience, and
    it is safe only because the three conditions landed first. HEAD is a
    trustworthy pin exactly when condition (1) proves the working tree
    holds the same bytes as the commit, and condition (2) proves the pin
    is that commit. Ship the default without them and you ship the silent-
    wrong-pin behaviour this whole change exists to remove, wearing a
    friendlier interface.

    An explicit `--commit` still means exactly what it says. It is never
    substituted, never discovered, and above all never resolved from the
    remote: the remote's tip was measured to be OLDER than the entrypoint
    the operator needed, which existed only in an unpushed commit. Remote
    resolution would pin code older than the caller's, pass every local
    check because generation validates against the working tree, and die
    in the kernel after quota is spent — the same failure class,
    reintroduced by helpfulness.

    The pin's SOURCE is reported on stdout and is deliberately absent from
    `run-config.json`. How the caller typed an argument is feedback for the
    person who typed it; it is not a fact about the job, and a job folder
    records facts about the job.
    """

    FAKE_SERVICE = "commit-default-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def setUp(self) -> None:
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "_verify_commit_reachable", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "commit-default-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "commit-default-tests@example.invalid"
        return subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check
        )

    def _init_repo(self, target: Path) -> str:
        target.mkdir(parents=True, exist_ok=True)
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        harness.parent.mkdir(parents=True, exist_ok=True)
        harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")
        self._git(target, "init", "-q")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", "initial")
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _fixture_assets(self, tmp: str) -> tuple[Path, Path]:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# cell-0\n", encoding="utf-8")
        invoke.write_text("# cell-1\n", encoding="utf-8")
        return bootstrap, invoke

    def _generate(self, tmp: str, target: Path, **overrides) -> Path:
        bootstrap, invoke = self._fixture_assets(tmp)
        kwargs = dict(
            target=target,
            service=self.FAKE_SERVICE,
            job_name="search-a",
            product="MIL-CREDA",
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            clone_paths=["src/MIL_CREDA_Benchmark"],
            run_module="MIL_CREDA_Benchmark.harness",
            run_function="campaign",
            bootstrap_asset=bootstrap,
            invoke_asset=invoke,
        )
        kwargs.update(overrides)
        return JOBFOLDER.generate_job(**kwargs)

    def _cli(self, tmp: str, target: Path, *extra: str) -> tuple[int, dict]:
        bootstrap, invoke = self._fixture_assets(tmp)
        stdout = io.StringIO()
        with unittest.mock.patch.object(
            JOBFOLDER, "DEFAULT_BOOTSTRAP_ASSET", bootstrap
        ), unittest.mock.patch.object(
            JOBFOLDER, "DEFAULT_INVOKE_ASSET", invoke
        ), contextlib.redirect_stdout(stdout):
            exit_code = REMOTE_CLI.main([
                "generate-job",
                "--target", str(target),
                "--service", self.FAKE_SERVICE,
                "--job-name", "cli-job",
                "--product", "MIL-CREDA",
                "--repo-url", "https://example.invalid/repo.git",
                "--repo-ref", "main",
                "--clone-path", "src/MIL_CREDA_Benchmark",
                "--run-module", "MIL_CREDA_Benchmark.harness",
                "--run-function", "campaign",
                *extra,
            ])
        printed = stdout.getvalue().strip()
        return exit_code, (json.loads(printed) if printed else {})

    # -- the default ------------------------------------------------------

    def test_omitting_the_commit_pins_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)

            job_dir = self._generate(tmp, target)

            written = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
            self.assertEqual(written["commit"], head)

    def test_the_python_api_and_the_cli_share_one_resolution(self) -> None:
        """One implementation, not two that can disagree about what HEAD
        means.
        """
        source = JOBFOLDER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("rev-parse", source)
        cli_source = REMOTE_CLI_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('"rev-parse"', cli_source)

    def test_stdout_reports_the_pinned_commit_and_that_it_was_defaulted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)

            exit_code, printed = self._cli(tmp, target)

            self.assertEqual(exit_code, 0)
            self.assertEqual(printed["commit"], head)
            self.assertEqual(printed["commitSource"], "default-head")

    def test_stdout_reports_an_explicit_pin_as_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)

            exit_code, printed = self._cli(tmp, target, "--commit", head)

            self.assertEqual(exit_code, 0)
            self.assertEqual(printed["commit"], head)
            self.assertEqual(printed["commitSource"], "explicit")

    def test_commit_source_is_absent_from_run_config(self) -> None:
        """It describes how the caller typed an argument, not a fact about
        the job. A job folder records facts about the job.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)

            job_dir = self._generate(tmp, target)

            written = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
            self.assertNotIn("commitSource", written)
            self.assertNotIn(
                "commitSource", (job_dir / "run-config.json").read_text(encoding="utf-8")
            )

    # -- the default is not independent of the conditions ------------------

    def test_omitting_the_commit_with_a_dirty_tree_refuses_and_writes_nothing(self) -> None:
        """The default cannot exist independently of condition (1). HEAD is
        a safe pin only because the tree is proven to hold the same bytes.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "def search():\n    pass\n", encoding="utf-8"
            )

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._generate(tmp, target)

            self.assertIn("run_search.py", str(caught.exception))
            self.assertFalse((target / "tools").exists())

    def test_a_defaulted_pin_goes_through_every_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            recorded = {}

            with unittest.mock.patch.object(
                JOBFOLDER, "verify_pin_preconditions",
                side_effect=lambda **kwargs: recorded.update(kwargs),
            ):
                self._generate(tmp, target)

            self.assertEqual(recorded["commit"], head)
            self.assertEqual(recorded["decision"], "generation")

    def test_defaulting_in_a_target_with_no_history_refuses_with_gits_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "src" / "MIL_CREDA_Benchmark").mkdir(parents=True)
            (target / "src" / "MIL_CREDA_Benchmark" / "harness.py").write_text(
                "def campaign():\n    pass\n", encoding="utf-8"
            )
            self._git(target, "init", "-q")

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._generate(tmp, target)

            self.assertIn("HEAD", str(caught.exception))
            self.assertFalse((target / "tools").exists())

    # -- explicit still means explicit -------------------------------------

    def test_an_explicit_commit_is_never_substituted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            first = self._init_repo(target)
            (target / "README.md").write_text("docs\n", encoding="utf-8")
            self._git(target, "add", "-A")
            self._git(target, "commit", "-q", "-m", "docs only")
            head = self._git(target, "rev-parse", "HEAD").stdout.strip()
            self.assertNotEqual(first, head)

            job_dir = self._generate(tmp, target, commit=first)

            written = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
            self.assertEqual(written["commit"], first)
            self.assertNotEqual(written["commit"], head)

    def test_no_remote_derived_commit_is_ever_substituted(self) -> None:
        """Measured against the live remote before this was written: its
        tip was OLDER than the entrypoint the operator needed. Resolving a
        pin from the remote would silently ship code older than the
        caller's and pass every local check, because generation validates
        against the working tree.
        """
        source = JOBFOLDER_SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        generate = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_resolve_pin"
        )
        argv_strings = {
            node.value for node in ast.walk(generate)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        for remote_shaped in ("ls-remote", "fetch", "origin", "FETCH_HEAD"):
            self.assertNotIn(remote_shaped, argv_strings, remote_shaped)

    def test_a_shape_invalid_explicit_commit_still_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)

            with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                self._generate(tmp, target, commit="main")

            self.assertIn("main", str(caught.exception))

    def test_the_dead_return_after_read_is_gone(self) -> None:
        """No behavioural delta; recorded in the spec so it is not read as
        scope creep. `read()` ended with a second, unreachable `return
        destination` — a name that does not even exist in that function's
        scope. Unreachable code is prose that lies about what a function
        does, and this one lied about what it returns.
        """
        tree = ast.parse(JOBFOLDER_SCRIPT.read_text(encoding="utf-8"))
        read = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "read"
        )
        top_level_returns = [
            node for node in read.body if isinstance(node, ast.Return)
        ]
        self.assertEqual(
            len(top_level_returns), 1,
            "read() has an unreachable statement after its return",
        )


class ResolveClonePathsTests(unittest.TestCase):
    """`jobfolder.resolve_clone_paths()` — the AST-based, transitive
    dependency check (design #744 section 3). Reuses
    `implementation_cli.py`'s `prior_work_state()` idiom (`ast.parse` +
    `ast.walk` over `ast.Import`/`ast.ImportFrom`, inspecting only
    `node.module`/`alias.name`, with no relative-import resolution and no
    per-name submodule disambiguation) verbatim, walked transitively over
    every module an entry module reaches instead of one fixed file set.

    Every test in this class has a reachable red: before this task,
    `jobfolder` exposed no `resolve_clone_paths` attribute at all, so every
    test here fails with `AttributeError` on the very first call.
    """

    def _write(self, root: Path, relative: str, text: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_transitive_import_is_computed_and_external_imports_are_filtered(self) -> None:
        """A directly-imported local package, one reached transitively
        through it, and a stdlib import alongside both — only the two
        local top-level directories become clone paths.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(
                target, "src/A/entry.py",
                "import os\nimport B.helper\n\n\ndef run():\n    return B.helper.value\n",
            )
            self._write(target, "src/B/helper.py", "value = 1\n")

            result = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A", "src/B"])

            self.assertEqual(result["computed"], ["src/A", "src/B"])
            self.assertEqual(result["computedNotDeclared"], [])
            self.assertEqual(result["unresolved"], [])

    def test_from_package_import_of_a_name_also_reaches_that_submodules_own_imports(
        self,
    ) -> None:
        """`from A import sub` names `sub` only as an imported NAME on
        `node.module = "A"` — the walk's own documented "no per-name
        submodule disambiguation" means `enqueue("A")` alone resolves to
        `A/__init__.py`, never to `A/sub.py`, when `sub` is actually a
        submodule FILE rather than an attribute `__init__.py` itself
        defines. `A/sub.py`'s own imports were then never walked at
        all — confirmed as a real production gap: a job folder generated
        for `from MIL_CREDA_Benchmark import bags, config, report_digest,
        wiring` (an empty `__init__.py`) let `wiring.py`'s own `from
        MIL_CREDA.attention import ...` slip through undeclared, and the
        clone failed at runtime with `ModuleNotFoundError: No module named
        'MIL_CREDA'` — exactly the silent gap `computedNotDeclared` exists
        to refuse.

        The fix must stay conservative: `A.sub` is enqueued ONLY when it
        actually resolves to a file on disk (a real submodule); an
        ordinary `from A import some_attribute` where `some_attribute` is
        merely a name `__init__.py` defines must not become a spurious
        `unresolved` entry.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(target, "src/A/__init__.py", "")
            self._write(target, "src/A/entry.py", "from A import sub\n")
            self._write(target, "src/A/sub.py", "import C.thing\n")
            self._write(target, "src/C/thing.py", "value = 1\n")

            missing = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A"])
            self.assertEqual(missing["computedNotDeclared"], ["src/C"])

            complete = JOBFOLDER.resolve_clone_paths(
                target, ["A.entry"], ["src/A", "src/C"]
            )
            self.assertEqual(complete["computed"], ["src/A", "src/C"])
            self.assertEqual(complete["computedNotDeclared"], [])
            self.assertEqual(complete["unresolved"], [])

    def test_from_package_import_of_a_plain_attribute_is_not_flagged_unresolved(
        self,
    ) -> None:
        """The conservative half of the same fix: `from A import value`,
        where `value` is an ordinary name `__init__.py` defines (not a
        submodule file), must not become a spurious `unresolved` entry —
        only a candidate that actually resolves to a file on disk is ever
        enqueued at all.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(target, "src/A/__init__.py", "value = 1\n")
            self._write(target, "src/A/entry.py", "from A import value\n")

            result = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A"])

            self.assertEqual(result["computed"], ["src/A"])
            self.assertEqual(result["computedNotDeclared"], [])
            self.assertEqual(result["unresolved"], [])

    def test_computed_not_declared_is_reported_and_never_silently_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(target, "src/A/entry.py", "import B.helper\n")
            self._write(target, "src/B/helper.py", "value = 1\n")

            result = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A"])

            self.assertEqual(result["computedNotDeclared"], ["src/B"])
            self.assertEqual(result["declared"], ["src/A"])

    def test_granularity_rule_maps_a_deep_import_to_its_top_level_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(target, "src/A/B/C.py", "value = 1\n")
            self._write(target, "src/A/entry.py", "import A.B.C\n")

            result = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A"])

            self.assertEqual(result["computed"], ["src/A"])

    def test_true_top_level_module_clone_path_is_the_file_itself(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(target, "src/single.py", "def entry():\n    pass\n")

            result = JOBFOLDER.resolve_clone_paths(target, ["single"], ["src/single.py"])

            self.assertEqual(result["computed"], ["src/single.py"])
            self.assertEqual(result["computedNotDeclared"], [])

    def test_entry_module_missing_on_disk_is_uncertain_not_external(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "src").mkdir()

            result = JOBFOLDER.resolve_clone_paths(
                target, ["Missing.entry"], ["src/Placeholder"]
            )

            self.assertEqual(result["computed"], [])
            self.assertEqual(len(result["unresolved"]), 1)
            self.assertIn("Missing.entry", result["unresolved"][0])

    def test_import_resolving_to_nothing_under_an_existing_package_is_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(target, "src/A/entry.py", "import A.missing_submodule\n")

            result = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A"])

            self.assertEqual(len(result["unresolved"]), 1)
            self.assertIn("A.missing_submodule", result["unresolved"][0])

    def test_non_literal_import_module_call_is_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(
                target, "src/A/entry.py",
                "import importlib\n\nname = 'A.' + str(1)\nimportlib.import_module(name)\n",
            )

            result = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A"])

            self.assertEqual(len(result["unresolved"]), 1)
            self.assertIn("import_module", result["unresolved"][0])

    def test_dunder_import_call_is_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(target, "src/A/entry.py", "mod = __import__('A.sibling')\n")

            result = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A"])

            self.assertEqual(len(result["unresolved"]), 1)
            self.assertIn("__import__", result["unresolved"][0])

    def test_sys_path_mutation_is_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(
                target, "src/A/entry.py", "import sys\nsys.path.append('/tmp/extra')\n"
            )

            result = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A"])

            self.assertEqual(len(result["unresolved"]), 1)
            self.assertIn("sys.path", result["unresolved"][0])

    def test_unparsable_file_is_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._write(target, "src/A/entry.py", "def broken(:\n    pass\n")

            result = JOBFOLDER.resolve_clone_paths(target, ["A.entry"], ["src/A"])

            self.assertEqual(result["computed"], ["src/A"])
            self.assertEqual(len(result["unresolved"]), 1)
            self.assertIn("unparsable", result["unresolved"][0])

    def test_validate_clone_paths_target_argument_refuses_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (target / "src").mkdir()
            (target / "src" / "escaped").symlink_to(outside)

            with self.assertRaises(JOBFOLDER.JobFolderError):
                JOBFOLDER.validate_clone_paths(["src/escaped"], target)

    def test_validate_clone_paths_without_target_argument_is_unchanged(self) -> None:
        self.assertEqual(JOBFOLDER.validate_clone_paths(["src/A"]), ("src/A",))


class StalenessTests(unittest.TestCase):
    """`jobfolder.read()` — design #744 section 4: there is no `is_stale()`
    a caller can forget, because staleness is computed INSIDE the one
    reader. `JobFolder.staleness` is therefore always present on whatever
    `read()` returns; getting a `JobFolder` back without a staleness
    verdict alongside it is not something this module's API can express.

    Every test in this class has a reachable red: before this task,
    `jobfolder` exposed no `read` attribute at all, so every test here
    fails with `AttributeError` on the very first call.
    """

    FAKE_SERVICE = "staleness-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def setUp(self) -> None:
        # Staleness (this class's own subject) is orthogonal to the pin
        # preconditions — every `repo_url` here is `example.invalid`, a
        # fixture, never a real remote, and several tests here
        # deliberately generate into a non-repository or against a pin
        # absent from history, which are exactly the states conditions (1)
        # and (2) forbid at a decision point and `read()` only reports.
        # The whole-precondition seam is stubbed, not just the probe.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "verify_pin_preconditions", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "staleness-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "staleness-tests@example.invalid"
        return subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check
        )

    def _init_repo(self, target: Path) -> str:
        """A real, throwaway git repository AT `target` itself — not a
        clone source the way `RunnerBootstrapTests`' `_make_origin_repo`
        is, since `read()`'s staleness runs `git` directly inside the
        resolved target, never against a clone.
        """
        target.mkdir(parents=True, exist_ok=True)
        self._git(target, "init", "-q")
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        harness.parent.mkdir(parents=True, exist_ok=True)
        harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")
        (target / "README.md").write_text("scratch fixture\n", encoding="utf-8")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", "initial")
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _fixture_assets(self, tmp: str) -> tuple[Path, Path]:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# fixture bootstrap cell\n", encoding="utf-8")
        invoke.write_text("# fixture invoke cell\n", encoding="utf-8")
        return bootstrap, invoke

    def _ensure_source_tree(self, target: Path) -> None:
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        if not harness.exists():
            harness.parent.mkdir(parents=True, exist_ok=True)
            harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")

    def _generate(self, tmp: str, target: Path, *, commit: str, job_name: str = "search-a") -> Path:
        self._ensure_source_tree(target)
        bootstrap, invoke = self._fixture_assets(tmp)
        return JOBFOLDER.generate_job(
            target=target,
            service=self.FAKE_SERVICE,
            job_name=job_name,
            product="MIL-CREDA",
            commit=commit,
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            clone_paths=["src/MIL_CREDA_Benchmark"],
            run_module="MIL_CREDA_Benchmark.harness",
            run_function="campaign",
            bootstrap_asset=bootstrap,
            invoke_asset=invoke,
        )

    # -- the runtime harness: declared vs. undeclared clone path ----------

    def test_runtime_harness_drift_vs_not_stale_by_declared_vs_undeclared_clone_path(
        self,
    ) -> None:
        """The contrast that proves the pathspec is doing the intersection:
        a job folder generated in a scratch git repo, then HEAD advances
        twice — once touching only an UNDECLARED path, once touching the
        DECLARED clone path — and only the second one reports `drift`.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            initial_commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=initial_commit)

            fresh = JOBFOLDER.read(job_dir)
            self.assertEqual(fresh.staleness["status"], "fresh")
            self.assertEqual(fresh.staleness["changedPaths"], [])

            # Advance HEAD touching only an UNDECLARED path.
            (target / "README.md").write_text("changed\n", encoding="utf-8")
            self._git(target, "add", "-A")
            self._git(target, "commit", "-q", "-m", "undeclared change")

            still_not_stale = JOBFOLDER.read(job_dir)
            self.assertEqual(still_not_stale.staleness["status"], "fresh")

            # Advance HEAD again, this time touching the DECLARED clone path.
            (target / "src" / "MIL_CREDA_Benchmark" / "harness.py").write_text(
                "def campaign(*args, **kwargs):\n    return 1\n", encoding="utf-8"
            )
            self._git(target, "add", "-A")
            self._git(target, "commit", "-q", "-m", "declared change")

            drifted = JOBFOLDER.read(job_dir)
            self.assertEqual(drifted.staleness["status"], "drift")
            self.assertIn(
                "src/MIL_CREDA_Benchmark/harness.py", drifted.staleness["changedPaths"]
            )

    def test_drift_is_never_a_refusal(self) -> None:
        """`read()` returns a `JobFolder` even when the verdict is
        `drift` — it never raises. Staleness informs; it does not block.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            initial_commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=initial_commit)

            (target / "src" / "MIL_CREDA_Benchmark" / "harness.py").write_text(
                "def campaign(*args, **kwargs):\n    return 2\n", encoding="utf-8"
            )
            self._git(target, "add", "-A")
            self._git(target, "commit", "-q", "-m", "declared change")

            job_folder = JOBFOLDER.read(job_dir)
            self.assertEqual(job_folder.staleness["status"], "drift")
            self.assertIsInstance(job_folder, JOBFOLDER.JobFolder)

    # -- unknown, and unknown is never fresh -------------------------------

    def test_unknown_when_target_has_no_git_history_at_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            job_dir = self._generate(tmp, target, commit="a" * 40)

            result = JOBFOLDER.read(job_dir)

            self.assertEqual(result.staleness["status"], "unknown")
            self.assertIsNotNone(result.staleness["reason"])
            self.assertNotEqual(result.staleness["status"], "fresh")

    def test_unknown_when_pinned_commit_is_absent_from_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)
            # A syntactically plausible commit that was never actually
            # committed in this repository's history.
            job_dir = self._generate(tmp, target, commit="f" * 40)

            result = JOBFOLDER.read(job_dir)

            self.assertEqual(result.staleness["status"], "unknown")
            self.assertIn("f" * 40, result.staleness["reason"])

    def test_unknown_is_never_rendered_as_fresh(self) -> None:
        """Absence of evidence is not evidence of freshness. Explicit,
        separate from the two cases above: this asserts the DISTINCTION,
        not merely that one particular unknown case exists.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            job_dir = self._generate(tmp, target, commit="a" * 40)

            result = JOBFOLDER.read(job_dir)

            self.assertIn(result.staleness["status"], ("unknown", "drift"))
            self.assertNotEqual(result.staleness["status"], "fresh")
            self.assertEqual(result.staleness["status"], "unknown")

    # -- clone paths validated again on every read -------------------------

    def test_read_reuses_validate_clone_paths_and_refuses_a_symlink_escape(self) -> None:
        """`read()` re-validates `clonePaths` through the SAME
        `validate_clone_paths()` `generate_job()` already calls — never a
        second, parallel validator. Proven here by making the declared
        clone path escape target via a symlink installed AFTER generation.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            initial_commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=initial_commit)

            outside = Path(tmp) / "outside"
            outside.mkdir()
            real_dir = target / "src" / "MIL_CREDA_Benchmark"
            shutil.rmtree(real_dir)
            real_dir.symlink_to(outside)

            with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                JOBFOLDER.read(job_dir)
            self.assertIn("symlink escape", str(ctx.exception))

    # -- security: git invocation -------------------------------------------

    def test_run_git_env_admits_nothing_beyond_the_declared_allowlist(self) -> None:
        """This test used to read `assertEqual(set(recorded_env), {"PATH"})`,
        and it was the only thing in the suite holding the allowlist at
        all — a fact the plan for widening it had recorded as "no test
        asserts the allowlist today", wrongly.

        Spelling the expected set out literally was fine while the
        allowlist had exactly one entry and became a maintenance
        assertion the moment it did not: it fails whenever the list
        changes, whether the change is a proxy variable or a credential
        helper, and so distinguishes neither. What it was actually for is
        kept and made explicit here — nothing reaches the child that the
        allowlist did not name, and a variable that is merely present in
        the parent's environment does not get in. Which names the
        allowlist may contain is a separate question with a separate
        answer, in `ProbeAuthorityTests`, where it is decided by what the
        name confers rather than by how long the list is.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)
            recorded_env: dict = {}
            real_run = subprocess.run

            def recording_run(argv, **kwargs):
                recorded_env.update(kwargs.get("env") or {})
                return real_run(argv, **kwargs)

            intruders = {
                "SOME_OTHER_VAR": "leak-me-not",
                # The shapes that would matter if they did leak: git's own
                # user configuration, and an agent the probe must not have.
                "HOME": str(target),
                "SSH_AUTH_SOCK": "/tmp/leak-me-not.sock",
                "GIT_CONFIG_GLOBAL": str(target / "leak-me-not.gitconfig"),
            }
            with unittest.mock.patch.object(
                JOBFOLDER.subprocess, "run", side_effect=recording_run
            ), unittest.mock.patch.dict(os.environ, intruders):
                JOBFOLDER._run_git(["rev-parse", "HEAD"], cwd=target)

            self.assertIn("PATH", recorded_env)
            for name in intruders:
                with self.subTest(name=name):
                    self.assertNotIn(name, recorded_env)
            # `GIT_TERMINAL_PROMPT` is set by `_run_git` itself rather
            # than forwarded from the parent, so it is the one key here
            # that is not an allowlist entry.
            self.assertEqual(
                set(recorded_env) - {"GIT_TERMINAL_PROMPT"} - set(JOBFOLDER.GIT_ENV_ALLOWLIST),
                set(),
            )

    def test_run_git_non_zero_exit_is_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            with self.assertRaises(JOBFOLDER.JobFolderError):
                JOBFOLDER._run_git(["this-is-not-a-real-git-subcommand"], cwd=target)

    def test_run_git_timeout_is_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            target.mkdir()
            with unittest.mock.patch.object(
                JOBFOLDER.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd=["git", "init"], timeout=1.0),
            ):
                with self.assertRaises(JOBFOLDER.JobFolderError):
                    JOBFOLDER._run_git(["init"], cwd=target, timeout=1.0)

    def test_pinned_commit_carrying_shell_metacharacters_reaches_argv_verbatim_and_executes_nothing(
        self,
    ) -> None:
        """The mandated RED test: a pinned commit value carrying shell
        metacharacters must reach `_run_git`'s own argv verbatim and
        execute nothing — `shell=False` plus a list argv means the whole
        malicious string travels as ONE argv element, never evaluated by a
        shell.

        Driven straight at `_staleness_for()` rather than through a
        generated job folder, because commit-shape validation now refuses
        such a value at `build_run_config()` and again at every `read()`:
        it can no longer reach a job folder at all
        (`CommitShapeTests.test_a_commit_carrying_shell_metacharacters_is_refused_by_shape`
        holds that half). The claim this test makes is about `_run_git()`,
        not about the job folder that used to be the only way to reach it,
        and it is worth keeping precisely because the outer layer is not a
        reason to stop proving the inner one: `_staleness_for()` is called
        with a pin from a config this process did not necessarily write.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)
            marker_name = "pwned-marker-jobfolder"
            marker_path = Path.cwd() / marker_name
            malicious = f"a$(touch {marker_name})`touch {marker_name}`;touch {marker_name}"

            recorded_argv: list = []
            real_run = subprocess.run

            def recording_run(argv, **kwargs):
                recorded_argv.append(list(argv))
                return real_run(argv, **kwargs)

            try:
                with unittest.mock.patch.object(
                    JOBFOLDER.subprocess, "run", side_effect=recording_run
                ):
                    staleness = JOBFOLDER._staleness_for(
                        target.resolve(), malicious, ["src/MIL_CREDA_Benchmark"]
                    )

                self.assertEqual(staleness["status"], "unknown")
                self.assertFalse(marker_path.exists())
                self.assertTrue(
                    any(malicious in "".join(call) for call in recorded_argv)
                )
            finally:
                if marker_path.exists():
                    marker_path.unlink()

    def test_jobfolder_module_names_no_service_still_holds(self) -> None:
        """Re-confirms the existing guard stays green with `read()`,
        `_run_git()` and the staleness helpers added — no ninth guard is
        needed since this is the same module, not a new sibling.
        """
        source = JOBFOLDER_SCRIPT.read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)


class SubmitPinGateTests(unittest.TestCase):
    """`remote_cli._gate_job_folder_pin()` — `submit` refuses before quota
    is spent, instead of reporting after it.

    `cmd_submit` computed a staleness verdict and put it in its RETURN
    VALUE, after `LEDGER.append(event)` had already run. By the time the
    operator could read it, the adapter had accepted the job, the quota was
    gone and the ledger said a submission had happened. It reported on a
    submission that had already occurred, which is not a gate — it is a
    receipt with a warning printed on it.

    The gate runs the same three conditions, from the same one function
    `generate-job` calls, against the job folder's OWN declared pin, clone
    paths and remote. It sits after `product_for()` and before the digest
    walk, the plan, `adapter.submit()` and `LEDGER.append()`, so a refusal
    costs nothing and leaves no trace.

    It discriminates on `run-config.json`'s PRESENCE, deliberately not on
    `_job_folder_staleness()`, which returns `None` on two different paths:
    the legacy shape AND a `run-config.json` it cannot read. Reusing it
    would let a job folder skip all three conditions by being unreadable,
    which is the worse half of this change's own defect class. A legacy
    entrypoint skipping the conditions is not a finding — it has no
    declared pin, no declared clone paths and no declared remote, so there
    is nothing to check, and it never promised a runner a commit.
    """

    FAKE_SERVICE = "submit-gate-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "submit-gate-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "submit-gate-tests@example.invalid"
        return subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check
        )

    def _init_repo(self, target: Path) -> str:
        target.mkdir(parents=True, exist_ok=True)
        (target / "MIL-CREDA").mkdir(parents=True, exist_ok=True)
        (target / "MIL-CREDA" / ".keep").write_text("", encoding="utf-8")
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        harness.parent.mkdir(parents=True, exist_ok=True)
        harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")
        self._git(target, "init", "-q")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", "initial")
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _commit_all(self, target: Path, message: str) -> str:
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", message)
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _generate(self, tmp: str, target: Path, *, commit: str) -> Path:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# cell-0\n", encoding="utf-8")
        invoke.write_text("# cell-1\n", encoding="utf-8")
        with unittest.mock.patch.object(
            JOBFOLDER, "verify_pin_preconditions", return_value=None
        ):
            return JOBFOLDER.generate_job(
                target=target,
                service=self.FAKE_SERVICE,
                job_name="search-a",
                product="MIL-CREDA",
                commit=commit,
                repo_url="https://example.invalid/repo.git",
                repo_ref="main",
                clone_paths=["src/MIL_CREDA_Benchmark"],
                run_module="MIL_CREDA_Benchmark.harness",
                run_function="campaign",
                bootstrap_asset=bootstrap,
                invoke_asset=invoke,
            )

    class _SpyAdapter(FakeAdapter):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.submitted: list = []

        def submit(self, job):
            self.submitted.append(job)
            return super().submit(job)

    def _submit(self, target: Path, notebook: Path, adapter) -> dict:
        return REMOTE_CLI.cmd_submit(
            target=target,
            entrypoint=notebook,
            worker="w1",
            requested=1,
            adapter=adapter,
            source_digest=lambda t, n: "d" * 64,
        )

    def _ledger_path(self, target: Path) -> Path:
        return target.resolve() / "MIL-CREDA" / ".remote-execution" / "ledger.jsonl"

    # -- the three conditions, at submit time ----------------------------

    def test_a_dirty_tree_refuses_with_no_adapter_call_and_no_ledger_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "def search():\n    pass\n", encoding="utf-8"
            )
            adapter = self._SpyAdapter(worker_id="w1", capacity=2)

            with unittest.mock.patch.object(
                JOBFOLDER, "_verify_commit_reachable", return_value=None
            ):
                with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                    self._submit(target, job_dir / "runner.ipynb", adapter)

            self.assertIn("run_search.py", str(caught.exception))
            self.assertEqual(adapter.submitted, [], "the adapter was called anyway")
            self.assertFalse(
                self._ledger_path(target).exists(), "a ledger line was appended anyway"
            )

    def test_a_drifted_pin_refuses_before_the_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)
            harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
            harness.write_text("def campaign():\n    return 2\n", encoding="utf-8")
            self._commit_all(target, "move the harness on")
            adapter = self._SpyAdapter(worker_id="w1", capacity=2)

            with unittest.mock.patch.object(
                JOBFOLDER, "_verify_commit_reachable", return_value=None
            ):
                with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                    self._submit(target, job_dir / "runner.ipynb", adapter)

            self.assertIn(head, str(caught.exception))
            self.assertEqual(adapter.submitted, [])
            self.assertFalse(self._ledger_path(target).exists())

    def test_an_unpushed_pin_refuses_naming_the_commit_the_remote_and_the_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)
            adapter = self._SpyAdapter(worker_id="w1", capacity=2)

            def fake_run_git(args, *, cwd, timeout=None):
                if args and args[0] == "fetch":
                    raise JOBFOLDER.JobFolderError(
                        "git fetch --dry-run exited 128: fatal: remote error: "
                        "upload-pack: not our ref"
                    )
                return REAL_RUN_GIT(args, cwd=cwd, timeout=timeout)

            REAL_RUN_GIT = JOBFOLDER._run_git
            with unittest.mock.patch.object(
                JOBFOLDER, "_run_git", side_effect=fake_run_git
            ):
                with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                    self._submit(target, job_dir / "runner.ipynb", adapter)

            message = str(caught.exception)
            self.assertIn(head, message)
            self.assertIn("https://example.invalid/repo.git", message)
            self.assertIn("push", message)
            self.assertEqual(adapter.submitted, [])
            self.assertFalse(self._ledger_path(target).exists())

    def test_the_refusal_says_submission_not_generation(self) -> None:
        """One implementation, two callers, and exactly one word different
        between them — the word that says which decision was refused.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "x = 1\n", encoding="utf-8"
            )

            with unittest.mock.patch.object(
                JOBFOLDER, "_verify_commit_reachable", return_value=None
            ):
                with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
                    self._submit(
                        target,
                        job_dir / "runner.ipynb",
                        self._SpyAdapter(worker_id="w1", capacity=2),
                    )

            self.assertIn("submission refuses", str(caught.exception))

    def test_a_clean_job_folder_still_submits_and_keeps_staleness_in_the_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)
            adapter = self._SpyAdapter(worker_id="w1", capacity=2)

            with unittest.mock.patch.object(
                JOBFOLDER, "_verify_commit_reachable", return_value=None
            ):
                result = self._submit(target, job_dir / "runner.ipynb", adapter)

            self.assertEqual(len(adapter.submitted), 1)
            self.assertEqual(result["staleness"]["status"], "fresh")
            self.assertTrue(self._ledger_path(target).exists())

    def test_the_gate_runs_before_the_digest_walk(self) -> None:
        """Refusing must cost nothing. The digest walk reads the whole
        product tree; running it first would make every refusal pay for a
        submission that is not going to happen.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "x = 1\n", encoding="utf-8"
            )
            digest_calls = []

            with unittest.mock.patch.object(
                JOBFOLDER, "_verify_commit_reachable", return_value=None
            ):
                with self.assertRaises(JOBFOLDER.JobFolderError):
                    REMOTE_CLI.cmd_submit(
                        target=target,
                        entrypoint=job_dir / "runner.ipynb",
                        worker="w1",
                        requested=1,
                        adapter=self._SpyAdapter(worker_id="w1", capacity=2),
                        source_digest=lambda t, n: digest_calls.append((t, n)) or "d" * 64,
                    )

            self.assertEqual(digest_calls, [], "the digest walk ran before the gate")

    def test_a_smoke_rehearsal_meets_the_same_gate(self) -> None:
        """A rehearsal is a real submission: it dials out, uploads and
        spends quota. Exempting it would make the gate optional in
        exactly the workflow that runs most often.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "x = 1\n", encoding="utf-8"
            )
            adapter = self._SpyAdapter(worker_id="w1", capacity=2)

            with unittest.mock.patch.object(
                JOBFOLDER, "_verify_commit_reachable", return_value=None
            ):
                with self.assertRaises(JOBFOLDER.JobFolderError):
                    REMOTE_CLI.cmd_submit(
                        target=target,
                        entrypoint=job_dir / "runner.ipynb",
                        worker="w1",
                        requested=1,
                        adapter=adapter,
                        source_digest=lambda t, n: "d" * 64,
                        smoke=True,
                    )

            self.assertEqual(adapter.submitted, [])

    # -- the discriminator ------------------------------------------------

    def test_a_legacy_entrypoint_with_no_run_config_is_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            self._init_repo(target)
            notebooks = target / "MIL-CREDA" / "Notebooks"
            notebooks.mkdir(parents=True)
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            # Deliberately dirty, and deliberately not a job folder: there
            # is no declared pin, no declared clone paths and no declared
            # remote here, so there is nothing for the gate to check.
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "x = 1\n", encoding="utf-8"
            )
            adapter = self._SpyAdapter(worker_id="w1", capacity=2)

            result = self._submit(target, notebook, adapter)

            self.assertEqual(len(adapter.submitted), 1)
            self.assertIsNone(result["staleness"])

    def test_a_malformed_run_config_refuses_rather_than_skipping_every_condition(self) -> None:
        """`_job_folder_staleness()` returns `None` for BOTH the legacy
        shape and an unreadable `run-config.json`. Discriminating on that
        return value would let a job folder skip all three conditions by
        being unreadable — a new refusal path this change adds
        deliberately, and the one place it is stricter than the spec's own
        wording. Precedent: `cmd_smoke_record` already refuses to swallow
        a `JobFolderError` for the same reason.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)
            (job_dir / "run-config.json").write_text(
                json.dumps({"product": "MIL-CREDA"}), encoding="utf-8"
            )
            adapter = self._SpyAdapter(worker_id="w1", capacity=2)

            with self.assertRaises(JOBFOLDER.JobFolderError):
                self._submit(target, job_dir / "runner.ipynb", adapter)

            self.assertEqual(adapter.submitted, [])
            self.assertFalse(self._ledger_path(target).exists())

    def test_the_gate_does_not_reuse_the_staleness_helper_as_its_discriminator(self) -> None:
        """A source-level lock on the finding above: `_job_folder_staleness`
        is tolerant by design and must not become the gate's fork.
        """
        tree = ast.parse(REMOTE_CLI_SCRIPT.read_text(encoding="utf-8"))
        gate = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_gate_job_folder_pin"
        )
        called = {
            node.func.id
            for node in ast.walk(gate)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        # Read off the code, never off the prose: the docstring names the
        # tolerant helper precisely in order to say why it is not used.
        self.assertNotIn("_job_folder_staleness", called)
        names = {
            node.id for node in ast.walk(gate) if isinstance(node, ast.Name)
        }
        self.assertIn("RUN_CONFIG_FILENAME", names)

    def test_a_job_folder_refusal_reaches_stderr_through_the_cli(self) -> None:
        """`submit`'s CLI except-tuple has to carry `JobFolderError`
        unwrapped, so the message an operator sees at submit is
        byte-identical to the one generation would have printed.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            head = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=head)
            (target / "src" / "MIL_CREDA_Benchmark" / "run_search.py").write_text(
                "x = 1\n", encoding="utf-8"
            )
            stderr = io.StringIO()

            with unittest.mock.patch.object(
                JOBFOLDER, "_verify_commit_reachable", return_value=None
            ), unittest.mock.patch.object(
                REMOTE_CLI, "_load_backend_module", return_value=None
            ), unittest.mock.patch.object(
                REMOTE_CLI.ADAPTER, "resolve", return_value=FakeAdapter
            ), unittest.mock.patch.object(
                REMOTE_CLI, "_construct_adapter",
                return_value=FakeAdapter(worker_id="w1", capacity=2),
            ), contextlib.redirect_stderr(stderr):
                exit_code = REMOTE_CLI.main([
                    "submit",
                    "--target", str(target),
                    "--entrypoint", str(job_dir / "runner.ipynb"),
                    "--worker", "w1",
                    "--requested", "1",
                    "--backend", "fake",
                ])

            self.assertEqual(exit_code, 1)
            self.assertIn("run_search.py", stderr.getvalue())
            self.assertIn("submission refuses", stderr.getvalue())


class StalenessRoutingTests(unittest.TestCase):
    """Every existing job-folder-touching command in `remote_cli.py` routes
    staleness reporting through `jobfolder.read()` — design #744 section 4:
    `generate-job`, `submit`, `status`, `fetch`, `reconcile`. (`readiness`
    and probe's fact do not exist yet — T11/T13 build them.)
    """

    FAKE_SERVICE = "staleness-routing-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def setUp(self) -> None:
        # This class exercises staleness routing, not the pin
        # preconditions — every `repo_url` here is `example.invalid`, a
        # fixture. The whole-precondition seam is stubbed so this class
        # stays offline and deterministic.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "verify_pin_preconditions", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "staleness-routing-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "staleness-routing-tests@example.invalid"
        return subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check
        )

    def _init_repo(self, target: Path) -> str:
        target.mkdir(parents=True, exist_ok=True)
        self._git(target, "init", "-q")
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        harness.parent.mkdir(parents=True, exist_ok=True)
        harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")
        (target / "MIL-CREDA").mkdir(parents=True, exist_ok=True)
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", "initial")
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _fixture_assets(self, tmp: str) -> tuple[Path, Path]:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# fixture bootstrap cell\n", encoding="utf-8")
        invoke.write_text("# fixture invoke cell\n", encoding="utf-8")
        return bootstrap, invoke

    def _generate(self, tmp: str, target: Path, *, commit: str) -> Path:
        bootstrap, invoke = self._fixture_assets(tmp)
        return JOBFOLDER.generate_job(
            target=target,
            service=self.FAKE_SERVICE,
            job_name="search-a",
            product="MIL-CREDA",
            commit=commit,
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            clone_paths=["src/MIL_CREDA_Benchmark"],
            run_module="MIL_CREDA_Benchmark.harness",
            run_function="campaign",
            bootstrap_asset=bootstrap,
            invoke_asset=invoke,
        )

    def test_cmd_status_reports_none_for_the_legacy_shape(self) -> None:
        """A legacy-shape entrypoint has no job folder at all, so there is
        nothing for `read()` to route through: `staleness` is `None`, not
        a guessed or defaulted verdict.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            result = REMOTE_CLI.cmd_status(
                target=target, entrypoint=notebook, source_digest=lambda t, n: "d" * 64
            )

            self.assertIsNone(result["staleness"])

    def test_cmd_status_reports_staleness_for_a_job_folder_shaped_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            initial_commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=initial_commit)
            notebook = job_dir / "runner.ipynb"

            result = REMOTE_CLI.cmd_status(
                target=target, entrypoint=notebook, source_digest=lambda t, n: "d" * 64
            )

            self.assertIsNotNone(result["staleness"])
            self.assertEqual(result["staleness"]["status"], "fresh")

    def test_cmd_submit_reports_staleness_for_a_job_folder_shaped_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            initial_commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=initial_commit)
            notebook = job_dir / "runner.ipynb"

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            result = REMOTE_CLI.cmd_submit(
                target=target,
                entrypoint=notebook,
                worker="w1",
                requested=1,
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )

            self.assertIsNotNone(result["staleness"])
            self.assertEqual(result["staleness"]["status"], "fresh")

    def test_cmd_submit_refuses_an_incomplete_run_config_rather_than_tolerating_it(
        self,
    ) -> None:
        """Corrected in place, because the behaviour it asserted is the
        behaviour this change removes.

        It used to require that a job folder with a minimal
        `run-config.json` (declaring only `product`) still submitted, and
        merely reported `staleness: None`, on the reasoning that routing
        staleness REPORTING through `read()` must not make an
        already-tolerant command stricter. That reasoning was correct for
        reporting and is wrong for gating. `_job_folder_staleness()`
        returns `None` on two paths — the legacy shape and an unreadable
        config — so a gate that inherited that tolerance would let a job
        folder skip all three pin conditions by being malformed, which is
        the worse half of the defect this change exists to close.

        This is a new refusal path the spec does not name, adopted
        deliberately. The tolerance it replaces still exists exactly where
        it belongs: `_job_folder_staleness()` is unchanged, and
        `product_for()`'s own tolerance of an incomplete config keeps its
        coverage in `ProductForTests`. Precedent for refusing rather than
        swallowing at a decision point: `cmd_smoke_record()`.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "MIL-CREDA").mkdir(parents=True)
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            (job_dir / "run-config.json").write_text(
                json.dumps({"product": "MIL-CREDA"}), encoding="utf-8"
            )

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            with self.assertRaises(JOBFOLDER.JobFolderError):
                REMOTE_CLI.cmd_submit(
                    target=target,
                    entrypoint=notebook,
                    worker="w1",
                    requested=1,
                    adapter=adapter,
                    source_digest=lambda t, n: "d" * 64,
                )

            self.assertFalse(
                (target.resolve() / "MIL-CREDA" / ".remote-execution").exists()
            )

    def test_the_staleness_helper_itself_stays_tolerant(self) -> None:
        """The tolerance was not deleted, only removed from the gate's
        path. `_job_folder_staleness()` still falls through cleanly for an
        unreadable config, because REPORTING staleness beside whatever
        else a command reports must not become the thing that breaks it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "MIL-CREDA").mkdir(parents=True)
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            (job_dir / "run-config.json").write_text(
                json.dumps({"product": "MIL-CREDA"}), encoding="utf-8"
            )

            self.assertIsNone(REMOTE_CLI._job_folder_staleness(notebook))

    def test_cmd_fetch_reports_staleness_for_a_job_folder_shaped_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            initial_commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=initial_commit)
            notebook = job_dir / "runner.ipynb"

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            submit_result = REMOTE_CLI.cmd_submit(
                target=target,
                entrypoint=notebook,
                worker="w1",
                requested=1,
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )

            dest = target.resolve() / "MIL-CREDA" / "Results" / "shards" / "search-a"
            fetch_result = REMOTE_CLI.cmd_fetch(
                target=target,
                entrypoint=notebook,
                submission_id=submit_result["submission"].id,
                dest=dest,
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )

            self.assertIsNotNone(fetch_result["staleness"])
            self.assertEqual(fetch_result["staleness"]["status"], "fresh")

    def test_cmd_reconcile_reports_staleness_for_a_job_folder_shaped_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            initial_commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=initial_commit)
            notebook = job_dir / "runner.ipynb"

            adapter = ScriptedListActiveAdapter(worker_id="w1", active=())
            result = REMOTE_CLI.cmd_reconcile(
                target=target,
                entrypoint=notebook,
                worker="w1",
                adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )

            self.assertIsNotNone(result["staleness"])
            self.assertEqual(result["staleness"]["status"], "fresh")

    def test_generate_job_cli_reports_staleness_in_its_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            initial_commit = self._init_repo(target)
            bootstrap, invoke = self._fixture_assets(tmp)

            stdout = io.StringIO()
            with unittest.mock.patch.object(
                JOBFOLDER, "DEFAULT_BOOTSTRAP_ASSET", bootstrap
            ), unittest.mock.patch.object(
                JOBFOLDER, "DEFAULT_INVOKE_ASSET", invoke
            ), contextlib.redirect_stdout(stdout):
                exit_code = REMOTE_CLI.main([
                    "generate-job",
                    "--target", str(target),
                    "--service", self.FAKE_SERVICE,
                    "--job-name", "cli-job",
                    "--product", "MIL-CREDA",
                    "--commit", initial_commit,
                    "--repo-url", "https://example.invalid/repo.git",
                    "--repo-ref", "main",
                    "--clone-path", "src/MIL_CREDA_Benchmark",
                    "--run-module", "MIL_CREDA_Benchmark.harness",
                    "--run-function", "campaign",
                ])

            self.assertEqual(exit_code, 0)
            printed = json.loads(stdout.getvalue())
            self.assertIn("staleness", printed)
            self.assertIn(printed["staleness"]["status"], ("fresh", "drift", "unknown"))


def _make_origin_repo(tmp: str, files: dict) -> tuple:
    """A real, throwaway local git repository — the sole `git` fixture
    every `RunnerBootstrapTests` test that exercises `clone_repo()` or
    `bootstrap()` end to end clones FROM. Real `git`, not a fake
    executable: sparse-checkout and fetch-by-commit semantics are exactly
    what this cell's own correctness depends on, and only real git proves
    them.
    """
    origin = Path(tmp) / f"origin-{uuid.uuid4().hex}"
    origin.mkdir()
    for relative, content in files.items():
        path = origin / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "runner-bootstrap-tests"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "runner-bootstrap-tests@example.invalid"
    subprocess.run(["git", "init", "-q"], cwd=origin, env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=origin, env=env, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"], cwd=origin, env=env, check=True
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=origin, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()
    return origin, commit


class RunnerBootstrapTests(unittest.TestCase):
    """`assets/runner_bootstrap.py` — cell 0's real content, driven as an
    importable module against fake `run-config.json` payloads. Every test
    in this class has a reachable red: before this task, the file raised
    `NotImplementedError` at import time, and the module-loading block at
    the top of this file would fail collection for the whole suite.
    """

    def _fake_run_config(self, **overrides) -> dict:
        run_config = {
            "schemaVersion": 1,
            "product": "P",
            "service": "runner-bootstrap-fake-service",
            "jobName": "j",
            "commit": "a" * 40,
            "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
            "clonePaths": ["src/fixturepkg"],
            "run": {"module": "fixturepkg", "function": "run"},
            "runnerTemplate": [{"path": "x", "sha256": "y"}],
        }
        run_config.update(overrides)
        return run_config

    def test_load_run_config_reads_a_valid_fixture_beside_the_notebook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / RUNNER_BOOTSTRAP.CONFIG_FILENAME).write_text(
                json.dumps(self._fake_run_config()), encoding="utf-8"
            )
            run_config = RUNNER_BOOTSTRAP.load_run_config(tmp)
            self.assertEqual(run_config["run"]["module"], "fixturepkg")

    def test_load_run_config_refuses_when_the_file_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError):
                RUNNER_BOOTSTRAP.load_run_config(tmp)

    def test_load_run_config_refuses_an_unknown_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / RUNNER_BOOTSTRAP.CONFIG_FILENAME).write_text(
                json.dumps(self._fake_run_config(schemaVersion=99)), encoding="utf-8"
            )
            with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError):
                RUNNER_BOOTSTRAP.load_run_config(tmp)

    def test_run_git_env_is_a_path_only_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recorded_env = {}
            real_run = subprocess.run

            def recording_run(argv, **kwargs):
                recorded_env.update(kwargs.get("env") or {})
                return real_run(argv, **kwargs)

            with unittest.mock.patch.object(
                RUNNER_BOOTSTRAP.subprocess, "run", side_effect=recording_run
            ), unittest.mock.patch.dict(os.environ, {"SOME_OTHER_VAR": "leak-me-not"}):
                RUNNER_BOOTSTRAP._run_git(["init"], cwd=Path(tmp))

            self.assertEqual(set(recorded_env), {"PATH"})

    def test_run_git_non_zero_exit_is_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError):
                RUNNER_BOOTSTRAP._run_git(
                    ["this-is-not-a-real-git-subcommand"], cwd=Path(tmp)
                )

    def test_run_git_timeout_is_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.object(
                RUNNER_BOOTSTRAP.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd=["git", "init"], timeout=1.0),
            ):
                with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError):
                    RUNNER_BOOTSTRAP._run_git(["init"], cwd=Path(tmp), timeout=1.0)

    def test_shell_metacharacters_in_a_git_argument_reach_argv_verbatim_and_execute_nothing(
        self,
    ) -> None:
        """The mandated RED test: a value carrying shell metacharacters
        reaches `_run_git`'s own argv verbatim and executes nothing —
        `shell=False` plus a list argv means the whole malicious string
        travels as ONE argv element, never evaluated by a shell.
        """
        with tempfile.TemporaryDirectory() as tmp:
            marker_name = "pwned-marker-bootstrap"
            marker_path = Path.cwd() / marker_name
            malicious = f"a$(touch {marker_name})`touch {marker_name}`;touch {marker_name}"
            recorded_argv: list = []
            real_run = subprocess.run

            def recording_run(argv, **kwargs):
                recorded_argv.append(list(argv))
                return real_run(argv, **kwargs)

            try:
                with unittest.mock.patch.object(
                    RUNNER_BOOTSTRAP.subprocess, "run", side_effect=recording_run
                ):
                    with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError):
                        RUNNER_BOOTSTRAP._run_git(
                            ["fetch", "--depth", "1", "origin", malicious], cwd=Path(tmp)
                        )
                self.assertFalse(marker_path.exists())
                self.assertEqual(recorded_argv[-1][-1], malicious)
            finally:
                if marker_path.exists():
                    marker_path.unlink()

    def test_clone_repo_sparse_checks_out_only_the_declared_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            origin, commit = _make_origin_repo(
                tmp,
                {
                    "src/fixturepkg/__init__.py": "VALUE = 1\n",
                    "unrelated/file.txt": "not cloned\n",
                },
            )
            run_config = self._fake_run_config(
                commit=commit,
                repo={"url": str(origin), "ref": "main"},
                clonePaths=["src/fixturepkg"],
            )
            clone_dir = Path(tmp) / "clone"

            RUNNER_BOOTSTRAP.clone_repo(run_config, clone_dir)

            self.assertTrue((clone_dir / "src" / "fixturepkg" / "__init__.py").is_file())
            self.assertFalse((clone_dir / "unrelated").exists())

    def test_add_clone_to_path_inserts_the_clone_src_at_the_front(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clone_dir = Path(tmp) / "clone"
            (clone_dir / "src").mkdir(parents=True)
            saved_path = list(sys.path)
            try:
                src_dir = RUNNER_BOOTSTRAP.add_clone_to_path(clone_dir)
                self.assertEqual(Path(sys.path[0]).resolve(), src_dir.resolve())
            finally:
                sys.path[:] = saved_path

    def test_declared_modules_includes_the_smoke_module_only_when_declared(self) -> None:
        with_smoke = self._fake_run_config(
            run={"module": "fixturepkg", "function": "run", "smoke": {"module": "fixturepkg.smoke", "function": "run"}}
        )
        without_smoke = self._fake_run_config()

        self.assertEqual(
            RUNNER_BOOTSTRAP.declared_modules(with_smoke), ["fixturepkg", "fixturepkg.smoke"]
        )
        self.assertEqual(RUNNER_BOOTSTRAP.declared_modules(without_smoke), ["fixturepkg"])

    def test_verify_imports_under_clone_succeeds_when_the_module_resolves_inside_src(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module_name = f"fixture_inside_{uuid.uuid4().hex}"
            src_dir = Path(tmp) / "src"
            (src_dir / module_name).mkdir(parents=True)
            (src_dir / module_name / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
            saved_path = list(sys.path)
            sys.path.insert(0, str(src_dir))
            try:
                verified = RUNNER_BOOTSTRAP.verify_imports_under_clone([module_name], src_dir)
                self.assertEqual(
                    Path(verified[module_name]).resolve(),
                    (src_dir / module_name / "__init__.py").resolve(),
                )
            finally:
                sys.path[:] = saved_path
                sys.modules.pop(module_name, None)

    def test_verify_imports_under_clone_refuses_the_pip_installed_copy_case(self) -> None:
        """A module importable from somewhere ELSE already on `sys.path` —
        never placed under the clone's own `src` at all — is exactly the
        "pip-installed copy" this responsibility exists to catch.
        """
        with tempfile.TemporaryDirectory() as tmp:
            module_name = f"fixture_decoy_{uuid.uuid4().hex}"
            decoy_root = Path(tmp) / "decoy-site-packages"
            (decoy_root / module_name).mkdir(parents=True)
            (decoy_root / module_name / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
            empty_src = Path(tmp) / "src"
            empty_src.mkdir()
            saved_path = list(sys.path)
            sys.path.append(str(decoy_root))
            try:
                with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError) as ctx:
                    RUNNER_BOOTSTRAP.verify_imports_under_clone([module_name], empty_src)
                self.assertIn("pip-installed copy", str(ctx.exception))
            finally:
                sys.path[:] = saved_path
                sys.modules.pop(module_name, None)

    def test_detect_hardware_refuses_when_torch_is_not_importable(self) -> None:
        def _no_torch(name: str):
            raise ImportError(f"no module named {name!r}")

        with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError) as ctx:
            RUNNER_BOOTSTRAP.detect_hardware(import_module=_no_torch)
        self.assertIn("hardware missing", str(ctx.exception))

    def test_detect_hardware_succeeds_with_an_injected_torch(self) -> None:
        fake_torch = SimpleNamespace(
            __version__="9.9.9",
            cuda=SimpleNamespace(is_available=lambda: True, get_device_name=lambda i: "FakeGPU"),
        )

        def _fake_import(name: str):
            self.assertEqual(name, "torch")
            return fake_torch

        environment = RUNNER_BOOTSTRAP.detect_hardware(import_module=_fake_import)
        self.assertEqual(environment["device"], {"kind": "cuda", "name": "FakeGPU"})
        self.assertEqual(environment["torch"], "9.9.9")

    def test_bootstrap_exits_before_cell_one_when_config_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                RUNNER_BOOTSTRAP.bootstrap(tmp)
            self.assertFalse((Path(tmp) / RUNNER_BOOTSTRAP.BOOTSTRAP_OUTPUT_FILENAME).exists())

    def test_bootstrap_exits_before_cell_one_when_code_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            origin, commit = _make_origin_repo(tmp, {"src/fixturepkg/__init__.py": "VALUE = 1\n"})
            run_config = self._fake_run_config(
                commit=commit,
                repo={"url": str(origin), "ref": "main"},
                clonePaths=["src/fixturepkg"],
                run={"module": "this_module_does_not_exist_anywhere", "function": "run"},
            )
            (Path(tmp) / RUNNER_BOOTSTRAP.CONFIG_FILENAME).write_text(
                json.dumps(run_config), encoding="utf-8"
            )
            saved_path = list(sys.path)
            try:
                with self.assertRaises(SystemExit):
                    RUNNER_BOOTSTRAP.bootstrap(tmp)
            finally:
                sys.path[:] = saved_path
            self.assertFalse((Path(tmp) / RUNNER_BOOTSTRAP.BOOTSTRAP_OUTPUT_FILENAME).exists())

    def test_bootstrap_exits_before_cell_one_when_hardware_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            origin, commit = _make_origin_repo(tmp, {"src/fixturepkg/__init__.py": "VALUE = 1\n"})
            run_config = self._fake_run_config(
                commit=commit,
                repo={"url": str(origin), "ref": "main"},
                clonePaths=["src/fixturepkg"],
                run={"module": "fixturepkg", "function": "run"},
            )
            (Path(tmp) / RUNNER_BOOTSTRAP.CONFIG_FILENAME).write_text(
                json.dumps(run_config), encoding="utf-8"
            )
            saved_path = list(sys.path)

            def _no_torch(name: str):
                raise ImportError("no torch")

            try:
                with self.assertRaises(SystemExit):
                    RUNNER_BOOTSTRAP.bootstrap(tmp, hardware_import=_no_torch)
            finally:
                sys.path[:] = saved_path
                sys.modules.pop("fixturepkg", None)
            self.assertFalse((Path(tmp) / RUNNER_BOOTSTRAP.BOOTSTRAP_OUTPUT_FILENAME).exists())

    def test_bootstrap_succeeds_writes_bootstrap_json_and_returns_commit_environment_and_imports(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            origin, commit = _make_origin_repo(tmp, {"src/fixturepkg/__init__.py": "VALUE = 1\n"})
            run_config = self._fake_run_config(
                commit=commit,
                repo={"url": str(origin), "ref": "main"},
                clonePaths=["src/fixturepkg"],
                run={"module": "fixturepkg", "function": "run"},
            )
            (Path(tmp) / RUNNER_BOOTSTRAP.CONFIG_FILENAME).write_text(
                json.dumps(run_config), encoding="utf-8"
            )
            saved_path = list(sys.path)
            fake_torch = SimpleNamespace(
                __version__="1.2.3",
                cuda=SimpleNamespace(is_available=lambda: False, get_device_name=lambda i: "n/a"),
            )
            try:
                result = RUNNER_BOOTSTRAP.bootstrap(
                    tmp, hardware_import=lambda name: fake_torch
                )
            finally:
                sys.path[:] = saved_path
                sys.modules.pop("fixturepkg", None)

            self.assertEqual(result["commit"], commit)
            self.assertEqual(result["environment"]["device"]["kind"], "cpu")
            self.assertIn("fixturepkg", result["imports"])
            output_path = Path(tmp) / RUNNER_BOOTSTRAP.BOOTSTRAP_OUTPUT_FILENAME
            self.assertTrue(output_path.is_file())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["commit"], commit)

    def test_runner_bootstrap_module_names_no_service(self) -> None:
        """This asset's own no-service guard — in the same family as
        `test_adapter_module_names_no_service`,
        `test_remote_cli_module_names_no_service`,
        `test_credentials_module_names_no_service` and
        `test_jobfolder_module_names_no_service`.
        """
        source = RUNNER_BOOTSTRAP_SCRIPT.read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)


class RunnerInvokeTests(unittest.TestCase):
    """`assets/runner_invoke.py` — cell 1's real content, driven as an
    importable module against fake `run-config.json` payloads. Every test
    in this class has a reachable red for the same reason
    `RunnerBootstrapTests` does: the file raised `NotImplementedError` at
    import time before this task.
    """

    def _fixture_module(self, tmp: str) -> str:
        module_name = f"fixture_invoke_target_{uuid.uuid4().hex}"
        (Path(tmp) / f"{module_name}.py").write_text(
            "def run(**kwargs):\n"
            "    return {'ran': 'run', 'kwargs': kwargs}\n"
            "\n"
            "def smoke(**kwargs):\n"
            "    return {'ran': 'smoke', 'kwargs': kwargs}\n"
            "\n"
            "NOT_CALLABLE = 'not-a-function'\n",
            encoding="utf-8",
        )
        return module_name

    def test_select_block_returns_the_normal_run_block_by_default(self) -> None:
        run_config = {"run": {"module": "m", "function": "run"}}
        self.assertEqual(
            RUNNER_INVOKE.select_block(run_config), {"module": "m", "function": "run"}
        )

    def test_select_block_returns_the_smoke_block_when_mode_is_smoke(self) -> None:
        run_config = {
            "mode": "smoke",
            "run": {
                "module": "m", "function": "run",
                "smoke": {"module": "m", "function": "smoke"},
            },
        }
        self.assertEqual(
            RUNNER_INVOKE.select_block(run_config), {"module": "m", "function": "smoke"}
        )

    def test_select_block_refuses_smoke_mode_with_no_declared_smoke_block(self) -> None:
        run_config = {"mode": "smoke", "run": {"module": "m", "function": "run"}}
        with self.assertRaises(RUNNER_INVOKE.InvokeError):
            RUNNER_INVOKE.select_block(run_config)

    def test_resolve_callable_succeeds_for_a_real_function(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module_name = self._fixture_module(tmp)
            saved_path = list(sys.path)
            sys.path.insert(0, tmp)
            try:
                func = RUNNER_INVOKE.resolve_callable({"module": module_name, "function": "run"})
                self.assertEqual(func(x=1), {"ran": "run", "kwargs": {"x": 1}})
            finally:
                sys.path[:] = saved_path
                sys.modules.pop(module_name, None)

    def test_resolve_callable_refuses_when_the_module_cannot_be_imported(self) -> None:
        with self.assertRaises(RUNNER_INVOKE.InvokeError):
            RUNNER_INVOKE.resolve_callable(
                {"module": "this_module_does_not_exist_anywhere", "function": "run"}
            )

    def test_resolve_callable_refuses_a_missing_attribute_and_a_non_callable_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module_name = self._fixture_module(tmp)
            saved_path = list(sys.path)
            sys.path.insert(0, tmp)
            try:
                with self.assertRaises(RUNNER_INVOKE.InvokeError):
                    RUNNER_INVOKE.resolve_callable(
                        {"module": module_name, "function": "no_such_function"}
                    )
                with self.assertRaises(RUNNER_INVOKE.InvokeError):
                    RUNNER_INVOKE.resolve_callable(
                        {"module": module_name, "function": "NOT_CALLABLE"}
                    )
            finally:
                sys.path[:] = saved_path
                sys.modules.pop(module_name, None)

    def test_invoke_calls_the_normal_run_function_with_its_declared_kwargs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module_name = self._fixture_module(tmp)
            saved_path = list(sys.path)
            sys.path.insert(0, tmp)
            try:
                run_config = {
                    "run": {"module": module_name, "function": "run", "kwargs": {"seed": 3}}
                }
                self.assertEqual(
                    RUNNER_INVOKE.invoke(run_config), {"ran": "run", "kwargs": {"seed": 3}}
                )
            finally:
                sys.path[:] = saved_path
                sys.modules.pop(module_name, None)

    def test_invoke_calls_the_smoke_function_when_mode_is_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module_name = self._fixture_module(tmp)
            saved_path = list(sys.path)
            sys.path.insert(0, tmp)
            try:
                run_config = {
                    "mode": "smoke",
                    "run": {
                        "module": module_name, "function": "run", "kwargs": {"seed": 3},
                        "smoke": {"module": module_name, "function": "smoke", "kwargs": {"seed": 0}},
                    },
                }
                self.assertEqual(
                    RUNNER_INVOKE.invoke(run_config), {"ran": "smoke", "kwargs": {"seed": 0}}
                )
            finally:
                sys.path[:] = saved_path
                sys.modules.pop(module_name, None)

    def test_runner_invoke_module_names_no_service(self) -> None:
        """This asset's own no-service guard, same family as
        `test_runner_bootstrap_module_names_no_service` — the eighth in
        the whole skill's `*_module_names_no_service` family.
        """
        source = RUNNER_INVOKE_SCRIPT.read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)


class ShardIoTests(unittest.TestCase):
    """`shard_io.py` — the generic half of a target repository's shard reader.

    Every test here exercises `read_shards`/`disagreements` directly against
    a real temporary shard tree, never a mock of the filesystem: the module
    has no dependency the tests would need to fake.

    Every test in this class has a reachable red: `shard_io.py` did not
    exist before this task, so the module import above would fail and every
    test here would fail to collect.
    """

    def test_a_shard_with_no_stamp_is_absent_not_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "no-stamp").mkdir()
            (root / "no-stamp" / "runs.jsonl").write_text(
                json.dumps({"seed": 0}) + "\n", encoding="utf-8"
            )

            self.assertEqual(SHARD_IO.read_shards(root), [])

    def test_a_shard_with_a_stamp_and_no_runs_reports_an_empty_run_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shard_dir = root / "k01"
            shard_dir.mkdir()
            (shard_dir / "shard.json").write_text(
                json.dumps({"shard": "k01", "epochs": 20}), encoding="utf-8"
            )

            found = SHARD_IO.read_shards(root)

            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["shard"], "k01")
            self.assertEqual(found[0]["stamp"]["epochs"], 20)
            self.assertEqual(found[0]["runs"], [])

    def test_a_shard_s_runs_are_read_from_its_runs_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shard_dir = root / "k02"
            shard_dir.mkdir()
            (shard_dir / "shard.json").write_text(
                json.dumps({"shard": "k02"}), encoding="utf-8"
            )
            (shard_dir / "runs.jsonl").write_text(
                "\n".join(json.dumps({"seed": s}) for s in (0, 1)) + "\n",
                encoding="utf-8",
            )

            found = SHARD_IO.read_shards(root)

            self.assertEqual(len(found), 1)
            self.assertEqual([r["seed"] for r in found[0]["runs"]], [0, 1])

    def test_a_missing_root_reports_no_shards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "never-created"

            self.assertEqual(SHARD_IO.read_shards(root), [])

    def test_shards_agreeing_on_a_field_report_no_disagreement(self) -> None:
        shards = [
            {"shard": "a", "stamp": {"epochs": 20}},
            {"shard": "b", "stamp": {"epochs": 20}},
        ]

        self.assertEqual(SHARD_IO.disagreements(shards, ["epochs"]), [])

    def test_shards_disagreeing_on_a_field_report_every_value_and_its_shards(self) -> None:
        shards = [
            {"shard": "a", "stamp": {"epochs": 20}},
            {"shard": "b", "stamp": {"epochs": 3}},
            {"shard": "c", "stamp": {"epochs": 20}},
        ]

        found = SHARD_IO.disagreements(shards, ["epochs"])

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["field"], "epochs")
        values = found[0]["values"]
        self.assertEqual(values[json.dumps(20)], ["a", "c"])
        self.assertEqual(values[json.dumps(3)], ["b"])

    def test_shard_io_source_names_no_service_and_no_domain_term(self) -> None:
        """The leak guard this module exists to make impossible to miss: a
        static scan over the raw file text (source and every docstring
        alike) for the two service literals a second backend would
        introduce, and the two domain literals that would mean the rest of
        `shards.py` — the half that keys cells on those two dimensions —
        followed this half into the forge without anyone noticing.
        """
        source = SHARD_IO_SCRIPT.read_text(encoding="utf-8").lower()
        # Whole words, not substrings. `arm` alone fires on `warm`, `harm` and
        # `alarm`, and a guard that fails on an innocent word is a guard the
        # next contributor deletes rather than reads — which would leave the
        # boundary it protects with nothing watching it at all.
        for leaked in ("kaggle", "t4", "transfer", "arm"):
            self.assertIsNone(
                re.search(rf"\b{leaked}s?\b", source), leaked)


class CompletenessTests(unittest.TestCase):
    """`shard_io.completeness(stamp, required)` — the same argument shape as
    `disagreements(shards, fields)` above: the caller brings the field
    vocabulary, this module only walks it. Every test here drives the
    function with field paths this module has never heard of (some drawn
    from a completely unrelated vocabulary), which is itself part of the
    proof that the function names no field of its own.

    Every test in this class has a reachable red: `completeness` did not
    exist on `SHARD_IO` before this task, so every call below would raise
    `AttributeError`.
    """

    def test_every_required_path_present_reports_complete_with_nothing_missing(self) -> None:
        stamp = {
            "epochs": 20,
            "evidence": {"commit": "abc123", "codeDigest": "deadbeef"},
        }

        result = SHARD_IO.completeness(
            stamp, ["epochs", "evidence.commit", "evidence.codeDigest"]
        )

        self.assertEqual(result, {"complete": True, "missing": []})

    def test_a_missing_top_level_path_is_reported_incomplete_by_its_own_name(self) -> None:
        stamp = {"epochs": 20}

        result = SHARD_IO.completeness(stamp, ["epochs", "seeds"])

        self.assertEqual(result, {"complete": False, "missing": ["seeds"]})

    def test_a_stamp_with_no_evidence_key_at_all_reports_its_nested_paths_missing(self) -> None:
        stamp = {"epochs": 20}

        result = SHARD_IO.completeness(
            stamp, ["evidence.commit", "environment.device.kind"]
        )

        self.assertEqual(
            result,
            {
                "complete": False,
                "missing": ["evidence.commit", "environment.device.kind"],
            },
        )

    def test_an_intermediate_non_mapping_value_is_reported_missing_never_raised(self) -> None:
        stamp = {"evidence": "not-a-mapping"}

        result = SHARD_IO.completeness(stamp, ["evidence.commit"])

        self.assertEqual(result, {"complete": False, "missing": ["evidence.commit"]})

    def test_missing_paths_are_reported_in_the_caller_s_own_order(self) -> None:
        stamp = {"epochs": 20}

        result = SHARD_IO.completeness(
            stamp, ["seeds", "epochs", "evidence.commit"]
        )

        self.assertEqual(result["missing"], ["seeds", "evidence.commit"])

    def test_the_function_carries_no_vocabulary_of_its_own(self) -> None:
        """Field paths belonging to nothing this module has ever named —
        this is the caller-supplied-vocabulary contract exercised directly,
        not just inferred from the source-scan guard below."""
        stamp = {"widget": {"gizmo": "present"}}

        result = SHARD_IO.completeness(
            stamp, ["widget.gizmo", "widget.absent", "unrelated.path"]
        )

        self.assertEqual(
            result,
            {"complete": False, "missing": ["widget.absent", "unrelated.path"]},
        )


class SmokeTests(unittest.TestCase):
    """`smoke.jsonl`, `submit --smoke`, `smoke record --from-artifact`, and
    `readiness` (design #744 section 7) — exercised against `FakeAdapter`
    only. Every test here has a reachable red: before this task,
    `cmd_submit` accepted no `smoke` keyword, and `REMOTE_CLI` exposed no
    `cmd_smoke_record`/`cmd_readiness` attribute.
    """

    FAKE_SERVICE = "smoke-fake-service"

    @classmethod
    def setUpClass(cls) -> None:
        ADAPTER.register_metadata(
            cls.FAKE_SERVICE,
            lambda run_config: ("fake-metadata.json", json.dumps({"ok": True})),
        )

    def setUp(self) -> None:
        # This class exercises smoke recording, not the pin preconditions
        # — every `repo_url` here is `example.invalid`, a fixture. The
        # whole-precondition seam is stubbed so this class stays offline
        # and deterministic.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "verify_pin_preconditions", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- fixtures: a real git repo + a real generated job folder, the same
    # shape `StalenessTests` already establishes for exercising
    # `JOBFOLDER.read()` end to end ------------------------------------

    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "smoke-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "smoke-tests@example.invalid"
        return subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check
        )

    def _init_repo(self, target: Path) -> str:
        target.mkdir(parents=True, exist_ok=True)
        harness = target / "src" / "MIL_CREDA_Benchmark" / "harness.py"
        harness.parent.mkdir(parents=True, exist_ok=True)
        harness.write_text("def campaign(*args, **kwargs):\n    pass\n", encoding="utf-8")
        self._git(target, "init", "-q")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-q", "-m", "initial")
        return self._git(target, "rev-parse", "HEAD").stdout.strip()

    def _fixture_assets(self, tmp: str) -> tuple[Path, Path]:
        bootstrap = Path(tmp) / "fixture_bootstrap.py"
        invoke = Path(tmp) / "fixture_invoke.py"
        bootstrap.write_text("# fixture bootstrap cell\n", encoding="utf-8")
        invoke.write_text("# fixture invoke cell\n", encoding="utf-8")
        return bootstrap, invoke

    def _generate(
        self,
        tmp: str,
        target: Path,
        *,
        commit: str,
        job_name: str = "search-a",
        required_evidence=("evidence.commit", "evidence.outputs"),
        regenerate: bool = False,
    ) -> Path:
        (target / "MIL-CREDA").mkdir(parents=True, exist_ok=True)
        bootstrap, invoke = self._fixture_assets(tmp)
        return JOBFOLDER.generate_job(
            target=target,
            service=self.FAKE_SERVICE,
            job_name=job_name,
            product="MIL-CREDA",
            commit=commit,
            repo_url="https://example.invalid/repo.git",
            repo_ref="main",
            clone_paths=["src/MIL_CREDA_Benchmark"],
            run_module="MIL_CREDA_Benchmark.harness",
            run_function="campaign",
            smoke_module="MIL_CREDA_Benchmark.harness",
            smoke_function="campaign",
            smoke_required_evidence=list(required_evidence) if required_evidence else None,
            bootstrap_asset=bootstrap,
            invoke_asset=invoke,
            regenerate=regenerate,
        )

    # -- (a) smoke.jsonl is a distinct file; the mandated RED test --------

    def test_smoke_submission_never_enters_the_fold_or_supersedes_a_real_run(self) -> None:
        """A fourth `kind` inside the main ledger would become
        `latest[entrypoint]` and silently reclassify a real, still-pending
        full run as superseded (design #744 section 7's own rejection)."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "MIL-CREDA").mkdir(parents=True)
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            _write_job_folder_run_config(job_dir)

            adapter = FakeAdapter(worker_id="w1", capacity=2)

            full_result = REMOTE_CLI.cmd_submit(
                target=target, entrypoint=notebook, worker="w1", requested=1,
                adapter=adapter, source_digest=lambda t, n: "d" * 64,
            )
            smoke_result = REMOTE_CLI.cmd_submit(
                target=target, entrypoint=notebook, worker="w1", requested=1,
                adapter=adapter, source_digest=lambda t, n: "d" * 64, smoke=True,
            )

            # Different files -- the whole point of the design's rejection.
            self.assertEqual(full_result["ledgerPath"].name, "ledger.jsonl")
            self.assertEqual(smoke_result["ledgerPath"].name, "smoke.jsonl")
            self.assertNotEqual(full_result["ledgerPath"], smoke_result["ledgerPath"])

            main_lines = full_result["ledgerPath"].read_text(encoding="utf-8").splitlines()
            # The smoke run's own submitted event never touched this file.
            self.assertEqual(len(main_lines), 1)

            state = LEDGER.fold(main_lines, live_digest="d" * 64)
            entry = "tools/kaggle/search-a/runner.ipynb"
            self.assertEqual(state.entrypoints[entry].state, "pending")
            self.assertEqual(
                state.latest[entry]["submissionId"], full_result["submission"].id,
            )
            self.assertNotEqual(
                state.latest[entry]["submissionId"], smoke_result["submission"].id,
            )

    def test_smoke_first_then_full_still_leaves_the_full_run_as_latest(self) -> None:
        """OPPOSITE order: a smoke submission before the real one must not
        prevent the real one from becoming this entrypoint's latest."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            (target / "MIL-CREDA").mkdir(parents=True)
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")
            _write_job_folder_run_config(job_dir)

            adapter = FakeAdapter(worker_id="w1", capacity=2)

            REMOTE_CLI.cmd_submit(
                target=target, entrypoint=notebook, worker="w1", requested=1,
                adapter=adapter, source_digest=lambda t, n: "d" * 64, smoke=True,
            )
            full_result = REMOTE_CLI.cmd_submit(
                target=target, entrypoint=notebook, worker="w1", requested=1,
                adapter=adapter, source_digest=lambda t, n: "d" * 64,
            )

            main_lines = full_result["ledgerPath"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(main_lines), 1)
            state = LEDGER.fold(main_lines, live_digest="d" * 64)
            entry = "tools/kaggle/search-a/runner.ipynb"
            self.assertEqual(
                state.latest[entry]["submissionId"], full_result["submission"].id,
            )

    # -- (b) submit --smoke sets run_config['mode'], opaque to packer/ledger

    def test_submit_smoke_sets_run_config_mode_full_submit_keeps_it_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            spy = _SpySubmitAdapter(worker_id="w1", capacity=2)
            REMOTE_CLI.cmd_submit(
                target=target, entrypoint=notebook, worker="w1", requested=1,
                adapter=spy, source_digest=lambda t, n: "d" * 64, smoke=True,
            )
            self.assertEqual(dict(spy.last_job.run_config), {"mode": "smoke"})

            REMOTE_CLI.cmd_submit(
                target=target, entrypoint=notebook, worker="w1", requested=1,
                adapter=spy, source_digest=lambda t, n: "d" * 64,
            )
            self.assertEqual(dict(spy.last_job.run_config), {})

    def test_submit_parser_exposes_a_smoke_flag_defaulting_to_false(self) -> None:
        parser = REMOTE_CLI._build_parser()
        args = parser.parse_args([
            "submit", "--target", "/tmp/x", "--entrypoint", "/tmp/x/a.ipynb",
            "--worker", "w1", "--backend", "fake",
        ])
        self.assertFalse(args.smoke)

        args = parser.parse_args([
            "submit", "--target", "/tmp/x", "--entrypoint", "/tmp/x/a.ipynb",
            "--worker", "w1", "--backend", "fake", "--smoke",
        ])
        self.assertTrue(args.smoke)

    # -- (c) smoke record derives its verdict from completeness() alone ---

    def test_smoke_record_passes_when_completeness_reports_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)

            artifact = Path(tmp) / "shard.json"
            artifact.write_text(
                json.dumps({"evidence": {"commit": commit, "outputs": ["runs.jsonl"]}}),
                encoding="utf-8",
            )

            result = REMOTE_CLI.cmd_smoke_record(
                job_dir=job_dir, artifact_path=artifact, worker="w1",
            )

            self.assertEqual(result["result"], "pass")
            self.assertEqual(result["missing"], [])
            self.assertEqual(
                result["requiredEvidence"], ["evidence.commit", "evidence.outputs"]
            )
            self.assertEqual(result["smokeLedgerPath"].name, "smoke.jsonl")
            self.assertEqual(
                result["smokeLedgerPath"].parent,
                target.resolve() / "MIL-CREDA" / ".remote-execution",
            )

            lines = result["smokeLedgerPath"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[0])
            self.assertEqual(event["kind"], "smokeResult")
            self.assertEqual(event["result"], "pass")
            self.assertEqual(event["commit"], commit)
            self.assertEqual(event["worker"], "w1")
            self.assertEqual(event["jobName"], "search-a")
            self.assertEqual(event["missing"], [])

    def test_smoke_record_fails_when_completeness_reports_missing_fields(self) -> None:
        """Triangulates the pass case with a stamp missing one path."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)

            artifact = Path(tmp) / "shard.json"
            artifact.write_text(
                json.dumps({"evidence": {"commit": commit}}), encoding="utf-8"
            )

            result = REMOTE_CLI.cmd_smoke_record(
                job_dir=job_dir, artifact_path=artifact, worker="w1",
            )

            self.assertEqual(result["result"], "fail")
            self.assertEqual(result["missing"], ["evidence.outputs"])

            lines = result["smokeLedgerPath"].read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[0])
            self.assertEqual(event["result"], "fail")
            self.assertEqual(event["missing"], ["evidence.outputs"])

    def test_required_evidence_comes_from_the_job_s_own_run_config_not_a_forge_constant(
        self,
    ) -> None:
        """A DIFFERENT, unrelated vocabulary -- proving the list travels
        from run-config.json, not a literal this module names itself."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(
                tmp, target, commit=commit, job_name="search-b",
                required_evidence=["widget.gizmo"],
            )

            artifact = Path(tmp) / "shard.json"
            artifact.write_text(
                json.dumps({"widget": {"gizmo": "present"}}), encoding="utf-8"
            )

            result = REMOTE_CLI.cmd_smoke_record(
                job_dir=job_dir, artifact_path=artifact, worker="w1",
            )

            self.assertEqual(result["requiredEvidence"], ["widget.gizmo"])
            self.assertEqual(result["result"], "pass")

    def test_remote_cli_source_names_no_evidence_field_of_its_own(self) -> None:
        """Scans for literals this forge module has no business knowing."""
        source = REMOTE_CLI_SCRIPT.read_text(encoding="utf-8")
        for leaked in (
            "evidence.commit", "evidence.outputs", "evidence.codeDigest",
            "environment.torch", "environment.device",
        ):
            self.assertNotIn(leaked, source, leaked)

    def test_smoke_record_propagates_job_folder_error_for_a_non_generated_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            not_a_job = Path(tmp) / "not-a-job"
            not_a_job.mkdir()
            artifact = Path(tmp) / "shard.json"
            artifact.write_text("{}", encoding="utf-8")

            with self.assertRaises(JOBFOLDER.JobFolderError):
                REMOTE_CLI.cmd_smoke_record(
                    job_dir=not_a_job, artifact_path=artifact, worker="w1"
                )

    def test_smoke_record_refuses_a_missing_artifact_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)

            missing = Path(tmp) / "does-not-exist.json"
            with self.assertRaises(REMOTE_CLI.RemoteCLIError):
                REMOTE_CLI.cmd_smoke_record(
                    job_dir=job_dir, artifact_path=missing, worker="w1"
                )

    def test_smoke_record_parser_requires_job_dir_from_artifact_and_worker(self) -> None:
        parser = REMOTE_CLI._build_parser()
        args = parser.parse_args([
            "smoke", "record",
            "--job-dir", "/tmp/x/tools/svc/job",
            "--from-artifact", "/tmp/x/shard.json",
            "--worker", "w1",
        ])
        self.assertEqual(args.command, "smoke")
        self.assertEqual(args.smoke_command, "record")
        self.assertEqual(args.job_dir, Path("/tmp/x/tools/svc/job"))
        self.assertEqual(args.from_artifact, Path("/tmp/x/shard.json"))
        self.assertEqual(args.worker, "w1")

    def test_generate_job_parser_exposes_repeatable_smoke_required_evidence(self) -> None:
        parser = REMOTE_CLI._build_parser()
        args = parser.parse_args([
            "generate-job", "--target", "/tmp/x", "--service", "svc",
            "--job-name", "job", "--product", "P", "--commit", "a" * 40,
            "--repo-url", "https://example.invalid/r.git", "--repo-ref", "main",
            "--run-module", "m", "--run-function", "f",
            "--smoke-module", "m.smoke", "--smoke-function", "smoke",
            "--smoke-required-evidence", "evidence.commit",
            "--smoke-required-evidence", "evidence.outputs",
        ])
        self.assertEqual(
            args.smoke_required_evidence, ["evidence.commit", "evidence.outputs"]
        )

    def test_build_run_config_refuses_required_evidence_without_a_smoke_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap, invoke = self._fixture_assets(tmp)
            with self.assertRaises(JOBFOLDER.JobFolderError):
                JOBFOLDER.build_run_config(
                    product="P", service="svc", job_name="job", commit="a" * 40,
                    repo_url="https://example.invalid/r.git", repo_ref="main",
                    clone_paths=["src/A"], run_module="A.mod", run_function="f",
                    run_kwargs=None, smoke_module=None, smoke_function=None,
                    smoke_kwargs=None, bootstrap_asset=bootstrap, invoke_asset=invoke,
                    smoke_required_evidence=["evidence.commit"],
                )

    # -- (d) readiness binds result + commit + worker; no clock -----------

    def test_readiness_is_true_when_latest_smoke_record_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)

            artifact = Path(tmp) / "shard.json"
            artifact.write_text(
                json.dumps({"evidence": {"commit": commit, "outputs": ["runs.jsonl"]}}),
                encoding="utf-8",
            )
            REMOTE_CLI.cmd_smoke_record(job_dir=job_dir, artifact_path=artifact, worker="w1")

            result = REMOTE_CLI.cmd_readiness(job_dir=job_dir, worker="w1")

            self.assertTrue(result["ready"])
            self.assertIsNone(result["reason"])
            self.assertEqual(result["latestSmokeRecord"]["result"], "pass")

    def test_readiness_is_false_when_worker_does_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)

            artifact = Path(tmp) / "shard.json"
            artifact.write_text(
                json.dumps({"evidence": {"commit": commit, "outputs": ["runs.jsonl"]}}),
                encoding="utf-8",
            )
            REMOTE_CLI.cmd_smoke_record(job_dir=job_dir, artifact_path=artifact, worker="w1")

            result = REMOTE_CLI.cmd_readiness(job_dir=job_dir, worker="w2")

            self.assertFalse(result["ready"])
            self.assertIsNotNone(result["reason"])

    def test_readiness_expires_when_the_job_repins_to_a_different_commit_no_clock(
        self,
    ) -> None:
        """'Expiry falls out of the record's own fields; no clock.'
        Re-pinning the job's commit invalidates a passing smoke record."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)

            artifact = Path(tmp) / "shard.json"
            artifact.write_text(
                json.dumps({"evidence": {"commit": commit, "outputs": ["runs.jsonl"]}}),
                encoding="utf-8",
            )
            REMOTE_CLI.cmd_smoke_record(job_dir=job_dir, artifact_path=artifact, worker="w1")
            self.assertTrue(
                REMOTE_CLI.cmd_readiness(job_dir=job_dir, worker="w1")["ready"]
            )

            (target / "src" / "MIL_CREDA_Benchmark" / "harness.py").write_text(
                "def campaign(*args, **kwargs):\n    return 1\n", encoding="utf-8"
            )
            self._git(target, "add", "-A")
            self._git(target, "commit", "-q", "-m", "advance")
            new_commit = self._git(target, "rev-parse", "HEAD").stdout.strip()
            self._generate(tmp, target, commit=new_commit, regenerate=True)

            result = REMOTE_CLI.cmd_readiness(job_dir=job_dir, worker="w1")
            self.assertFalse(result["ready"])
            self.assertEqual(result["latestSmokeRecord"]["commit"], commit)

    def test_readiness_is_false_with_no_smoke_record_on_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)

            result = REMOTE_CLI.cmd_readiness(job_dir=job_dir, worker="w1")

            self.assertFalse(result["ready"])
            self.assertIsNone(result["latestSmokeRecord"])
            self.assertIn("no smoke record", result["reason"])

    def test_readiness_uses_the_latest_smoke_record_not_an_earlier_failing_one(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)

            failing_artifact = Path(tmp) / "failing-shard.json"
            failing_artifact.write_text(
                json.dumps({"evidence": {"commit": commit}}), encoding="utf-8"
            )
            REMOTE_CLI.cmd_smoke_record(
                job_dir=job_dir, artifact_path=failing_artifact, worker="w1"
            )
            self.assertFalse(
                REMOTE_CLI.cmd_readiness(job_dir=job_dir, worker="w1")["ready"]
            )

            passing_artifact = Path(tmp) / "passing-shard.json"
            passing_artifact.write_text(
                json.dumps({"evidence": {"commit": commit, "outputs": ["runs.jsonl"]}}),
                encoding="utf-8",
            )
            REMOTE_CLI.cmd_smoke_record(
                job_dir=job_dir, artifact_path=passing_artifact, worker="w1"
            )

            result = REMOTE_CLI.cmd_readiness(job_dir=job_dir, worker="w1")
            self.assertTrue(result["ready"])

    def test_readiness_ignores_timestamp_entirely(self) -> None:
        """An arbitrarily old `ts` still counts as ready -- nothing here
        reads `ts` to decide anything."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)

            smoke_ledger_path = (
                target.resolve() / "MIL-CREDA" / ".remote-execution" / "smoke.jsonl"
            )
            LEDGER.append(
                smoke_ledger_path,
                {
                    "kind": "smokeResult",
                    "ts": "1970-01-01T00:00:00Z",
                    "jobName": "search-a",
                    "result": "pass",
                    "commit": commit,
                    "worker": "w1",
                    "missing": [],
                },
            )

            result = REMOTE_CLI.cmd_readiness(job_dir=job_dir, worker="w1")
            self.assertTrue(result["ready"])

    def test_readiness_parser_requires_job_dir_and_worker(self) -> None:
        parser = REMOTE_CLI._build_parser()
        args = parser.parse_args([
            "readiness", "--job-dir", "/tmp/x/tools/svc/job", "--worker", "w1",
        ])
        self.assertEqual(args.command, "readiness")
        self.assertEqual(args.job_dir, Path("/tmp/x/tools/svc/job"))
        self.assertEqual(args.worker, "w1")

    # -- (e) probe states the fact; no menu, no submission ----------------

    def test_readiness_issues_no_submission_and_carries_no_menu(self) -> None:
        """No `adapter` parameter at all -- structurally cannot submit,
        the same signature-level guarantee `cmd_status()` already holds."""
        parameters = inspect.signature(REMOTE_CLI.cmd_readiness).parameters
        self.assertNotIn("adapter", parameters)

    # -- end-to-end runtime harness: real remote_cli.main() calls ---------

    def test_runtime_harness_submit_smoke_then_record_then_readiness_via_main(
        self,
    ) -> None:
        """`submit --smoke` -> `smoke record` -> `readiness`, all through
        the real `remote_cli.main()` entry point against `FakeAdapter`."""
        backend_name = "smoke-harness-fake-backend"
        ADAPTER.register(backend_name, FakeAdapter)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            commit = self._init_repo(target)
            job_dir = self._generate(tmp, target, commit=commit)
            notebook = job_dir / "runner.ipynb"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = REMOTE_CLI.main([
                    "submit",
                    "--target", str(target),
                    "--entrypoint", str(notebook),
                    "--worker", "fake-1",  # FakeAdapter's own default worker id
                    "--backend", backend_name,
                    "--smoke",
                ])
            self.assertEqual(exit_code, 0)
            submit_printed = json.loads(stdout.getvalue())
            self.assertTrue(submit_printed["smoke"])
            self.assertTrue(submit_printed["ledgerPath"].endswith("smoke.jsonl"))

            # Stands in for what `fetch` would have materialized --
            # `fetch()`'s own mechanics are covered by `FetchTests`.
            artifact = Path(tmp) / "fetched-shard.json"
            artifact.write_text(
                json.dumps({"evidence": {"commit": commit, "outputs": ["runs.jsonl"]}}),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = REMOTE_CLI.main([
                    "smoke", "record",
                    "--job-dir", str(job_dir),
                    "--from-artifact", str(artifact),
                    "--worker", "w1",
                ])
            self.assertEqual(exit_code, 0)
            record_printed = json.loads(stdout.getvalue())
            self.assertEqual(record_printed["result"], "pass")
            self.assertEqual(record_printed["missing"], [])

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = REMOTE_CLI.main([
                    "readiness", "--job-dir", str(job_dir), "--worker", "w1",
                ])
            self.assertEqual(exit_code, 0)
            readiness_printed = json.loads(stdout.getvalue())
            self.assertTrue(readiness_printed["ready"])

    def test_remote_cli_module_names_no_service_still_holds(self) -> None:
        """Re-confirms the guard stays green with the smoke/readiness
        surface added -- no ninth guard needed, same module not a new
        sibling (the family stays at eight).
        """
        source = REMOTE_CLI_SCRIPT.read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)


class TargetVocabularyLeakTests(unittest.TestCase):
    """The `*_module_names_no_service` family above (eight tests) forbids
    naming a SERVICE outside `adapters/kaggle.py`. Nothing forbade naming a
    TARGET repository's own product, and that gap is exactly how two
    mentions of `MIL_CREDA_Benchmark` — this forge's real target package —
    reached `jobfolder.py` unnoticed: every existing guard above was blind
    to that literal, since none of them looked for it.

    Scoped to the literal that actually leaked, generalized past its exact
    spelling — `CREDA`, `MIL-CREDA`, `MIL_CREDA_Benchmark` and `MilCreda`
    all share the substring `creda`, so any casing or punctuation variant
    is caught, not only the one string seen today — plus this forge's real
    target dataset names, added on the same reasoning even though none has
    leaked yet: proper nouns with no ordinary-English collision, exactly
    like `creda`.

    Deliberately NOT extended to generic ML/benchmark vocabulary (`epoch`,
    `seed`, `checkpoint`, `arm`, `transfer`, `ceiling`): this skill's own
    modules legitimately use words like these in illustrative prose —
    `adapter.py` names "a set of seeds" as an example of an opaque
    `run_config` key it never reads — and a skill-wide ban on them would
    fail that legitimate usage, not catch a leak. `shard_io.py` already
    forbids `transfer`/`arm` for itself alone, in
    `test_shard_io_source_names_no_service_and_no_domain_term`, because
    that module's own job is reading dimension-keyed shard trees; nothing
    here widens that narrower, module-specific choice.

    Every module in the skill is checked, including `adapters/kaggle.py`:
    that file may name the SERVICE it backs, never the TARGET it happens
    to run today — the two are independent axes, and the existing
    `*_module_names_no_service` tests only ever policed the first one.
    """

    TARGET_LITERALS = ("creda", "mnist", "usps", "svhn")

    def _assert_clean(self, script: Path) -> None:
        source = script.read_text(encoding="utf-8").lower()
        for leaked in self.TARGET_LITERALS:
            self.assertNotIn(leaked, source, f"{leaked!r} in {script}")

    def test_no_module_in_the_skill_names_the_target(self) -> None:
        for script in (
            SCRIPT,
            ADAPTER_SCRIPT,
            PACKER_SCRIPT,
            REMOTE_CLI_SCRIPT,
            REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/credentials.py",
            JOBFOLDER_SCRIPT,
            KAGGLE_SCRIPT,
            RUNNER_BOOTSTRAP_SCRIPT,
            RUNNER_INVOKE_SCRIPT,
            SHARD_IO_SCRIPT,
        ):
            self._assert_clean(script)


class AdapterEnvironmentTests(unittest.TestCase):
    """This skill's `## Environment` section says `None. Stdlib-only`, and that
    is true of its Python and false of the one backend it ships: the adapter
    shells out to a service CLI that arrives through `pip install kaggle` and
    that nothing in the skill, the README, or any requirements file names.

    So the first person to reach the service on a machine without it meets a
    bare `FileNotFoundError` from `subprocess`, with no sentence saying what is
    missing — a dependency whose instruction half was never written, which is
    exactly the shape this repository has spent the session closing.
    """

    def test_a_missing_service_cli_says_what_to_install_not_just_what_failed(self) -> None:
        """`_run` already wraps `OSError` into a refusal that names the binary
        (`could not run <argv0>: [Errno 2] ...`), which is where this test's
        first draft went falsely green: the fixture binary was named
        `...-not-an-installed-binary-...`, so a check for "install" matched the
        fixture's own name rather than any guidance. The name below carries no
        such substring, so the assertion can only pass on a real sentence.

        Naming the binary says WHAT failed. It does not say what to do, and on
        a machine where the service CLI was never installed that is the whole
        question — the skill's own `## Environment` section says `None`, so a
        reader has nowhere else to learn it.
        """
        absent = "zzz-no-such-service-binary-zzz"
        adapter = KAGGLE.KaggleAdapter(kaggle_executable=absent)
        with self.assertRaises(KAGGLE.KaggleAdapterError) as ctx:
            adapter._run([absent, "--version"])
        message = str(ctx.exception)
        self.assertIn(absent, message)
        self.assertNotIn("install", absent,
                         "the fixture name must not contain the word this "
                         "assertion looks for")
        self.assertIn("install", message.lower(),
                      "the refusal names what failed and never what to install")

    def test_the_environment_section_states_the_cli_this_adapter_shells_out_to(self) -> None:
        """Doctrine held to the code that contradicts it. `Environment` claiming
        `None` is what let the dependency stay unwritten; a reader who follows
        it installs nothing and cannot submit.
        """
        text = (REPOSITORY_ROOT / ".claude" / "skills" / "remote-execution"
                / "SKILL.md").read_text(encoding="utf-8")
        section = text.split("## Environment", 1)
        self.assertEqual(len(section), 2, "no Environment section to hold")
        body = section[1].split("\n## ", 1)[0]
        self.assertIn(KAGGLE.KAGGLE_EXECUTABLE, body,
                      "the Environment section never names the service CLI the "
                      "shipped adapter shells out to")


class ClonePathExistenceTests(unittest.TestCase):
    """A declared clone path that does not exist at the pin arrives as nothing.

    `git sparse-checkout set` accepts a path the tree does not contain and
    checks out nothing for it, without a word. So a job could declare the data
    file its run depends on, generate cleanly, push, spend the quota, and have
    the kernel refuse for the absence of a file the operator believed they had
    declared their way to.

    Generation already cross-checks clone paths against what the entry modules
    import. That answers "is every import covered", never "does every declared
    path exist" — and a data path is in the second question's domain and not
    the first's.

    Checked at the PIN, not in the working tree, because the pin is what the
    runner fetches. A file created and not committed is exactly the case that
    would otherwise pass here and fail there.
    """

    def target_with_remote(self, root: Path):
        origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        target = root / "target"
        subprocess.run(["git", "init", "-q", str(target)], check=True)
        package = target / "src" / "pkg"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "harness.py").write_text(
            "def run():\n    return {}\n", encoding="utf-8")
        git = ["git", "-C", str(target), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "seed"], check=True)
        subprocess.run([*git, "remote", "add", "origin", str(origin)], check=True)
        subprocess.run([*git, "push", "-q", "origin", "HEAD:refs/heads/main"], check=True)
        return origin, target, git

    def generate(self, target: Path, origin: Path, *extra_paths: str):
        argv = [sys.executable, str(REMOTE_CLI_SCRIPT), "generate-job",
                "--target", str(target), "--service", "kaggle",
                "--job-name", "probe-job", "--product", "Product",
                "--repo-url", str(origin), "--repo-ref", "main",
                "--clone-path", "src/pkg"]
        for path in extra_paths:
            argv += ["--clone-path", path]
        argv += ["--run-module", "pkg.harness", "--run-function", "run"]
        return subprocess.run(argv, capture_output=True, text=True, cwd=str(target))

    def test_a_declared_path_absent_from_the_pin_refuses_and_names_it(self):
        with tempfile.TemporaryDirectory() as raw:
            origin, target, _ = self.target_with_remote(Path(raw))
            completed = self.generate(target, origin, "Results/ceilings.json")
            output = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0,
                                "generation declared a path the pin does not "
                                "contain: " + output.strip()[:300])
            self.assertIn("Results/ceilings.json", output)
            self.assertFalse((target / "tools").exists(),
                             "a job folder was written for an absent clone path")

    def test_a_path_that_exists_only_in_the_working_tree_still_refuses(self):
        """The runner fetches the pin. A file the operator can see and the pin
        cannot is the case this check exists for, and the one a working-tree
        check would miss.
        """
        with tempfile.TemporaryDirectory() as raw:
            origin, target, _ = self.target_with_remote(Path(raw))
            data = target / "Results"
            data.mkdir()
            (data / "ceilings.json").write_text("{}\n", encoding="utf-8")
            completed = self.generate(target, origin, "Results/ceilings.json")
            output = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0,
                                "an uncommitted file passed as a declared path")
            self.assertIn("Results/ceilings.json", output)

    def test_a_declared_path_present_in_the_pin_is_accepted(self):
        """Non-vacuity: the check must pass for a committed data path, or it is
        only ever refusing and proves nothing about what it admits.
        """
        with tempfile.TemporaryDirectory() as raw:
            origin, target, git = self.target_with_remote(Path(raw))
            data = target / "Results"
            data.mkdir()
            (data / "ceilings.json").write_text("{}\n", encoding="utf-8")
            subprocess.run([*git, "add", "-A"], check=True)
            subprocess.run([*git, "commit", "-q", "-m", "record"], check=True)
            subprocess.run([*git, "push", "-q", "origin", "HEAD:refs/heads/main"],
                           check=True)
            completed = self.generate(target, origin, "Results/ceilings.json")
            self.assertEqual(completed.returncode, 0,
                             (completed.stdout + completed.stderr).strip()[:300])


class PublishedPinResolutionTests(unittest.TestCase):
    """Defaulting to HEAD refuses a pin the runner would never have noticed.

    Generating a job folder writes files under `tools/`, and committing them
    moves HEAD past what the remote has. The next generation then defaults to
    that unpublished HEAD and condition (3) refuses — correctly, since a runner
    cannot fetch it — over a commit that touched nothing the runner clones. The
    author is told to push a commit whose entire content is the job folder they
    are in the middle of regenerating.

    Measured on the live target rather than imagined: `03ac154` changed only
    `tools/kaggle/ceiling-search/`, and `git diff d903d14 03ac154 -- <every
    clone path>` came back empty. The runner would have received byte-identical
    code from the published commit.

    So the default narrows: when HEAD is unpublished and the declared ref's
    published tip carries the same clone-path content, pin the tip. This is not
    the remote-derived default `_resolve_pin`'s docstring rejects — that one
    pins whatever is newest on the remote and can be OLDER than the caller's
    code. This one pins a published commit only after proving it delivers the
    same code, and refuses exactly as before when it does not.
    """

    def published_target(self, root: Path):
        """A bare origin plus a clone holding one published commit."""
        origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        target = root / "target"
        subprocess.run(["git", "init", "-q", str(target)], check=True)
        package = target / "src" / "pkg"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "harness.py").write_text(
            "def run():\n    return {}\n", encoding="utf-8")
        git = ["git", "-C", str(target), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "published"], check=True)
        subprocess.run([*git, "remote", "add", "origin", str(origin)], check=True)
        subprocess.run([*git, "push", "-q", "origin", "HEAD:refs/heads/main"], check=True)
        published = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True,
                                   text=True, check=True).stdout.strip()
        return origin, target, git, published

    def commit_local_only(self, target: Path, git, relative: str):
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("local\n", encoding="utf-8")
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "local only"], check=True)
        return subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()

    def generate(self, target: Path, origin: Path):
        return subprocess.run(
            [sys.executable, str(REMOTE_CLI_SCRIPT), "generate-job",
             "--target", str(target), "--service", "kaggle",
             "--job-name", "probe-job", "--product", "Product",
             "--repo-url", str(origin), "--repo-ref", "main",
             "--clone-path", "src/pkg",
             "--run-module", "pkg.harness", "--run-function", "run"],
            capture_output=True, text=True, cwd=str(target))

    def test_an_unpublished_head_that_changes_no_cloned_code_pins_the_published_tip(self):
        with tempfile.TemporaryDirectory() as raw:
            origin, target, git, published = self.published_target(Path(raw))
            head = self.commit_local_only(target, git, "tools/kaggle/job/run-config.json")
            self.assertNotEqual(head, published)

            completed = self.generate(target, origin)
            self.assertEqual(completed.returncode, 0,
                             "generation refused over a commit the runner never "
                             "clones: " + (completed.stdout + completed.stderr)[:300])
            reported = json.loads(completed.stdout)
            self.assertEqual(reported["commit"], published,
                             "the pin is an unpublished commit the runner cannot fetch")
            self.assertNotEqual(reported["commitSource"], "default-head")

    def test_an_unpublished_head_that_does_change_cloned_code_still_refuses(self):
        """The narrowing must not become permission. When the unpublished commit
        touches what the runner clones, pinning the published tip would ship
        older code — which is the failure `_resolve_pin` already refuses to
        create, and this must not create it by another door.
        """
        with tempfile.TemporaryDirectory() as raw:
            origin, target, git, published = self.published_target(Path(raw))
            self.commit_local_only(target, git, "src/pkg/later.py")

            completed = self.generate(target, origin)
            self.assertNotEqual(completed.returncode, 0,
                                "generation pinned around unpublished cloned code")
            output = completed.stdout + completed.stderr
            self.assertIn("could not be confirmed reachable", output)


class ServiceResolutionTests(unittest.TestCase):
    """The defect `BackendResolutionTests` closed, surviving under a second
    spelling of the same concept.

    `_load_backend_module()` is called at four dispatch sites, every one of
    them keyed on `args.backend`. `generate-job` does not take `--backend`; it
    takes `--service`, and it is the only subcommand that does. So it reached
    `ADAPTER.resolve_metadata(service)` with `adapters/<service>.py` never
    exec'd, and refused a correct invocation with `"no metadata assembler
    registered under 'kaggle'"` — for a service whose adapter sits on disk
    registering exactly that.

    Asserted in a fresh process on purpose: this suite imports the Kaggle
    adapter at module scope, so an in-process check finds the registry already
    populated and passes against the bug.
    """

    def test_generate_job_reaches_the_assembler_its_service_names(self) -> None:
        """An absence, and that is the assertion this defect deserves: what the
        fix restores is that resolution gets past the registry at all. The
        command may still refuse for its own reasons — this fixture builds no
        remote — but never because the adapter naming the service was never
        loaded.
        """
        # Generation refuses in order — reachable commit, resolvable imports,
        # declared clone paths — and only past all three does it ask the
        # registry. A fixture tripping any earlier guard never reaches the
        # defect, which is how the first draft of this test passed against it.
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            origin = root / "origin.git"
            subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
            target = root / "target"
            subprocess.run(["git", "init", "-q", str(target)], check=True)
            package = target / "src" / "product"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "harness.py").write_text(
                "def run():\n    return {}\n", encoding="utf-8")
            git = ["git", "-C", str(target),
                   "-c", "user.email=t@t", "-c", "user.name=t"]
            subprocess.run([*git, "add", "-A"], check=True)
            subprocess.run([*git, "commit", "-q", "-m", "seed"], check=True)
            subprocess.run([*git, "remote", "add", "origin", str(origin)], check=True)
            subprocess.run([*git, "push", "-q", "origin", "HEAD:refs/heads/main"],
                           check=True)
            commit = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True,
                                    text=True, check=True).stdout.strip()
            completed = subprocess.run(
                [sys.executable, str(REMOTE_CLI_SCRIPT), "generate-job",
                 "--target", str(target), "--service", "kaggle",
                 "--job-name", "probe-job", "--product", "Product",
                 "--commit", commit,
                 "--repo-url", str(origin),
                 "--repo-ref", "main",
                 "--clone-path", "src/product",
                 "--run-module", "product.harness", "--run-function", "run"],
                capture_output=True, text=True, cwd=str(target),
            )
        output = completed.stdout + completed.stderr
        self.assertNotIn("no metadata assembler registered", output,
                         "generate-job never side-loaded the adapter its own "
                         "--service names: " + output.strip()[:300])


class BackendResolutionTests(unittest.TestCase):
    """`--backend` used to name an adapter nothing ever registered, for any
    backend whose module `remote_cli.py` never imports — which, before this
    task, was every backend: nothing in this file ever imported
    `adapters/kaggle.py`, so `submit`/`poll`/`fetch`/`reconcile --backend
    kaggle` all failed with `"no adapter registered under 'kaggle'"`
    regardless of anything else being correct.

    `REMOTE_CLI._load_backend_module()` is the fix: a generic, best-effort
    side-loader that execs `adapters/<name>.py` (constrained to a bare
    identifier, checked structurally against the resolved adapters
    directory too) before `ADAPTER.resolve(name)` is asked to find
    anything, so a module dropped into `adapters/` becomes reachable by its
    own filename with zero changes to this CLI.
    """

    def test_unknown_backend_error_names_what_is_registered(self) -> None:
        """The patch this replaces left a caller staring at "no adapter
        registered under 'x'" with no way to tell a typo from a module that
        was never even loaded. The fix names what IS available.
        """
        ADAPTER.register("known-fixture-for-message-test", FakeAdapter)
        with self.assertRaises(KeyError) as ctx:
            ADAPTER.resolve("definitely-not-registered-xyz")
        message = str(ctx.exception)
        self.assertIn("known-fixture-for-message-test", message)
        self.assertIn("available", message)

    def test_hostile_backend_value_cannot_escape_adapters_directory(self) -> None:
        """`--backend`'s value is used to locate a module, so it is
        constrained BEFORE it ever touches the filesystem: a bare
        identifier only (letters, digits, `_`, `-`) — no `.`, `/`, or `\\`,
        which is what makes `..`, an absolute path, or any other
        directory-separator trick impossible to spell in the first place.

        Proven here by planting a marker file OUTSIDE `adapters/` that
        raises the instant it is ever exec'd, then feeding
        `_load_backend_module()` values that would reach it if traversal
        worked. `assertRaises` would surface that `RuntimeError` directly
        if the guard ever failed; its absence, plus `ADAPTER.resolve()`
        still raising `KeyError` for every one of these values afterward,
        is the proof nothing outside `adapters/` was ever read, let alone
        executed.
        """
        adapters_dir = REMOTE_CLI_SCRIPT.parent / "adapters"
        marker = adapters_dir.parent / "zz_escape_marker_for_test.py"
        marker.write_text(
            "raise RuntimeError('a hostile --backend value executed this')\n",
            encoding="utf-8",
        )
        self.addCleanup(marker.unlink)

        hostile_values = (
            "../zz_escape_marker_for_test",
            "../../zz_escape_marker_for_test",
            "/etc/passwd",
            str(marker),
            "kaggle/../../zz_escape_marker_for_test",
            "..",
            "./kaggle",
        )
        for value in hostile_values:
            with self.subTest(value=value):
                REMOTE_CLI._load_backend_module(value)  # must not raise
                with self.assertRaises(KeyError):
                    ADAPTER.resolve(value)

    def test_dropping_a_module_into_adapters_becomes_reachable_by_backend_name(
        self,
    ) -> None:
        """Genericity: a module this test writes at runtime, never imported
        by ANY line in `remote_cli.py`, becomes resolvable purely by
        dropping it into `adapters/` under a matching filename — and both
        of its own registrations (`ADAPTER.register` AND
        `ADAPTER.register_metadata`) take effect, not only the first.
        """
        adapters_dir = REMOTE_CLI_SCRIPT.parent / "adapters"
        fixture_name = "zz_fixture_backend_for_test"
        fixture_path = adapters_dir / f"{fixture_name}.py"
        fixture_path.write_text(
            "import importlib.util\n"
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "def _load_adapter_seam():\n"
            "    module_name = 'remote_execution_adapter'\n"
            "    if module_name in sys.modules:\n"
            "        return sys.modules[module_name]\n"
            "    script = Path(__file__).resolve().parent.parent / 'adapter.py'\n"
            "    spec = importlib.util.spec_from_file_location(module_name, script)\n"
            "    module = importlib.util.module_from_spec(spec)\n"
            "    sys.modules[module_name] = module\n"
            "    spec.loader.exec_module(module)\n"
            "    return module\n"
            "\n"
            "ADAPTER = _load_adapter_seam()\n"
            "\n"
            "class _FixtureAdapter(ADAPTER.Adapter):\n"
            "    def workers(self):\n"
            "        return []\n"
            "    def submit(self, job):\n"
            "        return ADAPTER.Submission(id='fixture-1', worker=job.worker)\n"
            "    def poll(self, submission_id):\n"
            "        return ADAPTER.Status(state='running', detail='fixture-marker')\n"
            "    def fetch(self, submission_id, into):\n"
            "        return ADAPTER.Fetched(path=into, complete=True, files=())\n"
            "    def cancel(self, submission_id):\n"
            "        return None\n"
            "    def list_active(self, worker):\n"
            "        return []\n"
            "\n"
            "ADAPTER.register('zz_fixture_backend_for_test', _FixtureAdapter)\n"
            "ADAPTER.register_metadata(\n"
            "    'zz_fixture_backend_for_test',\n"
            "    lambda run_config: ('fixture-metadata.json', '{}'),\n"
            ")\n",
            encoding="utf-8",
        )
        self.addCleanup(fixture_path.unlink)
        self.addCleanup(
            lambda: shutil.rmtree(adapters_dir / "__pycache__", ignore_errors=True)
        )

        with self.assertRaises(KeyError):
            ADAPTER.resolve(fixture_name)

        REMOTE_CLI._load_backend_module(fixture_name)

        adapter_cls = ADAPTER.resolve(fixture_name)
        self.assertTrue(issubclass(adapter_cls, ADAPTER.Adapter))

        metadata_fn = ADAPTER.resolve_metadata(fixture_name)
        filename, text = metadata_fn({})
        self.assertEqual(filename, "fixture-metadata.json")
        self.assertEqual(text, "{}")

    def test_live_poll_resolves_the_real_kaggle_adapter_without_any_network_call(
        self,
    ) -> None:
        """A real, separate `python3 remote_cli.py poll --backend kaggle`
        invocation, in a FRESH process — unlike every other test in this
        file, which shares one process where `adapters/kaggle.py` is
        already preloaded at module scope (see `KAGGLE` above), so
        `ADAPTER.resolve('kaggle')` would trivially succeed in-process
        regardless of whether `remote_cli.py` itself can resolve it.

        `PATH` is forced empty for the child, so the `kaggle` executable is
        guaranteed unfindable: `subprocess.run(['kaggle', ...])` fails with
        a purely local `FileNotFoundError` before any network I/O is even
        attempted, wrapped by `adapters/kaggle.py` into `"could not run
        kaggle: ..."`. That message — NOT `"no adapter registered under
        'kaggle'"` — is the proof `--backend kaggle` resolved to the real
        adapter and got as far as trying to invoke it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            # A real credential file, because the adapter now reads one
            # before it shells out: an unreadable path would refuse EARLIER
            # than the invocation this test is about, and the refusal it
            # proved would be the wrong one.
            fake_credential = Path(tmp) / "fake-creds"
            fake_credential.write_text(FIXTURE_TOKEN + "\n", encoding="utf-8")
            env = dict(os.environ)
            env["PATH"] = ""
            result = subprocess.run(
                [
                    sys.executable, str(REMOTE_CLI_SCRIPT),
                    "poll",
                    "--submission-id", "someuser/some-slug",
                    "--backend", "kaggle",
                    "--credential-dir", str(fake_credential),
                ],
                env=env, capture_output=True, text=True, timeout=30,
            )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("no adapter registered", result.stderr)
        self.assertIn("could not run", result.stderr)


class SmokeLedgerResolutionTests(unittest.TestCase):
    """`cmd_status`, `cmd_fetch` and `cmd_reconcile` each hardcoded
    `LEDGER_FILENAME` and never once referenced `smoke.jsonl` — so a
    submission `submit --smoke` recorded could never be fetched, never
    showed up in `status`, and a still-active smoke submission reconcile
    should have accounted for instead misreported as `orphanRemote`.

    `resolve_submission_ledger()` is the single-point fix every command
    that resolves ONE submission id now goes through. It still folds
    `ledger.jsonl` and `smoke.jsonl` SEPARATELY — never concatenated —
    which is what keeps `test_smoke_submission_never_enters_the_fold_or_
    supersedes_a_real_run` (above) true through this new code path too.
    """

    def test_status_reports_a_parallel_smoke_section_without_merging_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            main_ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME
                / REMOTE_CLI.LEDGER_FILENAME
            )
            smoke_ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME
                / REMOTE_CLI.SMOKE_LEDGER_FILENAME
            )
            _append_pending_submission(
                main_ledger_path, entrypoint="Notebooks/a.ipynb",
                submission_id="main-1", worker="w1", source_digest="d" * 64,
            )
            _append_pending_submission(
                smoke_ledger_path, entrypoint="Notebooks/a.ipynb",
                submission_id="smoke-1", worker="w1", source_digest="d" * 64,
            )

            result = REMOTE_CLI.cmd_status(
                target=target, entrypoint=notebook, source_digest=lambda t, n: "d" * 64,
            )

            self.assertEqual(
                result["entrypoints"]["Notebooks/a.ipynb"]["state"], "pending",
            )
            self.assertIn("smoke", result)
            self.assertEqual(
                result["smoke"]["entrypoints"]["Notebooks/a.ipynb"]["state"],
                "pending",
            )
            self.assertEqual(result["smoke"]["ledgerPath"], smoke_ledger_path)
            # Reported side by side, never merged: the main section's own
            # fold was computed from ledger.jsonl alone (one line), and
            # stays that way regardless of what smoke.jsonl also holds.
            self.assertEqual(
                len(main_ledger_path.read_text(encoding="utf-8").splitlines()), 1,
            )

    def test_fetch_materializes_a_smoke_submissions_result_and_writes_only_smoke_jsonl(
        self,
    ) -> None:
        """Before this fix, `cmd_fetch` could never find a submission
        `submit --smoke` recorded at all — this is the reachable RED this
        test pins.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            submit_result = REMOTE_CLI.cmd_submit(
                target=target, entrypoint=notebook, worker="w1", requested=1,
                adapter=adapter, source_digest=lambda t, n: "d" * 64, smoke=True,
            )
            submission_id = submit_result["submission"].id
            self.assertTrue(submit_result["ledgerPath"].name, "smoke.jsonl")

            dest = target.resolve() / "MIL-CREDA" / "Results" / "shards" / "a"
            fetch_result = REMOTE_CLI.cmd_fetch(
                target=target, entrypoint=notebook, submission_id=submission_id,
                dest=dest, adapter=adapter, source_digest=lambda t, n: "d" * 64,
            )

            self.assertTrue(fetch_result["complete"])
            self.assertEqual(fetch_result["verdict"], "current")
            self.assertTrue((dest / "result.txt").exists())

            smoke_ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME
                / REMOTE_CLI.SMOKE_LEDGER_FILENAME
            )
            main_ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME
                / REMOTE_CLI.LEDGER_FILENAME
            )
            smoke_lines = smoke_ledger_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(smoke_lines), 2)  # submitted + returned
            self.assertEqual(json.loads(smoke_lines[-1])["kind"], "returned")
            # The smoke submission's own `returned` event never touched the
            # main ledger -- ledger.jsonl was never even created.
            self.assertFalse(main_ledger_path.exists())

    def test_fetch_raises_a_clear_error_when_submission_is_in_neither_ledger(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            adapter = FakeAdapter(worker_id="w1", capacity=2)
            dest = target.resolve() / "MIL-CREDA" / "Results" / "shards" / "a"
            with self.assertRaises(REMOTE_CLI.RemoteCLIError) as ctx:
                REMOTE_CLI.cmd_fetch(
                    target=target, entrypoint=notebook, submission_id="ghost",
                    dest=dest, adapter=adapter, source_digest=lambda t, n: "d" * 64,
                )
            message = str(ctx.exception)
            self.assertIn(REMOTE_CLI.LEDGER_FILENAME, message)
            self.assertIn(REMOTE_CLI.SMOKE_LEDGER_FILENAME, message)

    def test_resolve_submission_ledger_refuses_when_id_is_recorded_in_both_files(
        self,
    ) -> None:
        """Defensive: an id is only ever supposed to land in ONE file. If
        it somehow reached both, guessing which one is authoritative would
        hide a corruption instead of surfacing it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            (notebooks / "a.ipynb").write_text("{}", encoding="utf-8")

            main_ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME
                / REMOTE_CLI.LEDGER_FILENAME
            )
            smoke_ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME
                / REMOTE_CLI.SMOKE_LEDGER_FILENAME
            )
            _append_pending_submission(
                main_ledger_path, entrypoint="Notebooks/a.ipynb",
                submission_id="dup-1", worker="w1", source_digest="d" * 64,
            )
            _append_pending_submission(
                smoke_ledger_path, entrypoint="Notebooks/a.ipynb",
                submission_id="dup-1", worker="w1", source_digest="d" * 64,
            )

            with self.assertRaises(REMOTE_CLI.RemoteCLIError) as ctx:
                REMOTE_CLI.resolve_submission_ledger(
                    target.resolve(), "MIL-CREDA", "dup-1", "d" * 64,
                )
            self.assertIn("both", str(ctx.exception))

    def test_reconcile_does_not_misreport_a_still_active_smoke_submission(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            smoke_ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME
                / REMOTE_CLI.SMOKE_LEDGER_FILENAME
            )
            _append_pending_submission(
                smoke_ledger_path, entrypoint="Notebooks/a.ipynb",
                submission_id="smk-1", worker="w1", source_digest="d" * 64,
            )

            adapter = ScriptedListActiveAdapter(worker_id="w1", active=("smk-1",))
            result = REMOTE_CLI.cmd_reconcile(
                target=target, entrypoint=notebook, worker="w1", adapter=adapter,
                source_digest=lambda t, n: "d" * 64,
            )

            self.assertEqual(result["orphanRemote"], ())
            self.assertEqual(result["orphanLocal"], ())

    def test_reconcile_resolve_appends_errored_event_to_the_smoke_ledger_for_a_smoke_orphan(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            smoke_ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME
                / REMOTE_CLI.SMOKE_LEDGER_FILENAME
            )
            main_ledger_path = (
                target.resolve() / "MIL-CREDA" / REMOTE_CLI.LEDGER_DIRNAME
                / REMOTE_CLI.LEDGER_FILENAME
            )
            _append_pending_submission(
                smoke_ledger_path, entrypoint="Notebooks/a.ipynb",
                submission_id="smk-2", worker="w1", source_digest="d" * 64,
            )

            # The service no longer lists smk-2 at all.
            adapter = ScriptedListActiveAdapter(worker_id="w1", active=())
            result = REMOTE_CLI.cmd_reconcile(
                target=target, entrypoint=notebook, worker="w1", adapter=adapter,
                resolve=True, source_digest=lambda t, n: "d" * 64,
            )

            self.assertEqual(result["orphanLocal"], ("smk-2",))
            self.assertEqual(len(result["resolved"]), 1)
            self.assertEqual(result["resolved"][0]["submissionId"], "smk-2")

            smoke_lines = smoke_ledger_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(smoke_lines), 2)
            self.assertEqual(json.loads(smoke_lines[-1])["kind"], "errored")
            # Never touched: the orphan lived in smoke.jsonl alone.
            self.assertFalse(main_ledger_path.exists())


if __name__ == "__main__":
    unittest.main()
