#!/usr/bin/env python3
"""The CLI front door for forge-owned remote execution.

This module is the top of this skill's own dependency chain —
`remote_cli -> packer -> ledger -> adapter` — and it is deliberately the
ONLY module in that chain that names a command-line entry point, parses
`--target`/`--entrypoint`/`--worker` arguments, and decides what counts as
a submittable path in this forge's own repository layout. Everything below
it (`packer.py`, `ledger.py`, `adapter.py`) stays blind to both concerns:
they take paths, ids and dicts as arguments and never ask where an argument
came from or what kind of file it names.

`submit`, `status`, `poll`, `fetch` and `reconcile` are the five commands.
`status` reports the fold and calls no adapter at all — it never resolves
anything, only renders what the ledger already says. `poll` and `fetch`
call the adapter; `fetch` is the only command that ever writes an artifact
to disk, and it does so through a materialize-then-rename sequence so a
crash never leaves a false `returned` event behind (see `cmd_fetch`).
`reconcile` compares the ledger against `adapter.list_active()` in both
directions and reports the difference; it never auto-adopts a remote orphan
and never auto-resolves a local one — `--resolve` is the one human-invoked
exception, and even then it only ever appends `errored`, never `returned`
or `submitted`.

`submit`, `poll`, `fetch` and `reconcile` construct their adapter with a
credential PROVIDER, never a value and never a pre-built mapping this
module would have to assemble itself: `credentials.provider()` returns a
callable an adapter calls lazily, by worker id, the first time it actually
needs one. `--credential-dir` is an override only, for tests and
already-materialized credentials — the default is lazy materialization,
and no target configuration file is ever consulted for a credential path.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Sequence


def _load_sibling(module_name: str, filename: str):
    """Path-import a sibling module from this same directory, reusing an
    already-loaded copy under `module_name` when one exists.

    Same technique and same correctness reason as `packer.py`'s own
    `_load_sibling`: this skill's scripts are not a package, so a
    cross-module dependency goes by file path, and checking `sys.modules`
    first is what keeps `isinstance` checks against `ADAPTER.Adapter`
    working when this module and `packer.py` both load `adapter.py` — a
    second, separately exec'd copy would define a second, distinct
    `Adapter` class with the same name.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]
    script = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


LEDGER = _load_sibling("remote_execution_ledger", "ledger.py")
ADAPTER = _load_sibling("remote_execution_adapter", "adapter.py")
PACKER = _load_sibling("remote_execution_packer", "packer.py")

# Loaded AFTER adapter.py above, for the same sys.modules-reuse reason
# documented next to PACKER's own load above: `credentials.py`'s own
# `ADAPTER.CredentialHandle` has to be the exact same class every other
# module in this chain already loaded, not a second, separately exec'd
# copy of the same name.
CREDENTIALS = _load_sibling("remote_execution_credentials", "credentials.py")

# Loaded the same way, for the same reason: `jobfolder.py`'s own `ADAPTER`
# (it calls `ADAPTER.resolve_metadata()`) has to be this exact module
# object too.
JOBFOLDER = _load_sibling("remote_execution_jobfolder", "jobfolder.py")

# `smoke record`'s verdict comes from the SAME predicate T10's `merge()`
# uses — never a second, independently written completeness check here.
SHARD_IO = _load_sibling("remote_execution_shard_io", "shard_io.py")


def _load_source_digest() -> Callable[[Path, str], str]:
    """Path-import `source_digest()` from proposal-implementation's digest kit.

    A `submitted` event's `sourceDigest` has to be the SAME hash
    proposal-implementation's own admissibility and verify machinery already
    treats as canonical for a given source tree — a second, independently
    written hash here would be safe only until the day the two quietly
    drifted apart, at which point every submission this CLI records would
    carry a digest nothing else in the repository recognizes as current.

    `assets/kit/nb/report_digest.py` is the file this reaches for, not
    `implementation_cli.py`: it is the lightweight, stdlib-only half of the
    pair proposal-implementation's own test suite already holds to
    byte-for-byte parity with the CLI's copy (`ReportDigestJoinTests` in
    `tests/test_proposal_implementation.py`), and loading it costs nothing
    but `hashlib` and `pathlib` — not the whole argparse-driven
    proposal-implementation CLI, which this module never touches. This IS a
    dependency reaching outside this skill's own
    `remote_cli -> packer -> ledger -> adapter` chain, and this function is
    the one place in the whole skill that reaches for it — `fold()`'s own
    docstring (`ledger.py`) already anticipates exactly this: it says the
    real `source_digest()` "lives in proposal-implementation's own module"
    and must be supplied by a caller that already knows how to compute one.
    This function is that caller, called only when `submit` actually needs
    a digest, never at import time.
    """
    module_name = "remote_execution_source_digest_kit"
    if module_name in sys.modules:
        return sys.modules[module_name].source_digest
    script = (
        Path(__file__).resolve().parents[2]
        / "proposal-implementation"
        / "assets"
        / "kit"
        / "nb"
        / "report_digest.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise RemoteCLIError(
            f"the source-digest kit is not where this expects it: {script}. "
            "If it moved, this loader is the one place that has to follow it."
        )
    module = importlib.util.module_from_spec(spec)
    # Registered only once it has actually run. Publishing the module before
    # executing it is the usual shape, and it is wrong here: a failed exec
    # would leave an empty module under this name, and every later call would
    # take the cache branch above and raise AttributeError on a module that
    # never loaded — reporting a missing attribute instead of the real fault,
    # for the rest of the process. Registering after means a failure is
    # retryable and always reports itself.
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module.source_digest


class RemoteCLIError(Exception):
    """Something this CLI's own validation refused before doing any work."""


class PathGuardError(RemoteCLIError):
    """An entrypoint failed this forge's own file-kind policy for what may run remotely."""


class ConsentError(RemoteCLIError):
    """ANY `submit` refused for lack of, or a mismatch in, the consent
    token this invocation needs -- campaign, single send, and rehearsal
    alike (Finding 3; Decisions 4, 5; and this phase's own correction: the
    original gate fired only for campaign mode, which let a plain `submit`
    or `submit --smoke` reach `adapter.submit()` with nobody having been
    asked -- the exact launch the user's complaint named).

    Raised BEFORE `packer.select()`/`packer.plan()`/`packer.distribute()`
    runs -- no adapter health read, no plan, no quota spent, no ledger
    line appended -- for exactly the same "refuse while refusing still
    costs nothing" reason `_gate_job_folder_pin()` already refuses ahead
    of it.
    """


NOTEBOOKS_DIRNAME = "Notebooks"
NOTEBOOK_SUFFIX = ".ipynb"
LEDGER_DIRNAME = ".remote-execution"
LEDGER_FILENAME = "ledger.jsonl"
QUARANTINE_DIRNAME = "quarantine"
PARTIAL_SUFFIX = ".partial"
TOOLS_DIRNAME = "tools"
RUN_CONFIG_FILENAME = "run-config.json"

# `smoke.jsonl` — a DISTINCT file from `ledger.jsonl`, beside it in the
# same product's `.remote-execution/` directory, appended through the
# same `LEDGER.append()`. A fourth `kind` inside `ledger.jsonl` was
# rejected: `fold()` indexes `latest[entrypoint]`, so a smoke submission
# recorded there would silently reclassify a real run as superseded.
# `fold()` never reads this file, so that is structurally impossible. See
# `SKILL.md`'s "Smoke" section for the full rationale.
SMOKE_LEDGER_FILENAME = "smoke.jsonl"

# The `kind` a `smoke record` verdict carries inside `smoke.jsonl` (which
# also carries the ordinary `submitted` events a smoke SUBMISSION writes —
# see `cmd_submit`). Never folded, so free of the fourth-kind constraint.
SMOKE_RESULT_KIND = "smokeResult"


def _subcommand_option_strings(command: str) -> frozenset[str]:
    """The exact `--flag` strings `_build_parser()` declares for `command`'s
    own subparser — read from the parser itself, never a second,
    hand-maintained list a refusal message could drift from the CLI it
    describes (Finding 4 case C; Decision 13c).

    Built fresh from `_build_parser()` rather than cached: this only runs
    on `product_for()`'s own refusal path, never on a resolved call, so
    the cost of rebuilding the whole parser is paid at most once per
    refusal, never on the path that matters for speed.
    """
    parser = _build_parser()
    subparsers_action = next(
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    subparser = subparsers_action.choices[command]
    return frozenset(subparser._option_string_actions)


def product_for(
    target: Path,
    entrypoint: str | Path,
    explicit: str | None = None,
    *,
    command: str | None = None,
) -> str:
    """Resolve which product's ledger `entrypoint` belongs to — explicitly,
    never guessed. Replaces `name_for()`, reusing its same resolve-first
    discipline (resolve first, then read path components past `target`) so
    `status`, `fetch`'s quarantine path, and `reconcile`'s ledger selection
    keep calling the SAME derivation rather than each growing its own copy
    that could quietly disagree.

    `command` names the CALLING subcommand (`"submit"`, `"status"`,
    `"distribute"`, `"fetch"`, `"reconcile"`) and affects nothing but the
    wording of the refusal at the bottom of this function (Finding 4 case
    C). Only `submit` (and `generate-job`, which never calls this
    function) declares a `--product` override; `status`, `distribute`,
    `fetch` and `reconcile` do not. All five used to reach the SAME
    hand-written "no explicit --product" refusal regardless of which
    subcommand asked, which sent a `status` caller looking for a flag
    `status`'s own parser never accepts — a remedy that cannot be
    performed is worse than a refusal that names nothing, because it
    costs the caller the attempt. The remedy is now derived from
    `_build_parser()`'s own declared flags for `command`, never
    hand-written prose: `--product` is named only when `command`'s own
    subparser actually declares it. Omitted (`None`), the refusal never
    names `--product` either — the same conservative choice as a
    subcommand confirmed not to declare it, since an unknown caller's
    flags cannot be confirmed at all.

    Four steps, in this fixed order, mirroring the fold's own treatment of
    an unrecognized event `kind`: an ambiguous input is refused, not
    silently mapped to the least-wrong guess.

    1. `explicit` — a caller-supplied `--product` — wins outright, over
       both steps below, whatever the entrypoint's own shape says.
    2. Else, for the job-folder shape (`<target>/tools/<service>/
       <job-name>/*.ipynb`), the `product` field declared in that job's own
       `run-config.json`, read beside the entrypoint. Absent, unreadable,
       or missing that field falls through to step 3 rather than refusing
       immediately — a job-folder path is only refused once every earlier
       step has genuinely found nothing.
    3. Else, for the legacy shape (`<target>/<Name>/Notebooks/**.ipynb`),
       `<Name>` — the first path component past `target` — exactly as
       `name_for()` always derived it.
    4. Else: refused. `TOOLS_DIRNAME` ("tools") is a forge-layout constant,
       not a product, and this function never derives it as one — a
       job-folder path with no declared product is refused here rather
       than falling back to `parts[0]` the way the legacy shape does.

    Whatever step resolves a product, the result is validated the same way
    regardless of source: it must name an existing directory directly
    under `target`, and it must not be `TOOLS_DIRNAME` itself — an explicit
    `--product tools` or a `run-config.json` misdeclaring `"product":
    "tools"` is refused exactly like an unresolved one, because `tools` is
    forge layout, never a product this skill's ledger can shard by.

    This forge's real target has hosted more than one product at once;
    nothing in this skill is allowed to assume which one a caller means —
    a product is always read off a path, a flag, or a job's own recorded
    config, never typed in as a bare string by this function itself.
    """
    resolved = Path(entrypoint).resolve()
    try:
        relative = resolved.relative_to(target)
    except ValueError:
        raise RemoteCLIError(
            f"cannot resolve a product: {resolved} does not stay under "
            f"target {target} at all"
        ) from None
    if not relative.parts:
        raise RemoteCLIError(
            f"cannot resolve a product: {resolved} equals target {target} "
            "itself"
        )

    parts = relative.parts
    product = explicit

    if product is None and len(parts) == 4 and parts[0] == TOOLS_DIRNAME:
        run_config_path = resolved.parent / RUN_CONFIG_FILENAME
        if run_config_path.is_file():
            try:
                run_config = json.loads(
                    run_config_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                run_config = None
            declared = (
                run_config.get("product")
                if isinstance(run_config, dict)
                else None
            )
            if isinstance(declared, str) and declared:
                product = declared

    if product is None and len(parts) >= 3 and parts[1] == NOTEBOOKS_DIRNAME:
        product = parts[0]

    if product is None:
        can_override = (
            command is not None and "--product" in _subcommand_option_strings(command)
        )
        if can_override:
            # Only a subcommand whose OWN parser actually declares
            # `--product` (confirmed via `_subcommand_option_strings()`,
            # never assumed) gets a message naming it as a remedy.
            reason = (
                "no explicit --product, no product declared in its "
                "run-config.json, and the legacy <Name>/Notebooks/ shape "
                "does not apply"
            )
        else:
            # `command` names a subcommand that does not declare
            # `--product` (e.g. `status`), or `command` is unknown
            # (`None`) and therefore cannot be confirmed to declare it
            # either way. Either way, the message never names a flag the
            # caller cannot actually type: a remedy that cannot be
            # performed is worse than a refusal that names nothing.
            reason = (
                "no product declared in its run-config.json, and the "
                "legacy <Name>/Notebooks/ shape does not apply"
            )
        raise RemoteCLIError(f"cannot resolve a product for {resolved}: {reason}")

    if product == TOOLS_DIRNAME:
        raise RemoteCLIError(
            f"refusing product {product!r}: {TOOLS_DIRNAME!r} is a "
            "forge-layout constant, never a product"
        )

    product_dir = target / product
    if not product_dir.is_dir():
        raise RemoteCLIError(
            f"refusing product {product!r}: {product_dir} is not an "
            "existing directory"
        )

    return product


def _job_folder_staleness(resolved_entrypoint: Path) -> dict | None:
    """Route `resolved_entrypoint` through `jobfolder.read()` — the single
    staleness reader design #744 §4 mandates — whenever it sits beside a
    `run-config.json`, i.e. the job-folder shape. Every command that
    touches an already-generated job folder (`submit`, `status`, `fetch`,
    `reconcile`) calls this so staleness is reported alongside whatever
    else that command already reports, never recomputed a second way.

    Returns `None` for the legacy shape, which has no job folder and
    therefore nothing to report staleness about, and for a
    `run-config.json` `jobfolder.read()` cannot make sense of (missing a
    required field, invalid JSON) — the SAME "falls through cleanly"
    tolerance `product_for()`'s own narrower run-config lookup already
    applies one step up (see its docstring, step 2): a command already
    resilient to an incomplete run-config.json does not become stricter
    just because staleness reporting was added beside it.
    """
    job_dir = resolved_entrypoint.parent
    if not (job_dir / RUN_CONFIG_FILENAME).is_file():
        return None
    try:
        return dict(JOBFOLDER.read(job_dir).staleness)
    except JOBFOLDER.JobFolderError:
        return None


def _job_folder_commit(resolved_entrypoint: Path) -> str | None:
    """The pin a campaign consent token binds to (Decision 4's "commit-state
    threat-matrix case"): the job folder's OWN declared `commit`, read the
    SAME way `_gate_job_folder_pin()` reads it — through `JOBFOLDER.read()`,
    never a second, independent parse of `run-config.json`.

    `None` for the legacy shape (no job folder at all) and for a
    `run-config.json` `read()` cannot make sense of — the SAME two-path
    tolerance `_job_folder_staleness()` already applies one function up,
    for the same reason: a discriminator this narrow does not need to be
    stricter than the staleness reporter sitting right beside it.
    `campaign_consent_token()` hashes `None` exactly like any other value;
    it is part of the payload here, not a special case this function has
    to swallow.
    """
    job_dir = resolved_entrypoint.parent
    if not (job_dir / RUN_CONFIG_FILENAME).is_file():
        return None
    try:
        return JOBFOLDER.read(job_dir).run_config["commit"]
    except JOBFOLDER.JobFolderError:
        return None


def campaign_consent_token(
    *, pin_commit: str | None, relative_entrypoint: str | Path, units: Sequence[str],
    worker: str | None = None,
) -> str:
    """The ONE digest both `distribute` (which prints it) and `submit`
    (which verifies it) compute — a second, independently written hash
    here would be safe only until the day the two quietly drifted apart,
    at which point a legitimately-minted token would refuse and nobody
    could say why (Decision 4: "shared token-derivation function used by
    both distribute's print and submit's verify").

    `sha256(pin commit, relative entrypoint, ordered unit list[, worker])`.
    Every input in the payload is load-bearing:

    - `pin_commit` binds the token to the exact code a runner would
      clone. A job that re-pins to a different commit changes this value,
      and a token minted at the old pin no longer authorizes anything —
      self-expiring by construction, never by a staleness check this
      function would have to remember to run.
    - `relative_entrypoint` keeps a token minted for one product's
      campaign from ever authorizing a different one, even by accident —
      the cross-campaign case Decision 4 names explicitly.
    - `units`, hashed IN THE GIVEN ORDER, never sorted and never
      deduplicated: one approval covers the EXACT ordered unit list of
      that invocation (Decision 5). A unit added, removed, or reordered
      changes this payload and therefore the digest — there is no looser
      notion of "the same campaign" for this function to fall back to.
    - `worker`, present in the payload ONLY when the caller explicitly
      named one (`submit --worker <id>`, single-send, never `--unit`, never
      auto-selected) — see `_verify_launch_consent`'s own docstring for why
      an EXPLICIT worker must bind and an ABSENT one must not. Omitted
      entirely (not `null`, not an empty string) when no worker was named,
      so a campaign or auto-select derivation is byte-for-byte identical to
      before this parameter existed — this is what keeps
      `test_campaign_token_derivation_byte_identical_to_pre_change` true.

    Deliberately NOT a `--yes` boolean and deliberately not looked up
    anywhere but the arguments handed to it: this function reads no
    file, no environment variable, and no ledger line. Nothing it computes
    is ever written back to disk by this module — the whole reason a
    token is never persisted is that nothing downstream of this function
    ever tries to.
    """
    fields: dict[str, object] = {
        "pin": pin_commit,
        "entrypoint": str(relative_entrypoint),
        "units": list(units),
    }
    if worker is not None:
        fields["worker"] = worker
    payload = json.dumps(fields, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_launch_consent(
    *, consent: str | None, expected_consent: str, units: Sequence[str] | None,
    worker: str | None = None,
) -> None:
    """The ONE consent check every `submit` invocation goes through --
    campaign, single send, and rehearsal alike. Correction to Finding 3:
    the original gate fired only when `units` was truthy, which left a
    plain `submit` (no `--unit`, with or without `--smoke`) reaching
    `adapter.submit()` with NOBODY asked -- the exact launch the user's
    own complaint named. The fix is not a second case bolted onto the
    first; it is the same check, called unconditionally, for every mode,
    written as a structural invariant rather than a list of gated cases:
    nothing reaches `packer.select()`/`packer.plan()`/`packer.distribute()`
    -- and therefore never `adapter.submit()` -- without a token that
    matches what is being sent.

    `expected_consent` is always `campaign_consent_token()`'s own output
    -- ONE derivation, ONE shape, for BOTH campaign and single-send
    tokens: an empty ordered unit list is itself a legitimate input to
    that function, not a reason to invent a second one.

    CORRECTED (F2): the worker binds into that payload when, and only
    when, the caller explicitly named one with `--worker` at mint time.
    The prior rationale here claimed "the account is the caller's own
    explicit choice and does not need the token's protection to be
    honest" -- that was false the moment it was tested: three different
    real, named `--worker <account>` invocations on this machine all
    minted the IDENTICAL token, because none of them fed the worker into
    the digest at all. A token minted while approving one named account
    was therefore valid for launching on ANY account, which is exactly the
    cross-account authorization gap the token exists to close. With no
    `--worker` (campaign mode, or auto-select single-send), the account is
    chosen by `packer.select()`/`packer.distribute()` AFTER consent would
    be given, so binding it is still structurally impossible in
    advance -- that half of the old rationale survives; only the
    named-worker half was wrong.

    Missing consent for CAMPAIGN mode (`units` truthy) points the caller
    at `distribute --unit ...`, which mints and prints the token -- there
    is no other place a campaign token could come from.

    Missing consent for SINGLE-SEND mode (`units` empty, including a
    smoke rehearsal) has no equivalent minting command: there is no
    `distribute` step for one entrypoint. So THIS function prints the
    exact expected token itself, inside the refusal message. That is safe
    ONLY because the call that reaches this refusal never gets past it:
    no `packer.select()`/`packer.plan()`, no `adapter.submit()`, nothing
    launched. A token printed by a run that submitted nothing can never
    BE the approval it names -- only a second, deliberate invocation that
    copies it back into `--consent` is.
    """
    if consent is None:
        if units:
            raise ConsentError(
                "campaign submit refuses without --consent: run "
                "`distribute --unit ...` first, for this exact pin, "
                "entrypoint and ordered unit list, and pass back the "
                "token it prints. Nothing is launched without an "
                "explicit, per-campaign approval carried by this "
                "invocation's own argv."
            )
        account_note = (
            f" This token authorizes account {worker!r} only."
            if worker is not None
            else " This token names no single account -- it authorizes "
            "whichever account is chosen at launch time."
        )
        raise ConsentError(
            "submit refuses without --consent: nothing is launched "
            "without an explicit, per-launch approval carried by this "
            "invocation's own argv, and a single send has no "
            "`distribute` step to mint one ahead of time. This exact "
            "invocation submitted nothing -- no plan, no adapter call, "
            "no ledger line -- so printing the token it would need is "
            f"safe: re-run with --consent {expected_consent} to approve "
            "this exact pin and entrypoint." + account_note + " The token "
            "above is NOT itself the approval -- only a second, "
            "deliberate invocation that passes it back is."
        )
    if consent != expected_consent:
        raise ConsentError(
            "consent token does not match this invocation's pin, "
            "entrypoint, ordered unit list, or named worker: a token "
            "authorizes one exact launch only -- on the one account it "
            "named, when it named one -- and it stops authorizing the "
            "instant the pin, entrypoint, unit list, or worker moves -- "
            + (
                "mint a fresh one with `distribute --unit ...`"
                if units
                else "re-run with no --consent to see the token this "
                "exact invocation needs"
            )
        )


def _gate_job_folder_pin(resolved_entrypoint: Path) -> None:
    """Put a job-folder submission's own declared pin through the same
    three conditions `generate-job` enforces — BEFORE the digest walk, the
    plan, `adapter.submit()` and `LEDGER.append()`.

    `cmd_submit` used to compute a staleness verdict and place it in its
    return value, after the ledger event had already been appended. By the
    time an operator could read it, the adapter had accepted the job, the
    quota was gone and the ledger recorded a submission. That is not a
    gate; it is a receipt with a warning printed on it. Refusing has to
    happen while refusing still costs nothing, which is why this sits
    immediately after `product_for()` and before anything is computed,
    uploaded or written.

    It calls `jobfolder.verify_pin_preconditions()` — the same one
    function, in the same `PIN_CONDITIONS` order — with the job folder's
    OWN declared pin, clone paths and remote, read back through
    `JOBFOLDER.read()`. Not the caller's arguments: what is being
    submitted is the job folder, and the job folder is what promised a
    runner a commit.

    **The discriminator is `run-config.json`'s presence, deliberately not
    `_job_folder_staleness()`.** That helper returns `None` on TWO paths,
    not one: the legacy shape, and a `run-config.json` `read()` cannot make
    sense of. Reusing it here would let a job folder skip all three
    conditions by being unreadable, which is the worse half of the defect
    class this whole change is about. So a `JobFolderError` from `read()`
    is NOT swallowed — the same restraint `cmd_smoke_record()` already
    applies, and for the same reason. A malformed job folder refusing at
    submit is a new refusal path, and it is the intended one.

    A legacy entrypoint skipping all three conditions is not a finding and
    is left exactly as it was: it has no declared pin, no declared clone
    paths and no declared remote, so there is nothing to check, and unlike
    a job folder it never promised a runner a commit.

    A rehearsal (`submit --smoke`) meets this gate too. A rehearsal dials
    out, uploads a staged copy and spends quota; exempting it would make
    the gate optional in the workflow that runs most often, and it would
    break the very binding `cmd_readiness` depends on — that the rehearsed
    bytes and the submitted bytes are the same bytes.

    Raises `JobFolderError`, unwrapped, so the message reaching stderr is
    byte-identical to the one generation would have printed.
    """
    job_dir = resolved_entrypoint.parent
    if not (job_dir / RUN_CONFIG_FILENAME).is_file():
        return

    job_folder = JOBFOLDER.read(job_dir)
    run_config = job_folder.run_config
    repo = run_config["repo"]
    JOBFOLDER.verify_pin_preconditions(
        target=_target_for_job_dir(job_folder.path),
        commit=run_config["commit"],
        clone_paths=run_config["clonePaths"],
        repo_url=repo["url"],
        repo_ref=repo["ref"],
        decision="submission",
    )


def guard_entrypoint(target: Path, entrypoint: Path) -> Path:
    """Refuse anything that is not a notebook living under one of exactly
    two admitted shapes.

    THIS function is the single place in the entire remote-execution skill
    that holds an opinion about what KIND of file may run remotely.
    Everything below it is deliberately blind to that question:
    `adapter.Job.entrypoint` is typed as a bare path with no extension or
    directory-containment check (see `adapter.py`'s own docstring on that
    field), the ledger's `submitted`/`returned`/`errored` events store
    `entrypoint` as an opaque string, and the fold indexes by that same
    string without ever asking what it points to. That narrowing is
    deliberate, not an oversight left for later: a future workload that is
    a plain script, not a notebook, becomes admissible by widening the
    checks below — and ONLY the checks below. Nowhere else in this skill
    needs to change: not `Job`, not the ledger's event schema, not the
    fold's indices, not any downstream consumer that reads `entrypoint`
    today. Reworking all of those for a second file kind is exactly the
    refactor this one guard exists to make unnecessary.

    This forge's own layout rule, not a universal one, and not something a
    second deployment of this skill against a differently-shaped repository
    should assume holds. Exactly two shapes are admitted, both under
    `<target>`:

    - the legacy shape, `<Name>/Notebooks/**.ipynb` — the resolved path's
      second component is `Notebooks` and it has at least three components
      past `target`
    - the job-folder shape, `tools/<service>/<job-name>/*.ipynb` — exactly
      four components past `target`, the first of which is
      `TOOLS_DIRNAME`. This depth is exact, not a minimum: a fifth
      component (one level deeper than a job folder ever legitimately
      goes) is refused exactly like a path with too few. A shallower
      `tools/<service>/*.ipynb` is refused the same way — there is no
      service-level entrypoint, only a job-level one.

    `TOOLS_DIRNAME` ("tools") is a forge-layout constant fixed by this
    skill's own directory convention, never a service name — it must never
    be treated as one, and it is why it never appears in this module's own
    no-service source scan.

    Both shapes require the resolved path to end `.ipynb`; anything else is
    refused, with a message naming both the path that was refused and
    which rule it failed.

    `Path.resolve()` runs FIRST, and both shape checks below run only
    against the RESOLVED path — never the literal argument this function
    received. This order is load-bearing, not cosmetic, for EITHER shape: a
    symlink sitting inside `Notebooks/` or inside a job folder can point
    anywhere else on disk, and a check made against the literal path would
    see only the symlink's own in-bounds location, never where it actually
    leads. Checking containment before resolving is the exact hole a
    documentation-like escape (this skill's own threat matrix) would walk
    straight through; resolving first and checking the resolved target is
    what closes it, on both shapes alike.

    One narrower case gets its OWN message before either shape check's
    generic refusal (Finding 4 case B): a path that is exactly the
    job-folder DIRECTORY itself — three components past `target`, first
    `TOOLS_DIRNAME`, and actually holding both `run-config.json` and
    `runner.ipynb` — is one level above the answer, not a path in the
    wrong location. The generic "does not stay under ... nor under ..."
    message reads as a location problem and sends the caller to
    regenerate a job that was already sound; this instead says a file was
    expected, not a directory, and names exactly where the notebook is.
    A directory merely SHAPED like a job folder by depth alone, holding
    neither file, is not this case and still falls through to the generic
    refusal below — as does a `.ipynb` FILE one level too shallow (no
    `<job-name>` component at all), which is a different defect entirely.
    """
    resolved = Path(entrypoint).resolve()

    try:
        relative = resolved.relative_to(target)
    except ValueError:
        raise PathGuardError(
            f"refusing {entrypoint}: resolved path {resolved} does not stay "
            f"under target {target} at all"
        ) from None

    parts = relative.parts
    legacy_shape = len(parts) >= 3 and parts[1] == NOTEBOOKS_DIRNAME
    job_folder_shape = len(parts) == 4 and parts[0] == TOOLS_DIRNAME

    if not (legacy_shape or job_folder_shape):
        job_folder_directory = (
            len(parts) == 3
            and parts[0] == TOOLS_DIRNAME
            and resolved.is_dir()
            and (resolved / RUN_CONFIG_FILENAME).is_file()
            and (resolved / JOBFOLDER.RUNNER_FILENAME).is_file()
        )
        if job_folder_directory:
            # Finding 4 case B: `--entrypoint` was handed the job folder
            # DIRECTORY itself, one level above the answer, not the
            # notebook FILE inside it. The generic shape-mismatch message
            # below reads as though the folder were in the wrong
            # location and sends the caller to regenerate a job that was
            # perfectly sound — this names what was wanted, what was
            # given, and exactly what to type instead.
            notebook = resolved / JOBFOLDER.RUNNER_FILENAME
            raise PathGuardError(
                f"refusing {entrypoint}: a file was expected, not a "
                f"directory — {resolved} is the job folder itself, one "
                f"level above the answer; the notebook is at {notebook} — "
                "pass that path to --entrypoint instead"
            )
        raise PathGuardError(
            f"refusing {entrypoint}: resolved path {resolved} does not stay "
            f"under <target>/<Name>/{NOTEBOOKS_DIRNAME}/ nor under "
            f"<target>/{TOOLS_DIRNAME}/<service>/<job-name>/"
        )

    if resolved.suffix != NOTEBOOK_SUFFIX:
        raise PathGuardError(
            f"refusing {entrypoint}: resolved path {resolved} does not end "
            f"in {NOTEBOOK_SUFFIX}"
        )

    return resolved


def _relative_entrypoint(target: Path, resolved_entrypoint: Path, product: str) -> Path:
    """Derive the path recorded as a `submitted` event's own `entrypoint`
    field, from the SAME resolved entrypoint and the SAME product
    `product_for()` already resolved — never a second, independent
    derivation of either.

    For the legacy shape, `product` IS the entrypoint's own first path
    component past `target` (`product_for()`'s step 3 derives it that
    way), so the path relative to the product directory is exactly
    `Notebooks/...` — byte-identical to what this replaces, which computed
    `resolved_entrypoint.relative_to(target / name)` with `name` derived
    inline as that same first component.

    For the job-folder shape, the product directory is NOT an ancestor of
    the entrypoint at all: a job lives under
    `<target>/tools/<service>/<job-name>/`, structurally separate from
    wherever its declared product's own directory happens to live —
    `product_for()`'s whole reason for reading `run-config.json` instead of
    guessing `parts[0]` is that these two locations are unrelated for this
    shape. "Relative to the product directory" therefore has no meaning
    here, so this falls back to relative-to-`target` instead
    (`tools/<service>/<job-name>/runner.ipynb`), which stays unique and
    unambiguous per job folder without asserting a containment
    relationship that does not hold for this shape.
    """
    try:
        return resolved_entrypoint.relative_to(target / product)
    except ValueError:
        return resolved_entrypoint.relative_to(target)


def cmd_submit(
    *,
    target: str | Path,
    entrypoint: str | Path,
    worker: str | None = None,
    requested: int,
    adapter: "ADAPTER.Adapter",
    source_digest: Callable[[Path, str], str] | None = None,
    product: str | None = None,
    smoke: bool = False,
    units: Sequence[str] | None = None,
    consent: str | None = None,
) -> dict:
    """Guard, resolve a product, plan, submit, and record — the whole submit
    path, in this order.

    `units` is `submit --unit`'s own campaign switch (Finding 2; Decisions
    6, 7) — repeatable, the exact same flag `cmd_distribute` already
    declares. `None` or empty keeps every existing caller on TODAY's
    single-worker path below, byte-identical: `packer.select()` (no
    `--worker`) or `packer.plan()` (a named `--worker`), one
    `adapter.submit()`, one ledger event. A non-empty `units` switches
    into CAMPAIGN mode instead: `packer.distribute()` replaces
    `select()`/`plan()` entirely, consuming the spread across every
    healthy account rather than stopping at the first one — the defect
    this phase closes (`cmd_distribute`'s own docstring: "nothing is
    recorded and nothing is handed to" the adapter). `worker` is refused
    together with `units`: campaign mode has no "which account" fork for a
    caller to override, the same reason `distribute()` itself takes no
    `worker` parameter.

    Guard order past the target resolution is unchanged either way:
    `guard_entrypoint()` → `product_for()` → `_gate_job_folder_pin()` →
    the consent gate below → the digest, computed once and reused for
    every assignment in campaign mode — a single `distribute()` call
    already reads live health for every worker in one pass, so there is
    no per-assignment health re-read to stagger the digest around.

    `consent` gates EVERY mode this function has (Finding 3; Decisions 4,
    5 -- corrected: the original pass gated campaign mode only, which left
    a plain `submit` or `submit --smoke` reaching `adapter.submit()` with
    nobody asked, the exact launch the user's complaint named). Stated as
    the invariant it now is: nothing reaches
    `packer.select()`/`packer.plan()`/`packer.distribute()` -- and
    therefore never `adapter.submit()` -- without a `consent` token that
    matches `campaign_consent_token()`'s own output for THIS invocation's
    job folder pin (`_job_folder_commit()`, `None` for the legacy shape),
    relative entrypoint, and `units` in the exact order given (the empty
    tuple for a single send -- one derivation, one shape, never a second
    one invented for the non-campaign case). `_verify_launch_consent()`
    runs this check unconditionally, right after `_gate_job_folder_pin()`
    and before the digest is ever computed, so a refusal on any mode costs
    nothing: no digest walk, no plan, no adapter call, no ledger line.

    For a campaign, `distribute --unit ...` mints the token ahead of time
    and prints it -- the caller passes it back here. A single send has no
    equivalent minting command, so `submit` itself mints the expected
    token and prints it IN the refusal, which is safe only because the
    refusing call never gets past this gate: nothing was launched by the
    run that named the token. The worker is never part of what the token
    binds, in either mode: with no `--worker`, the account is chosen by
    `packer.select()` AFTER consent would be given, so binding it would
    make the token unmintable in advance; with `--worker` named, the
    account is the caller's own explicit, already-honest choice.

    Campaign mode issues one `adapter.submit()` and appends one ledger
    event per `packer.Distribution` assignment (Decision 6) — never one
    per unit, since a worker's whole assigned unit list travels inside
    that ONE job's opaque `run_config["units"]`, unread by this function.
    An assignment whose `units` came back empty (a healthy account with
    room but nothing left to hand it, `packer.Assignment`'s own documented
    case) submits nothing and is reported with `submissionId: None` —
    "had room, didn't need it" stays a fact about capacity, never a
    fabricated job. The returned mapping mirrors `packer.Distribution`
    field for field (Decision 7): `assignments[]`, `unplaced[]`, and
    `skipped[]` (worker → `Skip.reason`, unprefixed, exactly as
    `cmd_distribute` already renders it) — carried through unchanged, no
    new triage logic invented here.

    `smoke=True` (`submit --smoke`) does two things together, both
    load-bearing (design #744 section 7, and see `SMOKE_LEDGER_FILENAME`'s
    own comment above): sets `run_config["mode"] = "smoke"` on the `Job`
    (opaque to `packer.py`/`ledger.py`, read only by
    `assets/runner_invoke.py`'s `select_block()`), and routes the
    resulting `submitted` event to `smoke.jsonl` instead of
    `ledger.jsonl` — a different destination FILE, not a different event
    shape, which is what keeps a rehearsal from ever becoming an
    entrypoint's `latest[...]` submission in the main ledger's fold.
    `smoke=False` (the default) is byte-identical to this function's
    pre-T11 behavior.

    `target` is resolved to an absolute path as the very first thing this
    function does, before any other check and before any filesystem write —
    every data path this call touches (the guard's containment check, the
    ledger's location) is derived from that resolved value and never from
    the raw argument. A relative `--target` therefore never gets a chance to
    be interpreted against the wrong working directory later in the call,
    because by the time anything else runs, there is no relative path left
    to misinterpret.

    Order past that point is fixed by design, not incidental:
    `guard_entrypoint()` runs first because nothing after it — not the
    product, the digest, the plan, not the adapter call — should ever run
    against a path this forge's layout rule refuses. `product_for()` runs
    immediately after the guard, and BEFORE any digest, plan, or adapter
    call: a submission whose product cannot be resolved is refused right
    there, before anything is computed against a guessed tree (`tools`, in
    particular, which `product_for()` itself refuses to ever return) and
    before the adapter is given any chance to run — this is what keeps a
    job-folder submission with no resolvable product a clean refusal rather
    than a silently mis-recorded one. `_gate_job_folder_pin()` runs
    immediately after it and before everything else, so a job folder whose
    pin fails any of the three conditions is refused while refusing still
    costs nothing: no digest walk, no plan, no adapter call, no ledger
    line. This function used to compute a staleness verdict and place it
    in its return value AFTER `LEDGER.append()`, which reported on a
    submission that had already happened — a receipt with a warning
    printed on it rather than a gate. That verdict is still in the return
    payload for callers that read it; it is simply no longer the only
    thing standing between a stale pin and spent quota. `source_digest()`
    is called FRESH
    here, at submit time, and its result is never reused from a notebook's
    own post-hoc marker or from any earlier call in this process — that
    freshness is the one thing that later lets the ledger's fold tell a
    current result from a stale one (see `ledger.py`'s `currency_verdict`).
    `packer.plan()` runs before `adapter.submit()` so a submission is never
    attempted with no capacity clamp computed behind it. `ledger.append()`
    runs LAST, only after the adapter has already returned a real
    submission id — appending before that would risk recording a submission
    that was never actually made.

    `product` is this function's own `--product` override, forwarded
    unchanged to `product_for()` as its `explicit` argument — step 1 of
    that function's four-step resolution order, and the one step no
    earlier version of this function ever exposed a way to reach.

    `worker` is now OPTIONAL. `None` (no `--worker` on the CLI) hands the
    choice to `packer.select()`, which walks `adapter.workers()` in
    declared order and returns the first healthy one with capacity —
    naming an account is a decision this call no longer forces on a
    caller with no reason to make it. A caller that DOES name one keeps
    today's non-selecting behavior exactly: `packer.plan()` is called for
    that exact worker, and an unhealthy NAMED worker refuses outright
    (via `ADAPTER.WorkerUnauthorized`, propagated, never caught here)
    rather than silently falling back to a different account — silently
    switching accounts changes whose quota is spent, which is a decision
    only a caller who named the account in the first place gets to make.
    Either way, `plan()`/`select()` runs BEFORE `adapter.submit()`, so a
    refusal on either path costs no quota.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    resolved_entrypoint = guard_entrypoint(target, Path(entrypoint))
    resolved_product = product_for(
        target, resolved_entrypoint, explicit=product, command="submit"
    )
    _gate_job_folder_pin(resolved_entrypoint)
    relative_entrypoint = _relative_entrypoint(
        target, resolved_entrypoint, resolved_product
    )

    if units and worker is not None:
        raise RemoteCLIError(
            "--worker and --unit are mutually exclusive: campaign mode "
            "(--unit) spreads across every healthy account itself and "
            "has no single named account for --worker to select"
        )

    # Unconditional invariant (this phase's correction to Finding 3):
    # every mode -- campaign, single send, rehearsal -- is verified here,
    # before the digest is computed, before any plan, and before
    # `adapter.submit()`. `units or ()` feeds `campaign_consent_token()`
    # the empty ordered unit list for a single send -- a legitimate input
    # to the SAME derivation, never a second one.
    # `worker` here is still the caller's own raw argument -- None unless
    # `--worker` was explicitly passed. The mutual-exclusivity refusal
    # above guarantees it is None whenever `units` is truthy, so passing
    # it straight through binds an explicit single-send worker and leaves
    # campaign/auto-select derivation untouched, in one expression.
    expected_consent = campaign_consent_token(
        pin_commit=_job_folder_commit(resolved_entrypoint),
        relative_entrypoint=relative_entrypoint,
        units=units or (),
        worker=worker,
    )
    _verify_launch_consent(
        consent=consent, expected_consent=expected_consent, units=units,
        worker=worker,
    )

    digest_fn = source_digest or _load_source_digest()
    digest = digest_fn(target, resolved_product)

    ledger_path = (
        _smoke_ledger_path(target, resolved_product)
        if smoke
        else _main_ledger_path(target, resolved_product)
    )
    ledger_lines = _read_ledger_lines(ledger_path)

    if units:
        distribution = PACKER.distribute(
            adapter=adapter,
            units=units,
            ledger_lines=ledger_lines,
            live_digest=digest,
        )

        assignments: list[dict] = []
        for row in distribution.assignments:
            submission_id = None
            if row.units:
                run_config = {"mode": "smoke"} if smoke else {}
                run_config = dict(run_config)
                run_config["units"] = list(row.units)
                job = ADAPTER.Job(
                    entrypoint=resolved_entrypoint,
                    run_config=run_config,
                    worker=row.plan.worker,
                )
                submission = adapter.submit(job)
                submission_id = submission.id

                event = LEDGER.submitted_event(
                    entrypoint=str(relative_entrypoint),
                    source_digest=digest,
                    submission_id=submission_id,
                    worker=row.plan.worker,
                    requested_capacity=row.plan.requested,
                    granted_capacity=row.plan.granted,
                )
                LEDGER.append(ledger_path, event)

            assignments.append(
                {
                    "worker": row.plan.worker,
                    "requested": row.plan.requested,
                    "cap": row.plan.cap,
                    "inFlight": row.plan.in_flight,
                    "granted": row.plan.granted,
                    "inFlightSource": row.plan.in_flight_source,
                    "units": list(row.units),
                    "submissionId": submission_id,
                }
            )

        return {
            "assignments": assignments,
            "unplaced": list(distribution.unplaced),
            "skipped": [
                {"worker": row.worker, "reason": row.reason} for row in distribution.skipped
            ],
            "ledgerPath": ledger_path,
            "staleness": _job_folder_staleness(resolved_entrypoint),
            "smoke": smoke,
        }

    if worker is None:
        plan = PACKER.select(
            adapter=adapter,
            requested=requested,
            ledger_lines=ledger_lines,
            live_digest=digest,
        )
        worker = plan.worker
    else:
        plan = PACKER.plan(
            adapter=adapter,
            worker_id=worker,
            requested=requested,
            ledger_lines=ledger_lines,
            live_digest=digest,
        )

    run_config = {"mode": "smoke"} if smoke else {}
    job = ADAPTER.Job(entrypoint=resolved_entrypoint, run_config=run_config, worker=worker)
    submission = adapter.submit(job)

    event = LEDGER.submitted_event(
        entrypoint=str(relative_entrypoint),
        source_digest=digest,
        submission_id=submission.id,
        worker=worker,
        requested_capacity=requested,
        granted_capacity=plan.granted,
    )
    LEDGER.append(ledger_path, event)

    return {
        "plan": plan,
        "submission": submission,
        "event": event,
        "ledgerPath": ledger_path,
        "staleness": _job_folder_staleness(resolved_entrypoint),
        "smoke": smoke,
    }


def cmd_status(
    *,
    target: str | Path,
    entrypoint: str | Path,
    source_digest: Callable[[Path, str], str] | None = None,
) -> dict:
    """The fold, rendered for a human: per-entrypoint state, what is
    pending, what is `staleInFlight`, what is quarantined, and how many
    lines could not be read at all — for `ledger.jsonl`, at this dict's own
    top-level keys, exactly as before, PLUS the same shape folded from
    `smoke.jsonl` alone, under `"smoke"`. The two are reported side by side,
    never merged into one: `smoke.jsonl` is folded through its own,
    separate `LEDGER.fold()` call, so a rehearsal submission still can never
    become part of `entrypoints`' own `latest[entrypoint]` index — only a
    second, clearly-labeled section a human can also see, where before
    there was nothing to see at all for a smoke-only entrypoint.

    This function accepts no `adapter` parameter at all — not merely
    "does not call one" but structurally cannot, since none is in scope to
    call. `status` reports what the ledgers already say; it never resolves
    anything, and the signature itself is what makes that true rather than
    a rule this function's body would otherwise have to be trusted to
    follow.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    product = product_for(target, entrypoint, command="status")
    ledger_path = _main_ledger_path(target, product)
    smoke_ledger_path = _smoke_ledger_path(target, product)

    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, product)
    state = LEDGER.fold(_read_ledger_lines(ledger_path), live_digest=live)
    smoke_state = LEDGER.fold(_read_ledger_lines(smoke_ledger_path), live_digest=live)

    def _render(folded: "LEDGER.LedgerState") -> dict:
        # `folded.entrypoints` is keyed by `(entrypoint, worker)` (F4:
        # Decision 6) -- `"entrypoints"` ALWAYS nests a per-worker sub-dict
        # under each entrypoint now, a documented breaking shape change
        # from the flat `{entrypoint: {...}}` this used to render. Five
        # accounts submitting the same entrypoint used to fold into one
        # flat entry where four of the five silently vanished; nesting is
        # what makes all five visible in one render.
        nested: dict[str, dict[str, dict]] = {}
        for (entry_name, worker), entry in folded.entrypoints.items():
            nested.setdefault(entry_name, {})[worker] = {
                "state": entry.state,
                "staleInFlight": entry.stale_in_flight,
            }
        return {
            "entrypoints": nested,
            "staleInFlight": folded.stale_in_flight,
            "quarantined": folded.from_stale_submission,
            "unreadableLines": folded.unreadable_lines,
        }

    return {
        "ledgerPath": ledger_path,
        **_render(state),
        "smoke": {"ledgerPath": smoke_ledger_path, **_render(smoke_state)},
        "staleness": _job_folder_staleness(Path(entrypoint).resolve()),
    }


def cmd_distribute(
    *,
    target: str | Path,
    entrypoint: str | Path,
    adapter: "ADAPTER.Adapter",
    units: Sequence[str],
    source_digest: Callable[[Path, str], str] | None = None,
) -> dict:
    """Report how `units` -- opaque identifiers this function never
    inspects beyond passing them through -- would spread across every
    worker `adapter` reports right now, aggregated by
    `packer.distribute()`. Nothing is recorded and nothing is handed to
    the adapter's own work-issuing operation: this call's only route to
    the adapter is `distribute()`'s own health read, the same
    `list_active()`/`list_active()`-fallback path `plan()` already uses.

    Target/entrypoint resolve exactly as `cmd_status` resolves them --
    `product_for()`, the same main ledger path, the same digest seam --
    because this is `status`'s read discipline extended across every
    worker at once, never a dispatch-and-record command's write one.
    Unlike `cmd_status`,
    an `adapter` parameter genuinely is in scope, because a worker's
    health is read live here; that live read is the only thing this
    function does with the adapter, and three separate proofs at the
    CLI layer -- a double forbidding any work-issuing call, a whole-tree
    hash snapshot proving no path under `target` ever changes, and this
    function's own source naming neither of the two operations that
    would move work or record it -- hold that plainly rather than
    resting on this paragraph alone.

    The returned mapping carries four separate facts, mirroring
    `packer.Distribution` field for field: `units` (how many were
    handed in), `places` (total granted capacity, summed across every
    healthy worker), `assigned` (how many of `units` actually landed
    somewhere), and `unplaced` (the exact identities that did not).
    `assignments` renders each worker's whole `Plan` -- all four of its
    own numbers, plus `inFlightSource` -- next to the identities it was
    given, never a bare granted count alone; `skipped` names every
    worker `packer.distribute()` could not use and why.

    PLUS a fifth fact this call is the ONE place that ever prints
    (Finding 3; Decision 4): `consentToken`, the digest a caller must
    pass back through `--consent` before this exact pin, entrypoint and
    ordered unit list may go on to spend a single account's quota.
    Computed by `campaign_consent_token()` -- the SAME function the
    quota-spending command's own verification calls -- never a second,
    independently written hash here that could quietly drift from it.
    This function still issues no work and records nothing: printing a
    token is no more a write than reporting `places` or `unplaced`
    already was.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    resolved_entrypoint = Path(entrypoint).resolve()
    product = product_for(target, resolved_entrypoint, command="distribute")
    relative_entrypoint = _relative_entrypoint(target, resolved_entrypoint, product)
    ledger_path = _main_ledger_path(target, product)
    ledger_lines = _read_ledger_lines(ledger_path)

    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, product)

    result = PACKER.distribute(
        adapter=adapter, units=units, ledger_lines=ledger_lines, live_digest=live,
    )

    consent_token = campaign_consent_token(
        pin_commit=_job_folder_commit(resolved_entrypoint),
        relative_entrypoint=relative_entrypoint,
        units=units,
    )

    return {
        "units": len(result.units),
        "places": result.places,
        "assigned": len(result.units) - len(result.unplaced),
        "unplaced": list(result.unplaced),
        "assignments": [
            {
                "worker": row.plan.worker,
                "requested": row.plan.requested,
                "cap": row.plan.cap,
                "inFlight": row.plan.in_flight,
                "granted": row.plan.granted,
                "inFlightSource": row.plan.in_flight_source,
                "units": list(row.units),
            }
            for row in result.assignments
        ],
        "skipped": [{"worker": row.worker, "reason": row.reason} for row in result.skipped],
        "consentToken": consent_token,
    }


def cmd_poll(*, submission_id: str, adapter: "ADAPTER.Adapter") -> "ADAPTER.Status":
    """Ask the adapter for one submission's status, in the seam's own
    five-value vocabulary — never the backend's raw text.

    `ADAPTER.Status.__post_init__` already refuses an out-of-vocabulary
    `state` for a genuine `Status` built the ordinary way, but that
    validation runs only at construction time, inside the adapter, and this
    function has no way to confirm every adapter actually goes through it —
    a misbehaving adapter could hand back any object carrying a `.state`
    attribute the ordinary constructor never touched. The check below is
    this seam's OWN refusal, made again at the one place a bad value would
    otherwise reach a caller: a state outside `ADAPTER.STATES` is the
    adapter's fault, and it is refused here, not translated, not guessed
    at, and never passed through.
    """
    status = adapter.poll(submission_id)
    state = getattr(status, "state", None)
    if state not in ADAPTER.STATES:
        raise RemoteCLIError(
            f"adapter.poll() returned state {state!r}, outside this seam's "
            f"own vocabulary {ADAPTER.STATES}; that is the adapter's fault, "
            "not something this CLI passes through"
        )
    return status


def cmd_fetch(
    *,
    target: str | Path,
    entrypoint: str | Path,
    submission_id: str,
    dest: str | Path,
    adapter: "ADAPTER.Adapter",
    source_digest: Callable[[Path, str], str] | None = None,
    force: bool = False,
    smoke: bool = False,
) -> dict:
    """Materialize one submission's result, quarantining it structurally
    when it is not judged current — never discarding it, and never merging
    it either.

    Ordering is fixed, and every step past the first exists to protect the
    one fact that matters most: a `returned` event must never be recorded
    unless the artifact it names is actually, completely, on disk.

    0. Once `final_dest` is known (step 2's placement decision), and
       BEFORE `adapter.fetch()` is ever called: if `final_dest` already
       exists, this is a re-fetch of a submission this call already
       materialized. Paying for a second download only to discover that
       `os.replace()` cannot replace a non-empty destination directory
       (`OSError: [Errno 66] Directory not empty`) is the wrong place to
       notice — the guard runs here, before the network call, not after
       it. Default: refuse cleanly, naming the existing path and the way
       out (`--force`). `force=True` REMOVES the existing `final_dest`
       tree (`shutil.rmtree`) before the fetch proceeds, so the fresh
       download replaces it outright — this is a destructive overwrite of
       whatever the earlier fetch left there, stated here so it is never
       an implicit side effect of passing the flag. A duplicate `returned`
       ledger event, if one is ever appended for the same submission id
       regardless, is harmless: `fold()` has no accumulator for it —
       `terminal_by_id[submissionId]` is an overwrite by an
       equal-kind event and `verdicts[submissionId]` recomputes the
       identical value under the identical key.
    1. `<final_dest>.partial/` is a DIFFERENT fact from step 0's, and it
       is checked first — before step 0's `shutil.rmtree()` can destroy
       anything on a refusal that was going to happen anyway. Its
       presence means a previous fetch of this submission ended without
       reaching step 6's rename: a crashed or killed download, a
       `complete=False` result step 5 deliberately left on disk, or
       another fetch of this same submission running right now. Step 3
       hands that exact path to `adapter.fetch()`, which is free to write
       into a directory that already has files in it — so without this
       guard the leftover run's files and this run's files are promoted
       together, by step 6, as one artifact set that never existed. That
       is worse than either failure this function already refuses,
       because it does not raise: it produces a plausible wrong answer,
       which is precisely what the ledger machinery around it exists to
       prevent. Refuse, naming the leftover path and the action that
       clears it. `--force` does NOT clear it, deliberately: `--force`
       means "the destination is already materialized, replace it", and
       a `.partial/` is neither materialized nor necessarily inert — it
       may hold the only copy of bytes already paid for, or be the live
       working directory of a fetch still running. Removing it is a
       decision with real cost, so this reports and lets the human make
       it.
    2. `LEDGER.currency_verdict()` — the SAME rule `fold()` itself uses for
       an already-recorded `returned` event — is evaluated here BEFORE one
       exists, against the ledger state read at the top of this call. A
       `current` verdict uses the caller's own `dest`; anything else
       (`fromStaleSubmission`) overrides `dest` entirely and reroutes to
       `<target>/<Name>/.remote-execution/quarantine/<submissionId>/` — a
       location structurally outside `Results/shards/`, the only tree a
       shard reader ever enumerates. This is a placement decision made
       once, not a filter a merge step could forget to apply later: the
       artifact is never even offered a path a merge could reach.
    3. `observed_concurrency` is read from the SAME pre-fetch ledger state,
       via `LedgerState.pending_for()` — the count of this worker's pending
       submissions at the instant just before this one is about to be
       recorded as done, including itself. A grant the packer allowed for
       N concurrent jobs, honored by the service for fewer than N, shows up
       here as a smaller number than N — visible, not assumed.
    4. `adapter.fetch()` is handed `<dest-or-quarantine>.partial/`, never
       the final path directly. This is the ONE call in this whole function
       that can fail partway through after having already written SOME
       bytes to disk — a network drop, a killed process, a raised
       exception from inside the adapter itself. Nothing before this line
       has touched the filesystem at all, and nothing after it runs unless
       this call returns normally.
    5. `Fetched.complete` is checked before anything else happens. `False`
       means the backend itself considers the result unfinished — this
       function returns without renaming and without appending anything,
       leaving the ledger's own state exactly as `pending` as it already
       was, which is what makes a retry safe. The `.partial/` directory
       stays on disk and is returned as `path`, so the retry meets step
       1's guard rather than silently merging into it. Only
       `complete=True` reaches the rename.
    6. `os.replace()` — an atomic rename on the same filesystem — moves the
       `.partial/` directory into its final name. This is the one line
       that turns "an artifact happens to exist on disk" into "the
       artifact is at the path this call promises callers", and it runs
       before the ledger is touched.
    7. `LEDGER.append()` runs LAST, only after the rename above has
       already succeeded. If the process is killed at any point before
       this line, the submission reads back as `pending` on the next fold
       — retryable, never a false `returned` — because nothing before this
       line ever wrote to the ledger.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    product = product_for(target, entrypoint, command="fetch")
    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, product)

    # `resolve_submission_ledger()` is what makes this reach a submission
    # recorded by `submit --smoke` into `smoke.jsonl` — this used to hardcode
    # `LEDGER_FILENAME` and could never find one, at all, no matter how
    # complete the artifact it was asked to fetch.
    ledger_path, state, arbitration = resolve_submission_ledger(
        target, product, submission_id, live, smoke=smoke
    )
    submission = state.by_id[submission_id]

    verdict = LEDGER.currency_verdict(submission, state.latest, live)
    if verdict == "current":
        final_dest = Path(dest).resolve()
    else:
        final_dest = target / product / LEDGER_DIRNAME / QUARANTINE_DIRNAME / submission_id

    partial_dest = final_dest.with_name(final_dest.name + PARTIAL_SUFFIX)

    # Ahead of the `--force` removal below on purpose: a refusal that was
    # going to happen anyway must not first delete an already-fetched tree.
    if partial_dest.exists():
        raise RemoteCLIError(
            f"a leftover {partial_dest} exists from a fetch that never "
            "finished -- a crashed or killed download, a result the "
            "backend reported as incomplete, or another fetch of this "
            "same submission running right now. It is never merged into "
            "and never promoted, because mixing two runs' files into one "
            "artifact set is a wrong answer that does not announce "
            "itself. --force does not clear it: it may hold the only "
            "copy of bytes already paid for, or be a running fetch's "
            "working directory. Inspect it, then remove it by hand "
            f"(rm -rf {partial_dest}) before retrying"
        )

    if final_dest.exists():
        if not force:
            raise RemoteCLIError(
                f"already fetched at {final_dest} -- pass --force to "
                "remove the existing directory and re-fetch"
            )
        shutil.rmtree(final_dest)

    observed_concurrency = state.pending_for(submission["worker"])
    staleness = _job_folder_staleness(Path(entrypoint).resolve())

    fetched = adapter.fetch(submission_id, partial_dest)

    if not fetched.complete:
        # Not renamed, not recorded: the ledger's own state stays exactly
        # `pending`, which is the one state a retry can safely start from.
        return {
            "verdict": verdict,
            "complete": False,
            "path": partial_dest,
            "event": None,
            "staleness": staleness,
            "arbitration": arbitration,
        }

    final_dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(partial_dest), str(final_dest))

    event = LEDGER.returned_event(
        submission_id=submission_id,
        artifact_path=str(final_dest),
        observed_concurrency=observed_concurrency,
    )
    LEDGER.append(ledger_path, event)

    return {
        "verdict": verdict,
        "complete": True,
        "path": final_dest,
        "event": event,
        "staleness": staleness,
        "arbitration": arbitration,
    }


def cmd_reconcile(
    *,
    target: str | Path,
    entrypoint: str | Path,
    worker: str,
    adapter: "ADAPTER.Adapter",
    resolve: bool = False,
    source_digest: Callable[[Path, str], str] | None = None,
    smoke: bool = False,
) -> dict:
    """Compare the ledger's pending submissions for `worker` against what
    `adapter.list_active(worker)` reports right now, in both directions,
    and report the difference. Never resolves either side on its own
    initiative.

    An id `list_active()` reports that this ledger has no `submitted` event
    for at all is `orphanRemote`. It is reported ONLY — never cancelled
    (this function never calls `adapter.cancel()`, the same restraint
    `fold()`'s own `staleInFlight` handling already applies to a source
    that moved out from under a pending submission) and NEVER auto-adopted
    by fabricating a `submitted` line for it. Adoption would have to invent
    a `sourceDigest` this function has no way to know, and `sourceDigest`
    is the entire basis the fold's currency rule later judges a result by
    — a fabricated one would turn every future currency verdict for that id
    into a guess wearing the shape of a fact. Reporting the orphan and
    leaving the ledger untouched is the guarantee-preserving choice;
    adoption is the guarantee-destroying one.

    A `pending` submission EITHER ledger still expects — `ledger.jsonl` or
    `smoke.jsonl`, both folded here, separately, the same way
    `resolve_submission_ledger()` folds them for `fetch` — that
    `list_active()` no longer lists is `orphanLocal`. A still-active SMOKE
    submission is what `local_pending` including `smoke.jsonl`'s own pending
    ids actually protects here: without it, a rehearsal the service still
    considers active would misreport as `orphanRemote` on every call, since
    a smoke submission never touches `ledger.jsonl` at all. It is always
    reported, regardless of `resolve`. Only when `resolve=True` — reserved
    for a human explicitly passing `--resolve`, never set by any automated
    caller in this skill — does this function append one `errored` event
    per orphan, through the exact same `LEDGER.append()` path every other
    terminal event goes through, to WHICHEVER ledger that orphan's own
    `submitted` event actually lives in (`resolve_submission_ledger()`
    again — never assumed to be the main one). `resolve=False`, the
    default, appends nothing at all: an orphan-remote id is reported
    without a single ledger write, on every call.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    product = product_for(target, entrypoint, command="reconcile")
    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, product)

    main_state = LEDGER.fold(
        _read_ledger_lines(_main_ledger_path(target, product)), live_digest=live
    )
    smoke_state = LEDGER.fold(
        _read_ledger_lines(_smoke_ledger_path(target, product)), live_digest=live
    )

    def _pending_ids(folded: "LEDGER.LedgerState") -> set[str]:
        # `folded.entrypoints`/`folded.latest` are keyed by
        # `(entrypoint, worker)` (F4: Decision 6) -- filtering `.latest`
        # by `worker` first and indexing `.entrypoints` by the same pair
        # is what keeps this reconcile call scoped to only THIS worker's
        # own state, never another worker's resubmission of the same
        # entrypoint.
        return {
            submission["submissionId"]
            for (entrypoint, submission_worker), submission in folded.latest.items()
            if submission_worker == worker
            and folded.entrypoints[(entrypoint, submission_worker)].state == "pending"
        }

    remote_active = set(adapter.list_active(worker))
    local_pending = _pending_ids(main_state) | _pending_ids(smoke_state)

    orphan_remote = tuple(sorted(remote_active - local_pending))
    orphan_local = tuple(sorted(local_pending - remote_active))

    resolved_events: list[dict] = []
    arbitrations: list[str] = []
    if resolve:
        for submission_id in orphan_local:
            orphan_ledger_path, _, arbitration = resolve_submission_ledger(
                target, product, submission_id, live, smoke=smoke
            )
            if arbitration is not None:
                arbitrations.append(arbitration)
            event = LEDGER.errored_event(
                submission_id=submission_id, reason="not-found-at-service"
            )
            LEDGER.append(orphan_ledger_path, event)
            resolved_events.append(event)

    return {
        "orphanRemote": orphan_remote,
        "orphanLocal": orphan_local,
        "resolved": tuple(resolved_events),
        "staleness": _job_folder_staleness(Path(entrypoint).resolve()),
        "arbitration": tuple(arbitrations),
    }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _target_for_job_dir(resolved_job_dir: Path) -> Path:
    """The repository a job folder belongs to, derived the exact same
    structural way `jobfolder.read()` derives it internally
    (`<target>/tools/<service>/<job-name>/` → `.parents[2]`). Only ever
    called after `JOBFOLDER.read()` has already confirmed this exact
    shape by not raising.
    """
    return resolved_job_dir.parents[2]


def _smoke_ledger_path(target: Path, product: str) -> Path:
    return target / product / LEDGER_DIRNAME / SMOKE_LEDGER_FILENAME


def _main_ledger_path(target: Path, product: str) -> Path:
    return target / product / LEDGER_DIRNAME / LEDGER_FILENAME


def _read_ledger_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def resolve_submission_ledger(
    target: Path, product: str, submission_id: str, live_digest: str,
    *, smoke: bool = False,
) -> tuple[Path, "LEDGER.LedgerState", str | None]:
    """The one place in this module that answers "which ledger holds THIS
    submission id" — `ledger.jsonl` or `smoke.jsonl` — for every command
    that needs to act on one specific submission afterward (`cmd_fetch`,
    and `cmd_reconcile`'s `--resolve`). Neither command builds a ledger
    path for a submission id any other way: getting one now has exactly
    one route through this module, which is what keeps a future command
    that resolves a submission from being written blind to `smoke.jsonl`
    the way `cmd_status`, `cmd_fetch` and `cmd_reconcile` all were before
    this function existed — there is no second, ad hoc way left to spell
    "the ledger" that could quietly forget the smoke one exists.

    `ledger.jsonl` and `smoke.jsonl` are folded SEPARATELY here, through
    the exact same `LEDGER.fold()` every other reader in this module already
    calls — never concatenated into one call, and never merged into one
    `LedgerState`. That separation is not incidental: it is what
    `test_smoke_submission_never_enters_the_fold_or_supersedes_a_real_run`
    already pins — a smoke submission must never become part of the main
    ledger's own `latest[entrypoint]` index — and folding the two logs
    together here, even transiently, would do exactly that the moment this
    function's caller reused the merged result for anything shaped like
    "the main ledger's state". Each returned `LedgerState` is only ever
    valid against the file it was folded from; this function hands back
    both the path and that matching state together so no caller has to
    remember which one goes with which.

    A submission id absent from BOTH files is refused: there is nothing on
    record for it anywhere this module looks.

    A submission id present in BOTH is NOT, on its own, refused. A backend
    is free to mint an id deterministically from a worker/entrypoint pair,
    so a legitimate rehearse-then-launch pair — `submit --smoke` followed
    by a real `submit` of the identical job — can reuse the identical id BY
    CONSTRUCTION. A shared id is an expected condition on such a backend,
    not corruption. Only the two `submitted` records' recorded `entrypoint`
    and `worker` fields are compared (never the id string itself —
    `adapter.py` permits the ledger exactly equality and dict-key use on an
    id, and forbids splitting, parsing, or pattern-matching any part of
    it):

    - DISAGREE on `entrypoint` or `worker` → still refused, unconditionally
      (even under `smoke=True`): one record lies about what was actually
      submitted, and picking either file to act on would be guessing. This
      is the genuine corruption case — a hand-edited ledger line, a ledger
      file copied across targets, or an adapter whose id no longer encodes
      worker/entrypoint.
    - AGREE → resolves to the main ledger by default, with a returned
      arbitration note (the caller decides whether/where to surface it —
      this function never writes to stderr; every `file=sys.stderr` call
      in this module lives in `main()`). `smoke=True` (mirroring `submit
      --smoke`) overrides that precedence and resolves to the smoke ledger
      instead, with no note. `smoke` overrides PRECEDENCE only, never
      COHERENCE: the disagreement refusal above still fires regardless of
      `smoke`.
    """
    main_path = _main_ledger_path(target, product)
    smoke_path = _smoke_ledger_path(target, product)
    main_state = LEDGER.fold(_read_ledger_lines(main_path), live_digest=live_digest)
    smoke_state = LEDGER.fold(_read_ledger_lines(smoke_path), live_digest=live_digest)

    in_main = submission_id in main_state.by_id
    in_smoke = submission_id in smoke_state.by_id

    if in_main and in_smoke:
        main_record = main_state.by_id[submission_id]
        smoke_record = smoke_state.by_id[submission_id]
        if main_record["entrypoint"] != smoke_record["entrypoint"]:
            raise RemoteCLIError(
                f"submission {submission_id!r} is recorded in both "
                f"{main_path} and {smoke_path}, and the two records "
                f"disagree on entrypoint ({main_record['entrypoint']!r} vs "
                f"{smoke_record['entrypoint']!r}); refusing to guess which "
                "one is authoritative"
            )
        if main_record["worker"] != smoke_record["worker"]:
            raise RemoteCLIError(
                f"submission {submission_id!r} is recorded in both "
                f"{main_path} and {smoke_path}, and the two records "
                f"disagree on worker ({main_record['worker']!r} vs "
                f"{smoke_record['worker']!r}); refusing to guess which one "
                "is authoritative"
            )
        if smoke:
            return (smoke_path, smoke_state, None)
        note = (
            f"submission {submission_id!r} is recorded in both {main_path} "
            f"and {smoke_path} with agreeing entrypoint/worker; resolved to "
            f"the main ledger {main_path}"
        )
        return (main_path, main_state, note)
    if not in_main and not in_smoke:
        raise RemoteCLIError(
            f"no submitted event on record for submission {submission_id!r} "
            f"in {main_path} or {smoke_path}"
        )
    return (main_path, main_state, None) if in_main else (smoke_path, smoke_state, None)


def cmd_smoke_record(
    *,
    job_dir: str | Path,
    artifact_path: str | Path,
    worker: str,
) -> dict:
    """Record a smoke run's verdict — never a human assertion. Reads
    `artifact_path` (a fetched `shard.json`) and passes iff
    `shard_io.completeness(...)` reports it complete: the SAME predicate
    T10's `merge()` uses, two consumers.

    The `required` field list reaches this function WITHOUT this module
    ever naming a field of its own: read from the job's own
    `run-config.json`, at `run.smoke.requiredEvidence` — a list the TARGET
    declares at `generate-job` time (repeatable `--smoke-required-evidence`
    flag; see `jobfolder.build_run_config()`). This forge module only
    carries that list from where the target wrote it to where
    `shard_io.completeness()` needs it; confirmed by
    `test_remote_cli_source_names_no_evidence_field_of_its_own` that no
    evidence-stamp field path exists in this module's own source — the
    same "caller brings the vocabulary" discipline
    `shard_io.completeness()` already states, carried one hop further.

    Routes through `JOBFOLDER.read()` — the single job-folder reader.
    Unlike `_job_folder_staleness()`, a `JobFolderError` here is NOT
    swallowed: `smoke record` has no legacy-shape fallback to fall through
    to at all.

    Appended to `smoke.jsonl` through the SAME `LEDGER.append()` every
    other event in this skill goes through — see `cmd_submit`'s own
    docstring and the module-level comment above `SMOKE_LEDGER_FILENAME`.
    """
    resolved_job_dir = Path(job_dir).resolve()
    job_folder = JOBFOLDER.read(resolved_job_dir)
    run_config = job_folder.run_config

    smoke_block = run_config.get("run", {}).get("smoke") or {}
    required = list(smoke_block.get("requiredEvidence") or [])

    try:
        artifact_text = Path(artifact_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RemoteCLIError(
            f"could not read artifact {artifact_path}: {exc}"
        ) from None
    try:
        stamp = json.loads(artifact_text)
    except json.JSONDecodeError as exc:
        raise RemoteCLIError(f"{artifact_path} is not valid JSON: {exc}") from None

    verdict = SHARD_IO.completeness(stamp, required)
    result = "pass" if verdict["complete"] else "fail"

    target = _target_for_job_dir(resolved_job_dir)
    smoke_ledger_path = _smoke_ledger_path(target, run_config["product"])

    event = {
        "kind": SMOKE_RESULT_KIND,
        "ts": _now(),
        "jobName": run_config["jobName"],
        "result": result,
        "commit": run_config["commit"],
        "worker": worker,
        "missing": verdict["missing"],
    }
    LEDGER.append(smoke_ledger_path, event)

    return {
        "result": result,
        "missing": verdict["missing"],
        "requiredEvidence": required,
        "smokeLedgerPath": smoke_ledger_path,
        "event": event,
    }


def latest_smoke_event(smoke_ledger_path: Path, job_name: str) -> dict | None:
    """The latest `smokeResult` line for `job_name` in `smoke_ledger_path`,
    by append order — last line wins, the same last-write-wins rule
    `ledger.fold()` already applies to its own log. `None` when the smoke
    ledger does not exist or holds no matching record.

    Extracted out of `cmd_readiness()` so a second caller —
    `proposal-implementation`'s own `probe` fact (design #744 section 9)
    — can find the SAME latest record `cmd_readiness()` itself binds
    against, rather than writing a second "walk `smoke.jsonl` for the
    newest match" loop that could quietly drift from this one.
    """
    if not smoke_ledger_path.exists():
        return None
    latest: dict | None = None
    for raw_line in smoke_ledger_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(event, dict)
            and event.get("kind") == SMOKE_RESULT_KIND
            and event.get("jobName") == job_name
        ):
            latest = event
    return latest


def cmd_readiness(*, job_dir: str | Path, worker: str) -> dict:
    """States whether `job_dir` is ready to run its full submission on
    `worker` — reports only, the same "resolves nothing" discipline
    `cmd_status()` already holds structurally (no `adapter` parameter):
    issues no submission, offers no menu. (This is remote-execution's own
    report command — not a call into `implementation_cli.py`'s own
    `cmd_probe`, a later task's territory this function does not touch.)

    Binds three facts on ONE record — the latest smoke record for this
    job, by append order in `smoke.jsonl` (last line wins, same rule
    `ledger.fold()` already applies to its own log): `result == "pass"`,
    `commit` equal to the job's OWN currently-pinned commit, `worker`
    equal to the worker asked about. No clock: nothing here reads or
    compares a timestamp. A record's usefulness expires the moment the
    job re-pins to a different commit or the worker changes — never after
    elapsed time.
    """
    resolved_job_dir = Path(job_dir).resolve()
    job_folder = JOBFOLDER.read(resolved_job_dir)
    run_config = job_folder.run_config

    target = _target_for_job_dir(resolved_job_dir)
    smoke_ledger_path = _smoke_ledger_path(target, run_config["product"])

    latest = latest_smoke_event(smoke_ledger_path, run_config["jobName"])

    if latest is None:
        return {
            "ready": False,
            "reason": "no smoke record on file for this job",
            "latestSmokeRecord": None,
            "staleness": dict(job_folder.staleness),
        }

    ready = (
        latest.get("result") == "pass"
        and latest.get("commit") == run_config["commit"]
        and latest.get("worker") == worker
    )
    reason = None
    if not ready:
        reason = (
            "latest smoke record does not match: expected result 'pass', "
            f"commit {run_config['commit']!r}, worker {worker!r}; got "
            f"result {latest.get('result')!r}, commit {latest.get('commit')!r}, "
            f"worker {latest.get('worker')!r}"
        )

    return {
        "ready": ready,
        "reason": reason,
        "latestSmokeRecord": latest,
        "staleness": dict(job_folder.staleness),
    }


def _construct_adapter(
    adapter_cls: type["ADAPTER.Adapter"],
    credentials_provider: Callable[[str], "ADAPTER.CredentialHandle"],
) -> "ADAPTER.Adapter":
    """Construct a registered adapter, handing it a credential provider only
    when its own constructor is written to accept one.

    The `Adapter` ABC constrains exactly six operations and nothing about
    `__init__` — a second adapter genuinely may take no arguments at all
    (this skill's own test doubles do exactly that), and that has to keep
    working, unmodified, for the seam's own "zero ledger/packer changes"
    guarantee to mean anything at the CLI's own construction site too.
    Introspecting the signature here, rather than trying `credentials=` and
    falling back on a bare `TypeError`, is what keeps a GENUINE defect
    inside a compliant adapter's own `__init__` from being swallowed as
    "this adapter must not want credentials".
    """
    try:
        parameters = inspect.signature(adapter_cls).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_credentials = "credentials" in parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    )
    if accepts_credentials:
        return adapter_cls(credentials=credentials_provider)
    return adapter_cls()


def _accounts_cli_for(adapter_cls: type["ADAPTER.Adapter"]) -> Path | None:
    """Read a resolved backend's own credential-materializing CLI location
    off its class, without this module ever naming which backend that is.

    `credentials.py` is the only producer of a `CredentialHandle`, but it
    holds no opinion about WHERE a given backend's own materialize command
    lives — that knowledge is confined to the one file per backend allowed
    to name a service at all, one level below this seam, through that
    module's own `CREDENTIAL_CLI` class attribute. `CREDENTIAL_CLI` is an
    ordinary class attribute, not one of the `Adapter` ABC's six
    operations, so an adapter that never declares one (this skill's own
    test doubles included) is read as `None` here — `credentials.provider()`
    only refuses if it is actually asked to materialize with neither this
    nor `--credential-dir` supplied.
    """
    return getattr(adapter_cls, "CREDENTIAL_CLI", None)


ADAPTERS_DIRNAME = "adapters"

# `--backend`'s raw value is the one part of this mechanism actually driven
# by untrusted input, so it is constrained before it ever reaches the
# filesystem: a bare identifier only, no `.`, `/`, or `\\` — which is what
# makes `..`, an absolute path, or any other directory-separator trick
# impossible to SPELL in the first place, not merely unlikely to be tried.
_BACKEND_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _load_backend_module(name: str) -> None:
    """Best-effort: if `<this file's own directory>/adapters/<name>.py`
    exists, exec it once so its own top-level `ADAPTER.register(...)` (and,
    where present, `ADAPTER.register_metadata(...)`) calls run — before
    `ADAPTER.resolve(name)` is ever asked to find anything under that same
    name.

    This is the whole mechanism that lets `--backend` name a concrete
    adapter without this module ever importing one directly: a module
    dropped into `adapters/` becomes reachable through `--backend <its own
    filename, minus .py>` with no change to this file at all. It is also
    what keeps this file free of naming a service itself — `name` arrives
    at runtime, off the command line, typed by whoever is running this
    command; nothing in this function or anywhere else in this module ever
    spells a service's name as a literal.

    `name` is constrained BEFORE it ever touches the filesystem:
    `_BACKEND_NAME_RE` admits letters, digits, `_` and `-` only, so `..`, a
    leading `/`, or a `\\` component can never be spelled in it at all —
    refused structurally, not merely rejected after the fact by a
    containment check that a differently-shaped hostile value might slip
    past. The resolved candidate path is then checked a second, independent
    way — `candidate.relative_to(adapters_dir)` — so a future loosening of
    the regex alone could never reopen this by itself.

    Any value failing either check, or naming no file, is left alone here,
    silently: this function only ever ADDS a registration; it never raises
    for a name nothing backs, and it never removes or second-guesses a
    registration a caller already made directly (this skill's own test
    suite registers several fake adapters exactly that way, under names no
    file in `adapters/` ever backs). `ADAPTER.resolve()` still runs
    immediately after every call site below, and stays the one place a
    genuinely unknown backend is refused — now naming what IS registered,
    which is what turns an unknown value into an actionable message instead
    of a dead end.
    """
    if not _BACKEND_NAME_RE.match(name):
        return

    adapters_dir = (Path(__file__).resolve().parent / ADAPTERS_DIRNAME).resolve()
    candidate = (adapters_dir / f"{name}.py").resolve()
    try:
        candidate.relative_to(adapters_dir)
    except ValueError:
        return
    if not candidate.is_file():
        return

    module_name = f"remote_execution_adapters_{name.replace('-', '_')}"
    if module_name in sys.modules:
        return

    spec = importlib.util.spec_from_file_location(module_name, candidate)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    # Registered only once it has actually run — the same "retryable on
    # failure, never cached half-loaded" ordering `_load_source_digest()`
    # above already uses, for the same reason.
    spec.loader.exec_module(module)
    sys.modules[module_name] = module


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remote_cli",
        description="Forge-owned remote execution CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit = subparsers.add_parser(
        "submit", help="submit one notebook to a registered backend's worker"
    )
    submit.add_argument("--target", required=True, type=Path)
    submit.add_argument("--entrypoint", required=True, type=Path)
    submit.add_argument(
        "--worker", required=False, default=None,
        help="optional: the account to submit under. Omitted, `packer.select()` "
        "picks the first healthy account with capacity, in the accounts CLI's "
        "own declared order — naming one an existing decision, never a "
        "requirement this command asks the caller to make. Naming a specific "
        "account is still a legitimate override and is never gated by "
        "capacity the way automatic selection is: an unhealthy NAMED account "
        "refuses outright rather than silently falling back to another one.",
    )
    submit.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    submit.add_argument("--requested", type=int, default=1)
    submit.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )
    submit.add_argument(
        "--product", default=None,
        help="override: which product's ledger this submission belongs to; wins over a "
        "job folder's own declared run-config.json product and over the legacy shape's "
        "<Name> component",
    )
    submit.add_argument(
        "--smoke", action="store_true",
        help="submit a rehearsal run: mode='smoke', recorded to smoke.jsonl, never ledger.jsonl",
    )
    submit.add_argument(
        "--unit", dest="units", action="append", default=None,
        help="repeatable: the exact same flag `distribute` declares. Switches "
        "`submit` into campaign mode -- `packer.distribute()` replaces "
        "`packer.select()`/`packer.plan()`, spreading across every healthy "
        "account instead of stopping at the first one. Mutually exclusive "
        "with --worker: campaign mode has no single named account to select.",
    )
    submit.add_argument(
        "--consent", default=None,
        help="required for EVERY submission, campaign or single-send, "
        "rehearsal or not: the token authorizing this exact pin, "
        "entrypoint, and ordered unit list (empty for a single send). "
        "With --unit, `distribute --unit ...` mints and prints it first. "
        "Without --unit, there is no minting command -- run `submit` once "
        "with no --consent and it refuses, printing the exact token to "
        "pass back on a second, deliberate invocation. Read only from "
        "parsed argv -- never a config key, an environment variable, or "
        "any switch that outlives this process.",
    )

    status = subparsers.add_parser(
        "status", help="report the fold for one product's ledger; resolves nothing"
    )
    status.add_argument("--target", required=True, type=Path)
    status.add_argument("--entrypoint", required=True, type=Path)

    distribute = subparsers.add_parser(
        "distribute",
        help="report how opaque work units would spread across every healthy "
        "worker account right now; issues no work and records nothing",
    )
    distribute.add_argument("--target", required=True, type=Path)
    distribute.add_argument("--entrypoint", required=True, type=Path)
    distribute.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    distribute.add_argument(
        "--unit", dest="units", action="append", required=True,
        help="repeatable: one opaque work-unit identifier. Never comma-separated -- "
        "a separator would impose structure on an identifier this command, like "
        "packer.distribute() underneath it, treats as opaque; a unit containing "
        "its own comma would otherwise be split.",
    )
    distribute.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )

    poll = subparsers.add_parser(
        "poll", help="ask the adapter for one submission's status"
    )
    poll.add_argument("--submission-id", required=True)
    poll.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    poll.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )

    fetch = subparsers.add_parser(
        "fetch",
        help="materialize one submission's result, quarantining it when it is not current",
    )
    fetch.add_argument("--target", required=True, type=Path)
    fetch.add_argument("--entrypoint", required=True, type=Path)
    fetch.add_argument("--submission-id", required=True)
    fetch.add_argument("--dest", required=True, type=Path)
    fetch.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    fetch.add_argument(
        "--force",
        action="store_true",
        help="remove an already-materialized destination and re-fetch, "
        "instead of refusing; a leftover <dest>.partial/ from a fetch "
        "that never finished is never cleared by this flag",
    )
    fetch.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )
    fetch.add_argument(
        "--smoke", action="store_true",
        help="when the submission id is recorded in both ledgers with "
        "agreeing entrypoint/worker, resolve to smoke.jsonl instead of the "
        "default main ledger.jsonl; does not suppress the refusal when the "
        "two records disagree",
    )

    reconcile = subparsers.add_parser(
        "reconcile",
        help="compare the ledger against the adapter's list_active() in both directions",
    )
    reconcile.add_argument("--target", required=True, type=Path)
    reconcile.add_argument("--entrypoint", required=True, type=Path)
    # Stays required, deliberately not widened to `submit`'s optional
    # selection: `reconcile` compares ONE already-known account's own
    # local ledger against that SAME account's remote state — it names no
    # new submission decision at all, so there is no "which account"
    # fork here for automatic selection to remove in the first place.
    reconcile.add_argument("--worker", required=True)
    reconcile.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    reconcile.add_argument(
        "--resolve",
        action="store_true",
        help="human-invoked only: append errored(reason=not-found-at-service) for each orphanLocal id",
    )
    reconcile.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )
    reconcile.add_argument(
        "--smoke", action="store_true",
        help="within --resolve: when an orphan's submission id is recorded "
        "in both ledgers with agreeing entrypoint/worker, resolve it to "
        "smoke.jsonl instead of the default main ledger.jsonl; does not "
        "suppress the refusal when the two records disagree",
    )

    generate_job = subparsers.add_parser(
        "generate-job",
        help="generate a forge-owned job folder at <target>/tools/<service>/<job-name>/",
    )
    generate_job.add_argument("--target", required=True, type=Path)
    generate_job.add_argument("--service", required=True)
    generate_job.add_argument("--job-name", required=True)
    generate_job.add_argument("--product", required=True)
    generate_job.add_argument(
        "--commit", default=None,
        help=(
            "the pinned commit, lowercase 40- or 64-hex. Optional: omitted, "
            "it defaults to the target's HEAD, which is a safe default only "
            "because generation refuses a dirty tree and a pin that is not "
            "HEAD. Never resolved from the remote"
        ),
    )
    generate_job.add_argument("--repo-url", required=True)
    generate_job.add_argument("--repo-ref", required=True)
    generate_job.add_argument(
        "--clone-path", dest="clone_paths", action="append", default=[],
        help="repeatable: one declared clone path, relative to the clone's own root",
    )
    generate_job.add_argument("--run-module", required=True)
    generate_job.add_argument("--run-function", required=True)
    generate_job.add_argument(
        "--run-kwargs", default="{}", help="a JSON object, passed to run.function as kwargs"
    )
    generate_job.add_argument("--smoke-module", default=None)
    generate_job.add_argument("--smoke-function", default=None)
    generate_job.add_argument("--smoke-kwargs", default=None, help="a JSON object")
    generate_job.add_argument(
        "--smoke-required-evidence", dest="smoke_required_evidence",
        action="append", default=[],
        help="repeatable: a field path shard_io.completeness() requires of a smoke "
        "run's shard.json; refused without --smoke-module/--smoke-function set",
    )
    generate_job.add_argument(
        "--regenerate", action="store_true",
        help="replace an existing job folder atomically instead of refusing",
    )
    generate_job.add_argument(
        "--accept-unresolved", action="store_true",
        help=(
            "record uncertain imports found by resolve_clone_paths() in "
            "run-config.json's unresolvedImports instead of refusing; never "
            "bypasses a computedNotDeclared refusal"
        ),
    )
    generate_job.add_argument(
        "--accept-unresolved-reads", action="store_true",
        help=(
            "record uncertain reads found by resolve_clone_paths() in "
            "run-config.json's unresolvedReads instead of refusing; a "
            "SEPARATE flag from --accept-unresolved — neither waives the "
            "other's refusal, and this never bypasses a "
            "computedReadsNotDeclared refusal"
        ),
    )
    generate_job.add_argument(
        "--accelerator-kind", dest="accelerator_kind", default=None,
        help="override: the expected accelerator kind (e.g. 'cuda'). Omitted "
        "together with --accelerator-architecture, the service adapter's own "
        "registered default is used instead (never a forge-invented value); "
        "given without --accelerator-architecture, refused.",
    )
    generate_job.add_argument(
        "--accelerator-architecture", dest="accelerator_architectures",
        action="append", default=None,
        help="repeatable override: an expected accelerator architecture "
        "(e.g. 'sm_60'). Given without --accelerator-kind, refused.",
    )
    generate_job.add_argument(
        "--environment-requirement", dest="environment_requirements",
        action="append", default=None,
        help="repeatable: a pip requirement specifier for the target's own "
        "declared environment install — target knowledge, never a service "
        "or forge default.",
    )
    generate_job.add_argument(
        "--environment-index-url", dest="environment_index_url", default=None,
        help="optional index URL for --environment-requirement; given "
        "without at least one --environment-requirement, refused.",
    )

    smoke = subparsers.add_parser(
        "smoke", help="smoke-run bookkeeping: recording a rehearsal's evidence-derived verdict"
    )
    smoke_subparsers = smoke.add_subparsers(dest="smoke_command", required=True)
    smoke_record = smoke_subparsers.add_parser(
        "record",
        help="record a smoke run's verdict from its returned shard.json, "
        "derived from shard_io.completeness() — never a human assertion",
    )
    smoke_record.add_argument("--job-dir", required=True, type=Path)
    smoke_record.add_argument(
        "--from-artifact", required=True, type=Path, dest="from_artifact"
    )
    # Stays required: a smoke record files evidence for a rehearsal that
    # already RAN under one specific, already-known account — it reports
    # on a submission decision already made elsewhere, never makes one of
    # its own for automatic selection to take over.
    smoke_record.add_argument("--worker", required=True)

    readiness = subparsers.add_parser(
        "readiness",
        help="state whether a job is ready for a full submission on a worker; "
        "reports only, issues no submission",
    )
    readiness.add_argument("--job-dir", required=True, type=Path)
    # Stays required: readiness reports whether a job is fit to submit ON
    # a named account (its capacity, its own pending state) — it answers
    # "is THIS account ready", not "which account should this go to", so
    # there is nothing here for automatic selection to stand in for.
    readiness.add_argument("--worker", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "submit":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_submit(
                target=args.target,
                entrypoint=args.entrypoint,
                worker=args.worker,
                requested=args.requested,
                adapter=_construct_adapter(adapter_cls, provider),
                product=args.product,
                smoke=args.smoke,
                units=args.units,
                consent=args.consent,
            )
        except (RemoteCLIError, PACKER.PackerError, LEDGER.LedgerError,
                ADAPTER.AdapterError, JOBFOLDER.JobFolderError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        if args.units:
            # Campaign mode's own JSON shape -- `assignments[]`/
            # `unplaced[]`/`skipped[]`, mirroring `distribute`'s own CLI
            # rendering, never the single-submission shape below.
            print(
                json.dumps(
                    {**result, "ledgerPath": str(result["ledgerPath"])},
                    sort_keys=True,
                )
            )
            if not result["assignments"] and result["unplaced"]:
                return 1
            return 0

        print(
            json.dumps(
                {
                    "submissionId": result["submission"].id,
                    "worker": result["submission"].worker,
                    "granted": result["plan"].granted,
                    "ledgerPath": str(result["ledgerPath"]),
                    "staleness": result["staleness"],
                    "smoke": result["smoke"],
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "status":
        try:
            result = cmd_status(target=args.target, entrypoint=args.entrypoint)
        except (RemoteCLIError, LEDGER.LedgerError, ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        # `default=str` rather than naming each `Path` key by hand: the
        # hand-named form stringified the top-level `ledgerPath` and left
        # `smoke.ledgerPath` a `Path`, so this command could never print at
        # all. Naming keys one at a time is what made a nested one
        # unreachable; naming none makes the next one harmless.
        print(json.dumps(result, sort_keys=True, default=str))
        return 0

    if args.command == "distribute":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_distribute(
                target=args.target,
                entrypoint=args.entrypoint,
                adapter=_construct_adapter(adapter_cls, provider),
                units=args.units,
            )
        except (RemoteCLIError, PACKER.PackerError, LEDGER.LedgerError,
                ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(json.dumps(result, sort_keys=True))
        if result["places"] == 0 and result["units"] > 0:
            return 1
        return 0

    if args.command == "poll":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            status_result = cmd_poll(
                submission_id=args.submission_id, adapter=_construct_adapter(adapter_cls, provider)
            )
        except (RemoteCLIError, ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(
            json.dumps(
                {"state": status_result.state, "detail": status_result.detail},
                sort_keys=True,
            )
        )
        return 0

    if args.command == "fetch":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_fetch(
                target=args.target,
                entrypoint=args.entrypoint,
                submission_id=args.submission_id,
                dest=args.dest,
                adapter=_construct_adapter(adapter_cls, provider),
                force=args.force,
                smoke=args.smoke,
            )
        except (RemoteCLIError, LEDGER.LedgerError, ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        arbitration = result["arbitration"]
        if arbitration is not None:
            print(arbitration, file=sys.stderr)

        print(
            json.dumps(
                {
                    "verdict": result["verdict"],
                    "complete": result["complete"],
                    "path": str(result["path"]),
                    "event": result["event"],
                    "staleness": result["staleness"],
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "reconcile":
        try:
            _load_backend_module(args.backend)
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_reconcile(
                target=args.target,
                entrypoint=args.entrypoint,
                worker=args.worker,
                adapter=_construct_adapter(adapter_cls, provider),
                resolve=args.resolve,
                smoke=args.smoke,
            )
        except (RemoteCLIError, LEDGER.LedgerError, ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        arbitration = result.pop("arbitration")
        for note in arbitration:
            print(note, file=sys.stderr)

        print(json.dumps(result, sort_keys=True))
        return 0

    if args.command == "generate-job":
        # `--service` is `--backend` under a second name: both select a module
        # in `adapters/`, and generation resolves a metadata assembler out of
        # the same registry the other four commands resolve an adapter from.
        # The side-loader was wired to `args.backend` at all four of its call
        # sites, so this one command — the first anybody runs to reach a
        # service at all — asked an empty registry and refused a correct
        # invocation.
        _load_backend_module(args.service)
        try:
            destination = JOBFOLDER.generate_job(
                target=args.target,
                service=args.service,
                job_name=args.job_name,
                product=args.product,
                commit=args.commit,
                repo_url=args.repo_url,
                repo_ref=args.repo_ref,
                clone_paths=args.clone_paths,
                run_module=args.run_module,
                run_function=args.run_function,
                run_kwargs=json.loads(args.run_kwargs),
                smoke_module=args.smoke_module,
                smoke_function=args.smoke_function,
                smoke_kwargs=json.loads(args.smoke_kwargs) if args.smoke_kwargs else None,
                smoke_required_evidence=args.smoke_required_evidence or None,
                regenerate=args.regenerate,
                accept_unresolved=args.accept_unresolved,
                accept_unresolved_reads=args.accept_unresolved_reads,
                accelerator_kind=args.accelerator_kind,
                accelerator_architectures=args.accelerator_architectures,
                environment_requirements=args.environment_requirements,
                environment_index_url=args.environment_index_url,
            )
        except (JOBFOLDER.JobFolderError, ADAPTER.AdapterError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        # Routes through the SAME single reader every other job-folder-
        # touching command uses (design #744 §4) — a job folder is never
        # even momentarily reported without its staleness alongside it.
        job_folder = JOBFOLDER.read(destination)
        staleness = dict(job_folder.staleness)
        # `commitSource` is operator feedback and lives on stdout ONLY. It
        # describes how the caller typed an argument, not a fact about the
        # job, and `run-config.json` records facts about the job. The pin
        # itself is read back out of the written config rather than out of
        # `args`, so what is reported is what was actually recorded.
        print(
            json.dumps(
                {
                    "jobFolder": str(destination),
                    "staleness": staleness,
                    "commit": job_folder.run_config["commit"],
                    # Three sources, not two, and the third is why this is
                    # derived rather than inferred from the flag alone: an
                    # omitted `--commit` may resolve to HEAD or to the declared
                    # ref's published tip, and a reader who is told
                    # `default-head` when the pin is neither has been told the
                    # wrong thing about which code will run.
                    "commitSource": JOBFOLDER.pin_source(
                        args.target, args.commit, job_folder.run_config["commit"]),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "smoke":
        if args.smoke_command == "record":
            try:
                result = cmd_smoke_record(
                    job_dir=args.job_dir,
                    artifact_path=args.from_artifact,
                    worker=args.worker,
                )
            except (RemoteCLIError, LEDGER.LedgerError, JOBFOLDER.JobFolderError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1

            print(
                json.dumps(
                    {
                        "result": result["result"],
                        "missing": result["missing"],
                        "requiredEvidence": result["requiredEvidence"],
                        "smokeLedgerPath": str(result["smokeLedgerPath"]),
                    },
                    sort_keys=True,
                )
            )
            return 0
        return 1

    if args.command == "readiness":
        try:
            result = cmd_readiness(job_dir=args.job_dir, worker=args.worker)
        except (RemoteCLIError, JOBFOLDER.JobFolderError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(json.dumps(result, sort_keys=True))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
