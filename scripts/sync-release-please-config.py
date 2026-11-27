#!/usr/bin/env python3
"""Synchronize release-please manifest components from the Hiroba app layout."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import discover, write_if_changed  # noqa: E402

CONFIG_SCHEMA = "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json"
MARKER = "x-release-please-version"
SOURCE_SUFFIXES = {".go", ".ts", ".tsx"}
EXCLUDED_DIRECTORIES = {".git", "dist", "node_modules", "vendor"}
SEMVER = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
GO_DECLARATION = re.compile(
    rf'(?P<prefix>\s*(?:const\s+)?Version\s*=\s*")(?P<version>{SEMVER})(?P<suffix>"\s*//\s*{MARKER}\s*)'
)
TS_DECLARATION = re.compile(
    rf"(?P<prefix>\s*version\s*:\s*(?P<quote>['\"]))(?P<version>{SEMVER})(?P<suffix>(?P=quote)\s*,?\s*//\s*{MARKER}\s*)"
)


def component_config(component: dict[str, Any], version_files: list[str] | None = None) -> dict[str, Any]:
    kind = component["kind"]
    release_type = {"extension": "go", "ui": "node"}.get(kind, "simple")
    config: dict[str, Any] = {
        "release-type": release_type,
        "changelog-path": "CHANGELOG.md",
        "bump-minor-pre-major": True,
        "bump-patch-for-minor-pre-major": True,
    }
    extra_files = {
        "extension": [{"type": "generic", "path": "/extension.yaml"}],
        "chart": ["Chart.yaml"],
        "package": ["package.yaml"],
        "template": ["template.yaml"],
        "smoke": ["suite.yaml"],
    }.get(kind, [])
    if kind in {"extension", "ui"}:
        extra_files = [
            *extra_files,
            *(version_files or []),
            {"type": "yaml", "path": "/.hiroba.yaml", "jsonpath": f"$.components.{kind}.version"},
        ]
    if extra_files:
        config["extra-files"] = extra_files
    if kind == "smoke" or component.get("releaseComponent"):
        config["component"] = component.get("releaseComponent", component["name"])
    return config


def previous_version_files(root: Path, component: dict[str, Any]) -> set[str]:
    try:
        config = json.loads((root / "release-please-config.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return set()
    package = config.get("packages", {}).get(component["path"], {}) if isinstance(config, dict) else {}
    extra_files = package.get("extra-files", []) if isinstance(package, dict) else []
    if not isinstance(extra_files, list):
        return set()
    built_in = {"../extension.yaml"} if component["kind"] == "extension" else set()
    return {item for item in extra_files if isinstance(item, str) and item not in built_in}


def render_marked_source(path: Path, data: bytes, version: str) -> str:
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: marked version source must be valid UTF-8") from exc
    pattern = GO_DECLARATION if path.suffix == ".go" else TS_DECLARATION
    declarations: list[tuple[int, re.Match[str], str]] = []
    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        if MARKER not in body:
            continue
        match = pattern.fullmatch(body)
        if match is None:
            raise ValueError(f"{path}: malformed or ambiguous {MARKER} declaration")
        declarations.append((index, match, ending))
    if len(declarations) != 1:
        raise ValueError(f"{path}: expected exactly one {MARKER} declaration, found {len(declarations)}")
    index, match, ending = declarations[0]
    lines[index] = f"{match['prefix']}{version}{match['suffix']}{ending}"
    return "".join(lines)


def discover_version_sources(root: Path, component: dict[str, Any]) -> dict[str, tuple[Path, str]]:
    component_root = root / component["path"]
    discovered: dict[str, tuple[Path, str]] = {}
    for directory, directories, files in os.walk(component_root, followlinks=False):
        directories[:] = sorted(
            name for name in directories
            if name not in EXCLUDED_DIRECTORIES and not (Path(directory) / name).is_symlink()
        )
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix not in SOURCE_SUFFIXES or path.is_symlink():
                continue
            data = path.read_bytes()
            if MARKER.encode() not in data:
                continue
            relative = path.relative_to(component_root).as_posix()
            discovered[relative] = (path, render_marked_source(path, data, component["version"]))
    previous = previous_version_files(root, component)
    missing = previous - discovered.keys()
    if missing:
        raise ValueError(f"{component['path']}: previously managed version declarations are missing or unmarked: {sorted(missing)}")
    return discovered


def generate(root: Path) -> tuple[str, str, list[tuple[Path, str]]]:
    plan = discover(root)
    components = [
        component for component in plan["components"]
        if component["kind"] != "smoke" or component.get("fixtureOnly") is True
    ]
    version_sources = {
        component["path"]: discover_version_sources(root, component)
        for component in components
        if component["kind"] in {"extension", "ui"}
    }
    packages = {
        component["path"]: component_config(component, sorted(version_sources.get(component["path"], {})))
        for component in components
    }
    config: dict[str, Any] = {
        "$schema": CONFIG_SCHEMA,
        "separate-pull-requests": False,
        "include-component-in-tag": True,
        "include-v-in-tag": True,
        "tag-separator": "-v",
        "pull-request-title-pattern": "chore: release ${component} ${version}",
        "packages": packages,
    }
    manifest = {component["path"]: component["version"] for component in components}
    source_outputs = sorted(
        (output for sources in version_sources.values() for output in sources.values()),
        key=lambda output: str(output[0]),
    )
    return (
        json.dumps(config, indent=2, sort_keys=False) + "\n",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        source_outputs,
    )


def write_source_if_changed(path: Path, content: str, check: bool, errors: list[str]) -> None:
    encoded = content.encode("utf-8")
    if check:
        if not path.is_file() or path.read_bytes() != encoded:
            errors.append(f"{path} is out of date; run the generator without --check")
        return
    if path.read_bytes() != encoded:
        path.write_bytes(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        config, manifest, source_outputs = generate(root)
    except (OSError, ValueError) as exc:
        print(f"::error::{exc}")
        return 2
    errors: list[str] = []
    write_if_changed(root / "release-please-config.json", config, args.check, errors)
    write_if_changed(root / ".release-please-manifest.json", manifest, args.check, errors)
    for path, content in source_outputs:
        write_source_if_changed(path, content, args.check, errors)
    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    print("release-please metadata is in sync" if args.check else "synchronized release-please metadata")
    return 0


if __name__ == "__main__":
    sys.exit(main())
