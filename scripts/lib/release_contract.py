"""Expected artifact coordinates and signed release identity for every component."""

from __future__ import annotations

from typing import Any

from lib.metadata import verified_artifact

MEDIA = {
    "package": "application/vnd.inari.catalog.package.v1+yaml",
    "template": "application/vnd.inari.template.v1",
    "chart": "application/vnd.cncf.helm.chart.v1",
    "smoke": "application/vnd.inari.smoke.suite.v1+yaml",
    "ui": "application/vnd.inari.extension.ui.v1",
    "index-catalog": "application/vnd.inari.catalog.index.v1+yaml",
    "index-template": "application/vnd.inari.template.index.v1+yaml",
}


def release_tag(component: dict[str, Any]) -> str:
    if component["kind"] == "extension":
        return f"extension-v{component['version']}"
    if component["kind"] == "ui":
        return f"ui-v{component['version']}"
    return f"{component['name']}-v{component['version']}"


def artifact_key(component: dict[str, Any]) -> str:
    kind = component["kind"]
    if kind == "ui":
        return "extension-ui"
    if kind == "extension":
        return "extension"
    prefix = {"package": "catalog", "template": "templates"}.get(kind, kind)
    return f"{prefix}-{component['name']}"


def contract(component: dict[str, Any], app: str, registry_prefix: str, source_sha: str, mode: str) -> dict[str, str]:
    """Derive the only acceptable registry and signed release identity."""
    kind = component["kind"]
    name = component["name"]
    if kind == "package":
        repository = f"{registry_prefix}/{app}/catalog/{name}"
    elif kind == "template":
        repository = f"{registry_prefix}/{app}/templates/{name}"
    elif kind == "chart":
        repository = f"{registry_prefix}/{app}/charts/{name}"
    elif kind == "smoke":
        repository = f"{registry_prefix}/{app}/smoke/{name}"
    elif kind == "extension":
        repository = f"{registry_prefix}/{app}/extension"
    elif kind == "ui":
        repository = f"{registry_prefix}/{app}/extension-ui"
    elif kind == "index":
        directory = "catalog" if name == "catalog" else "templates"
        repository = f"{registry_prefix}/{app}/{directory}/index"
    else:
        raise ValueError(f"unsupported release component kind: {kind}")
    artifact_tag = component.get("version", source_sha) if kind != "index" else source_sha
    signed_tag = release_tag(component) if kind != "index" else f"release-set-{source_sha[:12]}"
    if mode == "rehearsal":
        artifact_tag = f"{component['version']}-ci.{source_sha[:12]}" if kind == "chart" else source_sha
        signed_tag = f"ci-{source_sha[:12]}"
    return {
        "key": artifact_key(component),
        "repository": repository,
        "artifactTag": artifact_tag,
        "releaseTag": signed_tag,
        "mediaType": MEDIA.get(kind if kind != "index" else f"index-{name}", ""),
        "mediaPrefix": "application/vnd.oci.image." if kind == "extension" else "",
    }


def validate_artifact(data: dict[str, Any], component: dict[str, Any], app: str, registry_prefix: str, source_sha: str, mode: str) -> dict[str, str]:
    """Require verified bytes and signed evidence for exactly this planned component."""
    expected = contract(component, app, registry_prefix, source_sha, mode)
    media_type = data.get("mediaType")
    if expected["mediaPrefix"]:
        if not isinstance(media_type, str) or not media_type.startswith(expected["mediaPrefix"]):
            raise ValueError(f"{expected['key']}: unexpected backend image media type")
    else:
        media_type = expected["mediaType"]
    verified_artifact({"artifact": data}, "artifact", media_type, source_sha, repository=expected["repository"])
    if data.get("tag") != expected["artifactTag"]:
        raise ValueError(f"{expected['key']}: immutable artifact tag does not match the release plan")
    if data.get("testEvidence", {}).get("releaseTag") != expected["releaseTag"]:
        raise ValueError(f"{expected['key']}: signed predicate releaseTag does not match the release plan")
    return expected
