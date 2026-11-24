"""Trusted release-linked test evidence construction and validation."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
class StaleEvidenceError(ValueError):
    """A well-bound historical predicate that cannot authorize a new verification."""


PRODUCERS = {
    ".github/workflows/release-oci.yml",
    ".github/workflows/release-chart.yml",
    ".github/workflows/release-extension.yml",
    ".github/workflows/release-smoke-suite.yml",
    ".github/workflows/release.yml",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_documents(path: Path) -> list[Any]:
    """Load every whitespace-separated JSON value, rejecting empty or trailing junk."""
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    documents = []
    offset = 0
    while True:
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset == len(text):
            break
        document, offset = decoder.raw_decode(text, offset)
        documents.append(document)
    if not documents:
        raise ValueError("expected at least one JSON document")
    return documents


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("evidence timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_stack_lane(lane: dict[str, Any]) -> None:
    """Reject lifecycle evidence that omits the one-cluster install/upgrade proof."""
    if lane.get("clusterCreateCount") != 1 or lane.get("clusterDeleteCount") != 1:
        raise ValueError("stack-lifecycle evidence must create and delete exactly one cluster")
    if lane.get("freshState") is not True or lane.get("cleanedUp") is not True:
        raise ValueError("stack-lifecycle cluster must be fresh and cleaned up")
    if lane.get("functionalE2E") is not False or lane.get("deployedReadiness") != "not-tested":
        raise ValueError("stack-lifecycle cannot claim functional E2E or deployed readiness")
    if not SHA_RE.fullmatch(str(lane.get("workflowSha", ""))):
        raise ValueError("stack-lifecycle workflowSha is missing or invalid")
    if not str(lane.get("runId", "")) or not str(lane.get("runAttempt", "")):
        raise ValueError("stack-lifecycle run identity is required")
    cache = lane.get("cache")
    if not isinstance(cache, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(cache.get("cacheKey", ""))) or not isinstance(cache.get("cacheHit"), bool):
        raise ValueError("stack-lifecycle exact cache identity is required")
    phases = lane.get("phases")
    if not isinstance(phases, list) or [phase.get("phase") for phase in phases if isinstance(phase, dict)] != ["install", "upgrade"]:
        raise ValueError("stack-lifecycle requires ordered install and upgrade phases")
    digests = []
    for phase in phases:
        if phase.get("converged") is not True or not DIGEST_RE.fullmatch(str(phase.get("contentDigest", ""))):
            raise ValueError("stack-lifecycle phase must converge at an exact content digest")
        if not isinstance(phase.get("durationSeconds"), int) or phase["durationSeconds"] < 0:
            raise ValueError("stack-lifecycle phase duration is invalid")
        digests.append(phase["contentDigest"])
    if digests[0] == digests[1]:
        raise ValueError("stack-lifecycle install and upgrade content identities must be distinct")
    if not isinstance(lane.get("fixtureOnly"), bool):
        raise ValueError("stack-lifecycle fixtureOnly must be boolean")
    if not isinstance(lane.get("totalDurationSeconds"), int) or lane["totalDurationSeconds"] < 0:
        raise ValueError("stack-lifecycle total duration is invalid")


def validate_chart_lifecycle_lane(lane: dict[str, Any]) -> None:
    """Reject chart upgrade evidence that omits any security-relevant invariant."""
    name = str(lane.get("lane", ""))
    if not re.fullmatch(r"chart-lifecycle-[a-z0-9][a-z0-9-]*", name):
        raise ValueError("invalid chart lifecycle lane name")
    if lane.get("chartName") != name.removeprefix("chart-lifecycle-"):
        raise ValueError("chart lifecycle chartName does not match its lane")
    raw_chart_path = str(lane.get("chartPath", ""))
    chart_path = PurePosixPath(raw_chart_path)
    if not raw_chart_path or chart_path.is_absolute() or ".." in chart_path.parts:
        raise ValueError("chart lifecycle chartPath must be consumer-relative")
    if not str(lane.get("clusterName", "")):
        raise ValueError("chart lifecycle cluster identity is required")
    if lane.get("clusterCreateCount") != 1 or lane.get("clusterDeleteCount") != 1:
        raise ValueError("chart lifecycle must create and delete exactly one cluster")
    if lane.get("freshState") is not True:
        raise ValueError("chart lifecycle cluster must be fresh")
    if lane.get("cleanedUp") is not True:
        raise ValueError("chart lifecycle cluster must be cleaned up")
    if lane.get("functionalE2E") is not False or lane.get("deployedReadiness") != "not-tested":
        raise ValueError("chart lifecycle cannot claim functional E2E or deployed readiness")
    if lane.get("fixtureOnly") is not False:
        raise ValueError("chart lifecycle fixtureOnly must be false")
    if lane.get("evidenceScope") != "application":
        raise ValueError("chart lifecycle evidenceScope must be application")
    if lane.get("appEvidenceEligible") is not True:
        raise ValueError("chart lifecycle must be application evidence eligible")
    if not SHA_RE.fullmatch(str(lane.get("workflowSha", ""))):
        raise ValueError("chart lifecycle workflowSha is missing or invalid")
    if "prHeadSha" in lane and not SHA_RE.fullmatch(str(lane["prHeadSha"])):
        raise ValueError("chart lifecycle prHeadSha is invalid")
    if not str(lane.get("runId", "")) or not str(lane.get("runAttempt", "")):
        raise ValueError("chart lifecycle run identity is required")
    started = parse_time(str(lane.get("startedAt", "")))
    finished = parse_time(str(lane.get("finishedAt", "")))
    if finished < started:
        raise ValueError("chart lifecycle finishedAt must not precede startedAt")
    if not isinstance(lane.get("totalDurationSeconds"), int) or lane["totalDurationSeconds"] < 0:
        raise ValueError("chart lifecycle total duration is invalid")
    phases = lane.get("phases")
    if not isinstance(phases, list) or len(phases) != 2 or not all(isinstance(phase, dict) for phase in phases) or [phase.get("phase") for phase in phases] != ["install", "upgrade"]:
        raise ValueError("chart lifecycle requires ordered install and upgrade phases")
    for phase, expected_revision in zip(phases, (1, 2)):
        if phase.get("status") != "passed":
            raise ValueError("chart lifecycle phase must be passed")
        if phase.get("converged") is not True:
            raise ValueError("chart lifecycle phase must be converged")
        if phase.get("assertions") != "passed":
            raise ValueError("chart lifecycle targeted assertions must pass")
        if phase.get("revision") != expected_revision:
            raise ValueError("chart lifecycle Helm revision is invalid")
        if phase.get("releaseName") != lane.get("releaseName") or not str(lane.get("releaseName", "")):
            raise ValueError("chart lifecycle release name is not stable")
        if phase.get("namespace") != lane.get("namespace") or lane.get("namespace") != "default":
            raise ValueError("chart lifecycle namespace is not stable")
        if phase.get("clusterName") != lane.get("clusterName"):
            raise ValueError("chart lifecycle cluster is not stable")
        if not str(phase.get("version", "")) or not DIGEST_RE.fullmatch(str(phase.get("packageDigest", ""))):
            raise ValueError("chart lifecycle phase version/package digest is invalid")
        if not isinstance(phase.get("durationSeconds"), int) or phase["durationSeconds"] < 0:
            raise ValueError("chart lifecycle phase duration is invalid")
    if phases[0]["version"] == phases[1]["version"]:
        raise ValueError("chart lifecycle package versions must be distinct")
    if phases[0]["packageDigest"] == phases[1]["packageDigest"]:
        raise ValueError("chart lifecycle package content digests must be distinct")


def validate_stack_lane_binding(lanes: list[dict[str, Any]], workflow_sha: str, run_id: str, run_attempt: str) -> None:
    """Bind stack and chart lifecycle evidence to the workflow run that signs it."""
    for lane in lanes:
        name = str(lane.get("lane", ""))
        if name != "stack-lifecycle" and not name.startswith("chart-lifecycle-"):
            continue
        if str(lane.get("workflowSha", "")).lower() != workflow_sha.lower():
            raise ValueError(f"{name} workflowSha does not match evidence producer")
        if str(lane.get("runId", "")) != str(run_id):
            raise ValueError(f"{name} runId does not match evidence producer")
        if str(lane.get("runAttempt", "")) != str(run_attempt):
            raise ValueError(f"{name} runAttempt does not match evidence producer")


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
        if not isinstance(lane.get("sourceSha"), str) or lane["sourceSha"].lower() != source_sha.lower():
            raise ValueError(f"{name} evidence sourceSha does not match artifact source")
        if name == "compat":
            completed = parse_time(str(lane.get("completedAt", "")))
            now = datetime.now(timezone.utc)
            if completed > now + timedelta(minutes=5) or completed < now - timedelta(days=7):
                raise ValueError("compat evidence is future-dated or older than 7 days")
        if name in {"browser", "runtime-smoke"} and lane.get("sourceSha") != source_sha:
            raise ValueError(f"{name} evidence sourceSha does not match artifact source")
        if name == "stack-lifecycle":
            validate_stack_lane(lane)
        elif name.startswith("chart-lifecycle-"):
            validate_chart_lifecycle_lane(lane)
        lane["required"] = name in required_lanes
        lanes[name] = lane
    missing = sorted(required_lanes - set(lanes))
    if missing:
        raise ValueError(f"missing required lane evidence: {missing}")
    return [lanes[name] for name in sorted(lanes)]


def runtime_evidence_policy(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    runtime = next((lane for lane in lanes if lane.get("lane") == "runtime-smoke"), None)
    if runtime is None:
        return {}
    fields = ("targetAdapter", "fixtureOnly", "executableProfiles", "evidenceScope", "appEvidenceEligible")
    if not any(field in runtime for field in fields):
        return {}
    if any(field not in runtime for field in fields):
        raise ValueError("new runtime-smoke evidence is missing fixture eligibility metadata")
    fixture = runtime["fixtureOnly"]
    profiles = runtime["executableProfiles"]
    scope = runtime["evidenceScope"]
    eligible = runtime["appEvidenceEligible"]
    if not isinstance(fixture, bool) or not isinstance(profiles, list) or not all(item in {"ci", "stage", "prod"} for item in profiles):
        raise ValueError("invalid runtime-smoke fixture/profile metadata")
    if not isinstance(scope, str) or not isinstance(eligible, bool):
        raise ValueError("invalid runtime-smoke evidence eligibility metadata")
    if runtime["targetAdapter"] not in {"helm", "manifests"}:
        raise ValueError("invalid runtime-smoke target adapter")
    if fixture:
        if runtime["targetAdapter"] != "manifests" or profiles != ["ci"] or scope != "fixture" or eligible is not False or runtime.get("targetComponent"):
            raise ValueError("fixtureOnly runtime evidence must be ci-only, manifest-based, and ineligible as application evidence")
    elif scope != "application" or eligible is not True:
        raise ValueError("artifact-bound runtime evidence must be application-scoped and eligible")
    return {field: runtime[field] for field in fields}


def validate_stack_fixture_eligibility(lanes: list[dict[str, Any]], trust_tier: str, media_type: str) -> None:
    stack = next((lane for lane in lanes if lane.get("lane") == "stack-lifecycle"), None)
    if stack and stack.get("fixtureOnly") and trust_tier in {"reviewed", "official"} and media_type != "application/vnd.inari.smoke.suite.v1+yaml":
        raise ValueError("fixtureOnly stack evidence cannot authorize a reviewed or official application artifact")


def build(evidence_dir: Path, args: Any) -> dict[str, Any]:
    for value in (args.source_sha, args.workflow_sha):
        if not SHA_RE.fullmatch(value):
            raise ValueError("source and workflow SHAs must be full 40-character values")
    if not DIGEST_RE.fullmatch(args.artifact_digest):
        raise ValueError("artifact digest must be a full sha256 OCI digest")
    if args.workflow_path not in PRODUCERS:
        raise ValueError(f"unexpected test-evidence producer: {args.workflow_path}")
    ordered = collect_lanes(evidence_dir, set(args.required_lane or []), args.source_sha)
    validate_stack_lane_binding(ordered, args.workflow_sha, str(args.run_id), str(args.run_attempt))
    validate_stack_fixture_eligibility(ordered, args.trust_tier, args.media_type)
    policy = runtime_evidence_policy(ordered)
    if policy.get("fixtureOnly") and args.trust_tier in {"reviewed", "official"} and args.media_type != "application/vnd.inari.smoke.suite.v1+yaml":
        raise ValueError("fixtureOnly runtime evidence cannot authorize a reviewed or official application artifact")
    evidence_digest = hashlib.sha256(json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    predicate = {
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
    predicate.update(policy)
    return predicate


def predicates_from_document(document: Any) -> list[dict[str, Any]]:
    """Extract every predicate from cosign's single-or-list verification document."""
    documents = document if isinstance(document, list) else [document]
    if not documents:
        raise ValueError("expected at least one attestation")
    predicates: list[dict[str, Any]] = []
    for item in documents:
        if not isinstance(item, dict):
            raise ValueError("attestation must be a JSON object")
        if isinstance(item.get("predicate"), dict):
            predicates.append(item["predicate"])
            continue
        if isinstance(item.get("payload"), str):
            decoded = json.loads(base64.b64decode(item["payload"]))
            if isinstance(decoded.get("predicate"), dict):
                predicates.append(decoded["predicate"])
                continue
        if item.get("schema") == "inari.test-evidence.v1":
            predicates.append(item)
            continue
        raise ValueError("no test-evidence predicate found")
    return predicates


def predicate_from_document(document: Any) -> dict[str, Any]:
    predicates = predicates_from_document(document)
    if len(predicates) != 1:
        raise ValueError("expected exactly one local predicate")
    return predicates[0]


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
        if not isinstance(lane.get("sourceSha"), str) or lane["sourceSha"].lower() != source_sha.lower():
            raise ValueError(f"{name} lane sourceSha mismatch")
        if name == "compat":
            completed = parse_time(lane.get("completedAt", ""))
            if completed > current + timedelta(minutes=5):
                raise ValueError("compat evidence is future-dated")
            if completed < current - timedelta(days=7):
                raise StaleEvidenceError("compat evidence is historical")
        if name in {"browser", "runtime-smoke"} and lane.get("sourceSha", "").lower() != source_sha.lower():
            raise ValueError(f"{name} lane sourceSha mismatch")
        if name == "stack-lifecycle":
            validate_stack_lane(lane)
        elif name.startswith("chart-lifecycle-"):
            validate_chart_lifecycle_lane(lane)
    validate_stack_lane_binding(lanes, workflow_sha, str(producer["runId"]), str(producer["runAttempt"]))
    policy = runtime_evidence_policy(lanes)
    for field, expected in policy.items():
        if predicate.get(field) != expected:
            raise ValueError(f"predicate {field} does not match signed runtime lane evidence")
    if policy.get("fixtureOnly") and predicate.get("trustTier") in {"reviewed", "official"} and media_type != "application/vnd.inari.smoke.suite.v1+yaml":
        raise ValueError("fixtureOnly runtime evidence cannot authorize a reviewed or official application artifact")
    missing = sorted(required_lanes - seen)
    if missing:
        raise ValueError(f"missing required predicate lanes: {missing}")
    validate_stack_fixture_eligibility(lanes, str(predicate.get("trustTier", "")), media_type)
    finished = parse_time(str(predicate.get("finishedAt", "")))
    if finished > current + timedelta(minutes=5):
        raise ValueError("test evidence is future-dated")
    if finished < current - timedelta(hours=24):
        raise StaleEvidenceError("test evidence is historical")
    expected_digest = hashlib.sha256(json.dumps(lanes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if predicate.get("evidenceDigest") != expected_digest:
        raise ValueError("evidenceDigest does not match predicate lanes")
