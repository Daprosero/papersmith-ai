#!/usr/bin/env python3
"""The Kaggle backend adapter — the ONLY file in this entire skill allowed
to name a service.

Every module above `adapter.py` (`ledger.py`, `packer.py`, `remote_cli.py`)
stays deliberately blind to what backend, if any, is behind a given worker.
This module is where that blindness ends: it is the one place permitted to
say "Kaggle", to shell out to the `kaggle` command-line tool, and to know
that tool's own vocabulary well enough to translate it into the seam's.

Two structural guarantees hold everywhere below, not by convention but by
what this file's own dependency graph can even reach:

1. This module imports `subprocess`, `json`, `csv`, `io`, `re`, `sys`, `os`,
   `dataclasses`, `pathlib` and this skill's own `adapter.py` — nothing
   else. It has no constant, no argument and no configuration key naming
   the credential file `kaggle-accounts` keeps for itself, and it never
   constructs a path into that skill's own data directory. Worker identity
   comes from exactly one sanctioned command, run as a subprocess:
   `python3 <kaggle-accounts>/scripts/accounts_cli.py list --json`, which
   answers with usernames and nothing else (`cmd_list` under `--json`
   builds a fresh dict holding only `username` per account — no other key
   can reach a caller even by accident). This module never imports that
   script; it only runs it, exactly the way a human at a terminal would.

2. Credentials move BY PATH, never by value. `CredentialHandle` below is
   the only credential type this adapter accepts, and it carries a
   directory, not a secret. Its single sink, in the whole file, is
   `env["KAGGLE_CONFIG_DIR"] = str(handle.config_dir)` on exactly one
   subprocess call. Nothing in this module ever opens, reads or parses
   whatever file lives inside that directory — the `kaggle` executable
   does that, in its own process, with its own environment, and this
   module never inspects what that process printed for anything other
   than a translated status word and an exit code.

Every subprocess call here is `shell=False` with a list argv, an explicit
timeout, and an env built from an allowlist (`PATH` plus, when a credential
is involved, `KAGGLE_CONFIG_DIR` — nothing else is ever forwarded from this
process's own environment). A non-zero exit or an expired timeout is a
refusal: this module raises `KaggleAdapterError` rather than fabricate a
`Status`, a `Submission` or a `Fetched` result the service never actually
confirmed.

Run with any Python 3.10+ (stdlib-only, no `kaggle` package import — this
module shells out to the CLI, it never imports it):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


def _load_adapter_seam():
    """Path-import `adapter.py`, one directory up from this file, reusing
    an already-loaded copy under `remote_execution_adapter` when one
    exists.

    Same `sys.modules`-reuse technique `remote_cli.py` and `packer.py` use
    for their own sibling loads, and the same correctness reason: a second,
    separately exec'd copy of `adapter.py` would define a second, distinct
    `Adapter` class with the same name, and `isinstance(kaggle_adapter,
    ADAPTER.Adapter)` checks made by a caller holding the first copy would
    silently fail against an instance built from the second.
    """
    module_name = "remote_execution_adapter"
    if module_name in sys.modules:
        return sys.modules[module_name]
    script = Path(__file__).resolve().parent.parent / "adapter.py"
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER = _load_adapter_seam()


class KaggleAdapterError(ADAPTER.AdapterError):
    """A refusal: the service CLI failed, timed out, or this adapter was
    asked to act for a worker it holds no `CredentialHandle` for.

    Never raised to report a guess — only to report that this adapter
    declined to fabricate an answer the service never actually confirmed.
    """


# `.claude/skills/kaggle-accounts/scripts/accounts_cli.py`, computed once
# relative to this file. This traversal names the sanctioned command's
# location only — never the credential file that command guards, which
# this module has no path to at all.
DEFAULT_ACCOUNTS_CLI = (
    Path(__file__).resolve().parents[3] / "kaggle-accounts" / "scripts" / "accounts_cli.py"
)

KAGGLE_EXECUTABLE = "kaggle"
SUBPROCESS_TIMEOUT_SECONDS = 120.0

# This service's documented per-worker concurrent-kernel allowance, stated
# here and nowhere else in this skill — NOT a universal constant, and not
# something a second backend's adapter should read off this module. A
# backend metering capacity some other way (a quota, a byte budget) would
# convert it into "concurrent jobs" inside its own adapter, exactly the
# same way this one does.
KAGGLE_WORKER_CAPACITY = 1

# The accelerator this repository's submissions request. A REQUEST, not a
# receipt: asking for one is not the same as receiving one. What a
# submission actually ran on is a fact the service states, at poll or fetch
# time, in `Status.detail` — never assumed from this constant, and never
# stamped anywhere by this module on its own initiative. Selecting an
# accelerator for a real kernel submission is governed by that kernel's own
# metadata, prepared by whatever assembles a submission's directory before
# `submit()` is ever called; this constant exists so that assembly has one
# sanctioned place, inside the one file allowed to name a service, to read
# the requested value from.
REQUESTED_ACCELERATOR = "T4"

# The seam's own five-value vocabulary a raw Kaggle status is translated
# into — never passed through. Anything Kaggle reports that is not a key
# here (a cancellation state, a future addition to Kaggle's own vocabulary,
# anything this table was not updated for) becomes "unknown", deliberately,
# rather than guessed at.
_KAGGLE_STATUS_TO_SEAM = {
    "queued": "queued",
    "running": "running",
    "complete": "complete",
    "error": "failed",
}

_QUOTED_STATUS = re.compile(r'"([^"]+)"')
_SLUG_DISALLOWED = re.compile(r"[^a-z0-9-]+")


def _extract_status_token(raw: str) -> str:
    """Pull a status word out of the CLI's own sentence, when it quotes
    one (`... has status "complete"`); fall back to the whole trimmed,
    lowercased line otherwise. Either way this returns a CANDIDATE token
    for `_KAGGLE_STATUS_TO_SEAM` to translate — never a value handed
    upward as `Status.state` directly.
    """
    match = _QUOTED_STATUS.search(raw)
    token = match.group(1) if match else raw
    return token.strip().lower()


def _kernel_slug(entrypoint: Path) -> str:
    """A deterministic slug derived from an entrypoint's own filename —
    never a lookup, never state kept anywhere in this process. Kaggle
    kernel refs are `<username>/<slug>`; this function supplies the second
    half from the notebook this job actually names.
    """
    lowered = entrypoint.stem.lower()
    slug = _SLUG_DISALLOWED.sub("-", lowered).strip("-")
    return slug or "kernel"


# The seam's own shape (`adapter.py`), aliased under this module's name so
# every existing caller and test that imports `CredentialHandle` FROM here
# keeps working unchanged. The class is defined exactly once, in the seam,
# because it carries no service-specific behavior at all — moving it there
# is what lets a second backend adapter reuse the same shape without
# redefining it; only the environment variable it is eventually handed to
# (`KAGGLE_CONFIG_DIR`, below) is this service's own.
CredentialHandle = ADAPTER.CredentialHandle


class KaggleAdapter(ADAPTER.Adapter):
    """The concrete `Adapter` this skill ships for Kaggle.

    Constructible with no arguments, matching every other adapter this
    skill's own CLI instantiates via `ADAPTER.resolve(name)()`
    (`remote_cli.py`'s `main()` calls `adapter_cls()`, never with
    arguments). With no credentials supplied, every method that needs one
    refuses cleanly the first time it is asked to act for a worker —
    fails closed, not silently.
    """

    # Read by `remote_cli.py`'s generic construction site, through a bare
    # `getattr(adapter_cls, "CREDENTIAL_CLI", None)` that names no backend
    # at all — see `_accounts_cli_for()` there. This is an ordinary class
    # attribute, not one of the `Adapter` ABC's six operations, which is
    # what lets an adapter with no credential-materializing CLI of its own
    # (this skill's own test doubles included) simply not define it. Reusing
    # `DEFAULT_ACCOUNTS_CLI` here, rather than declaring a second path, is
    # what keeps this module's own `workers()` and `credentials.py`'s
    # `materialize()` pointed at the exact same script.
    CREDENTIAL_CLI = DEFAULT_ACCOUNTS_CLI

    def __init__(
        self,
        *,
        credentials: (
            Mapping[str, CredentialHandle] | Callable[[str], CredentialHandle] | None
        ) = None,
        accounts_cli: Path | str | None = None,
        kaggle_executable: str = KAGGLE_EXECUTABLE,
        timeout: float = SUBPROCESS_TIMEOUT_SECONDS,
    ) -> None:
        self._credential_provider = self._normalize_credentials(credentials)
        self._accounts_cli = Path(accounts_cli) if accounts_cli else DEFAULT_ACCOUNTS_CLI
        self._kaggle_executable = kaggle_executable
        self._timeout = timeout

    @staticmethod
    def _normalize_credentials(
        credentials: (
            Mapping[str, CredentialHandle] | Callable[[str], CredentialHandle] | None
        ),
    ) -> Callable[[str], CredentialHandle]:
        """One internal shape regardless of what a caller handed in.

        A caller that already knows every worker it will ever ask for —
        most of this module's own test suite — passes a plain mapping,
        unchanged from before this method existed. A caller that does NOT
        pass one instead: `remote_cli.py`'s `poll` command never learns a
        worker id at all, only a submission id this adapter alone is
        permitted to split, so nothing above this seam can build a full
        mapping up front for that command. That caller passes a callable,
        resolved lazily the first time a worker is actually needed.

        Both collapse to the same shape here so `_credential_for()` below
        never has to ask which one it was given.
        """
        if credentials is None:
            def _none(worker: str) -> CredentialHandle:
                raise KeyError(worker)

            return _none
        if callable(credentials) and not isinstance(credentials, Mapping):
            return credentials
        mapping = dict(credentials)

        def _lookup(worker: str) -> CredentialHandle:
            return mapping[worker]

        return _lookup

    def _credential_for(self, worker: str) -> CredentialHandle:
        try:
            return self._credential_provider(worker)
        except KeyError:
            raise KaggleAdapterError(
                f"no credential handle registered for worker {worker!r}; this "
                "adapter accepts credentials only as CredentialHandle instances, "
                "supplied directly or produced by a provider callable, never by "
                "reading a credential file on its own initiative"
            ) from None

    def _env_for(self, handle: CredentialHandle | None) -> dict[str, str]:
        """Build the child process's WHOLE environment from an allowlist —
        never this process's own `os.environ` forwarded wholesale, which
        would leak every other variable this process happens to be
        carrying, credential-shaped or not.
        """
        env = {"PATH": os.environ.get("PATH", "")}
        if handle is not None:
            env["KAGGLE_CONFIG_DIR"] = str(handle.config_dir)
        return env

    def _run(self, argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise KaggleAdapterError(
                f"{argv[0]} timed out after {self._timeout}s: refusing to guess "
                "at a status or a completion this process never confirmed"
            ) from exc
        except OSError as exc:
            raise KaggleAdapterError(f"could not run {argv[0]}: {exc}") from exc

    def workers(self) -> list["ADAPTER.Worker"]:
        """Usernames from the sanctioned `list --json` command, each
        stamped with THIS service's documented per-worker allowance.

        Runs `python3 <accounts_cli> list --json` as a subprocess and reads
        only its stdout; never opens, globs or otherwise touches any file
        `accounts_cli` itself might consult. That is what lets this method
        answer normally even when whatever file backs `accounts_cli`'s own
        answer is unreadable to THIS process directly — this process never
        tries to read it at all.
        """
        result = self._run([sys.executable, str(self._accounts_cli), "list", "--json"])
        if result.returncode != 0:
            raise KaggleAdapterError(
                f"{self._accounts_cli} list --json exited {result.returncode}: "
                f"{result.stderr.strip()}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise KaggleAdapterError(
                f"{self._accounts_cli} list --json did not print JSON: {exc}"
            ) from exc

        return [
            ADAPTER.Worker(id=account["username"], capacity=KAGGLE_WORKER_CAPACITY)
            for account in payload.get("accounts", [])
        ]

    def submit(self, job: "ADAPTER.Job") -> "ADAPTER.Submission":
        """Push `job.entrypoint`'s own directory as a kernel version and
        report back the ref this adapter will recognize it by later.

        The submission id is `<worker>/<slug>` — derived from `job.worker`
        and `job.entrypoint`'s own filename ALONE, never read out of
        anything the `kaggle` process printed. `poll()`, `fetch()` and
        `list_active()` all recover `worker` from this same id, by
        splitting on the one `/` this construction guarantees is there.
        """
        handle = self._credential_for(job.worker)
        ref = f"{job.worker}/{_kernel_slug(job.entrypoint)}"
        argv = [self._kaggle_executable, "kernels", "push", "-p", str(job.entrypoint.parent)]
        result = self._run(argv, env=self._env_for(handle))
        if result.returncode != 0:
            raise KaggleAdapterError(
                f"kernels push for {job.entrypoint} exited {result.returncode}: "
                f"{result.stderr.strip()}"
            )
        return ADAPTER.Submission(id=ref, worker=job.worker)

    def poll(self, submission_id: str) -> "ADAPTER.Status":
        """Ask Kaggle for one kernel's status and translate it into the
        seam's own five-value vocabulary — never pass Kaggle's own text
        through as `state`. The full raw line goes in `detail` only.
        """
        worker = submission_id.split("/", 1)[0]
        handle = self._credential_for(worker)
        argv = [self._kaggle_executable, "kernels", "status", submission_id]
        result = self._run(argv, env=self._env_for(handle))
        if result.returncode != 0:
            raise KaggleAdapterError(
                f"kernels status for {submission_id} exited {result.returncode}: "
                f"{result.stderr.strip()}"
            )
        raw = result.stdout.strip()
        token = _extract_status_token(raw)
        state = _KAGGLE_STATUS_TO_SEAM.get(token, "unknown")
        return ADAPTER.Status(state=state, detail=raw)

    def fetch(self, submission_id: str, into: Path) -> "ADAPTER.Fetched":
        """Materialize a kernel's output under `into`. A non-zero exit is a
        refusal — this method never reports `complete=False` for a call
        that actually failed; `complete=False` is reserved for a backend
        that positively says "not finished yet", which Kaggle's own
        `kernels output` command does not distinguish from failure, so
        this adapter does not fabricate that distinction either.
        """
        worker = submission_id.split("/", 1)[0]
        handle = self._credential_for(worker)
        into.mkdir(parents=True, exist_ok=True)
        argv = [self._kaggle_executable, "kernels", "output", submission_id, "-p", str(into)]
        result = self._run(argv, env=self._env_for(handle))
        if result.returncode != 0:
            raise KaggleAdapterError(
                f"kernels output for {submission_id} exited {result.returncode}: "
                f"{result.stderr.strip()}"
            )
        files = tuple(sorted(p.name for p in into.iterdir() if p.is_file()))
        return ADAPTER.Fetched(path=into, complete=True, files=files)

    def cancel(self, submission_id: str) -> None:
        """Refuse, explicitly.

        Kaggle's own kernels CLI documents no single-kernel cancel
        operation; this method exists only to satisfy the ABC — the seam
        itself never calls `cancel()` on its own initiative (see
        `remote_cli.py`'s `reconcile` docstring: an `orphanRemote` id is
        reported, never cancelled). Raising here rather than guessing at
        an unofficial command is the same restraint every other refusal in
        this file already applies to a service response it cannot confirm.
        """
        raise KaggleAdapterError(
            f"cannot cancel {submission_id}: this backend's CLI has no "
            "documented single-kernel cancel operation, and this adapter "
            "will not guess at an unofficial one"
        )

    def list_active(self, worker: str) -> list[str]:
        """Refs this worker's account currently reports `queued` or
        `running`, read from `kernels list`'s own CSV output — never a
        table this module parses by column position, so a reordered
        column in a future CLI version fails loudly (`KeyError` from
        `csv.DictReader`) instead of silently reading the wrong field.
        """
        handle = self._credential_for(worker)
        argv = [self._kaggle_executable, "kernels", "list", "--mine", "--csv"]
        result = self._run(argv, env=self._env_for(handle))
        if result.returncode != 0:
            raise KaggleAdapterError(
                f"kernels list --mine for {worker} exited {result.returncode}: "
                f"{result.stderr.strip()}"
            )
        active: list[str] = []
        for row in csv.DictReader(io.StringIO(result.stdout)):
            ref = row.get("ref")
            if not ref:
                continue
            state = _KAGGLE_STATUS_TO_SEAM.get((row.get("status") or "").strip().lower(), "unknown")
            if state in ("queued", "running"):
                active.append(ref)
        return active


ADAPTER.register("kaggle", KaggleAdapter)
