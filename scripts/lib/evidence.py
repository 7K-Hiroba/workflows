"""Trusted release-linked test evidence construction and validation."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
PRODUCERS = {
    ".github/workflows/release-oci.yml",
    ".github/workflows/release-chart.yml",
    ".github/workflows/release-extension.yml",
    ".github/workflows/release-smoke-suite.yml",
    ".github/workflows/release.yml",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build(evidence_dir: Path, args: Any) -> dict[str, Any]:
    for value in (args.source_sha, args.workflow_sha):
        if not SHA_RE.fullmatch(value):
            raise ValueError("source and workflow SHAs must be full 40-character values")
    if not DIGEST_RE.fullmatch(args.artifact_digest):
        raise ValueError("artifact digest must be a full sha256 OCI digest")
    if args.workflow_path not in PRODUCERS:
        raise ValueError(f"unexpected test-evidence producer: {args.workflow_path}")
    required = set(args.required_lane or [])
    lanes: dict[str, dict[str, Any]] = {}
    for path in sorted(evidence_dir.glob("*.json")):
        try:
            data = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("schema") == "inari.lane-result.v1" and isinstance(data.get("lane"), str):
            lane = data
        elif data.get("schema") == "inari.compat-report.v1":
            lane = {"lane": "compat", "status": data.get("status"), "sourceSha": data.get("sourceSha"), "completedAt": data.get("completedAt"), "resolvedEdge": data.get("resolvedEdge")}
        elif data.get("schema") == "inari.browser-report.v1":
            lane = {"lane": "browser", "status": data.get("status"), "uiHostSha": data.get("uiHostSha")}
        else:
            continue
        name = lane["lane"]
        if name in lanes:
            raise ValueError(f"duplicate lane evidence: {name}")
        if lane.get("status") != "passed":
            raise ValueError(f"lane {name} did not pass")
        if name == "compat":
            if lane.get("sourceSha") != args.source_sha:
                raise ValueError("compat evidence sourceSha does not match artifact source")
            completed = parse_time(str(lane.get("completedAt", "")))
            now = datetime.now(timezone.utc)
            if completed > now + timedelta(minutes=5) or completed < now - timedelta(days=7):
                raise ValueError("compat evidence is future-dated or older than 7 days")
        lane["required"] = name in required
        lanes[name] = lane
    missing = sorted(required - set(lanes))
    if missing:
        raise ValueError(f"missing required lane evidence: {missing}")
    ordered = [lanes[name] for name in sorted(lanes)]
    evidence_digest = hashlib.sha256(json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": "inari.test-evidence.v1",
        "app": args.app,
        "component": args.component,
        "trustTier": args.trust_tier,
        "sourceRepository": args.source_repository,
        "sourceSha": args.source_sha,
        "releaseTag": args.release_tag,
        "artifact": {"repository": args.artifact_repository, "digest": args.artifact_digest, "mediaType": args.media_type},
        "producer": {
            "workflowRepository": "7K-Hiroba/workflows",
            "workflowPath": args.workflow_path,
            "workflowSha": args.workflow_sha,
            "runId": str(args.run_id),
            "runAttempt": str(args.run_attempt),
        },
        "lanes": ordered,
        "evidenceDigest": evidence_digest,
        "finishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def predicate_from_document(document: Any) -> dict[str, Any]:
    if isinstance(document, list):
        if len(document) != 1:
            raise ValueError("expected exactly one attestation")
        document = document[0]
    if not isinstance(document, dict):
        raise ValueError("attestation must be a JSON object")
    if isinstance(document.get("predicate"), dict):
        return document["predicate"]
    if isinstance(document.get("payload"), str):
        decoded = json.loads(base64.b64decode(document["payload"]))
        if isinstance(decoded.get("predicate"), dict):
            return decoded["predicate"]
    if document.get("schema") == "inari.test-evidence.v1":
        return document
    raise ValueError("no test-evidence predicate found")


def verify(predicate: dict[str, Any], source_sha: str, workflow_path: str, artifact_digest: str, release_tag: str) -> None:
    if predicate.get("schema") != "inari.test-evidence.v1":
        raise ValueError("unexpected predicate schema")
    if predicate.get("sourceSha") != source_sha:
        raise ValueError("predicate sourceSha mismatch")
    if predicate.get("producer", {}).get("workflowPath") != workflow_path:
        raise ValueError("predicate producer workflow mismatch")
    if predicate.get("artifact", {}).get("digest") != artifact_digest:
        raise ValueError("predicate artifact digest mismatch")
    if predicate.get("releaseTag") != release_tag:
        raise ValueError("predicate release tag mismatch")
    lanes = predicate.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise ValueError("predicate has no test lanes")
    for lane in lanes:
        if lane.get("status") != "passed":
            raise ValueError(f"lane {lane.get('lane')} did not pass")
        if lane.get("lane") == "compat":
            completed = parse_time(lane.get("completedAt", ""))
            now = datetime.now(timezone.utc)
            if completed > now + timedelta(minutes=5) or completed < now - timedelta(days=7):
                raise ValueError("compat evidence is stale or future-dated")
    expected_digest = hashlib.sha256(json.dumps(lanes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if predicate.get("evidenceDigest") != expected_digest:
        raise ValueError("evidenceDigest does not match predicate lanes")
