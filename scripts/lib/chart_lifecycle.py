"""Package integrity and ordered evidence for the opt-in chart lifecycle."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from lib.chart_testing import lifecycle_lane
from lib.names import bounded_resource_name


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonicalize_package(source: Path, destination: Path) -> None:
    """Normalize Helm's non-deterministic tar/gzip metadata without changing chart content."""
    if source.resolve() == destination.resolve():
        raise ValueError("canonical package input and output must differ")
    with tarfile.open(source, "r:gz") as archive:
        members = archive.getmembers()
        if any(not (member.isfile() or member.isdir()) for member in members):
            raise ValueError("chart package contains an unsupported non-regular member")
        normalized = []
        for member in sorted(members, key=lambda item: item.name):
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("chart package contains an unsafe member path")
            member.mtime = 0
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.pax_headers = {}
            data = archive.extractfile(member).read() if member.isfile() else None
            normalized.append((member, data))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, compresslevel=9, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for member, data in normalized:
                    if data is None:
                        archive.addfile(member)
                    else:
                        archive.addfile(member, io.BytesIO(data))


def package_metadata(path: Path) -> dict[str, Any]:
    result = subprocess.run(["helm", "show", "chart", str(path)], check=True, text=True, capture_output=True)
    document = yaml.safe_load(result.stdout)
    if not isinstance(document, dict) or not isinstance(document.get("name"), str) or not isinstance(document.get("version"), str):
        raise ValueError(f"chart package metadata is invalid: {path}")
    return {"path": str(path), "name": document["name"], "version": document["version"], "packageDigest": digest(path)}


def preflight(root: Path, chart: str, config: dict[str, Any], work: Path) -> dict[str, Any]:
    """Verify exact package identities and bind current bytes to reviewed source."""
    root = root.resolve()
    chart_dir = (root / chart).resolve()
    chart_yaml = yaml.safe_load((chart_dir / "Chart.yaml").read_text(encoding="utf-8"))
    if not isinstance(chart_yaml, dict):
        raise ValueError("current Chart.yaml must be a mapping")
    chart_name = str(chart_yaml.get("name", ""))
    chart_version = str(chart_yaml.get("version", ""))
    if not chart_name or not chart_version:
        raise ValueError("current chart name and version are required")
    upgrade = config["upgrade"]
    previous = package_metadata((root / upgrade["previousPackage"]).resolve())
    current = package_metadata((root / upgrade["currentPackage"]).resolve())
    for label, package in (("previous", previous), ("current", current)):
        if package["name"] != chart_name:
            raise ValueError(f"{label} package chart name does not match current chart")
    if current["version"] != chart_version:
        raise ValueError("current package version does not match current Chart.yaml version")
    if previous["version"] == current["version"]:
        raise ValueError("previous and current package versions must be distinct")
    if previous["packageDigest"] == current["packageDigest"]:
        raise ValueError("previous and current package content digests must be distinct")

    copied = work / "reproducible" / chart_dir.name
    destination = work / "reproducible-package"
    shutil.copytree(chart_dir, copied)
    destination.mkdir(parents=True)
    for path in copied.rglob("*"):
        if path.is_file():
            os.utime(path, (0, 0))
    subprocess.run(["helm", "package", str(copied), "--destination", str(destination)], check=True, capture_output=True)
    expected = destination / f"{chart_name}-{chart_version}.tgz"
    if not expected.is_file():
        raise ValueError("reproducible current chart package is missing")
    canonical = work / "canonical-current.tgz"
    canonicalize_package(expected, canonical)
    if canonical.read_bytes() != (root / upgrade["currentPackage"]).read_bytes():
        raise ValueError("current package is not the reproducible package of reviewed chart source")
    return {"chartName": chart_name, "previous": previous, "current": current}


def verify_unchanged(packages: dict[str, Any]) -> None:
    for label in ("previous", "current"):
        package = packages[label]
        if digest(Path(package["path"])) != package["packageDigest"]:
            raise ValueError(f"{label} package changed after lifecycle preflight")


def initial_state(packages: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    chart_name = packages["chartName"]
    release = bounded_resource_name(chart_name, 53)
    phases = []
    for phase, label in (("install", "previous"), ("upgrade", "current")):
        package = packages[label]
        phases.append({
            "phase": phase,
            "version": package["version"],
            "packageDigest": package["packageDigest"],
            "status": "not-run",
            "converged": False,
            "assertions": "not-run",
            "revision": 0,
            "releaseName": release,
            "namespace": "default",
            "clusterName": args.cluster,
            "durationSeconds": 0,
        })
    state = {
        "schema": "inari.lane-result.v1",
        "lane": lifecycle_lane(args.chart),
        "status": "failed",
        "chartName": chart_name,
        "chartPath": Path(args.chart).as_posix(),
        "releaseName": release,
        "namespace": "default",
        "clusterName": args.cluster,
        "sourceSha": args.source_sha,
        "workflowSha": args.workflow_sha,
        "runId": str(args.run_id),
        "runAttempt": str(args.run_attempt),
        "startedAt": args.started_at,
        "phases": phases,
    }
    if args.pr_head_sha:
        state["prHeadSha"] = args.pr_head_sha
    return state


def mark_phase(path: Path, args: argparse.Namespace) -> None:
    state = json.loads(path.read_text(encoding="utf-8"))
    phase = next(item for item in state["phases"] if item["phase"] == args.phase)
    phase["status"] = args.status
    if args.assertions:
        phase["assertions"] = args.assertions
    if args.revision is not None:
        phase["revision"] = args.revision
    if args.duration is not None:
        phase["durationSeconds"] = args.duration
    phase["converged"] = phase["status"] == "passed" and phase["assertions"] == "passed"
    path.write_text(json.dumps(state, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def finalize(path: Path, args: argparse.Namespace) -> None:
    state = json.loads(path.read_text(encoding="utf-8"))
    for phase, duration in zip(state["phases"], (args.install_duration, args.upgrade_duration)):
        if duration >= 0:
            phase["durationSeconds"] = duration
        if args.outcome == "failed":
            if phase["status"] == "running":
                phase["status"] = "failed"
            if phase["assertions"] == "running":
                phase["assertions"] = "failed"
        phase["converged"] = phase["status"] == "passed" and phase["assertions"] == "passed"
    if args.outcome == "passed" and any(
        phase["status"] != "passed" or not phase["converged"] or phase["assertions"] != "passed"
        for phase in state["phases"]
    ):
        raise ValueError("cannot emit passing chart lifecycle evidence with an incomplete phase")
    state.update({
        "status": args.outcome,
        "finishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "clusterCreateCount": args.create_count,
        "clusterDeleteCount": args.delete_count,
        "freshState": True,
        "cleanedUp": args.cleaned_up == "true",
        "fixtureOnly": False,
        "evidenceScope": "application",
        "appEvidenceEligible": True,
        "functionalE2E": False,
        "deployedReadiness": "not-tested",
        "totalDurationSeconds": args.total_duration,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    canonical = commands.add_parser("canonicalize-package")
    canonical.add_argument("--input", type=Path, required=True)
    canonical.add_argument("--output", type=Path, required=True)
    preflight_parser = commands.add_parser("preflight")
    preflight_parser.add_argument("--root", type=Path, required=True)
    preflight_parser.add_argument("--chart", required=True)
    preflight_parser.add_argument("--config", type=Path, required=True)
    preflight_parser.add_argument("--work", type=Path, required=True)
    unchanged = commands.add_parser("verify-unchanged")
    unchanged.add_argument("--packages", type=Path, required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--packages", type=Path, required=True)
    initialize.add_argument("--output", type=Path, required=True)
    initialize.add_argument("--chart", required=True)
    initialize.add_argument("--cluster", required=True)
    initialize.add_argument("--source-sha", required=True)
    initialize.add_argument("--pr-head-sha", default="")
    initialize.add_argument("--workflow-sha", required=True)
    initialize.add_argument("--run-id", required=True)
    initialize.add_argument("--run-attempt", required=True)
    initialize.add_argument("--started-at", required=True)
    phase = commands.add_parser("phase")
    phase.add_argument("--state", type=Path, required=True)
    phase.add_argument("--phase", choices=("install", "upgrade"), required=True)
    phase.add_argument("--status", choices=("running", "passed", "failed"), required=True)
    phase.add_argument("--assertions", choices=("running", "passed", "failed"))
    phase.add_argument("--revision", type=int)
    phase.add_argument("--duration", type=int)
    finish = commands.add_parser("finish")
    finish.add_argument("--state", type=Path, required=True)
    finish.add_argument("--output", type=Path, required=True)
    finish.add_argument("--outcome", choices=("passed", "failed"), required=True)
    finish.add_argument("--create-count", type=int, required=True)
    finish.add_argument("--delete-count", type=int, required=True)
    finish.add_argument("--cleaned-up", choices=("true", "false"), required=True)
    finish.add_argument("--install-duration", type=int, default=-1)
    finish.add_argument("--upgrade-duration", type=int, default=-1)
    finish.add_argument("--total-duration", type=int, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "canonicalize-package":
            canonicalize_package(args.input, args.output)
        elif args.command == "preflight":
            config = json.loads(args.config.read_text(encoding="utf-8"))
            packages = preflight(args.root, args.chart, config, args.work)
            print(json.dumps(packages, separators=(",", ":"), sort_keys=True))
        elif args.command == "verify-unchanged":
            verify_unchanged(json.loads(args.packages.read_text(encoding="utf-8")))
        elif args.command == "init":
            packages = json.loads(args.packages.read_text(encoding="utf-8"))
            args.output.write_text(json.dumps(initial_state(packages, args), separators=(",", ":"), sort_keys=True), encoding="utf-8")
        elif args.command == "phase":
            mark_phase(args.state, args)
        elif args.command == "finish":
            finalize(args.state, args)
    except (OSError, ValueError, TypeError, KeyError, StopIteration, json.JSONDecodeError, yaml.YAMLError, subprocess.CalledProcessError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
