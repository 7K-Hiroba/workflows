#!/usr/bin/env python3
"""Validate and emit a consumer-owned chart kind-test declaration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import yaml

from lib.paths import confined_path

SCHEMA = Path(__file__).resolve().parents[1] / "schemas/chart-test-v1.schema.json"


def load(root: Path, chart: str) -> dict:
    root = root.resolve()
    chart_dir = confined_path(root, chart, "chart")
    if not chart_dir.is_dir():
        raise ValueError("chart directory is missing")
    path = chart_dir / "ci/test.yaml"
    data = {"schema": "inari.chart-test.v1"}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("chart test declaration must be a mapping")
        data = loaded
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)
    install = data.get("install", {"timeout": "5m"})
    install.setdefault("values", [])
    result = {"image": data.get("image"), "dependencies": data.get("dependencies", []), "install": install}
    if result["image"] is not None:
        if not confined_path(root, result["image"]["context"], "image.context").is_dir():
            raise ValueError("image.context must be an existing consumer directory")
    for dependency in result["dependencies"]:
        if Path(dependency).suffix not in {".yaml", ".yml"} or not confined_path(root, dependency, "dependency").is_file():
            raise ValueError(f"dependency must be an existing consumer YAML file: {dependency!r}")
    for values_file in result["install"]["values"]:
        if Path(values_file).suffix not in {".yaml", ".yml"} or not confined_path(root, values_file, "install.values").is_file():
            raise ValueError(f"install values must be an existing consumer YAML file: {values_file!r}")
    native_values = sorted(path.relative_to(root).as_posix() for path in (chart_dir / "ci").glob("*-values.yaml"))
    if set(native_values) != set(result["install"]["values"]):
        raise ValueError("install.values must exactly declare every ci/*-values.yaml file used by chart-testing")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--chart", required=True)
    args = parser.parse_args()
    try:
        result = load(args.root, args.chart)
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError, jsonschema.ValidationError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
