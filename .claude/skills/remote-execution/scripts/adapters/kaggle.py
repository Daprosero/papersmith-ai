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

2. A credential VALUE is read at exactly one expression, here, and
   reaches exactly one child process's own environment. `CredentialHandle`
   below is the only credential type this adapter accepts; it carries a
   path, and `_env_for()` — the single sink in the whole file — reads the
   file that path names and puts its stripped content on
   `KAGGLE_API_TOKEN`.

   This is a TRADE, not a preserved invariant, and the old by-path claim
   is retracted rather than reworded: the installed client's
   `_try_fill_auth()` reads `KAGGLE_API_TOKEN` and hands it straight to
   `BearerAuth(api_token)`, by value, with no path check of any kind, so a
   path in that variable becomes the literal text of an
   `Authorization: Bearer` header and authenticates nothing. The legacy
   `KAGGLE_CONFIG_DIR`/`kaggle.json` shape is not an escape either — it
   routes an access token through a Basic-auth path it was never meant for
   and answers 401 for every account regardless of validity.

   What genuinely holds, and is locked by tests rather than stated here:
   `.token_path` is touched in no module above this one, so no credential
   value has any route into `credentials.py`, `remote_cli.py`, `ledger.py`,
   `packer.py` or `jobfolder.py`; the value is never logged, never
   interpolated into a refusal, and never returned upward; and a file that
   cannot be read, or that holds nothing once stripped, is refused instead
   of sent. See `SKILL.md`'s credential-transport table for the full list
   and the test that proves each row.

Every subprocess call here is `shell=False` with a list argv, an explicit
timeout, and an env built from an allowlist (`PATH` plus, when a credential
is involved, `KAGGLE_API_TOKEN` — nothing else is ever forwarded from this
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
import shutil
import subprocess
import sys
import tempfile
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

# `adapters/kaggle_driver.py`, this module's own sibling — the one file in
# this skill permitted to import the Kaggle SDK package. `submit()`/
# `_push()` shell out to it exactly the way this module used to shell out
# to the `kaggle` command-line tool: same `_run()`/`_env_for()` boundary,
# same `shell=False`/list-argv/allowlisted-env discipline, only the
# child's own identity changed. Overridable at construction
# (`driver_script=`) so a test can substitute a fake stand-in never
# running under a real interpreter that has the SDK installed nor within
# reach of the real service.
DEFAULT_KAGGLE_DRIVER = Path(__file__).resolve().parent / "kaggle_driver.py"

KAGGLE_EXECUTABLE = "kaggle"
SUBPROCESS_TIMEOUT_SECONDS = 120.0

# This service's documented per-worker concurrent-kernel allowance, stated
# here and nowhere else in this skill — NOT a universal constant, and not
# something a second backend's adapter should read off this module. A
# backend metering capacity some other way (a quota, a byte budget) would
# convert it into "concurrent jobs" inside its own adapter, exactly the
# same way this one does.
#
# This is the batch-session figure: how many `kernels push` submissions
# this service has, at the time this was last checked, let one account run
# concurrently. It is an observed property of the service, measured
# against `kernels push`, not a law — it is documented and expected to be
# revised as Kaggle's own concurrent-kernel allowance changes, and it is
# never asserted as a universal per-account or per-service ceiling.
KAGGLE_WORKER_CAPACITY = 2

# The accelerator this repository's submissions request, in the only
# vocabulary the installed client can express: a boolean. It is
# a request, not a receipt: asking for one is not the same as
# receiving one. What a
# submission actually ran on is a fact the service states, at poll or fetch
# time, in `Status.detail`, never assumed from this constant and never
# stamped anywhere by this module on its own initiative.
#
# A NAMED accelerator cannot be requested through this client at all, and
# that is measured rather than assumed: `kernels_push()` in the installed
# `kaggle` 1.7.4.5 builds its save-kernel request field by field and reads
# exactly `enable_gpu` and `enable_tpu` from a kernel's metadata; the string
# `machine_shape` appears nowhere in that package, so a `machine_shape` key
# in `kernel-metadata.json` is not merely ignored by the client — it is
# never transmitted, and no server-side reader could act on it either.
# Which GPU a session receives is therefore the service's choice, reported
# in `Status.detail` like every other fact this module refuses to guess at.
REQUEST_GPU = True

# The filename `kernels push -p <dir>` looks for beside a kernel's
# entrypoint — Kaggle's own convention, not this module's invention. A
# generated job's directory must carry this file before `submit()` will
# push it; see `KaggleAdapter.submit()`'s refusal below.
KERNEL_METADATA_FILENAME = "kernel-metadata.json"

# `jobfolder.py`'s own `RUN_CONFIG_FILENAME` constant, duplicated here
# rather than imported: this module never imports `jobfolder.py` (the
# dependency runs the other way — `jobfolder.py` reaches this module only
# through the opaque `ADAPTER.resolve_metadata()` registry, never a direct
# import), the same reason `KERNEL_METADATA_FILENAME` above is this
# module's own constant rather than a shared one. RE-VERIFIED against the
# installed `kaggle` 1.7.4.5, the version claim here having named one that
# was never installed on this machine: `kernels_push()` reads `code_file`,
# sends its bytes as the request's `text`, and has no directory upload at
# all, so no sibling file in the pushed directory ever reaches the worker
# on its own. A generated job's `run-config.json` is real and versioned
# beside its `runner.ipynb`, but the worker never sees it unless something
# puts it there; see `_run_config_cell()` below.
RUN_CONFIG_FILENAME = "run-config.json"

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


def _normalize_status_word(token: str) -> str:
    """Strip an enum class prefix, when the CLI quoted one, from an
    already-lowercased status token.

    RE-VERIFIED against the installed `kaggle` 1.7.4.5, in its source
    rather than from memory of a live run: `kernels_status_cli()` prints
    `'%s has status "%s"' % (kernel, status)` where `status` is a
    `KernelWorkerStatus` enum member, so the quoted text is the enum's own
    `str()` repr — `KernelWorkerStatus.RUNNING` — and not the bare word
    `"running"` earlier versions apparently used; the version claim here
    named one that was never installed on this machine. The bare word is
    always the part after the last `.` on every form observed; a genuine
    bare status word never contains one itself, so this is a no-op for
    that case.
    """
    return token.rsplit(".", 1)[-1] if "." in token else token


def _extract_status_token(raw: str) -> str:
    """Pull a status word out of the CLI's own sentence, when it quotes
    one (`... has status "complete"`, or the installed client's own
    `... has status "KernelWorkerStatus.RUNNING"`); fall back to the
    whole trimmed, lowercased line otherwise. Either way this returns a
    CANDIDATE token for `_KAGGLE_STATUS_TO_SEAM` to translate — never a
    value handed upward as `Status.state` directly.
    """
    match = _QUOTED_STATUS.search(raw)
    token = match.group(1) if match else raw
    return _normalize_status_word(token.strip().lower())


def _slugify(text: str) -> str:
    """A deterministic slug from raw text — never a lookup, never state
    kept anywhere in this process. Kaggle kernel refs are
    `<username>/<slug>`; this supplies the second half.
    """
    lowered = text.lower()
    slug = _SLUG_DISALLOWED.sub("-", lowered).strip("-")
    return slug or "kernel"


def _kernel_slug(entrypoint: Path) -> str:
    """A deterministic slug derived from an entrypoint's own filename —
    the legacy shape's own source of one: `<Name>/Notebooks/<Something>.ipynb`
    names exactly one notebook per file, so the filename is what actually
    tells two legacy submissions apart. NEVER the right source for a
    generated job folder, whose entrypoint is `runner.ipynb` for every
    job — see `submit()`'s own docstring for why that distinction matters.
    """
    return _slugify(entrypoint.stem)


def assemble_metadata(run_config: Mapping[str, object]) -> tuple[str, str]:
    """Build the `kernel-metadata.json` a generated job folder ships beside
    its runner notebook, so `kernels push -p <dir>` both accepts the push
    and requests the pinned accelerator.

    Registered under `ADAPTER.register_metadata("kaggle", ...)` below —
    the ONE thing a caller above the adapter registry ever gets back is an
    opaque `(filename, text)` pair; nothing above this module ever learns
    what either one means, only that they exist and where to write them.

    The field set below is read off `kernels_push()` and `kernels_initialize()`
    in the installed `kaggle` 1.7.4.5 (`kaggle/api/kaggle_api_extended.py`)
    — the client's own template and its own validation of that file:

    - `enable_gpu` — the key `kernels_push()` genuinely reads
      (`request.enable_gpu = self.get_bool(meta_data, 'enable_gpu', False)`),
      and the one the client's own `kernels init` template writes. This
      adapter used to send `machine_shape: "NvidiaTeslaT4"` instead, on a
      docstring's claim that `enable_gpu`/`enable_tpu` were "documented
      DEPRECATED in favor of it". `machine_shape` occurs nowhere in the
      installed client or its SDK, and the request is assembled field by
      field, so that key never reached the service at all: every push this
      skill has ever made silently ran on CPU. It is not carried alongside
      `enable_gpu` here either — a key nothing transmits is a claim nothing
      can verify, which is exactly the shape of the defect this replaced.

      This is where the honesty about scope belongs: emitting the key the
      client reads is a request, and a request is not a receipt. No offline
      test can prove a submission actually received a GPU. The receipt
      arrives with the first real run, in `Status.detail` — which is what
      that field is for.
    - `enable_internet` — `True`. The generated runner does `git init` /
      `remote add` / `fetch` inside the kernel to reach the pinned commit,
      and Kaggle kernels have internet access disabled by default; without
      this the clone fails at runtime, after the push already succeeded.
    - `language`/`kernel_type` — `"python"`/`"notebook"`: the runner this
      skill generates is always a `.ipynb` file of Python cells.
    - `is_private` — `True`, a deliberate default this brief left
      unspecified: nothing about a submitted training run should default
      to public.
    - `id` and `code_file` — present, but deliberately BLANK. `id` is
      `<owner>/<kernel-slug>`; it names the account, and no worker is
      assigned yet at `generate-job` time — the packer only assigns one at
      submit time, and the very same job folder pushed to five accounts
      needs five different `id` values. `code_file` names the entrypoint
      file relative to this folder, which this function has no path to
      either (`run_config` carries no notebook path). Both are completed
      by `KaggleAdapter.submit()` below, in a STAGED COPY of the job
      folder — never by mutating this versioned file in place.
    - `title` — derived from `run_config`'s own `jobName`, when present,
      so the pushed kernel is identifiable; padded to satisfy the client's
      own five-character minimum.

    `run_config` is read only for `jobName`, with a fallback when absent
    — this function must not crash on a caller (this module's own test
    suite included) that hands it a partial mapping.
    """
    job_name = str(run_config.get("jobName") or "job")
    title = f"papersmith-{job_name}"
    payload = {
        "id": "",
        "title": title,
        "code_file": "",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_internet": True,
        "enable_gpu": REQUEST_GPU,
    }
    return KERNEL_METADATA_FILENAME, json.dumps(payload)


def _run_config_cell_source(run_config_text: str) -> str:
    """The injected cell's own source: writes `run_config_text` — the job
    folder's own `run-config.json` content, staged by the caller either
    verbatim or merged with `job.run_config`'s submission-time overrides
    (see `submit()`'s own docstring for that merge rule) — to
    `run-config.json` in whatever directory the kernel is executing in.
    This function itself is agnostic to which of the two `run_config_text`
    is: it only ever writes the string it is handed.

    `Path("run-config.json")`, relative, deliberately not an absolute
    `/kaggle/working/...` guess: `runner_bootstrap.py`'s own
    `load_run_config()` resolves `Path.cwd() / "run-config.json"` when no
    `base_dir` is given, which is exactly how the real notebook cell runs
    it (`if __name__ == "__main__": bootstrap()`). This injected cell runs
    in the SAME kernel process, immediately before that one, so writing
    relative to whatever `Path.cwd()` already is at that point lands in
    the exact place the next cell will look — no assumption about
    Kaggle's own working directory convention needed, and none made.

    `repr(run_config_text)` is what keeps this safe for arbitrary JSON
    content (quotes, newlines, unicode) as a single Python string literal,
    without needing to guess at a quoting scheme of its own.
    """
    return (
        "from pathlib import Path\n\n"
        f"Path('run-config.json').write_text({run_config_text!r}, encoding='utf-8')\n"
    )


def _run_config_notebook_cell(run_config_text: str) -> dict:
    """One notebook cell, in the exact shape `jobfolder.py`'s own
    `_notebook_cell()` uses (`cell_type`/`metadata`/`execution_count`/
    `outputs`/`source`) — duplicated rather than imported, for the same
    reason `RUN_CONFIG_FILENAME` above is duplicated: this module does not
    import `jobfolder.py`. This is CONFIGURATION, not runner logic: unlike
    the two real cells `build_notebook()` copies byte for byte with zero
    interpolation, this cell's own source is job-specific by construction
    — it always was going to differ between two jobs, because the file it
    materializes differs between them. It is a NEW cell prepended ahead of
    the other two, never an edit to either of their bytes.
    """
    source = _run_config_cell_source(run_config_text)
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def _stage_run_config_cell(notebook_path: Path, run_config_text: str) -> None:
    """Prepend the injected cell to the notebook at `notebook_path` — a
    file inside the STAGED copy `submit()` builds, never the job folder's
    own versioned `runner.ipynb`. Reads and rewrites only that staged
    file; the two existing cells travel through unread and unmodified,
    since this only ever inserts at index 0.
    """
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    notebook["cells"].insert(0, _run_config_notebook_cell(run_config_text))
    notebook_path.write_text(json.dumps(notebook, indent=1), encoding="utf-8")


# The seam's own shape (`adapter.py`), aliased under this module's name so
# every existing caller and test that imports `CredentialHandle` FROM here
# keeps working unchanged. The class is defined exactly once, in the seam,
# because it carries no service-specific behavior at all — moving it there
# is what lets a second backend adapter reuse the same shape without
# redefining it; only the environment variable it is eventually handed to
# (`KAGGLE_API_TOKEN`, below) is this service's own.
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
        driver_script: Path | str | None = None,
    ) -> None:
        self._credential_provider = self._normalize_credentials(credentials)
        self._accounts_cli = Path(accounts_cli) if accounts_cli else DEFAULT_ACCOUNTS_CLI
        self._kaggle_executable = kaggle_executable
        self._timeout = timeout
        self._driver_script = Path(driver_script) if driver_script else DEFAULT_KAGGLE_DRIVER

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

        `KAGGLE_API_TOKEN` carries the token's VALUE, and this is the one
        expression in this skill that ever reads one. Measured, not
        assumed: the installed client's own `_try_fill_auth()` reads that
        variable and hands it straight to `BearerAuth(api_token)` — by
        value, with no path check of any kind — so a path here becomes
        the literal text of an `Authorization: Bearer` header and
        authenticates nothing. The legacy `KAGGLE_CONFIG_DIR`/`kaggle.json`
        shape is not an escape from that: it routes an access token
        through a Basic-auth path it was never meant for and answers 401
        for every account regardless of validity.

        So the by-path-only contract this adapter used to hold is SPENT,
        not preserved, and saying so is the point: what still holds is
        narrower and structural. The read happens here, in the one file
        allowed to name a service, in a single expression whose result goes
        straight onto one child process's environment; no module above this
        one touches `token_path` at all, and the value is never logged,
        never interpolated into a message, and never returned upward.

        `.strip()` is load-bearing: the credential file ends with the
        newline `materialize` writes, and a newline inside a bearer header
        is a malformed header rather than a credential. A file that cannot
        be read, or that holds nothing once stripped, is refused here —
        the same fail-closed discipline every other unusable answer in this
        module gets, rather than a request sent with a header the service
        can only answer 401 to.
        """
        env = {"PATH": os.environ.get("PATH", "")}
        if handle is not None:
            try:
                env["KAGGLE_API_TOKEN"] = handle.token_path.read_text(
                    encoding="utf-8"
                ).strip()
            except OSError as exc:
                raise KaggleAdapterError(
                    f"could not read the credential file for worker "
                    f"{handle.worker_id!r}: {exc}"
                ) from exc
            if not env["KAGGLE_API_TOKEN"]:
                raise KaggleAdapterError(
                    f"the credential file for worker {handle.worker_id!r} holds "
                    "nothing once stripped; materialize that worker's credential "
                    "again rather than sending an empty bearer header"
                )
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
            # Naming what failed is not naming what to do. On a machine where
            # the service CLI was never installed this is the whole question,
            # and the skill's own `## Environment` section is where a reader
            # would look — so the sentence lives here, in the one file this
            # skill lets name a service, rather than in a seam that must not.
            remedy = ""
            if argv and argv[0] == self._kaggle_executable:
                remedy = (
                    f" — this adapter shells out to the {argv[0]!r} command line, "
                    "which arrives with `pip install kaggle`; install it and make "
                    "sure the directory pip reports putting it in is on PATH"
                )
            elif len(argv) > 1 and argv[0] == sys.executable and argv[1] == str(
                self._driver_script
            ):
                # The SDK driver's own remedy, distinct from the CLI's: a
                # missing `kaggle_driver.py` (moved or deleted) is not the
                # same failure as a missing SDK import (that one is the
                # driver's own `selftest` refusal, printed as JSON on its
                # stdout, never an `OSError` this branch would ever see)
                # — this is "the interpreter could not even launch the
                # script", so the remedy names the interpreter and the
                # SDK-path install command for it, never the retired
                # `pip install kaggle` sentence a CLI-shaped failure used
                # to get.
                remedy = (
                    f" — this adapter shells out to the SDK driver at "
                    f"{argv[1]!r} under {sys.executable!r}; install the SDK "
                    f"for that interpreter with `{sys.executable} -m pip "
                    "install --user kaggle==1.7.4.5`"
                )
            raise KaggleAdapterError(
                f"could not run {argv[0]}: {exc}{remedy}") from exc

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
        """Push a kernel version and report back the ref this adapter will
        recognize it by later.

        The submission id is `<worker>/<slug>`, never read out of anything
        the `kaggle` process printed. `poll()`, `fetch()` and
        `list_active()` all recover `worker` from this same id, by
        splitting on the one `/` this construction guarantees is there.

        The slug itself has two different sources depending on shape, and
        conflating them was a real bug this docstring now exists to
        prevent reintroducing: for a GENERATED job folder (metadata file
        present), the slug is derived from the metadata's own `title` —
        confirmed against a real Kaggle account that a newly-created
        kernel's actual slug is the one the service derives from `title`,
        not from the `id` field this method sends it. That one is a LIVE
        observation and was not re-verified against the installed client,
        because it cannot be: the client only warns when `id`'s slug and
        `slugify(title)` disagree, and what the service does with the two
        is not visible in its source. It is recorded here as observed, not
        as read. `job.entrypoint`'s
        own filename is `runner.ipynb` for every generated job
        (`jobfolder.py`'s `RUNNER_FILENAME` constant), so deriving the
        slug from it instead — as this method used to — made every
        job-folder submission to the same worker collide on the identical
        ref `<worker>/runner`, silently overwriting one job's kernel with
        the next one pushed. For the LEGACY shape (no metadata file), the
        entrypoint genuinely does name one notebook per file, so its own
        filename remains the right source there.

        A non-empty `job.run_config` marks a generated job — one whose
        directory `jobfolder.py` was supposed to have written
        `assemble_metadata()`'s output into. This method refuses, before
        ever calling `kernels push`, when that metadata file is absent:
        pushing a folder the service will reject on its own is worse than
        refusing here. An empty `run_config` is the legacy shape and is
        never checked — it behaves exactly as it did before this refusal
        existed.

        The metadata file's own PRESENCE, not `job.run_config`, is what
        decides whether this method completes and stages it: `cmd_submit`
        only ever sets `run_config["mode"] = "smoke"` for a smoke run, so
        an ordinary (non-smoke) job-folder submission carries an EMPTY
        `run_config` exactly like the legacy shape does. `id` names an
        account, which is only known here at submit time — the same
        versioned job folder pushed to five different workers needs five
        different `id` values, and a static file written once at
        `generate-job` time cannot hold that. So when the metadata file is
        present, this method reads the template `assemble_metadata()`
        wrote, fills in `id` (`<worker>/<slug>`) and `code_file`
        (`job.entrypoint`'s own basename — known here, never guessed at by
        `assemble_metadata()`, which has no path to it), and writes the
        completed file into a STAGED COPY of the job folder in a temp
        directory — `kernels push -p <staged dir>` runs against that copy.
        The versioned `kernel-metadata.json` inside the job folder itself
        is read, never opened for writing, and stays byte-for-byte
        unchanged: nothing here mutates a committed artifact per worker.

        `kernels push` uploads `code_file` alone — re-verified by reading
        `kernels_push()` in the installed `kaggle` 1.7.4.5, there is no
        directory upload, so a job folder's own sibling `run-config.json`
        never reaches the worker on its own. This same staging step also
        prepends a cell to the STAGED notebook copy that materializes that
        file back onto disk before the runner's own first cell ever reads
        it (`_stage_run_config_cell()`), whenever `run-config.json` is
        present beside the entrypoint — it always is for a real generated
        job, written by `jobfolder.generate_job()` before the metadata
        file. Its absence (a synthetic job folder carrying only a
        metadata file, as several of this module's own narrower tests
        build) is not treated as an error here: there is nothing to
        materialize, so nothing is injected — a silent no-op rather than
        a refusal, since it changes nothing the caller asked for.

        The staged bytes are the FILE's own content merged with
        `job.run_config`, never the file verbatim on its own. The file was
        made authoritative by a prior fix (`kernels push` uploads only
        `code_file`, so the versioned `run-config.json` had to be injected
        as a cell), and that same stroke silently orphaned every
        submission-time mutation of `job.run_config` — `submit --smoke`
        sets `run_config["mode"] = "smoke"` on the in-memory `Job`, but
        `select_block()` in the pushed kernel only ever saw the file's own
        `mode`-less content, so a `--smoke` submission always ran the
        normal `run` block. The merge rule: when `job.run_config` is
        empty — the legacy shape, and also the ordinary (non-smoke)
        job-folder shape `cmd_submit` produces — the file's own bytes are
        read and staged completely unread otherwise, exactly as before
        this fix; no `json.loads`/`json.dumps` round-trip ever touches
        them, so this path stays byte-identical to today's behavior by
        construction, not by coincidence of formatting. Only when
        `job.run_config` is non-empty is the file parsed, shallow-updated
        at the TOP LEVEL with `dict(job.run_config)` (so `job.run_config`
        wins on a key collision), and re-serialized. Shallow/top-level is
        the deliberate choice, not an oversight: every override this seam
        has ever needed to express — `mode` — is itself a top-level key,
        and `job.run_config` is normalized to an opaque, flat mapping by
        `adapter.py`'s own `Job.__post_init__`; nothing upstream of this
        adapter ever constructs a nested override. This rule does NOT
        cover replacing a single nested field (say, one key inside the
        file's own `run.smoke` block) without clobbering the rest of that
        block — a caller needing that would have to pass the whole nested
        value, since a top-level key present in `job.run_config` replaces
        the file's value for that key entirely rather than merging into
        it.

        Both branches now stage into the SAME temporary copy and always
        complete a `kernel-metadata.json` there, even for the LEGACY
        shape: `_push()` shells out to `kaggle_driver.py` unconditionally
        now, and that driver's own request-mapping step
        (`_save_kernel_request_from_staging`) always reads one from the
        staging directory — Decision 4's table has nothing else to build
        an `ApiSaveKernelRequest` from. A legacy job folder that genuinely
        carries none gets a minimal template synthesized here, in the
        staged copy only; the job folder itself still never needs to
        carry one, exactly as before.
        """
        metadata_path = job.entrypoint.parent / KERNEL_METADATA_FILENAME
        if job.run_config and not metadata_path.is_file():
            raise KaggleAdapterError(
                f"{job.entrypoint} carries a non-empty run_config but "
                f"{metadata_path} is absent: refusing to push a kernel "
                "the service would reject for missing metadata"
            )

        handle = self._credential_for(job.worker)

        with tempfile.TemporaryDirectory(prefix="kaggle-push-") as staging_dir:
            staging_path = Path(staging_dir)
            shutil.copytree(job.entrypoint.parent, staging_path, dirs_exist_ok=True)

            if metadata_path.is_file():
                template = json.loads(metadata_path.read_text(encoding="utf-8"))
            else:
                # LEGACY shape, synthesized rather than read: the same
                # minimal template `assemble_metadata()` would have
                # written, built here in the staged copy only — never
                # written back to the job folder itself.
                template = {
                    "language": "python",
                    "kernel_type": "notebook",
                    "is_private": True,
                    "enable_internet": True,
                    "enable_gpu": REQUEST_GPU,
                }

            title = template.get("title")
            slug = _slugify(title) if title else _kernel_slug(job.entrypoint)
            ref = f"{job.worker}/{slug}"
            template["id"] = ref
            template["code_file"] = job.entrypoint.name
            (staging_path / KERNEL_METADATA_FILENAME).write_text(
                json.dumps(template), encoding="utf-8"
            )

            run_config_path = job.entrypoint.parent / RUN_CONFIG_FILENAME
            if run_config_path.is_file():
                run_config_text = run_config_path.read_text(encoding="utf-8")
                if job.run_config:
                    merged = json.loads(run_config_text)
                    merged.update(dict(job.run_config))
                    run_config_text = json.dumps(merged)
                _stage_run_config_cell(
                    staging_path / job.entrypoint.name,
                    run_config_text,
                )

            self._push(staging_path, handle)

        return ADAPTER.Submission(id=ref, worker=job.worker)

    def _push(self, push_dir: Path, handle: CredentialHandle) -> dict:
        """Invoke `kaggle_driver.py submit <push_dir>` as a child process —
        `kernels push -p <push_dir>` retargeted onto the SDK driver, the
        one composition point `submit()`'s staging step funnels through so
        nothing here can drift from the caller's own error handling.

        Argv carries only a path (`push_dir`; small, credential-free); the
        credential still crosses only through `env`, unchanged. `push_dir`
        is `sys.argv[2]` from the driver's own perspective (`argv[0]` is
        this script's own path, `argv[1]` is `"submit"`) — see
        `kaggle_driver.py`'s `main()`.
        """
        argv = [sys.executable, str(self._driver_script), "submit", str(push_dir)]
        result = self._run(argv, env=self._env_for(handle))
        return self._parse_driver_result(result, action=f"submit for {push_dir}")

    @staticmethod
    def _parse_driver_result(
        result: subprocess.CompletedProcess, *, action: str
    ) -> dict:
        """Read the one JSON object `kaggle_driver.py` always prints on
        stdout, and decide whether to raise from its own `ok` field —
        never from the exit code alone, since the driver's own contract
        is to print a typed refusal object rather than a bare non-zero
        exit whenever it can (`main()`'s own `except` clauses all do
        this).
        """
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise KaggleAdapterError(
                f"{action} did not print JSON: {exc}; stderr: "
                f"{result.stderr.strip()}"
            ) from exc
        if result.returncode != 0 or not payload.get("ok", False):
            raise KaggleAdapterError(
                f"{action} refused: {payload.get('error', result.stderr.strip())}"
            )
        return payload

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
            token = _normalize_status_word((row.get("status") or "").strip().lower())
            state = _KAGGLE_STATUS_TO_SEAM.get(token, "unknown")
            if state in ("queued", "running"):
                active.append(ref)
        return active


ADAPTER.register("kaggle", KaggleAdapter)
ADAPTER.register_metadata("kaggle", assemble_metadata)
