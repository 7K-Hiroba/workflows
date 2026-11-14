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
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("evidence timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def collect_lanes(evidence_dir: Path, required_lanes: set[str], source_sha: str) -> list[dict[str, Any]]:
    """Load one passing, source-bound representation of each required lane."""
    if not SHA_RE.fullmatch(source_sha):
        raise ValueError("source SHA must be a full 40-character value")
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
            lane = {"lane": "browser", "status": data.get("status"), "sourceSha": data.get("sourceSha"), "uiHostSha": data.get("uiHostSha")}
        else:
            continue
        name = lane["lane"]
        if name in lanes:
            raise ValueError(f"duplicate lane evidence: {name}")
        if lane.get("status") != "passed":
            raise ValueError(f"lane {name} did not pass")
        if name == "compat":
            if lane.get("sourceSha") != source_sha:
                raise ValueError("compat evidence sourceSha does not match artifact source")
            completed = parse_time(str(lane.get("completedAt", "")))
            now = datetime.now(timezone.utc)
            if completed > now + timedelta(minutes=5) or completed < now - timedelta(days=7):
                raise ValueError("compat evidence is future-dated or older than 7 days")
        lane["required"] = name in required_lanes
        lanes[name] = lane
    missing = sorted(required_lanes - set(lanes))
    if missing:
        raise ValueError(f"missing required lane evidence: {missing}")
    return [lanes[name] for name in sorted(lanes)]


def build(evidence_dir: Path, args: Any) -> dict[str, Any]:
    for value in (args.source_sha, args.workflow_sha):
        if not SHA_RE.fullmatch(value):
            raise ValueError("source and workflow SHAs must be full 40-character values")
    if not DIGEST_RE.fullmatch(args.artifact_digest):
        raise ValueError("artifact digest must be a full sha256 OCI digest")
    if args.workflow_path not in PRODUCERS:
        raise ValueError(f"unexpected test-evidence producer: {args.workflow_path}")
    ordered = collect_lanes(evidence_dir, set(args.required_lane or []), args.source_sha)
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


def verify(
    predicate: dict[str, Any],
    *,
    source_repository: str,
    source_sha: str,
    workflow_repository: str,
    workflow_path: str,
    workflow_sha: str,
    artifact_repository: str,
    artifact_digest: str,
    media_type: str,
    release_tag: str,
    required_lanes: set[str],
    now: datetime | None = None,
) -> None:
    """Verify every security-relevant predicate binding, not only its signature."""
    current = now or datetime.now(timezone.utc)
    if predicate.get("schema") != "inari.test-evidence.v1":
        raise ValueError("unexpected predicate schema")
    if not SHA_RE.fullmatch(source_sha) or not SHA_RE.fullmatch(workflow_sha) or not DIGEST_RE.fullmatch(artifact_digest):
        raise ValueError("source/workflow SHAs and artifact digest must be full immutable values")
    if not required_lanes:
        raise ValueError("at least one required lane must be supplied")
    if predicate.get("sourceRepository", "").lower() != source_repository.lower() or predicate.get("sourceSha", "").lower() != source_sha.lower():
        raise ValueError("predicate source repository/SHA mismatch")
    producer = predicate.get("producer", {})
    if not isinstance(producer, dict):
        raise ValueError("predicate producer is missing")
    if producer.get("workflowRepository", "").lower() != workflow_repository.lower() or producer.get("workflowPath") != workflow_path or producer.get("workflowSha", "").lower() != workflow_sha.lower():
        raise ValueError("predicate producer repository/path/SHA mismatch")
    if not str(producer.get("runId", "")) or not str(producer.get("runAttempt", "")):
        raise ValueError("predicate producer run identity is missing")
    artifact = predicate.get("artifact", {})
    if not isinstance(artifact, dict) or artifact.get("repository", "").lower() != artifact_repository.lower() or artifact.get("digest", "").lower() != artifact_digest.lower() or artifact.get("mediaType") != media_type:
        raise ValueError("predicate artifact repository/digest/media type mismatch")
    if predicate.get("releaseTag") != release_tag:
        raise ValueError("predicate release tag mismatch")
    lanes = predicate.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise ValueError("predicate has no test lanes")
    seen: set[str] = set()
    for lane in lanes:
        if not isinstance(lane, dict) or not isinstance(lane.get("lane"), str):
            raise ValueError("predicate contains an invalid lane")
        name = lane["lane"]
        if name in seen:
            raise ValueError(f"duplicate predicate lane: {name}")
        seen.add(name)
        if lane.get("status") != "passed":
            raise ValueError(f"lane {name} did not pass")
        if name in required_lanes and lane.get("required") is not True:
            raise ValueError(f"lane {name} is not marked required")
        if name == "compat":
            if lane.get("sourceSha", "").lower() != source_sha.lower():
                raise ValueError("compat lane sourceSha mismatch")
            completed = parse_time(lane.get("completedAt", ""))
            if completed > current + timedelta(minutes=5) or completed < current - timedelta(days=7):
                raise ValueError("compat evidence is stale or future-dated")
        if name == "browser" and lane.get("sourceSha", "").lower() != source_sha.lower():
            raise ValueError("browser lane sourceSha mismatch")
    missing = sorted(required_lanes - seen)
    if missing:
        raise ValueError(f"missing required predicate lanes: {missing}")
    finished = parse_time(str(predicate.get("finishedAt", "")))
    if finished > current + timedelta(minutes=5) or finished < current - timedelta(hours=24):
        raise ValueError("test evidence is stale or future-dated")
    expected_digest = hashlib.sha256(json.dumps(lanes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if predicate.get("evidenceDigest") != expected_digest:
        raise ValueError("evidenceDigest does not match predicate lanes")
