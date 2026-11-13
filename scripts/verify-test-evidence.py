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
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--release-tag", required=True)
    args = parser.parse_args()
    try:
        predicate = predicate_from_document(load_json(args.predicate))
        verify(predicate, args.source_sha.lower(), args.workflow_path, args.artifact_digest, args.release_tag)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print("test evidence predicate is bound, passing, and fresh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
