from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/move-release-channels.py"
DIGEST = "sha256:" + "a" * 64
SOURCE = "b" * 40


class ChannelCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.log"
        oras = self.bin / "oras"
        oras.write_text("#!/usr/bin/env bash\necho oras \"$@\" >> \"$CALL_LOG\"\n")
        crane = self.bin / "crane"
        crane.write_text("#!/usr/bin/env bash\necho crane \"$@\" >> \"$CALL_LOG\"\necho \"$DIGEST\"\n")
        oras.chmod(0o755)
        crane.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.bin) + ":" + os.environ["PATH"], "CALL_LOG": str(self.log), "DIGEST": DIGEST}
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({
            "app": "app",
            "publishComponents": [
                {"kind": "package", "name": "app", "channel": "incubating", "version": "0.1.0"},
                {"kind": "template", "name": "service", "channel": "stable", "version": "0.1.0"},
            ],
        }))
        for key, repository, media, channel in (
            ("catalog-app", "ghcr.io/7k-hiroba/app/catalog/app", "application/vnd.inari.catalog.package.v1+yaml", "incubating"),
            ("template-service", "ghcr.io/7k-hiroba/app/templates/service", "application/vnd.inari.template.v1", "stable"),
            ("index-catalog", "ghcr.io/7k-hiroba/app/catalog/index", "application/vnd.inari.catalog.index.v1+yaml", "latest"),
            ("index-template", "ghcr.io/7k-hiroba/app/templates/index", "application/vnd.inari.template.index.v1+yaml", "latest"),
        ):
            self.artifact(key, repository, media, channel)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def artifact(self, key: str, repository: str, media: str, channel: str) -> Path:
        path = self.evidence / f"artifact-{key}.json"
        component = key.split("-", 1)[1]
        is_index = key.startswith("index-")
        tag = SOURCE if is_index else "0.1.0"
        release_tag = f"release-set-{SOURCE[:12]}" if is_index else f"{component}-v0.1.0"
        path.write_text(json.dumps({
            "repository": repository,
            "digest": DIGEST,
            "mediaType": media,
            "tag": tag,
            "sourceSha": SOURCE,
            "channel": channel,
            "signature": {"verified": True},
            "provenance": {"verified": True},
            "testEvidence": {"status": "passed", "releaseTag": release_tag},
        }))
        return path

    def run_coordinator(self, mode: str = "normal") -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            str(ROOT / ".venv/bin/python"), str(SCRIPT), "--plan", str(self.plan), "--evidence", str(self.evidence),
            "--source-sha", SOURCE, "--registry-prefix", "ghcr.io/7k-hiroba", "--mode", mode,
        ], env=self.env, text=True, capture_output=True, check=False)

    def test_moves_all_channels_only_after_every_receipt_validates(self) -> None:
        result = self.run_coordinator()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text()
        for channel in ("incubating", "stable", "latest"):
            self.assertIn(channel, calls)
        self.assertIn(f"oras tag ghcr.io/7k-hiroba/app/catalog/app@{DIGEST} incubating", calls)

    def test_unverified_later_index_prevents_every_channel_move(self) -> None:
        path = self.evidence / "artifact-index-template.json"
        data = json.loads(path.read_text())
        data["testEvidence"]["status"] = "pending"
        path.write_text(json.dumps(data))
        result = self.run_coordinator()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists(), self.log.read_text() if self.log.exists() else "")

    def test_mismatched_version_or_signed_release_tag_prevents_all_moves(self) -> None:
        path = self.evidence / "artifact-catalog-app.json"
        baseline = json.loads(path.read_text())
        for mutate in (
            lambda data: data.update(repository="ghcr.io/7k-hiroba/other/catalog/app"),
            lambda data: data.update(tag="9.9.9"),
            lambda data: data["testEvidence"].update(releaseTag="app-v9.9.9"),
        ):
            data = json.loads(json.dumps(baseline))
            mutate(data)
            path.write_text(json.dumps(data))
            result = self.run_coordinator()
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.log.exists())

    def test_rehearsal_validates_without_moving_channels(self) -> None:
        for path in self.evidence.glob("artifact-*.json"):
            data = json.loads(path.read_text())
            data["channel"] = ""
            data["tag"] = SOURCE
            data["testEvidence"]["releaseTag"] = f"ci-{SOURCE[:12]}"
            path.write_text(json.dumps(data))
        result = self.run_coordinator("rehearsal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
