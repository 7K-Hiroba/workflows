#!/usr/bin/env python3
"""Independently verify a decoded release-linked test-evidence predicate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.evidence import load_json, predicate_from_document, verify  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predicate", type=Path, required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-repository", default="7K-Hiroba/workflows")
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--artifact-repository", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--media-type", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--required-lane", action="append", required=True)
    args = parser.parse_args()
    try:
        predicate = predicate_from_document(load_json(args.predicate))
        verify(
            predicate,
            source_repository=args.source_repository,
            source_sha=args.source_sha.lower(),
            workflow_repository=args.workflow_repository,
            workflow_path=args.workflow_path,
            workflow_sha=args.workflow_sha.lower(),
            artifact_repository=args.artifact_repository,
            artifact_digest=args.artifact_digest.lower(),
            media_type=args.media_type,
            release_tag=args.release_tag,
            required_lanes=set(args.required_lane),
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print("test evidence predicate is fully bound, passing, and fresh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
