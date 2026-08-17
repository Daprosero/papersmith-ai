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

import dataclasses
import importlib.util
import inspect
import json
import multiprocessing
import os
import re
import sys
import tempfile
import unittest
import unittest.mock
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

        job = ADAPTER.Job(entrypoint=Path("Notebooks/a.ipynb"), inputs=(), worker=workers[0].id)
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
        job = ADAPTER.Job(entrypoint=Path("Notebooks/a.ipynb"), inputs=("x",), worker="w1")
        self.assertEqual(job.entrypoint, Path("Notebooks/a.ipynb"))
        with self.assertRaises(TypeError):
            ADAPTER.Job(notebook=Path("a.ipynb"), inputs=(), worker="w1")

    def test_status_rejects_a_value_outside_the_five_state_vocabulary(self) -> None:
        with self.assertRaises(ValueError):
            ADAPTER.Status(state="succeeded", detail="a backend's own word, not the seam's")

    def test_frozen_shapes_refuse_assignment(self) -> None:
        worker = ADAPTER.Worker(id="w1", capacity=2)
        job = ADAPTER.Job(entrypoint=Path("a.ipynb"), inputs=(), worker="w1")
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
        job = ADAPTER.Job(entrypoint=Path("Notebooks/a.ipynb"), inputs=(), worker="w1")
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
        job = ADAPTER.Job(entrypoint=Path("Notebooks/a.ipynb"), inputs=(), worker="w1")
        submission = adapter.submit(job)

        with self.assertRaises(REMOTE_CLI.RemoteCLIError):
            REMOTE_CLI.cmd_poll(submission_id=submission.id, adapter=adapter)

    def test_poll_accepts_a_genuinely_valid_status(self) -> None:
        adapter = FakeAdapter(worker_id="w1", capacity=2)
        job = ADAPTER.Job(entrypoint=Path("Notebooks/a.ipynb"), inputs=(), worker="w1")
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


if __name__ == "__main__":
    unittest.main()
