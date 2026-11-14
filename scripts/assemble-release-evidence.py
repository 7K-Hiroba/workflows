#!/usr/bin/env python3
"""Assemble receipt-backed artifact evidence for release index generation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import SHA_RE, verified_artifact  # noqa: E402

NAME = re.compile(r"^artifact-(catalog|template)-([a-z0-9][a-z0-9-]*)\.json$")
MEDIA = {
    "catalog": "application/vnd.inari.catalog.package.v1+yaml",
    "template": "application/vnd.inari.template.v1",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_sha = args.source_sha.lower()
    if not SHA_RE.fullmatch(source_sha):
        parser.error("source SHA must be full 40 characters")
    artifacts = {}
    try:
        for path in sorted(args.artifacts.rglob("artifact-*.json")):
            match = NAME.fullmatch(path.name)
            if not match:
                continue
            kind, name = match.groups()
            key = f"{kind}/{name}"
            if key in artifacts:
                raise ValueError(f"duplicate artifact evidence: {key}")
            data = json.loads(path.read_text(encoding="utf-8"))
            artifacts[key] = verified_artifact({"artifact": data}, "artifact", MEDIA[kind], source_sha)
        if not artifacts:
            raise ValueError("no verified artifact evidence found")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps({"sourceSha": source_sha, "artifacts": artifacts}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"assembled {len(artifacts)} verified artifact(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
