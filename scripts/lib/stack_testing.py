"""Versioned Hiroba stack classification, lifecycle declarations, and pins."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from lib.paths import confined_path, relative_path

LIBRARY_ROOT = Path(__file__).resolve().parents[2]
APP_SCHEMA = LIBRARY_ROOT / "schemas/app-config-v2.schema.json"
STACK_SCHEMA = LIBRARY_ROOT / "schemas/stack-test-v1.schema.json"
PHASE_SCHEMA = LIBRARY_ROOT / "schemas/stack-phase-result-v1.schema.json"
PINS_PATH = LIBRARY_ROOT / "pins/stack-testing.json"


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping")
    return data


def validate_document(data: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        field = ".".join(str(part) for part in exc.absolute_path)
        prefix = f"{field}: " if field else ""
        raise ValueError(prefix + exc.message) from exc


def validate_app_config(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config = load_yaml(root / ".hiroba.yaml")
    validate_document(config, APP_SCHEMA)
    archetype = config["archetype"]
    if archetype == "non-stack" and "stackTest" in config:
        raise ValueError("archetype non-stack must not declare stackTest")
    return config


def load_pins() -> dict[str, Any]:
    pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    if not isinstance(pins, dict) or pins.get("schema") != "inari.stack-pins.v1":
        raise ValueError("central stack pins must use inari.stack-pins.v1")
    return pins


def cache_key(profiles: list[str]) -> str:
    pins = load_pins()
    selected = {
        "kind": pins["kind"],
        "kro": pins["kro"],
        "profiles": {profile: pins["profiles"].get(profile) for profile in sorted(profiles)},
    }
    encoded = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def expected_components(root: Path, config: dict[str, Any]) -> set[str]:
    expected: set[str] = set()
    components = config["components"]
    charts_root = confined_path(root, components.get("chartsRoot", "charts"), "components.chartsRoot")
    if charts_root.is_dir():
        for chart in charts_root.glob("*/Chart.yaml"):
            expected.add(relative_path(root, chart.parent.relative_to(root).as_posix(), "chart"))
    packages_root = confined_path(root, components.get("packagesRoot", "packages"), "components.packagesRoot")
    if packages_root.is_dir():
        for manifest in packages_root.glob("*/package.yaml"):
            package = load_yaml(manifest)
            if package.get("type") == "kro-rgd":
                expected.add(manifest.parent.relative_to(root).as_posix())
    return expected


def validate_script(base: Path, relative: str, label: str) -> None:
    path = confined_path(base, relative, label)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"{label} must reference an existing executable file: {relative}")


def load_stack_plan(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config = validate_app_config(root)
    archetype = config["archetype"]
    plan: dict[str, Any] = {
        "schema": "inari.stack-test-plan.v1",
        "app": config["app"],
        "archetype": archetype,
        "enabled": archetype == "stack",
    }
    if archetype == "non-stack":
        plan.update({"path": "", "covers": [], "setupProfiles": [], "fixtureOnly": False, "cacheKey": cache_key([])})
        return plan

    settings = config["stackTest"]
    stack_path = relative_path(root, settings["path"], "stackTest.path")
    base = confined_path(root, stack_path, "stackTest.path")
    suite_path = base / "suite.yaml"
    if not suite_path.is_file():
        raise ValueError(f"stackTest suite is missing: {stack_path}/suite.yaml")
    suite = load_yaml(suite_path)
    validate_document(suite, STACK_SCHEMA)
    for phase in ("install", "upgrade"):
        validate_script(base, suite[phase]["script"], f"{phase}.script")
    if suite.get("diagnostics"):
        validate_script(base, suite["diagnostics"], "diagnostics")

    covers = list(suite["covers"])
    expected = expected_components(root, config)
    covered = set(covers)
    missing = sorted(expected - covered)
    unknown = sorted(covered - expected)
    if missing:
        raise ValueError(f"stackTest is missing component coverage: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"stackTest covers unknown or unsupported components: {', '.join(unknown)}")

    profiles = list(suite["setupProfiles"])
    plan.update({
        **suite,
        "path": stack_path,
        "covers": covers,
        "setupProfiles": profiles,
        "fixtureOnly": suite.get("fixtureOnly", False),
        "cacheKey": cache_key(profiles),
    })
    return plan


def validate_phase_result(path: Path, phase: str) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"{phase} phase result must be an object")
    validate_document(result, PHASE_SCHEMA)
    if result["phase"] != phase:
        raise ValueError(f"phase result mismatch: expected {phase}")
    return result
