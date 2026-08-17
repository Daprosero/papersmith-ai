"""Focused unit tests for the remote-execution ledger.

Covers `ledger.py`'s write-integrity guarantees (the short-write check, the
per-event size cap, `errored.reason` truncation, concurrent appenders never
tearing or losing a line), and its fold: deriving per-entrypoint state from
the log, and the currency rule that tells a fresh result from a stale one.

Run with any Python 3.10+ (the module is stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / ".claude/skills/remote-execution/scripts/ledger.py"
SPEC = importlib.util.spec_from_file_location("remote_execution_ledger", SCRIPT)
assert SPEC and SPEC.loader
LEDGER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LEDGER
SPEC.loader.exec_module(LEDGER)


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


if __name__ == "__main__":
    unittest.main()
