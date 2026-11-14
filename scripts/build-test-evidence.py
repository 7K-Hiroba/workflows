#!/usr/bin/env python3
"""Build a release-linked test predicate from trusted structured lane results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.evidence import build  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--component", required=True)
    parser.add_argument("--trust-tier", required=True, choices=["official", "reviewed", "experimental"])
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--artifact-repository", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--media-type", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--required-lane", action="append")
    args = parser.parse_args()
    try:
        predicate = build(args.evidence_dir, args)
        args.output.write_text(json.dumps(predicate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"built signed-evidence predicate for {args.artifact_repository}@{args.artifact_digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
