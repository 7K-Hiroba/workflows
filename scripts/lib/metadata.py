"""Shared, deterministic Hiroba component and release metadata helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from lib.paths import relative_path
from lib.stack_testing import load_stack_plan, validate_app_config

SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
LEGACY_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
BRANCH_DELIMITER = "--components--"


def release_identity(component: dict[str, Any]) -> str:
    """Return the visible release-please identity for an independent component."""
    kind = component["kind"]
    if kind in {"extension", "ui"}:
        return kind
    return component.get("releaseComponent", component["name"])


def validate_release_identities(components: list[dict[str, Any]]) -> None:
    """Fail before generation when identities are unsafe or globally ambiguous."""
    by_identity: dict[str, list[str]] = {}
    for component in components:
        kind = component["kind"]
        if kind == "smoke" and not component.get("fixtureOnly"):
            continue
        identity = release_identity(component)
        location = f"{kind}:{component['path']}"
        if BRANCH_DELIMITER in identity:
            raise ValueError(f"release component {identity!r} for {location} contains reserved delimiter {BRANCH_DELIMITER!r}")
        if not component.get("releaseComponent") and kind not in {"extension", "ui"}:
            valid = (
                bool(LEGACY_COMPONENT_RE.fullmatch(identity))
                and ".." not in identity
                and not identity.endswith(".")
                and not identity.endswith(".lock")
            )
            if not valid:
                raise ValueError(f"invalid legacy release component {identity!r} for {location}")
        by_identity.setdefault(identity, []).append(location)
    duplicates = {
        identity: sorted(locations)
        for identity, locations in by_identity.items()
        if len(locations) > 1
    }
    if duplicates:
        details = "; ".join(f"{identity}: {', '.join(locations)}" for identity, locations in sorted(duplicates.items()))
        raise ValueError(f"duplicate release components independent of kind/version: {details}")



def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping")
    return data


def load_config(root: Path) -> dict[str, Any]:
    return validate_app_config(root)


def discover(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config = load_config(root)
    stack_test = load_stack_plan(root)
    app = config["app"]
    configured = config["components"]
    components: list[dict[str, Any]] = []

    for kind in ("extension", "ui"):
        item = configured.get(kind)
        if isinstance(item, dict):
            components.append({
                "kind": kind,
                "name": kind,
                "path": relative_path(root, item["path"], f"components.{kind}.path"),
                "version": str(item["version"]),
                "channel": "stable",
            })

    charts_root = relative_path(root, configured.get("chartsRoot", "charts"), "components.chartsRoot")
    for chart_path in sorted((root / charts_root).glob("*/Chart.yaml")):
        chart = load_yaml(chart_path)
        components.append({
            "kind": "chart",
            "name": str(chart["name"]),
            "path": str(chart_path.parent.relative_to(root)),
            "version": str(chart["version"]),
            "channel": "stable",
        })

    packages_root = relative_path(root, configured.get("packagesRoot", "packages"), "components.packagesRoot")
    for manifest in sorted((root / packages_root).glob("*/package.yaml")):
        package = load_yaml(manifest)
        components.append({
            "kind": "package",
            "name": manifest.parent.name,
            "path": str(manifest.parent.relative_to(root)),
            "version": str(package["version"]),
            "channel": str(package["channel"]),
            "packageType": str(package["type"]),
            "description": str(package.get("description", "")),
            "category": str(package.get("category", "")),
            "observability": package.get("observability"),
        })

    templates_root = relative_path(root, configured.get("templatesRoot", "templates"), "components.templatesRoot")
    for manifest in sorted((root / templates_root).glob("*/template.yaml")):
        template = load_yaml(manifest)
        components.append({
            "kind": "template",
            "name": manifest.parent.name,
            "path": str(manifest.parent.relative_to(root)),
            "version": str(template["version"]),
            "channel": str(template["channel"]),
            "description": str(template.get("description", "")),
            "templateKind": str(template.get("kind", "component")),
        })

    smoke = config.get("smoke")
    if isinstance(smoke, dict):
        smoke_path = relative_path(root, smoke["path"], "smoke.path")
        suite = load_yaml(root / smoke_path / "suite.yaml")
        target = suite["target"]
        adapter = target.get("adapter", {})
        fixture_only = adapter.get("fixtureOnly") is True
        component = {
            "kind": "smoke",
            "name": str(target["id"]),
            "path": smoke_path,
            "version": str(target["version"]),
            "channel": "stable",
            "targetAdapter": str(adapter.get("kind", "helm")),
            "fixtureOnly": fixture_only,
            "executableProfiles": suite.get("executableProfiles", ["ci", "stage", "prod"]),
            "evidenceScope": "fixture" if fixture_only else "application",
            "appEvidenceEligible": not fixture_only,
            "compatibleAppVersions": str(suite["compatibleAppVersions"]),
        }
        if target.get("component"):
            component["targetComponent"] = relative_path(root, str(target["component"]), "smoke.target.component")
        components.append(component)

    release_components = config.get("releaseComponents", {})
    if not isinstance(release_components, dict):
        raise ValueError("releaseComponents must be a mapping of component paths to release identities")
    by_path = {component["path"]: component for component in components}
    for path, release_component in release_components.items():
        component = by_path.get(path)
        if component is None:
            raise ValueError(f"releaseComponents references unknown component path {path!r}")
        if not isinstance(release_component, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", release_component):
            raise ValueError(f"invalid release component {release_component!r} for {path}")
        if component["kind"] in {"extension", "ui"}:
            raise ValueError("backend and UI have fixed extension/UI release identities")
        if component["kind"] == "smoke" and not component["fixtureOnly"]:
            raise ValueError("artifact-bound smoke inherits its target release component")
        component["releaseComponent"] = release_component

    for component in components:
        if component["kind"] != "smoke" or component["fixtureOnly"]:
            continue
        target = by_path.get(component.get("targetComponent", ""))
        if target is not None and target.get("releaseComponent"):
            component["releaseComponent"] = target["releaseComponent"]

    validate_release_identities(components)

    covered = set(stack_test["covers"])
    for component in components:
        component["stackCovered"] = component["path"] in covered
    components.sort(key=lambda item: (item["name"], item["kind"], item["path"]))
    return {
        "schema": "inari.release-plan.v1",
        "app": app,
        "archetype": config["archetype"],
        "trustTier": config.get("trustTier", "experimental"),
        "hasStackTest": stack_test["enabled"],
        "stackTest": stack_test,
        "components": components,
    }


def filter_changed(plan: dict[str, Any], changed_files: list[str]) -> dict[str, Any]:
    components = []
    for component in plan["components"]:
        prefix = component["path"].rstrip("/") + "/"
        if any(path.startswith(prefix) for path in changed_files):
            components.append(component)
            continue
        if "extension.yaml" in changed_files and component["kind"] in {"extension", "ui"}:
            components.append(component)
    return {**plan, "components": components}


def write_if_changed(path: Path, content: str, check: bool, errors: list[str]) -> None:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            errors.append(f"{path.name} is out of date; run the generator without --check")
        return
    path.write_text(content, encoding="utf-8")


def release_artifacts(evidence_path: Path) -> tuple[str, dict[str, Any]]:
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    source_sha = evidence.get("sourceSha", "")
    artifacts = evidence.get("artifacts")
    if not SHA_RE.fullmatch(source_sha):
        raise ValueError("release evidence must contain a full sourceSha")
    if not isinstance(artifacts, dict):
        raise ValueError("release evidence artifacts must be a mapping")
    return source_sha, artifacts


def verified_artifact(artifacts: dict[str, Any], key: str, media_type: str, source_sha: str, repository: str | None = None) -> dict[str, Any]:
    artifact = artifacts.get(key)
    if not isinstance(artifact, dict):
        raise ValueError(f"missing release evidence for {key}")
    if not DIGEST_RE.fullmatch(str(artifact.get("digest", ""))):
        raise ValueError(f"{key}: invalid or missing OCI digest")
    if artifact.get("mediaType") != media_type:
        raise ValueError(f"{key}: unexpected mediaType")
    if repository is not None and artifact.get("repository", "").lower() != repository.lower():
        raise ValueError(f"{key}: evidence repository does not match expected repository")
    if artifact.get("sourceSha") != source_sha:
        raise ValueError(f"{key}: artifact sourceSha does not match release")
    if artifact.get("signature", {}).get("verified") is not True:
        raise ValueError(f"{key}: signature is not verified")
    if artifact.get("provenance", {}).get("verified") is not True:
        raise ValueError(f"{key}: SLSA provenance is not verified")
    if artifact.get("testEvidence", {}).get("status") != "passed":
        raise ValueError(f"{key}: signed test evidence did not pass")
    return artifact
