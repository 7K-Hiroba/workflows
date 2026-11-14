#!/usr/bin/env python3
"""Validate a complete release, coordinate channels, and report recovery state."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import SHA_RE  # noqa: E402
from lib.release_contract import contract, validate_artifact  # noqa: E402

DIGEST_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


def write_report(path: Path, status: str, moves: list[dict[str, Any]], required: list[dict[str, str]], error: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": "inari.channel-reconciliation.v1",
        "status": status,
        "moves": moves,
        "reconciliationRequired": required,
    }
    if error:
        document["error"] = error
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def channel_digest(repository: str, channel: str, *, allow_absent: bool) -> str:
    result = subprocess.run(["crane", "digest", f"{repository}:{channel}"], text=True, capture_output=True, check=False)
    if result.returncode == 0:
        digest = result.stdout.strip()
        if not DIGEST_RE.fullmatch(digest):
            raise ValueError(f"invalid channel digest for {repository}:{channel}")
        return digest
    detail = (result.stderr + result.stdout).lower()
    if allow_absent and any(marker in detail for marker in ("name_unknown", "manifest unknown", "not found", "404")):
        return ""
    raise ValueError(f"cannot read channel {repository}:{channel}: {result.stderr.strip() or result.stdout.strip()}")


def reconcile(moves: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Restore previous digests where possible; never hide an unreconciled channel."""
    required: list[dict[str, str]] = []
    for move in moves:
        repository, channel = move["repository"], move["channel"]
        previous = move["previousDigest"]
        try:
            current = channel_digest(repository, channel, allow_absent=False)
            move["currentDigest"] = current
            if current == previous:
                continue
            if not previous:
                raise ValueError("channel did not exist before the move; safe untag requires registry-specific reconciliation")
            subprocess.run(["oras", "tag", f"{repository}@{previous}", channel], check=True, capture_output=True)
            restored = channel_digest(repository, channel, allow_absent=False)
            move["currentDigest"] = restored
            if restored != previous:
                raise ValueError(f"rollback digest is {restored}, expected {previous}")
        except (ValueError, subprocess.CalledProcessError) as exc:
            required.append({"repository": repository, "channel": channel, "previousDigest": previous, "reason": str(exc)})
    return required


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--registry-prefix", required=True)
    parser.add_argument("--mode", choices=["normal", "edge", "rehearsal"], required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    moves: list[dict[str, Any]] = []
    mutation_started = False
    try:
        source_sha = args.source_sha.lower()
        if not SHA_RE.fullmatch(source_sha):
            raise ValueError("source SHA must be full 40 characters")
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        app = plan["app"]
        expected: list[tuple[dict, str]] = []
        for component in plan["publishComponents"]:
            if args.mode == "rehearsal":
                channel = ""
            elif args.mode == "edge":
                channel = "edge"
            else:
                channel = component.get("channel", "") if component["kind"] in {"package", "template"} else ""
            expected.append((component, channel))
        index_channel = "" if args.mode == "rehearsal" else ("edge" if args.mode == "edge" else "latest")
        expected.extend([
            ({"kind": "index", "name": "catalog"}, index_channel),
            ({"kind": "index", "name": "template"}, index_channel),
        ])
        seen: set[tuple[str, str]] = set()
        for component, channel in expected:
            expected_contract = contract(component, app, args.registry_prefix, source_sha, args.mode)
            key = expected_contract["key"]
            data = json.loads((args.evidence / f"artifact-{key}.json").read_text(encoding="utf-8"))
            validate_artifact(data, component, app, args.registry_prefix, source_sha, args.mode)
            if data.get("channel", "") != channel:
                raise ValueError(f"{key}: channel does not match the coordinated release mode")
            if not channel:
                continue
            identity = (expected_contract["repository"], channel)
            if identity in seen:
                raise ValueError(f"duplicate channel destination: {expected_contract['repository']}:{channel}")
            seen.add(identity)
            moves.append({
                "repository": expected_contract["repository"],
                "channel": channel,
                "targetDigest": data["digest"],
                "previousDigest": "",
                "currentDigest": "",
            })
        # Snapshot every destination before the first mutation. Unexpected registry
        # errors are not treated as an absent channel.
        for move in moves:
            move["previousDigest"] = channel_digest(move["repository"], move["channel"], allow_absent=True)
        mutation_started = True
        for move in moves:
            subprocess.run(["oras", "tag", f"{move['repository']}@{move['targetDigest']}", move["channel"]], check=True, capture_output=True)
            move["currentDigest"] = channel_digest(move["repository"], move["channel"], allow_absent=False)
            if move["currentDigest"] != move["targetDigest"]:
                raise ValueError(f"channel digest mismatch for {move['repository']}:{move['channel']}")
        write_report(args.report, "completed", moves, [])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        if not mutation_started:
            write_report(args.report, "blocked", [], [], str(exc))
        else:
            required = reconcile(moves)
            status = "reconciliation-required" if required else "rolled-back"
            write_report(args.report, status, moves, required, str(exc))
        print(f"::error::{exc}; channel recovery evidence: {args.report}", file=sys.stderr)
        return 1
    print(f"coordinated {len(moves)} channel tag(s); recovery evidence: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
