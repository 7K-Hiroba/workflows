from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from tests.unit.test_release_metadata import write_marked_versions
from tests.unit.test_validate_repository import make_valid_repo

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")
SCRIPT = ROOT / "tests/release-please-contract/contract.js"
NEWER = "1" * 40
BOUNDARY = "2" * 40
OLDER = "3" * 40
ARGOCD_TAGS = {
    "chart-argocd-v0.1.0",
    "package-argocd-v1.3.0",
    "template-argocd-application-v0.1.0",
    "extension-v0.1.1",
    "package-observability-pack-v0.1.0",
    "ui-v0.3.0",
}

sys.path.insert(0, str(ROOT / "scripts"))
from lib.release_contract import release_tag  # noqa: E402


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def save_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def sync(root: Path) -> None:
    result = subprocess.run(
        [str(PYTHON), str(ROOT / "scripts/sync-release-please-config.py"), "--root", str(root)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)


def update_smoke(root: Path, chart_path: str) -> None:
    config_path = root / ".hiroba.yaml"
    config = load_yaml(config_path)
    config["smoke"]["targetComponent"] = chart_path
    config["observability"]["chart"] = chart_path
    save_yaml(config_path, config)
    suite_path = root / "tests/smoke/suite.yaml"
    suite = load_yaml(suite_path)
    suite["target"]["component"] = chart_path
    save_yaml(suite_path, suite)


def make_argocd(root: Path) -> None:
    make_valid_repo(root)
    (root / "packages/app").rename(root / "packages/argocd")
    shutil.rmtree(root / "packages/admission-example")
    (root / "templates/service").rename(root / "templates/argocd-application")
    (root / "charts/workflows-scaffold").rename(root / "charts/argocd")
    config_path = root / ".hiroba.yaml"
    config = load_yaml(config_path)
    config["app"] = "argocd"
    config["components"]["extension"]["version"] = "0.1.1"
    config["components"]["ui"]["version"] = "0.3.0"
    config["releaseComponents"] = {
        "charts/argocd": "chart-argocd",
        "packages/argocd": "package-argocd",
        "templates/argocd-application": "template-argocd-application",
        "packages/observability-pack": "package-observability-pack",
    }
    save_yaml(config_path, config)
    update_smoke(root, "charts/argocd")
    chart = load_yaml(root / "charts/argocd/Chart.yaml")
    chart["name"] = "argocd"
    save_yaml(root / "charts/argocd/Chart.yaml", chart)
    package_path = root / "packages/argocd/package.yaml"
    package_path.write_text(package_path.read_text().replace("version: 0.1.0", "version: 1.3.0"))
    template = load_yaml(root / "templates/argocd-application/template.yaml")
    template["name"] = "argocd-application"
    save_yaml(root / "templates/argocd-application/template.yaml", template)
    extension = root / "extension.yaml"
    extension.write_text(extension.read_text().replace(
        "version: 0.1.0", "version: 0.1.1 # x-release-please-version", 1
    ))
    ui_package = root / "ui/package.json"
    ui_package.write_text(json.dumps({"name": "argocd-ui", "version": "0.3.0"}))
    write_marked_versions(root, backend="0.1.1", ui="0.3.0")
    sync(root)


def make_monitoring(root: Path) -> None:
    """Synthetic producer contract data; these are not real Monitoring versions."""
    make_valid_repo(root)
    (root / "packages/app").rename(root / "packages/monitoring-stack")
    shutil.rmtree(root / "packages/admission-example")
    shutil.rmtree(root / "templates")
    (root / "charts/workflows-scaffold").rename(root / "charts/monitoring")
    config_path = root / ".hiroba.yaml"
    config = load_yaml(config_path)
    config["app"] = "monitoring"
    config["components"].pop("extension")
    config["components"].pop("ui")
    config["releaseComponents"] = {
        "charts/monitoring": "chart-monitoring",
        "packages/monitoring-stack": "package-monitoring-stack",
        "packages/observability-pack": "package-observability-pack",
    }
    save_yaml(config_path, config)
    update_smoke(root, "charts/monitoring")
    chart = load_yaml(root / "charts/monitoring/Chart.yaml")
    chart["name"] = "monitoring"
    save_yaml(root / "charts/monitoring/Chart.yaml", chart)
    for relative, version in (("packages/monitoring-stack/package.yaml", "0.2.0"), ("packages/observability-pack/package.yaml", "0.3.0")):
        path = root / relative
        path.write_text(path.read_text().replace("version: 0.1.0", f"version: {version}"))
    sync(root)


class ReleasePleaseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def commits(self, root: Path) -> list[dict]:
        config = json.loads((root / "release-please-config.json").read_text())
        files = []
        for package in config["packages"]:
            if package == "extension":
                files.append("extension/internal/extplugin/version.go")
            elif package == "ui":
                files.append("ui/src/index.tsx")
            else:
                files.append(f"{package}/CHANGELOG.md")
        return [
            {"sha": NEWER, "message": "fix: newer-release-change", "files": files},
            {"sha": BOUNDARY, "message": "chore: boundary-release-change", "files": files},
            {"sha": OLDER, "message": "fix: older-release-change", "files": files},
        ]

    def run_contract(
        self,
        root: Path,
        *,
        tags: list[dict] | None = None,
        mutate=None,
        branches: list[str] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict | None]:
        if mutate:
            mutate(root)
        if branches is not None:
            scenario = {"branches": branches}
        else:
            scenario = {"root": str(root), "tags": tags or [], "commits": self.commits(root)}
        scenario_path = self.base / f"scenario-{len(list(self.base.glob('scenario-*.json')))}.json"
        scenario_path.write_text(json.dumps(scenario))
        env = {key: value for key, value in os.environ.items() if key not in {"GH_TOKEN", "GITHUB_TOKEN"}}
        result = subprocess.run(
            ["node", str(SCRIPT), str(scenario_path)],
            text=True,
            capture_output=True,
            check=False,
            env=env,
            timeout=45,
        )
        if result.returncode:
            return result, None
        return result, json.loads(result.stdout.strip().splitlines()[-1])

    def validate_tags(self, payload: dict, expected: set[str]) -> None:
        self.assertEqual(payload["version"], "17.6.0")
        self.assertEqual(set(payload["lookups"]), expected)
        self.assertEqual(len(payload["lookups"]), len(expected))
        self.assertEqual(len(payload["pullRequests"]), 1)
        self.assertNotIn("-vv", " ".join(payload["lookups"]))

    def validate_history(self, payload: dict, expected: set[str]) -> None:
        self.validate_tags(payload, expected)
        self.assertEqual(payload["history"], [NEWER, BOUNDARY])
        body = payload["pullRequests"][0]["body"]
        self.assertIn("newer-release-change", body)
        self.assertNotIn("boundary-release-change", body)
        self.assertNotIn("older-release-change", body)

    def validate_extension_change(self, payload: dict) -> None:
        change = payload["changes"]["extension.yaml"]
        original = change["originalContent"]
        updated = change["content"]
        self.assertIn("x-release-please-version", original)
        self.assertIn("x-release-please-version", updated)
        before = original.splitlines(keepends=True)
        after = updated.splitlines(keepends=True)
        self.assertEqual(len(before), len(after))
        changed = [index for index, (left, right) in enumerate(zip(before, after)) if left != right]
        self.assertEqual(len(changed), 1)
        self.assertIn("version: 0.1.1", before[changed[0]])
        self.assertNotEqual(before[changed[0]], after[changed[0]])
        self.assertNotIn("\r\n", updated)

    def test_argocd_exact_tags_and_lf_generic_update(self) -> None:
        root = self.base / "argocd"
        make_argocd(root)
        _, payload = self.run_contract(root)
        self.validate_tags(payload, ARGOCD_TAGS)
        self.validate_extension_change(payload)
        config = json.loads((root / "release-please-config.json").read_text())
        self.assertNotIn("plugins", config)
        for package in config["packages"].values():
            self.assertNotIn("release-as", package)
            self.assertIs(package["include-v-in-tag"], False)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        plan = subprocess.run(
            [str(PYTHON), str(ROOT / "scripts/prepare-release-plan.py"), "--root", str(root), "--source-sha", "a" * 40, "--rehearsal"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
        components = json.loads(plan.stdout)["publishComponents"]
        plan_tags = {
            release_tag(component)
            for component in components
            if component["kind"] != "smoke" or component.get("fixtureOnly")
        }
        self.assertEqual(plan_tags, ARGOCD_TAGS)

    def test_existing_single_v_history_stops_at_exact_boundary(self) -> None:
        root = self.base / "history"
        make_argocd(root)
        tags = [{"name": tag, "sha": BOUNDARY} for tag in sorted(ARGOCD_TAGS)]
        _, payload = self.run_contract(root, tags=tags)
        self.validate_history(payload, ARGOCD_TAGS)

    def test_monitoring_and_real_nonplugin_exact_tags(self) -> None:
        monitoring = self.base / "monitoring"
        make_monitoring(monitoring)
        _, payload = self.run_contract(monitoring)
        self.validate_tags(payload, {
            "chart-monitoring-v0.1.0",
            "package-monitoring-stack-v0.2.0",
            "package-observability-pack-v0.3.0",
        })
        nonplugin = ROOT / "tests/fixtures/non-plugin-runtime"
        _, payload = self.run_contract(nonplugin)
        self.validate_tags(payload, {
            "hiroba-nonplugin-smoke-v0.1.0",
            "hiroba-nonplugin-package-v0.1.0",
        })

    def test_componentless_controls_expose_v_and_bare_version(self) -> None:
        root = self.base / "componentless"
        shutil.copytree(ROOT / "tests/fixtures/non-plugin-runtime", root)

        def componentless(target: Path, include_v: bool) -> None:
            path = target / "release-please-config.json"
            config = json.loads(path.read_text())
            for package in config["packages"].values():
                package.pop("component", None)
                package.pop("include-v-in-tag", None)
                if not include_v:
                    package["include-v-in-tag"] = False
            path.write_text(json.dumps(config))

        _, payload = self.run_contract(root, mutate=lambda target: componentless(target, True))
        self.assertEqual(set(payload["lookups"]), {"v0.1.0"})
        self.assertNotIn("0.1.0", payload["lookups"])
        _, payload = self.run_contract(root, mutate=lambda target: componentless(target, False))
        self.assertEqual(set(payload["lookups"]), {"0.1.0"})
        with self.assertRaises(AssertionError):
            self.validate_tags(payload, {"hiroba-nonplugin-smoke-v0.1.0", "hiroba-nonplugin-package-v0.1.0"})

    def test_invalid_path_components_and_double_v_fail_validation(self) -> None:
        cases = ("parent-path", "missing-extension", "wrong-ui", "double-v")
        for case in cases:
            with self.subTest(case=case):
                root = self.base / case
                make_argocd(root)

                def mutate(target: Path, selected: str = case) -> None:
                    path = target / "release-please-config.json"
                    config = json.loads(path.read_text())
                    if selected == "parent-path":
                        config["packages"]["extension"]["extra-files"][0] = "../extension.yaml"
                    elif selected == "missing-extension":
                        config["packages"]["extension"].pop("component")
                    elif selected == "wrong-ui":
                        config["packages"]["ui"]["component"] = "ext-argocd-ui"
                    else:
                        for package in config["packages"].values():
                            package["include-v-in-tag"] = True
                    path.write_text(json.dumps(config))

                result, payload = self.run_contract(root, mutate=mutate)
                if case == "parent-path":
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("illegal pathing characters in path: extension/../extension.yaml", result.stderr)
                    continue
                self.assertEqual(result.returncode, 0, result.stderr)
                with self.assertRaises(AssertionError):
                    self.validate_tags(payload, ARGOCD_TAGS)
                if case == "double-v":
                    self.assertIn("chart-argocd-vv0.1.0", payload["lookups"])

    def test_double_v_only_history_is_not_recognized(self) -> None:
        root = self.base / "wrong-history"
        make_argocd(root)
        wrong = sorted(tag.replace("-v", "-vv") for tag in ARGOCD_TAGS)
        _, payload = self.run_contract(root, tags=[{"name": tag, "sha": BOUNDARY} for tag in wrong])
        self.assertEqual(payload["history"], [NEWER, BOUNDARY, OLDER])
        with self.assertRaises(AssertionError):
            self.validate_history(payload, ARGOCD_TAGS)

    def test_missing_marker_and_crlf_do_not_pass_byte_validation(self) -> None:
        for case in ("missing-marker", "crlf"):
            with self.subTest(case=case):
                root = self.base / case
                make_argocd(root)
                path = root / "extension.yaml"
                if case == "missing-marker":
                    path.write_text(path.read_text().replace(" # x-release-please-version", ""))
                else:
                    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
                _, payload = self.run_contract(root)
                with self.assertRaises(AssertionError):
                    self.validate_extension_change(payload)
                if case == "crlf":
                    self.assertNotIn("\r\n", payload["changes"]["extension.yaml"]["content"])

    def test_branch_name_round_trip_and_delimiter_characterization(self) -> None:
        valid = ["extension", "ui", "Legacy_Name", "legacy.name", "_legacy", "legacy.locks"]
        invalid = "name--components--variant"
        _, payload = self.run_contract(self.base, branches=[*valid, invalid])
        for item, expected in zip(payload["branches"], [*valid, invalid]):
            self.assertEqual(item["component"], expected)
            if expected == invalid:
                self.assertEqual(item["targetBranch"], "main--components--name")
                self.assertEqual(item["parsedComponent"], "variant")
                checked = subprocess.run(
                    ["git", "check-ref-format", f"refs/heads/{item['branch']}"],
                    check=False,
                    capture_output=True,
                )
                self.assertEqual(checked.returncode, 0)
            else:
                self.assertEqual(item["targetBranch"], "main")
                self.assertEqual(item["parsedComponent"], expected)


if __name__ == "__main__":
    unittest.main()
