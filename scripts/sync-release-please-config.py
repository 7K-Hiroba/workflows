#!/usr/bin/env python3
"""Synchronize release-please manifest components from the Hiroba app layout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import discover, write_if_changed  # noqa: E402

CONFIG_SCHEMA = "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json"


def component_config(component: dict[str, Any]) -> dict[str, Any]:
    kind = component["kind"]
    release_type = {"extension": "go", "ui": "node"}.get(kind, "simple")
    config: dict[str, Any] = {
        "release-type": release_type,
        "changelog-path": "CHANGELOG.md",
        "bump-minor-pre-major": True,
        "bump-patch-for-minor-pre-major": True,
    }
    extra_files = {
        "extension": ["../extension.yaml"],
        "chart": ["Chart.yaml"],
        "package": ["package.yaml"],
        "template": ["template.yaml"],
    }.get(kind)
    if extra_files:
        config["extra-files"] = extra_files
    return config


def generate(root: Path) -> tuple[str, str]:
    plan = discover(root)
    components = [component for component in plan["components"] if component["kind"] != "smoke"]
    packages = {component["path"]: component_config(component) for component in components}
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
    return (
        json.dumps(config, indent=2, sort_keys=False) + "\n",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config, manifest = generate(args.root.resolve())
    errors: list[str] = []
    write_if_changed(args.root / "release-please-config.json", config, args.check, errors)
    write_if_changed(args.root / ".release-please-manifest.json", manifest, args.check, errors)
    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    print("release-please metadata is in sync" if args.check else "synchronized release-please metadata")
    return 0


if __name__ == "__main__":
    sys.exit(main())
