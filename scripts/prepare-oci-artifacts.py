#!/usr/bin/env python3
"""Prepare deterministic package/template/index descriptors for OCI publishing."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import SHA_RE, discover  # noqa: E402

PACKAGE_MEDIA = "application/vnd.inari.catalog.package.v1+yaml"
TEMPLATE_MEDIA = "application/vnd.inari.template.v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--kind", required=True, choices=["package", "template", "indexes"])
    parser.add_argument("--name")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--registry-prefix", default="ghcr.io/7k-hiroba")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--edge", action="store_true")
    args = parser.parse_args()
    if not SHA_RE.fullmatch(args.source_sha):
        parser.error("source SHA must be full 40 characters")
    root = args.root.resolve()
    plan = discover(root)
    app = plan["app"]
    descriptors = []
    if args.kind in {"package", "template"}:
        if not args.name:
            parser.error("--name is required for package/template")
        matches = [item for item in plan["components"] if item["kind"] == args.kind and item["name"] == args.name]
        if len(matches) != 1:
            print(f"::error::expected one {args.kind} named {args.name}", file=sys.stderr)
            return 1
        component = matches[0]
        directory = "catalog" if args.kind == "package" else "templates"
        media = PACKAGE_MEDIA if args.kind == "package" else TEMPLATE_MEDIA
        channel = "edge" if args.edge else component["channel"]
        descriptors.append({
            "key": f"{directory}-{component['name']}",
            "name": component["name"],
            "kind": args.kind,
            "source": component["path"],
            "file": "",
            "repository": f"{args.registry_prefix}/{app}/{directory}/{component['name']}",
            "tag": component["version"],
            "channel": channel,
            "mediaType": media,
            "releaseTag": f"{component['name']}-v{component['version']}",
            "sourceSha": args.source_sha.lower(),
            "app": app,
            "trustTier": plan.get("trustTier", "experimental"),
        })
    else:
        if not args.evidence:
            print("::error::indexes require --evidence", file=sys.stderr)
            return 1
        build = subprocess.run([
            sys.executable, str(Path(__file__).resolve().parent / "build-indexes.py"),
            "--root", str(root), "--release-evidence", str(args.evidence),
        ], text=True, capture_output=True, check=False)
        if build.returncode:
            print(build.stdout + build.stderr, file=sys.stderr)
            return build.returncode
        channel = "edge" if args.edge else "latest"
        for key, directory, filename, media in (
            ("catalog", "catalog", "catalog.yaml", "application/vnd.inari.catalog.index.v1+yaml"),
            ("template", "templates", "templates.yaml", "application/vnd.inari.template.index.v1+yaml"),
        ):
            descriptors.append({
                "key": f"index-{key}",
                "name": f"{key}-index",
                "kind": "index",
                "source": ".",
                "file": filename,
                "repository": f"{args.registry_prefix}/{app}/{directory}/index",
                "tag": args.source_sha.lower(),
                "channel": channel,
                "mediaType": media,
                "releaseTag": f"release-set-{args.source_sha[:12]}",
                "sourceSha": args.source_sha.lower(),
            "app": app,
            "trustTier": plan.get("trustTier", "experimental"),
            })
    print(json.dumps(descriptors, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
