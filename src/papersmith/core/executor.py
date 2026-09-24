"""Resolve execution profiles and dispatch local or remote jobs."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..bridges.python import mapped_returncode
from ..core.exit_codes import EXECUTION_ERROR, SUCCESS, USER_ERROR
from ..errors import ExecutionError, UserError
from . import config, ledger


def _job_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"job-{stamp}-{os.getpid()}"


def _substitute(value: str, *, paper_slug: str, job_id: str, shard_value: Any = None) -> str:
    result = value.replace("{paper_slug}", paper_slug).replace("{job_id}", job_id)
    if shard_value is not None:
        result = result.replace("{shard_value}", str(shard_value))
    return result


def _profile_jobs(root: Path, profile_name: str, target_name: str, profile: dict,
                  *, shard: int | None, job_id: str) -> list[dict[str, Any]]:
    entrypoint = profile.get("entrypoint")
    if not isinstance(entrypoint, str):
        raise UserError(f"execution_profiles.{profile_name}.entrypoint must be a string")
    sharding = profile.get("sharding") or {}
    enabled = bool(sharding.get("enabled", False))
    values = list(sharding.get("values", [])) if enabled else [None]
    if shard is not None:
        if not enabled:
            raise UserError(f"profile {profile_name} does not enable sharding")
        if shard < 0 or shard >= len(values):
            raise UserError(f"shard index {shard} is outside the profile's {len(values)} values")
        values = [values[shard]]
    jobs: list[dict[str, Any]] = []
    for value in values:
        rendered = _substitute(entrypoint, paper_slug=root.name, job_id=job_id, shard_value=value)
        command = shlex.split(rendered)
        if value is not None and sharding.get("parameter"):
            command.extend([str(sharding["parameter"]), str(value)])
        env = {
            str(key): _substitute(str(item), paper_slug=root.name, job_id=job_id, shard_value=value)
            for key, item in (profile.get("env_vars") or {}).items()
        }
        jobs.append({
            "command": command,
            "command_text": shlex.join(command),
            "entrypoint": rendered,
            "env": env,
            "shard_value": value,
            "target": target_name,
        })
    return jobs


def _local_job(root: Path, profile_name: str, job_id: str, job: dict[str, Any], profile: dict) -> int:
    environment = os.environ.copy()
    environment.update(job["env"])
    environment.update({
        "PAPERSMITH_PROFILE": profile_name,
        "PAPERSMITH_JOB_ID": job_id,
    })
    if job["shard_value"] is not None:
        environment["PAPERSMITH_SHARD"] = str(job["shard_value"])
    timeout = profile.get("timeout_seconds")
    try:
        result = subprocess.run(
            job["command"], cwd=root, env=environment,
            capture_output=False, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return EXECUTION_ERROR
    except OSError:
        return EXECUTION_ERROR
    return SUCCESS if result.returncode == 0 else EXECUTION_ERROR


def _remote_command(root: Path, job: dict[str, Any], target: dict, *, consent: str | None) -> list[str]:
    script = root / "skills" / "remote-execution" / "scripts" / "remote_cli.py"
    entrypoint = None
    for token in shlex.split(job["entrypoint"]):
        if token.startswith("-") or token in {"python", "python3", "pytest", "papermill"}:
            continue
        candidate = Path(token)
        if candidate.suffix in {".py", ".ipynb"}:
            entrypoint = candidate if candidate.is_absolute() else root / candidate
            break
    if entrypoint is None:
        entrypoint = root / "runner.ipynb"
    command = [
        os.fspath(__import__("sys").executable), os.fspath(script), "submit",
        "--target", str(root), "--entrypoint", str(entrypoint),
        "--backend", str(target.get("backend", "kaggle")),
    ]
    if job["shard_value"] is not None:
        command.extend(["--unit", str(job["shard_value"])])
    if consent:
        command.extend(["--consent", consent])
    return command


def _slurm_command(job: dict[str, Any], target: dict) -> list[str]:
    host = target.get("host")
    if not isinstance(host, str) or not host:
        raise UserError("remote-ssh target requires host")
    command = ["ssh", host, "sbatch"]
    for key, flag in (("partition", "--partition"), ("walltime", "--time")):
        if target.get(key):
            command.extend([flag, str(target[key])])
    command.extend(["--wrap", job["command_text"]])
    return command


def run_profile(workspace: str | Path, profile_name: str, *, target_override: str | None = None,
                dry_run: bool = False, shard: int | None = None,
                consent: str | None = None) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    yaml = config.load_papersmith_yaml(root)
    profiles = yaml["execution_profiles"]
    if profile_name not in profiles:
        raise UserError(f"unknown execution profile: {profile_name}")
    profile = profiles[profile_name]
    targets = yaml["compute_targets"]["targets"]
    target_name = target_override or profile.get("target") or yaml["compute_targets"]["default"]
    if target_name not in targets:
        raise UserError(f"unknown compute target: {target_name}")
    target = targets[target_name]
    job_id = _job_id()
    jobs = _profile_jobs(root, profile_name, target_name, profile, shard=shard, job_id=job_id)
    provider = target["provider"]
    results: list[dict[str, Any]] = []
    for job in jobs:
        command: list[str] | None = None
        if provider == "local":
            if dry_run:
                code = SUCCESS
                command = job["command"]
            else:
                code = _local_job(root, profile_name, job_id, job, profile)
        elif provider == "kaggle":
            command = _remote_command(root, job, target, consent=consent)
            if dry_run:
                code = SUCCESS
            else:
                try:
                    child = subprocess.run(command, cwd=root, check=False)
                    code = mapped_returncode(child)
                except OSError:
                    code = EXECUTION_ERROR
        elif provider == "remote-ssh":
            command = _slurm_command(job, target)
            if dry_run:
                code = SUCCESS
            else:
                try:
                    child = subprocess.run(command, cwd=root, check=False)
                    code = mapped_returncode(child)
                except OSError:
                    code = EXECUTION_ERROR
        else:
            raise UserError(f"unsupported target provider: {provider}")
        event = {
            "profile": profile_name,
            "target": target_name,
            "provider": provider,
            "job_id": job_id,
            "shard_value": job["shard_value"],
            "dry_run": dry_run,
            "exit": code,
            "command": command or job["command"],
        }
        ledger.append(root, event)
        results.append(event)
    status = "ok" if all(item["exit"] == 0 for item in results) else "failed"
    return {"status": status, "job_id": job_id, "profile": profile_name,
            "target": target_name, "jobs": results}


def print_result(result: dict[str, Any], *, dry_run: bool) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))
    if dry_run:
        print("dry-run: no job was dispatched", file=sys.stderr)


def register(subparsers) -> None:
    parser = subparsers.add_parser("run", help="run an execution profile")
    parser.add_argument("profile_name")
    parser.add_argument("--target", default=None, help="override the profile's compute target")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shard", type=int, default=None)
    parser.add_argument("--consent", default=None, help="remote submission consent token")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    result = run_profile(
        args.directory, args.profile_name, target_override=args.target,
        dry_run=args.dry_run, shard=args.shard, consent=args.consent,
    )
    print_result(result, dry_run=args.dry_run)
    return SUCCESS if result["status"] == "ok" else EXECUTION_ERROR
