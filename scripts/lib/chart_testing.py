"""Consumer-owned chart test declarations and lifecycle naming."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from lib.paths import confined_path

SCHEMA = Path(__file__).resolve().parents[2] / "schemas/chart-test-v1.schema.json"
CHART_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def lifecycle_lane(chart: str) -> str:
    """Return the derived, non-caller-authored evidence lane for a chart path."""
    name = Path(chart).name
    if not CHART_NAME.fullmatch(name):
        raise ValueError("chart directory name must be a valid lifecycle lane suffix")
    return f"chart-lifecycle-{name}"


def lifecycle_artifact(chart: str) -> str:
    return lifecycle_lane(chart).replace("chart-lifecycle-", "chart-lifecycle-evidence-", 1)


def _fixture_path(root: Path, chart_dir: Path, value: str, label: str) -> Path:
    path = confined_path(root, value, label)
    if path.is_relative_to(chart_dir):
        raise ValueError(f"{label} must be outside the packaged chart directory")
    return path


def load(root: Path, chart: str) -> dict[str, Any]:
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
    result: dict[str, Any] = {
        "image": data.get("image"),
        "dependencies": data.get("dependencies", []),
        "install": install,
    }
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

    if "upgrade" in data:
        upgrade = data["upgrade"]
        for label in ("previousPackage", "currentPackage"):
            package = _fixture_path(root, chart_dir, upgrade[label], f"upgrade.{label}")
            if Path(upgrade[label]).suffix != ".tgz" or not package.is_file():
                raise ValueError(f"upgrade.{label} must be an existing consumer .tgz file")
        assertions = _fixture_path(root, chart_dir, upgrade["assertions"], "upgrade.assertions")
        if Path(upgrade["assertions"]).suffix != ".sh" or not assertions.is_file() or not os.access(assertions, os.X_OK):
            raise ValueError("upgrade.assertions must be an existing executable consumer .sh file")
        lifecycle_lane(chart)
        result["upgrade"] = upgrade
    return result
