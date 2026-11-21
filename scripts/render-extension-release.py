#!/usr/bin/env python3
"""Render exact digest-bound extension registration metadata for a release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import DIGEST_RE  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--backend", type=Path)
    parser.add_argument("--ui", type=Path)
    parser.add_argument("--ui-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if not args.backend and not args.ui:
            raise ValueError("at least one backend or UI artifact is required")
        document = yaml.safe_load(args.extension.read_text(encoding="utf-8"))
        if args.backend:
            backend = json.loads(args.backend.read_text(encoding="utf-8"))
            if not DIGEST_RE.fullmatch(backend["digest"]):
                raise ValueError("backend artifact requires a full OCI digest")
            document["spec"]["backend"]["image"] = backend["repository"] + "@" + backend["digest"]
        if args.ui:
            if not args.ui_manifest:
                raise ValueError("UI artifact requires its bundle manifest")
            ui = json.loads(args.ui.read_text(encoding="utf-8"))
            manifest = json.loads(args.ui_manifest.read_text(encoding="utf-8"))
            if not DIGEST_RE.fullmatch(ui["digest"]):
                raise ValueError("UI artifact requires a full OCI digest")
            checksum = next(item["sha256"] for item in manifest["files"] if item["name"] == "remoteEntry.js")
            if len(checksum) != 64:
                raise ValueError("invalid remoteEntry checksum")
            document["spec"]["ui"]["remoteEntryOci"] = ui["repository"] + "@" + ui["digest"]
            document["spec"]["ui"]["checksum"] = checksum
            document["spec"]["ui"].pop("remoteEntry", None)
    except (OSError, ValueError, KeyError, StopIteration, TypeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    args.output.write_text("# GENERATED release metadata; source extension.yaml is unchanged.\n" + yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    print(f"wrote exact extension release metadata to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
