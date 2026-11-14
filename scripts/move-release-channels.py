#!/usr/bin/env python3
"""Validate the complete release set before moving any OCI channel tags."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import SHA_RE  # noqa: E402
from lib.release_contract import contract, validate_artifact  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--registry-prefix", required=True)
    parser.add_argument("--mode", choices=["normal", "edge", "rehearsal"], required=True)
    args = parser.parse_args()
    try:
        source_sha = args.source_sha.lower()
        if not SHA_RE.fullmatch(source_sha):
            raise ValueError("source SHA must be full 40 characters")
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        app = plan["app"]
        components = list(plan["publishComponents"])
        expected: list[tuple[dict, str]] = []
        for component in components:
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
        moves: list[tuple[str, str, str]] = []
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
            move = (expected_contract["repository"], data["digest"], channel)
            identity = (expected_contract["repository"], channel)
            if identity in seen:
                raise ValueError(f"duplicate channel destination: {expected_contract['repository']}:{channel}")
            seen.add(identity)
            moves.append(move)
        # Validation of the complete set intentionally precedes the first mutation.
        for repository, digest, channel in moves:
            subprocess.run(["oras", "tag", f"{repository}@{digest}", channel], check=True)
            resolved = subprocess.check_output(["crane", "digest", f"{repository}:{channel}"], text=True).strip()
            if resolved != digest:
                raise ValueError(f"channel digest mismatch for {repository}:{channel}")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"coordinated {len(moves)} channel tag(s) after complete receipt validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
