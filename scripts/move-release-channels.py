#!/usr/bin/env python3
"""Validate the complete release set before moving any OCI channel tags."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import SHA_RE, verified_artifact  # noqa: E402

PACKAGE_MEDIA = "application/vnd.inari.catalog.package.v1+yaml"
TEMPLATE_MEDIA = "application/vnd.inari.template.v1"
CATALOG_INDEX_MEDIA = "application/vnd.inari.catalog.index.v1+yaml"
TEMPLATE_INDEX_MEDIA = "application/vnd.inari.template.index.v1+yaml"


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
        components = plan["publishComponents"]
        expected: list[tuple[str, str, str, str]] = []
        for component in components:
            kind = component.get("kind")
            if kind not in {"package", "template"}:
                continue
            directory = "catalog" if kind == "package" else "templates"
            prefix = "catalog" if kind == "package" else "template"
            media = PACKAGE_MEDIA if kind == "package" else TEMPLATE_MEDIA
            channel = "" if args.mode == "rehearsal" else ("edge" if args.mode == "edge" else component["channel"])
            expected.append((f"{prefix}-{component['name']}", f"{args.registry_prefix}/{app}/{directory}/{component['name']}", media, channel))
        index_channel = "" if args.mode == "rehearsal" else ("edge" if args.mode == "edge" else "latest")
        expected.extend([
            ("index-catalog", f"{args.registry_prefix}/{app}/catalog/index", CATALOG_INDEX_MEDIA, index_channel),
            ("index-template", f"{args.registry_prefix}/{app}/templates/index", TEMPLATE_INDEX_MEDIA, index_channel),
        ])
        moves: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for key, repository, media, channel in expected:
            path = args.evidence / f"artifact-{key}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            artifact = verified_artifact({"artifact": data}, "artifact", media, source_sha, repository=repository)
            if data.get("channel", "") != channel:
                raise ValueError(f"{key}: channel does not match the coordinated release mode")
            if not channel:
                continue
            move = (repository, artifact["digest"], channel)
            identity = (repository, channel)
            if identity in seen:
                raise ValueError(f"duplicate channel destination: {repository}:{channel}")
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
