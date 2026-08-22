#!/usr/bin/env python3
"""The Kaggle SDK driver — the ONLY file in this entire skill allowed to
import `kagglesdk`.

`adapters/kaggle.py` shells out to this script as a child process, exactly
the way it used to shell out to the `kaggle` command-line tool. What moved
is the CHILD's identity, not the boundary: `_env_for()` in `kaggle.py` still
builds one child process's whole environment from an allowlist and puts the
stored account's credential value on it there; this file never reads that
variable itself and never constructs one of its own — the only route to
that value is `kagglesdk`'s own `_try_fill_auth()`, reading the child's
environment on its own, inside `_init_session()`, well after this process
starts.

The installed client's own `authenticate()` demands a classic key or a
`kaggle.json` and performs Basic auth before any request is built; the
stored accounts hold 37-character access tokens that answer Basic with 401
for every account, valid or not. `kagglesdk`'s own `_try_fill_auth()`
prefers a Bearer credential sourced from the child's environment over that
Basic fallback — a route Kaggle's own developers document as unfinished
(`kagglesdk/kaggle_http_client.py:14-17`: "This was created from
kaggle_api_client.py, prior to recent changes to auth handling. The new
client requires KAGGLE_API_TOKEN, so it is not currently usable by the
CLI."). Driving that route directly is the entire reason this file exists.

The child-process boundary is preserved deliberately, not incidentally:
`KaggleHttpClient.__init__` takes no credential argument at all, so the
only public way to hand it one is that process-global environment variable
— two concurrent workers sharing one process would race it. One process
per submission is what makes concurrent credentials correct, and it is the
exact same boundary that keeps an argv/env observation point alive for this
skill's own offline proof. See `SKILL.md`'s credential-transport table for
the guarantees this preserves and the ones a second interception point,
mounted on this driver's own `requests` session in its tests, exists to
prove instead (what a submission's outbound request actually contains).

The one client this file ever builds is constructed at exactly one
expression (`_build_client()`, below) — the same idiom
`CredentialSecurityTests` already locks `adapters/kaggle.py` to for
`.token_path`. Every operation function below receives that already-built
client rather than constructing its own; a function that built one anyway
would bypass whatever transport a caller (this file's own test suite
included) mounted on the shared session and attempt a real socket.

Run with the interpreter that has this package installed — measured on
this machine to be the interpreter the CommandLineTools ship,
`sys.executable` in the invoking (adapter) process, since that is the one
process the whole call chain already inherits from. `selftest` is the
first thing a caller should run: it reports whether `kagglesdk` imports
under the exact interpreter running this file, and if it does not, the
refusal names that interpreter and the install command by which it becomes
true, rather than a bare traceback.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from kagglesdk.kaggle_http_client import KaggleHttpClient
    from kagglesdk.kernels.services.kernels_api_service import KernelsApiClient
    from kagglesdk.kernels.types.kernels_api_service import (
        ApiGetKernelSessionStatusRequest,
        ApiSaveKernelRequest,
    )
    import requests  # a `kagglesdk` dependency in its own right; imported
    # after it, so an interpreter missing only this one still reports the
    # accurate cause below rather than a misleading `kagglesdk` complaint.

    _IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # exercised by running this file under an
    # interpreter with no `kaggle` distribution installed — see
    # `test_driver_selftest_imports_kagglesdk`'s failure half.
    requests = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


EXIT_OK = 0
EXIT_UNAUTHORIZED = 3
EXIT_REFUSED = 1

_KERNEL_METADATA_FILENAME = "kernel-metadata.json"

# The metadata keys `adapters/kaggle.py`'s own `assemble_metadata()` writes,
# and later completes with `id`/`code_file`, that map straight onto an
# identically-named `ApiSaveKernelRequest` attribute. `id` and `code_file`
# are handled separately, immediately below, because neither maps straight
# across: `id` on the request is an int the service assigns, while the
# metadata's own `id` carries the STRING `<owner>/<slug>` that belongs on
# `slug` instead; `code_file` names a path, not a request field, and is
# consumed to read the bytes that become `text`.
_METADATA_PASSTHROUGH_KEYS = (
    "language",
    "kernel_type",
    "is_private",
    "enable_gpu",
    "enable_internet",
)


class DriverError(Exception):
    """A refusal this driver raises on its own initiative: an unmapped
    metadata key, a request the service refused, or any other answer this
    file declines to fabricate. Caught once, in `main()`, and reported as
    one JSON object on stdout plus a non-zero exit — never a raw traceback,
    which a caller reading only an exit code and stdout could not act on.
    """


def _build_client() -> "KaggleHttpClient":
    """The one place in this whole file `KaggleHttpClient` is constructed.

    Locked by `test_driver_client_constructed_at_one_locked_expression`,
    parsed as an AST exactly like `CredentialSecurityTests` already locks
    `.token_path` in `adapters/kaggle.py`: a second construction inside an
    operation function would build a session nothing mounted a test
    transport onto, and would reach for a real socket instead of failing
    the lock.
    """
    return KaggleHttpClient()


def _save_kernel_request_from_staging(staging_dir: Path) -> "ApiSaveKernelRequest":
    """Read the staged `kernel-metadata.json` `adapters/kaggle.py` already
    completed with `id` and `code_file`, and map it onto one
    `ApiSaveKernelRequest` — the ONLY place in this driver that builds one.

    The table is CLOSED: every metadata key is either consumed explicitly
    above (`id`, `code_file`) or passed straight through by name
    (`_METADATA_PASSTHROUGH_KEYS`); a key that is neither is a refusal
    naming it, never a silent drop. That closes the `machine_shape` defect
    class structurally — the prior adapter emitted a key nothing on the
    installed client's request shape ever read, so it silently reached
    nobody; a key this table does not recognize now fails loudly here
    instead of travelling to nobody a second time, under a different name.
    """
    metadata_path = staging_dir / _KERNEL_METADATA_FILENAME
    metadata = dict(json.loads(metadata_path.read_text(encoding="utf-8")))

    request = ApiSaveKernelRequest()

    # TRAP, measured rather than assumed: the request's own `id` attribute
    # is typed `int` (the service's numeric kernel id); the metadata's `id`
    # carries the STRING `<owner>/<slug>` `adapters/kaggle.py` builds at
    # submit time. Assigning the metadata's `id` onto the request's `id`
    # raises `TypeError` immediately — assigning it onto `slug` instead is
    # the fix, not a workaround.
    owner_slug = metadata.pop("id", None)
    if owner_slug:
        request.slug = owner_slug

    title = metadata.pop("title", None)
    if title:
        request.new_title = title

    code_file = metadata.pop("code_file", None)
    if code_file:
        request.text = (staging_dir / code_file).read_text(encoding="utf-8")

    for key in _METADATA_PASSTHROUGH_KEYS:
        if key in metadata:
            setattr(request, key, metadata.pop(key))

    if metadata:
        raise DriverError(
            f"{metadata_path} carries key(s) {sorted(metadata)} this driver "
            "has no mapping for onto a save-kernel request; refusing rather "
            "than silently dropping them the way `machine_shape` once "
            "traveled to nobody"
        )

    return request


def cmd_submit(client: "KernelsApiClient", staging_dir: Path) -> dict:
    """Push one staged job folder's kernel, returning the service's own
    receipt fields — never anything this driver invented on its own.
    """
    request = _save_kernel_request_from_staging(staging_dir)
    response = client.save_kernel(request)
    return {
        "ref": response.ref,
        "url": response.url,
        "versionNumber": response.version_number,
    }


def cmd_poll(client: "KernelsApiClient", submission_id: str) -> dict:
    """Ask the service for one kernel session's status, translated no
    further than the enum's own name — `adapters/kaggle.py` is where a raw
    status becomes the seam's own five-value vocabulary, not here.
    """
    worker, slug = submission_id.split("/", 1)
    request = ApiGetKernelSessionStatusRequest()
    request.user_name = worker
    request.kernel_slug = slug
    response = client.get_kernel_session_status(request)
    return {
        "status": response.status.name,
        "failureMessage": response.failure_message,
    }


def cmd_fetch(client: "KernelsApiClient", submission_id: str, into: Path) -> dict:
    """Deliberately unimplemented in this commit.

    `download_kernel_output_zip` needs a `kernel_session_id` no measured
    `poll`/`status` response carries, so fetching file-by-file through
    `list_kernel_session_output`'s own per-file URLs is the design's
    intended shape — but whether those URLs need the session's own
    Bearer credential, or answer to an anonymous GET, is an open question
    only a live rehearsal (run solely on the user's explicit permission)
    can settle. Guessing at that shape now and being wrong would be a
    silent data loss at fetch time; refusing loudly here is the safer
    failure until Phase 3 resolves it.
    """
    raise DriverError(
        "fetch is not implemented by this driver in this commit: whether "
        "list_kernel_session_output's per-file URLs need this session's "
        "own credential is an open question a live rehearsal must settle "
        "first; see the design's open questions"
    )


def _print_result(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def main(argv: list[str]) -> int:
    if _IMPORT_ERROR is not None:
        _print_result(
            {
                "ok": False,
                "error": (
                    f"kagglesdk is not importable under {sys.executable}: "
                    f"{_IMPORT_ERROR}; install it with "
                    f"`{sys.executable} -m pip install --user kaggle==1.7.4.5`"
                ),
            }
        )
        return EXIT_REFUSED

    if not argv:
        _print_result(
            {
                "ok": False,
                "error": "no operation named; expected one of: submit, poll, fetch, selftest",
            }
        )
        return EXIT_REFUSED

    op, rest = argv[0], argv[1:]

    if op == "selftest":
        _print_result({"ok": True, "interpreter": sys.executable})
        return EXIT_OK

    client = KernelsApiClient(_build_client())

    try:
        if op == "submit":
            result = cmd_submit(client, Path(rest[0]))
        elif op == "poll":
            result = cmd_poll(client, rest[0])
        elif op == "fetch":
            result = cmd_fetch(client, rest[0], Path(rest[1]))
        else:
            _print_result({"ok": False, "error": f"unknown operation {op!r}"})
            return EXIT_REFUSED
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        _print_result({"ok": False, "error": str(exc)})
        return EXIT_UNAUTHORIZED if status in (401, 403) else EXIT_REFUSED
    except DriverError as exc:
        _print_result({"ok": False, "error": str(exc)})
        return EXIT_REFUSED
    except Exception as exc:  # a refusal, never a fabricated result
        _print_result({"ok": False, "error": str(exc)})
        return EXIT_REFUSED

    _print_result({"ok": True, **result})
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
