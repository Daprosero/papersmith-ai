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
import contextlib
import dataclasses
import importlib.util
import io
import inspect
import json
import multiprocessing
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import uuid
from pathlib import Path
from types import SimpleNamespace


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
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
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            job_dir = _make_job_folder(target, "kaggle", "search-a")
            notebook = job_dir / "runner.ipynb"
            notebook.write_text("{}", encoding="utf-8")

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


def _write_fake_kaggle(
    bin_dir: Path,
    *,
    status_text: str = "complete",
    exit_code: int = 0,
    sleep_seconds: float | None = None,
) -> Path:
    """A minimal stand-in for the real `kaggle` executable.

    Never touches a network, never reads whatever `KAGGLE_CONFIG_DIR`
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

    def test_requested_accelerator_is_declared_here_as_a_request_not_a_receipt(self) -> None:
        self.assertEqual(KAGGLE.REQUESTED_ACCELERATOR, "NvidiaTeslaT4")

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
            config_dir = tmp_path / "creds"
            config_dir.mkdir()

            handle = KAGGLE.CredentialHandle(worker_id="acct-1", config_dir=config_dir)
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
            config_dir = tmp_path / "creds"
            config_dir.mkdir()

            handle = KAGGLE.CredentialHandle(worker_id="acct-1", config_dir=config_dir)
            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"acct-1": handle})
                status = adapter.poll("acct-1/kernel-1")

            self.assertEqual(status.state, "running")

    def test_non_zero_exit_from_the_service_cli_produces_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir, exit_code=7)
            config_dir = tmp_path / "creds"
            config_dir.mkdir()

            handle = KAGGLE.CredentialHandle(worker_id="acct-1", config_dir=config_dir)
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
            config_dir = tmp_path / "creds"
            config_dir.mkdir()

            handle = KAGGLE.CredentialHandle(worker_id="acct-1", config_dir=config_dir)
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
            config_dir = tmp_path / "creds"
            config_dir.mkdir()
            # No "/" anywhere in this string: `poll()` derives a worker id
            # from a submission id by splitting on the FIRST "/", and this
            # test's own `/kernel-1` suffix is what that split is meant to
            # find — a malicious segment containing its own "/" would
            # confuse this test's own arithmetic, not the adapter's.
            marker_name = "pwned-marker"
            malicious_worker = (
                f"acct-1$(touch {marker_name})`touch {marker_name}`;touch {marker_name}"
            )
            handle = KAGGLE.CredentialHandle(worker_id=malicious_worker, config_dir=config_dir)

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
        """The one and only place `"NvidiaTeslaT4"` exists: `adapters/kaggle.py`
        registers `assemble_metadata` under the metadata registry, and
        calling it produces `kernel-metadata.json` naming the pinned
        accelerator.
        """
        assembler = ADAPTER.resolve_metadata("kaggle")
        filename, text = assembler({"mode": "smoke"})
        self.assertEqual(filename, "kernel-metadata.json")
        payload = json.loads(text)
        self.assertEqual(payload["accelerator"], "NvidiaTeslaT4")

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

            config_dir = tmp_path / "creds"
            config_dir.mkdir()
            handle = KAGGLE.CredentialHandle(worker_id="w1", config_dir=config_dir)
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
            config_dir = tmp_path / "creds"
            config_dir.mkdir()
            handle = KAGGLE.CredentialHandle(worker_id="w1", config_dir=config_dir)

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
            config_dir = tmp_path / "creds"
            config_dir.mkdir()
            handle = KAGGLE.CredentialHandle(worker_id="w1", config_dir=config_dir)

            with unittest.mock.patch.dict(
                os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
            ):
                adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})
                job = ADAPTER.Job(entrypoint=entrypoint, run_config={}, worker="w1")
                submission = adapter.submit(job)

            self.assertEqual(submission.worker, "w1")

    def test_credential_sentinel_absent_from_argv_stdout_stderr_ledger_and_quarantine(
        self,
    ) -> None:
        """The sentinel test: the whole point of `CredentialHandle` is that
        a key VALUE never becomes a value this process holds. A fake
        credential file, holding a unique sentinel, sits inside the
        directory this adapter is handed by PATH only — and after a real
        `submit()` followed by a `fetch()` that lands in quarantine (so
        both the ledger AND a quarantine file are exercised), the sentinel
        must appear in none of: every subprocess call's argv, its stdout,
        its stderr, the ledger file, or the quarantine file.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "repo"
            notebooks = _make_product(target, "MIL-CREDA")
            notebook = notebooks / "a.ipynb"
            notebook.write_text("{}", encoding="utf-8")

            sentinel = "SENTINEL-" + uuid.uuid4().hex
            config_dir = tmp_path / "creds" / "w1"
            config_dir.mkdir(parents=True)
            (config_dir / "kaggle.json").write_text(
                json.dumps({"username": "w1", "key": sentinel}), encoding="utf-8"
            )

            bin_dir = tmp_path / "bin"
            _write_fake_kaggle(bin_dir)

            fake_accounts_cli = tmp_path / "fake_accounts_cli.py"
            fake_accounts_cli.write_text(
                "import json\n"
                "print(json.dumps({'accounts': [{'username': 'w1'}]}))\n",
                encoding="utf-8",
            )

            handle = KAGGLE.CredentialHandle(worker_id="w1", config_dir=config_dir)

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
    only, never the key, mirroring `cmd_materialize`'s own contract.
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
        "(dest / 'kaggle.json').write_text(json.dumps({'username': args.worker, 'key': key}))\n"
        "os.chmod(dest / 'kaggle.json', 0o600)\n"
        "print(json.dumps({'worker': args.worker, 'configDir': str(dest)}))\n",
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
    argument resolves under `guarded_root`. Every call is still forwarded
    to the real implementation — this only OBSERVES, it never blocks —
    so the guarded code path keeps running exactly as it would otherwise.
    """
    hits: list[str] = []
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_open = builtins.open

    def guarded_read_text(path_self, *a, **kw):
        if _is_under(path_self, guarded_root):
            hits.append(f"Path.read_text:{path_self}")
        return real_read_text(path_self, *a, **kw)

    def guarded_read_bytes(path_self, *a, **kw):
        if _is_under(path_self, guarded_root):
            hits.append(f"Path.read_bytes:{path_self}")
        return real_read_bytes(path_self, *a, **kw)

    def guarded_open(file, *a, **kw):
        if _is_under(file, guarded_root):
            hits.append(f"open:{file}")
        return real_open(file, *a, **kw)

    with unittest.mock.patch.object(Path, "read_text", guarded_read_text), \
            unittest.mock.patch.object(Path, "read_bytes", guarded_read_bytes), \
            unittest.mock.patch("builtins.open", guarded_open):
        yield hits


class CredentialSecurityTests(unittest.TestCase):
    """T1's hard security constraints (C2-C6): no component above the
    adapter seam may open, read, print, or parse the credential store or
    any credential file. Credentials move BY PATH only; the sole sink is
    `KAGGLE_CONFIG_DIR` on a child process's own environment.

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

    def test_zero_file_read_interposition_across_a_full_submit_poll_fetch_status_run(
        self,
    ) -> None:
        """C2."""
        with tempfile.TemporaryDirectory() as tmp:
            cycle = self._run_full_cycle(Path(tmp))
            self.assertGreater(len(cycle["calls"]), 0)
            self.assertEqual(cycle["interposition_hits"], [])

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

    def test_credential_handle_carries_exactly_worker_id_and_config_dir(self) -> None:
        """C5."""
        fields = tuple(f.name for f in dataclasses.fields(ADAPTER.CredentialHandle))
        self.assertEqual(fields, ("worker_id", "config_dir"))

        # `.config_dir` is accessed exactly once in `adapters/kaggle.py`'s
        # actual CODE — the single sink documented at the top of this
        # module. Parsed as an AST rather than scanned as raw text, so a
        # docstring that quotes the same expression in prose (as this
        # module's own module docstring does, to document the sink) is not
        # mistaken for a second real access.
        tree = ast.parse(KAGGLE_SCRIPT.read_text(encoding="utf-8"))
        accesses = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "config_dir"
        ]
        self.assertEqual(len(accesses), 1)

    def test_the_only_sink_is_kaggle_config_dir_on_the_child_environment(self) -> None:
        """C6."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "creds"
            config_dir.mkdir()
            handle = KAGGLE.CredentialHandle(worker_id="w1", config_dir=config_dir)
            adapter = KAGGLE.KaggleAdapter(credentials={"w1": handle})

            env = adapter._env_for(handle)
            self.assertEqual(env.get("KAGGLE_CONFIG_DIR"), str(config_dir))
            self.assertEqual(sorted(env), ["KAGGLE_CONFIG_DIR", "PATH"])

            env_without_handle = adapter._env_for(None)
            self.assertEqual(sorted(env_without_handle), ["PATH"])


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


if __name__ == "__main__":
    unittest.main()
