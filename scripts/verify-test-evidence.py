#!/usr/bin/env python3
"""Independently verify a decoded release-linked test-evidence predicate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.evidence import StaleEvidenceError, load_json_documents, predicates_from_document, verify  # noqa: E402


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
        predicates = [
            predicate
            for document in load_json_documents(args.predicate)
            for predicate in predicates_from_document(document)
        ]
        # Exact duplicates are idempotent. Every distinct predicate must satisfy the
        # same binding and freshness policy; a conflicting signed member fails closed.
        unique: dict[str, dict] = {}
        for predicate in predicates:
            unique[json.dumps(predicate, sort_keys=True, separators=(",", ":"))] = predicate
        fresh = 0
        historical = 0
        for predicate in unique.values():
            try:
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
            except StaleEvidenceError:
                # Historical members still passed every immutable binding/conflict
                # check before their age was considered; they cannot authorize alone.
                historical += 1
            else:
                fresh += 1
        if fresh == 0:
            raise ValueError("no fully bound fresh test evidence predicate exists")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"verified {fresh} fresh and {historical} historical fully bound test evidence predicate(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
