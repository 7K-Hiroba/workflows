#!/usr/bin/env python3
"""Validate a Hiroba consumer repository without mutating its source tree."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import jsonschema
import yaml

LIBRARY_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = LIBRARY_ROOT / "schemas"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
DIGEST = re.compile(r"@sha256:[0-9a-fA-F]{64}$")
RBAC_KINDS = {"Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding"}
TYPE_FILES = {
    "kro-rgd": ("rgd.yaml", "ui-hints.yaml", "README.md", "tests/run.sh"),
    "platform-app": ("chart.yaml", "values-defaults.yaml", "values.schema.json", "README.md", "tests/run.sh"),
    "policy-pack": ("policies.yaml", "README.md", "tests/run.sh"),
}


class Validator:
    def __init__(self, root: Path, registry: Path | None) -> None:
        self.root = root.resolve()
        self.registry = registry
        self.errors: list[str] = []
        self.counts: Counter[str] = Counter()
        self.schema_cache: dict[str, Any] = {}

    def error(self, path: Path | str, message: str) -> None:
        if isinstance(path, Path):
            try:
                path = path.resolve().relative_to(self.root)
            except ValueError:
                path = Path(path.name)
        self.errors.append(f"{path}: {message}")

    def yaml(self, path: Path) -> Any:
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            self.error(path, f"invalid YAML: {exc}")
            return None

    def json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.error(path, f"invalid JSON: {exc}")
            return None

    def schema(self, name: str) -> dict[str, Any]:
        if name not in self.schema_cache:
            schema = self.json(SCHEMAS / name)
            if not isinstance(schema, dict):
                raise RuntimeError(f"library schema {name} is unavailable or invalid")
            jsonschema.validators.validator_for(schema).check_schema(schema)
            self.schema_cache[name] = schema
        return self.schema_cache[name]

    def validate_schema(self, data: Any, name: str, path: Path) -> None:
        schema = self.schema(name)
        validator = jsonschema.validators.validator_for(schema)(schema)
        for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
            field = ".".join(str(part) for part in error.absolute_path) or "document"
            self.error(path, f"{field}: {error.message}")

    def safe_path(self, base: Path, relative: str, label: Path) -> Path | None:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            self.error(label, f"unsafe path {relative!r}")
            return None
        resolved = (base / candidate).resolve()
        if not resolved.is_relative_to(base.resolve()):
            self.error(label, f"path escapes content root: {relative!r}")
            return None
        return resolved

    def validate_symlinks(self) -> None:
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [name for name in dirs if name not in {".git", ".venv", "node_modules", "dist"}]
            for name in [*dirs, *files]:
                path = Path(directory) / name
                if path.is_symlink():
                    self.error(path, "symlink content is not allowed in published source")

    def validate_packages(self, root_name: str) -> dict[str, dict[str, Any]]:
        packages: dict[str, dict[str, Any]] = {}
        packages_root = self.root / root_name
        if not packages_root.is_dir():
            return packages
        for directory in sorted(packages_root.iterdir()):
            manifest = directory / "package.yaml"
            if not directory.is_dir() or not manifest.is_file():
                continue
            data = self.yaml(manifest)
            if not isinstance(data, dict):
                self.error(manifest, "package manifest must be a mapping")
                continue
            self.validate_schema(data, "package-v1.schema.json", manifest)
            name = directory.name
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
                self.error(manifest, "package directory must be kebab-case")
            packages[name] = data
            self.counts["packages"] += 1
            package_type = data.get("type")
            for required in TYPE_FILES.get(package_type, ()):
                if not (directory / required).is_file():
                    self.error(manifest, f"missing required {required} for {package_type}")
            if package_type == "kro-rgd":
                rgd_path = directory / "rgd.yaml"
                rgd = self.yaml(rgd_path) if rgd_path.is_file() else None
                if isinstance(rgd, dict):
                    if rgd.get("kind") != "ResourceGraphDefinition" or rgd.get("apiVersion") != "kro.run/v1alpha1":
                        self.error(rgd_path, "must be a kro.run/v1alpha1 ResourceGraphDefinition")
                    spec = rgd.get("spec") if isinstance(rgd.get("spec"), dict) else {}
                    if not isinstance(spec.get("schema"), dict) or not isinstance(spec.get("resources"), list):
                        self.error(rgd_path, "spec.schema and spec.resources are required")
            if package_type == "platform-app":
                chart_path = directory / "chart.yaml"
                chart = self.yaml(chart_path) if chart_path.is_file() else None
                if isinstance(chart, dict) and not str(chart.get("repoURL", "")).startswith("oci://"):
                    self.error(chart_path, "repoURL must use OCI; classic Helm repositories are not supported")
                schema_path = directory / "values.schema.json"
                defaults_path = directory / "values-defaults.yaml"
                value_schema = self.json(schema_path) if schema_path.is_file() else None
                defaults = self.yaml(defaults_path) if defaults_path.is_file() else None
                if isinstance(value_schema, dict):
                    try:
                        jsonschema.validators.validator_for(value_schema).check_schema(value_schema)
                        if defaults is not None:
                            jsonschema.validate(defaults, value_schema)
                    except jsonschema.SchemaError as exc:
                        self.error(schema_path, f"invalid values JSON Schema: {exc.message}")
                    except jsonschema.ValidationError as exc:
                        self.error(defaults_path, f"default values do not match values.schema.json: {exc.message}")
            observability = data.get("observability")
            if isinstance(observability, dict) and str(observability.get("versionRange", "")).lower() == "latest":
                self.error(manifest, "observability pack must use an explicit compatible version range")
        return packages

    def validate_templates(self, root_name: str) -> dict[str, dict[str, Any]]:
        templates: dict[str, dict[str, Any]] = {}
        templates_root = self.root / root_name
        if not templates_root.is_dir():
            return templates
        for directory in sorted(templates_root.iterdir()):
            manifest = directory / "template.yaml"
            if not directory.is_dir() or not manifest.is_file():
                continue
            data = self.yaml(manifest)
            if not isinstance(data, dict):
                self.error(manifest, "template manifest must be a mapping")
                continue
            self.validate_schema(data, "template-v1.schema.json", manifest)
            if data.get("name") != directory.name:
                self.error(manifest, "template name must equal its directory name")
            for filename in ("schema.json", "uiSchema.json"):
                parsed = self.json(directory / filename) if (directory / filename).is_file() else None
                if parsed is None:
                    self.error(directory / filename, "required JSON file is missing or invalid")
            schema = self.json(directory / "schema.json")
            if isinstance(schema, dict):
                try:
                    jsonschema.validators.validator_for(schema).check_schema(schema)
                except jsonschema.SchemaError as exc:
                    self.error(directory / "schema.json", f"invalid JSON Schema: {exc.message}")
            skeleton = directory / "skeleton"
            if not skeleton.is_dir() or not any(path.is_file() for path in skeleton.rglob("*")):
                self.error(manifest, "skeleton/ must contain at least one file")
            templates[directory.name] = data
            self.counts["templates"] += 1
        return templates

    def validate_extension(self, config: dict[str, Any]) -> None:
        path = self.root / "extension.yaml"
        if not path.is_file():
            if "extension" in config["components"] or "ui" in config["components"]:
                self.error(path, "extension/ui components require extension.yaml")
            return
        data = self.yaml(path)
        if not isinstance(data, dict):
            self.error(path, "extension manifest must be a mapping")
            return
        self.validate_schema(data, "extension-v1.schema.json", path)
        text = path.read_text(encoding="utf-8")
        if "releases/download" in text or "gh release upload" in text:
            self.error(path, "GitHub Release UI remotes are forbidden; use remoteEntryOci")
        spec = data.get("spec") if isinstance(data.get("spec"), dict) else {}
        ui = spec.get("ui") if isinstance(spec.get("ui"), dict) else {}
        if "remoteEntry" in ui:
            self.error(path, "spec.ui.remoteEntry is forbidden; use remoteEntryOci")
        if str(ui.get("remoteEntryOci", "")).endswith(":latest"):
            self.error(path, "UI remote must not use latest")
        self.counts["extensions"] += 1

    def validate_observability(self, config: dict[str, Any], app: str, packages: dict[str, dict[str, Any]]) -> None:
        settings = config.get("observability")
        if not isinstance(settings, dict):
            return
        base_path = self.safe_path(self.root, settings.get("path", ""), self.root / ".hiroba.yaml")
        if base_path is None:
            return
        manifest = base_path / "observability.yaml"
        data = self.yaml(manifest)
        if not isinstance(data, dict):
            self.error(manifest, "observability manifest must be a mapping")
            return
        self.validate_schema(data, "observability-v1.schema.json", manifest)
        if data.get("app") != app:
            self.error(manifest, f"app must equal configured app {app}")
        if data.get("folder") != app and not str(data.get("folder", "")).startswith(app + "/"):
            self.error(manifest, "folder must use the registered app prefix")
        seen_uids: set[str] = set()
        for entry in data.get("dashboards", []):
            if not isinstance(entry, dict):
                continue
            uid = str(entry.get("uid", ""))
            if not uid.startswith(app + "-"):
                self.error(manifest, f"dashboard UID {uid!r} must start with {app}-")
            if uid in seen_uids:
                self.error(manifest, f"duplicate dashboard UID {uid!r}")
            seen_uids.add(uid)
            dashboard_path = self.safe_path(base_path, str(entry.get("file", "")), manifest)
            if dashboard_path is None or not dashboard_path.is_file():
                self.error(manifest, f"dashboard file is missing: {entry.get('file')}")
                continue
            dashboard = self.json(dashboard_path)
            if not isinstance(dashboard, dict):
                continue
            if dashboard.get("uid") != uid:
                self.error(dashboard_path, "dashboard UID does not match observability.yaml")
            panels = dashboard.get("panels")
            if not isinstance(panels, list) or not panels:
                self.error(dashboard_path, "reviewed dashboard must contain at least one panel")
                continue
            for index, panel in enumerate(panels):
                datasource = panel.get("datasource") if isinstance(panel, dict) else None
                variable = datasource.get("uid") if isinstance(datasource, dict) else None
                if not isinstance(variable, str) or not re.fullmatch(r"\$\{DS_[A-Z0-9_]+\}", variable):
                    self.error(dashboard_path, f"panel {index} datasource must use a templated DS_* variable")
        for entry in data.get("rules", []):
            if isinstance(entry, dict):
                rule_path = self.safe_path(base_path, str(entry.get("file", "")), manifest)
                if rule_path is None or not rule_path.is_file():
                    self.error(manifest, f"rule file is missing: {entry.get('file')}")
        pack = data.get("observabilityPack")
        if isinstance(pack, dict) and pack.get("package") not in packages:
            self.error(manifest, f"observability package {pack.get('package')!r} does not exist")
        self.counts["observability"] += 1

    def validate_smoke(self, config: dict[str, Any]) -> None:
        settings = config.get("smoke")
        if not isinstance(settings, dict):
            return
        base_path = self.safe_path(self.root, settings.get("path", ""), self.root / ".hiroba.yaml")
        if base_path is None:
            return
        suite_path = base_path / "suite.yaml"
        suite = self.yaml(suite_path)
        if not isinstance(suite, dict):
            self.error(suite_path, "smoke suite must be a mapping")
            return
        self.validate_schema(suite, "smoke-suite-v1.schema.json", suite_path)
        target = suite.get("target") if isinstance(suite.get("target"), dict) else {}
        if target.get("component") != settings.get("targetComponent"):
            self.error(suite_path, "target.component must match .hiroba.yaml smoke.targetComponent")
        if not SEMVER.fullmatch(str(target.get("version", ""))):
            self.error(suite_path, "target.version must be SemVer")
        profiles = suite.get("profiles") if isinstance(suite.get("profiles"), dict) else {}
        for environment in ("stage", "prod"):
            profile = profiles.get(environment) if isinstance(profiles.get(environment), dict) else {}
            effects = profile.get("sideEffects")
            if effects == "mutating" and (profile.get("approval") != "explicit" or not profile.get("changeWindow")):
                self.error(suite_path, f"{environment} mutating profile requires explicit approval and changeWindow")
            if environment == "prod" and effects not in {"readOnly", "syntheticWrite", "mutating"}:
                self.error(suite_path, "prod profile must declare an allowed side-effect level")
        for path in sorted(base_path.rglob("*")):
            if not path.is_file() or path.suffix not in {".yaml", ".yml"}:
                continue
            try:
                documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            except yaml.YAMLError as exc:
                self.error(path, f"invalid YAML: {exc}")
                continue
            for document in documents:
                self.validate_smoke_value(document, path)
        workflow = suite.get("workflowTemplate")
        if not isinstance(workflow, str) or not (base_path / workflow).is_file():
            self.error(suite_path, "workflowTemplate must reference an existing file")
        if not (base_path / "README.md").is_file():
            self.error(suite_path, "smoke suite requires README.md")
        self.counts["smoke"] += 1

    def validate_smoke_value(self, value: Any, path: Path) -> None:
        if isinstance(value, dict):
            kind = value.get("kind")
            if kind in RBAC_KINDS:
                self.error(path, f"suite-created RBAC resource {kind} is forbidden")
            image = value.get("image")
            if isinstance(image, str) and not DIGEST.search(image):
                self.error(path, f"smoke container image {image!r} must use a full sha256 digest")
            if value.get("privileged") is True:
                self.error(path, "privileged smoke containers are forbidden")
            for key, child in value.items():
                if str(key).lower() in {"endpoint", "targetendpoint", "baseurl"}:
                    self.error(path, f"real environment endpoint field {key!r} is forbidden in portable suites")
                self.validate_smoke_value(child, path)
        elif isinstance(value, list):
            for child in value:
                self.validate_smoke_value(child, path)

    def validate_registry(self, app: str) -> None:
        if self.registry is None:
            return
        data = self.yaml(self.registry)
        apps = data.get("apps") if isinstance(data, dict) else None
        if not isinstance(apps, list):
            self.error(self.registry, "registry must contain an apps list")
            return
        names = [entry.get("name") for entry in apps if isinstance(entry, dict)]
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        for name in duplicates:
            self.error(self.registry, f"duplicate app ID {name!r}")
        matches = [entry for entry in apps if isinstance(entry, dict) and entry.get("name") == app]
        if len(matches) == 1 and not matches[0].get("repository"):
            self.error(self.registry, f"app {app!r} has no owning repository")
        if not matches:
            self.error(self.registry, f"app {app!r} is not registered")

    def run(self) -> int:
        config_path = self.root / ".hiroba.yaml"
        config = self.yaml(config_path)
        if not isinstance(config, dict):
            self.error(config_path, "missing or invalid application configuration")
        else:
            self.validate_schema(config, "app-config-v1.schema.json", config_path)
            if isinstance(config.get("app"), str) and isinstance(config.get("components"), dict):
                self.validate_symlinks()
                packages = self.validate_packages(config["components"].get("packagesRoot", "packages"))
                self.validate_templates(config["components"].get("templatesRoot", "templates"))
                self.validate_extension(config)
                self.validate_observability(config, config["app"], packages)
                self.validate_smoke(config)
                self.validate_registry(config["app"])
                compatibility = config.get("compatibility")
                if isinstance(compatibility, dict):
                    matrix_path = self.safe_path(self.root, str(compatibility.get("matrix", "")), config_path)
                    if matrix_path is None or not matrix_path.is_file():
                        self.error(config_path, "compatibility matrix is missing")
                    else:
                        matrix = self.json(matrix_path)
                        if isinstance(matrix, dict):
                            self.validate_schema(matrix, "compatibility-matrix-v1.schema.json", matrix_path)
        for error in self.errors:
            print(f"::error::{error}")
        if self.errors:
            return 1
        summary = ", ".join(f"{key}={value}" for key, value in sorted(self.counts.items()))
        print(f"repository validation passed: {summary}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    return Validator(args.root, args.registry).run()


if __name__ == "__main__":
    sys.exit(main())
