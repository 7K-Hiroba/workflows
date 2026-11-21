from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/finalize-release.sh"
SHA = "a" * 40


class FinalizeReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "CI"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "ci@example.invalid"], check=True)
        (self.root / "README.md").write_text("test\n")
        subprocess.run(["git", "-C", str(self.root), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "test"], check=True, capture_output=True)
        self.source = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({"app": "workflows-scaffold", "registryPrefix": "ghcr.io/7k-hiroba", "components": [{"kind": "package", "name": "app", "path": "packages/app", "version": "0.1.0"}]}))
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        (self.evidence / "artifact-catalog-app.json").write_text(json.dumps({"repository": "ghcr.io/7k-hiroba/workflows-scaffold/catalog/app", "digest": "sha256:" + "c" * 64, "mediaType": "application/vnd.inari.catalog.package.v1+yaml", "tag": "0.1.0", "sourceSha": self.source, "signature": {"verified": True}, "provenance": {"verified": True}, "testEvidence": {"status": "passed", "releaseTag": "app-v0.1.0"}}))
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.log"
        self.gitsign = self.bin / "gitsign"
        self.gitsign.write_text("#!/usr/bin/env bash\necho gitsign \"$@\" >> \"$CALL_LOG\"\nif [[ \"$1\" != verify ]]; then echo '[GNUPG:] SIG_CREATED'; printf '%s\n' '-----BEGIN CMS-----' 'YQ==' '-----END CMS-----'; fi\nexit 0\n")
        self.gh = self.bin / "gh"
        self.gh.write_text("#!/usr/bin/env bash\necho gh \"$@\" >> \"$CALL_LOG\"\nif [[ \"$1 $2\" == \"release view\" ]]; then exit 1; fi\n")
        fake_git = self.bin / "git"
        fake_git.write_text("#!/usr/bin/env bash\nif [[ \"$3\" == tag && \"$4\" == -s ]]; then root=$2; shift 4; exec /usr/bin/git -C \"$root\" tag -a \"$@\"; fi\nexec /usr/bin/git \"$@\"\n")
        fake_git.chmod(0o755)
        self.gitsign.chmod(0o755)
        self.gh.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.bin) + ":" + str(ROOT / ".venv/bin") + ":" + os.environ["PATH"], "CALL_LOG": str(self.log), "EXPECTED_TAG_SIGNER": "https://github.com/7K-Hiroba/workflows/.github/workflows/release.yml@", "PUSH_TAGS": "false"}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_finalize(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPT), "--root", str(self.root), "--plan", str(self.plan), "--source-sha", self.source, "--evidence", str(self.evidence)], env=self.env, text=True, capture_output=True, check=False)

    def test_finalizes_signed_tag_and_release_without_assets(self) -> None:
        result = self.run_finalize()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tag = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "app-v0.1.0^{commit}"], text=True).strip()
        self.assertEqual(tag, self.source)
        calls = self.log.read_text()
        self.assertIn("gitsign verify", calls)
        self.assertIn("gh release create app-v0.1.0", calls)
        self.assertNotIn("release upload", calls)

    def test_finalizes_opt_in_release_component_identity(self) -> None:
        self.plan.write_text(json.dumps({"app": "workflows-scaffold", "registryPrefix": "ghcr.io/7k-hiroba", "components": [{"kind": "package", "name": "app", "path": "packages/app", "version": "0.1.0", "releaseComponent": "package-app"}]}))
        artifact = self.evidence / "artifact-catalog-app.json"
        data = json.loads(artifact.read_text())
        data["testEvidence"]["releaseTag"] = "package-app-v0.1.0"
        artifact.write_text(json.dumps(data))
        result = self.run_finalize()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        resolved = subprocess.run(["git", "-C", str(self.root), "rev-parse", "package-app-v0.1.0^{commit}"], text=True, capture_output=True, check=False)
        self.assertEqual(resolved.returncode, 0, resolved.stdout + resolved.stderr)
        self.assertEqual(resolved.stdout.strip(), self.source)
        self.assertIn("gh release create package-app-v0.1.0", self.log.read_text())

    def test_finalizes_standalone_fixture_smoke_with_its_own_identity(self) -> None:
        self.plan.write_text(json.dumps({"app": "workflows-scaffold", "registryPrefix": "ghcr.io/7k-hiroba", "components": [{"kind": "smoke", "name": "workflows-scaffold-smoke", "path": "tests/smoke", "version": "0.1.0", "fixtureOnly": True, "releaseComponent": "smoke-workflows-scaffold-smoke"}]}))
        (self.evidence / "artifact-smoke-workflows-scaffold-smoke.json").write_text(json.dumps({"repository": "ghcr.io/7k-hiroba/workflows-scaffold/smoke/workflows-scaffold-smoke", "digest": "sha256:" + "c" * 64, "mediaType": "application/vnd.inari.smoke.suite.v1+yaml", "tag": "0.1.0", "sourceSha": self.source, "signature": {"verified": True}, "provenance": {"verified": True}, "testEvidence": {"status": "passed", "releaseTag": "smoke-workflows-scaffold-smoke-v0.1.0"}}))
        result = self.run_finalize()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        resolved = subprocess.run(["git", "-C", str(self.root), "rev-parse", "smoke-workflows-scaffold-smoke-v0.1.0^{commit}"], text=True, capture_output=True, check=False)
        self.assertEqual(resolved.returncode, 0, resolved.stdout + resolved.stderr)
        self.assertIn("gh release create smoke-workflows-scaffold-smoke-v0.1.0", self.log.read_text())

    def test_finalizes_extension_and_ui_with_matching_artifact_names(self) -> None:
        self.plan.write_text(json.dumps({"app": "workflows-scaffold", "registryPrefix": "ghcr.io/7k-hiroba", "components": [
            {"kind": "extension", "name": "extension", "path": "extension", "version": "0.1.0"},
            {"kind": "ui", "name": "ui", "path": "ui", "version": "0.1.0"},
        ]}))
        for name, repository, media, release_tag in (
            ("artifact-extension.json", "ghcr.io/7k-hiroba/workflows-scaffold/extension", "application/vnd.oci.image.manifest.v1+json", "extension-v0.1.0"),
            ("artifact-extension-ui.json", "ghcr.io/7k-hiroba/workflows-scaffold/extension-ui", "application/vnd.inari.extension.ui.v1", "ui-v0.1.0"),
        ):
            (self.evidence / name).write_text(json.dumps({"repository": repository, "digest": "sha256:" + "c" * 64, "mediaType": media, "tag": "0.1.0", "sourceSha": self.source, "signature": {"verified": True}, "provenance": {"verified": True}, "testEvidence": {"status": "passed", "releaseTag": release_tag}}))
        result = self.run_finalize()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text()
        self.assertIn("gh release create extension-v0.1.0", calls)
        self.assertIn("gh release create ui-v0.1.0", calls)

    def test_missing_or_unverified_evidence_stops_before_tag(self) -> None:
        (self.evidence / "artifact-catalog-app.json").write_text(json.dumps({"sourceSha": self.source, "signature": {"verified": False}, "provenance": {"verified": True}, "testEvidence": {"status": "passed"}}))
        result = self.run_finalize()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(subprocess.run(["git", "-C", str(self.root), "rev-parse", "app-v0.1.0"], capture_output=True).returncode, 0)
        self.assertFalse(self.log.exists())

    def test_mismatched_repository_version_or_signed_release_tag_stops_before_tag(self) -> None:
        path = self.evidence / "artifact-catalog-app.json"
        baseline = json.loads(path.read_text())
        for field, value in (("repository", "ghcr.io/7k-hiroba/other/catalog/app"), ("tag", "9.9.9")):
            data = json.loads(json.dumps(baseline))
            data[field] = value
            path.write_text(json.dumps(data))
            result = self.run_finalize()
            self.assertNotEqual(result.returncode, 0, field)
            self.assertFalse(self.log.exists())
        data = json.loads(json.dumps(baseline))
        data["testEvidence"]["releaseTag"] = "app-v9.9.9"
        path.write_text(json.dumps(data))
        result = self.run_finalize()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_existing_tag_at_other_source_fails(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "tag", "app-v0.1.0", "HEAD"], check=True)
        result = subprocess.run(["bash", str(SCRIPT), "--root", str(self.root), "--plan", str(self.plan), "--source-sha", "b" * 40, "--evidence", str(self.evidence)], env=self.env, text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
