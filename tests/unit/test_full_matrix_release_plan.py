from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv/bin/python"
SOURCE = "a" * 40

sys.path.insert(0, str(ROOT / "scripts"))
from lib.release_contract import release_tag  # noqa: E402


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_matrix_repo(root: Path, kind: str, mask: int) -> dict:
    name = "matrix-app"
    plugin = bool(mask & 1) or kind == "extension"
    ui = bool(mask & 2)
    chart = bool(mask & 4)
    observability = bool(mask & 8)
    smoke = bool(mask & 16)
    config = {
        "schema": "inari.hiroba.app.v1",
        "app": name,
        "trustTier": "experimental",
        "components": {"chartsRoot": "charts", "packagesRoot": "packages", "templatesRoot": "templates"},
    }
    release_components = {}
    if plugin:
        config["components"]["extension"] = {"path": "extension", "version": "0.1.0"}
    if ui:
        config["components"]["ui"] = {"path": "ui", "version": "0.1.0"}
    if plugin or ui:
        config["compatibility"] = {"matrix": "ci/compatibility-matrix.json"}
        write(root / "ci/compatibility-matrix.json", json.dumps({"schema": "inari.compat.v1", "entries": []}))
        write(root / "extension.yaml", yaml.safe_dump({
            "apiVersion": "inari.io/v1alpha1",
            "kind": "Extension",
            "metadata": {"name": name},
            "spec": {
                "version": "0.1.0",
                "kinds": (["backend"] if plugin else []) + (["ui"] if ui else []),
                "backend": {"image": f"ghcr.io/7k-hiroba/{name}/extension", "digestPinning": "required"},
                "ui": {"remoteEntryOci": f"ghcr.io/7k-hiroba/{name}/extension-ui", "slots": [{"kind": "cluster-tab", "name": "health"}]},
                "contracts": {"backend": ["inari.plugin.v1"], "ui": {"sdk": ">=0.1.8 <2.0.0", "hostApi": "inari.ui.v1"}},
            },
        }, sort_keys=False))
    if kind in {"app", "catalog"}:
        release_components[f"packages/{name}"] = f"package-{name}"
        write(root / f"packages/{name}/package.yaml", "version: 0.1.0\nchannel: incubating\ntype: platform-app\ndescription: matrix package\ncategory: test\n")
    if kind in {"app", "template"}:
        release_components[f"templates/{name}"] = f"template-{name}"
        write(root / f"templates/{name}/template.yaml", f"name: {name}\nversion: 0.1.0\nchannel: incubating\ndescription: matrix template\nkind: component\n")
    if chart:
        release_components[f"charts/{name}"] = f"chart-{name}"
        write(root / f"charts/{name}/Chart.yaml", f"apiVersion: v2\nname: {name}\nversion: 0.1.0\nappVersion: 0.1.0\n")
    if observability:
        release_components["packages/observability-pack"] = "package-observability-pack"
        write(root / "packages/observability-pack/package.yaml", "version: 0.1.0\nchannel: incubating\ntype: kro-rgd\ndescription: companion\ncategory: observability\n")
    if smoke:
        target = {"id": name if chart else f"{name}-smoke", "version": "0.1.0", "adapter": {"kind": "helm" if chart else "manifests", "fixtureOnly": not chart}}
        config["smoke"] = {"path": "tests/smoke"}
        if chart:
            target["component"] = f"charts/{name}"
            config["smoke"]["targetComponent"] = f"charts/{name}"
        else:
            release_components["tests/smoke"] = f"smoke-{name}-smoke"
        write(root / "tests/smoke/suite.yaml", yaml.safe_dump({
            "suiteSchema": "inari.smoke.v1",
            "target": target,
            "compatibleAppVersions": ">=0.1.0 <2.0.0",
            "executableProfiles": ["ci", "stage", "prod"] if chart else ["ci"],
        }, sort_keys=False))
    if release_components:
        config["releaseComponents"] = release_components
    write(root / ".hiroba.yaml", yaml.safe_dump(config, sort_keys=False))
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    return {"plugin": plugin, "ui": ui, "chart": chart, "releaseComponents": release_components}


class FullMatrixReleasePlanTests(unittest.TestCase):
    def test_all_128_combinations_have_unique_release_identities_and_valid_lanes(self) -> None:
        checked = 0
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ("app", "extension", "catalog", "template"):
                for mask in range(32):
                    with self.subTest(kind=kind, mask=mask):
                        root = Path(tmp) / f"{kind}-{mask:02}"
                        selected = make_matrix_repo(root, kind, mask)
                        result = subprocess.run([
                            str(PYTHON), str(ROOT / "scripts/prepare-release-plan.py"),
                            "--root", str(root), "--source-sha", SOURCE, "--rehearsal",
                        ], text=True, capture_output=True, check=False)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        plan = json.loads(result.stdout)
                        components = plan["publishComponents"]
                        independent = [item for item in components if item["kind"] != "smoke" or item["fixtureOnly"]]
                        tags = [release_tag(item) for item in independent]
                        self.assertEqual(len(tags), len(set(tags)), tags)
                        artifact_smoke = [item for item in components if item["kind"] == "smoke" and not item["fixtureOnly"]]
                        for smoke in artifact_smoke:
                            target = next(item for item in components if item["path"] == smoke["targetComponent"])
                            self.assertEqual(release_tag(smoke), release_tag(target))
                        self.assertEqual(plan["hasExtension"], selected["plugin"])
                        self.assertEqual(plan["hasUI"], selected["ui"])
                        self.assertEqual("compat" in plan["requiredLanes"], selected["plugin"])
                        self.assertEqual("browser" in plan["requiredLanes"], selected["ui"])

                        synchronized = subprocess.run([
                            str(PYTHON), str(ROOT / "scripts/sync-release-please-config.py"), "--root", str(root),
                        ], text=True, capture_output=True, check=False)
                        self.assertEqual(synchronized.returncode, 0, synchronized.stdout + synchronized.stderr)
                        release_please = json.loads((root / "release-please-config.json").read_text())
                        for path, identity in selected["releaseComponents"].items():
                            self.assertEqual(release_please["packages"][path]["component"], identity)
                        for kind_name in ("extension", "ui"):
                            if kind_name in release_please["packages"]:
                                self.assertNotIn("component", release_please["packages"][kind_name])
                        checked += 1
        self.assertEqual(checked, 128)


if __name__ == "__main__":
    unittest.main()
