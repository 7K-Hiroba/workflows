#!/usr/bin/env python3
"""Mark artifact metadata verified only with a matching verification receipt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.evidence import load_json, predicate_from_document, verify  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--predicate", type=Path, required=True)
    args = parser.parse_args()
    try:
        artifact = load_json(args.artifact)
        receipt = load_json(args.receipt)
        predicate = predicate_from_document(load_json(args.predicate))
        if receipt.get("status") != "verified":
            raise ValueError("verification receipt is not verified")
        expected_ref = artifact["repository"] + "@" + artifact["digest"]
        for key, expected in (("artifactRef", expected_ref), ("digest", artifact["digest"]), ("sourceSha", artifact["sourceSha"])):
            if receipt.get(key) != expected:
                raise ValueError(f"verification receipt {key} mismatch")
        verify(
            predicate,
            source_repository=receipt["sourceRepository"],
            source_sha=artifact["sourceSha"],
            workflow_repository="7K-Hiroba/workflows",
            workflow_path=receipt["workflowPath"],
            workflow_sha=receipt["workflowSha"],
            artifact_repository=artifact["repository"],
            artifact_digest=artifact["digest"],
            media_type=artifact["mediaType"],
            release_tag=receipt["releaseTag"],
            required_lanes=set(receipt["requiredLanes"]),
        )
        artifact["signature"] = {"verified": True, "type": "cosign-keyless", "publisher": receipt["workflowPath"]}
        artifact["provenance"] = {"verified": True, "predicateType": "https://slsa.dev/provenance/v1"}
        artifact["testEvidence"] = {
            "status": "passed",
            "predicateType": "https://inari.dev/attestations/test-evidence/v1",
            "evidenceDigest": predicate["evidenceDigest"],
            "releaseTag": receipt["releaseTag"],
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    temporary = args.artifact.with_suffix(args.artifact.suffix + ".tmp")
    temporary.write_text(__import__("json").dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.artifact)
    print(f"marked {expected_ref} verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
