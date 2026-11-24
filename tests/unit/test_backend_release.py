from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/release-backend.sh"
CONFIG = json.dumps({"architecture": "amd64", "os": "linux", "rootfs": {"type": "layers", "diff_ids": []}}, sort_keys=True, separators=(",", ":")).encode()
CONFIG_DIGEST = hashlib.sha256(CONFIG).hexdigest()
MANIFEST = json.dumps({
    "schemaVersion": 2,
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": "sha256:" + CONFIG_DIGEST, "size": len(CONFIG)},
    "layers": [],
}, sort_keys=True, separators=(",", ":")).encode()
DIGEST = "sha256:" + hashlib.sha256(MANIFEST).hexdigest()
OTHER = "sha256:" + "d" * 64


class BackendReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = self.root / "context"
        self.context.mkdir()
        self.candidate = self.root / "candidate.tar"
        files = {
            "oci-layout": json.dumps({"imageLayoutVersion": "1.0.0"}).encode(),
            "index.json": json.dumps({"schemaVersion": 2, "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": DIGEST, "size": len(MANIFEST)}]}).encode(),
            "blobs/sha256/" + DIGEST.removeprefix("sha256:"): MANIFEST,
            "blobs/sha256/" + CONFIG_DIGEST: CONFIG,
        }
        with tarfile.open(self.candidate, "w") as archive:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        self.pushed = self.root / "pushed-layout"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.log"
        self.state = self.root / "state"
        docker = self.bin / "docker"
        docker.write_text("#!/usr/bin/env bash\nset -e\necho docker \"$@\" >> \"$CALL_LOG\"\nout=\"\"\nwhile [[ $# -gt 0 ]]; do if [[ \"$1\" == --output ]]; then out=${2#type=oci,dest=}; out=${out%%,*}; shift 2; else shift; fi; done\ncp \"$CANDIDATE\" \"$out\"\n")
        git = self.bin / "git"
        git.write_text("""#!/usr/bin/env bash
set -e
echo git "$@" >> "$CALL_LOG"
if [[ "${FAKE_GIT_FAIL:-}" == 1 ]]; then exit 1; fi
if [[ "$1" == -C && "$3" == log && "$4" == -1 && "$5" == --format=%ct ]]; then
  printf '%s\n' "$FAKE_EPOCH"
  exit 0
fi
exit 1
""")
        crane = self.bin / "crane"
        crane.write_text("""#!/usr/bin/env bash
set -e
echo crane "$@" >> "$CALL_LOG"
case "$1" in
  digest)
    if [[ -f "$STATE" ]]; then cat "$STATE"; else exit 1; fi
    ;;
  push)
    layout=$2
    [[ -d "$layout" ]] || { echo "crane push source is not an OCI layout directory: $layout" >&2; exit 1; }
    python3 - "$layout" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
layout = json.loads((root / "oci-layout").read_text())
assert layout["imageLayoutVersion"] == "1.0.0"
index = json.loads((root / "index.json").read_text())
assert index["schemaVersion"] == 2
for descriptor in index["manifests"]:
    digest = descriptor["digest"]
    blob = root / "blobs" / digest.replace(":", "/", 1)
    assert hashlib.sha256(blob.read_bytes()).hexdigest() == digest.split(":", 1)[1]
PY
    rm -rf "$PUSH_CAPTURE"
    cp -R "$layout" "$PUSH_CAPTURE"
    printf '%s' "$EXPECTED_DIGEST" > "$STATE"
    ;;
esac
""")
        docker.chmod(0o755)
        crane.chmod(0o755)
        git.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + ":" + os.environ["PATH"],
            "CALL_LOG": str(self.log),
            "STATE": str(self.state),
            "CANDIDATE": str(self.candidate),
            "EXPECTED_DIGEST": DIGEST,
            "PUSH_CAPTURE": str(self.pushed),
            "FAKE_EPOCH": "1700000000",
        }
        self.env.pop("SOURCE_DATE_EPOCH", None)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def publish(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            "bash", str(SCRIPT), "--context", str(self.context), "--repository", "ghcr.io/7k-hiroba/app/extension",
            "--tag", "1.0.0", "--source-sha", "a" * 40, "--output", str(self.root / "artifact.json"), *extra,
        ], env=self.env, text=True, capture_output=True, check=False)

    def test_edge_channel_is_recorded_only_when_requested(self) -> None:
        result = self.publish("--channel", "edge")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads((self.root / "artifact.json").read_text())["channel"], "edge")

    def test_always_builds_and_pushes_missing_candidate(self) -> None:
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text()
        self.assertIn("docker buildx build", calls)
        self.assertIn("crane push", calls)
        artifact = json.loads((self.root / "artifact.json").read_text())
        self.assertEqual(artifact["digest"], DIGEST)
        self.assertEqual(artifact["mediaType"], "application/vnd.oci.image.manifest.v1+json")

    def test_pushes_extracted_oci_layout_directory_not_tarball(self) -> None:
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        push = next(line for line in self.log.read_text().splitlines() if line.startswith("crane push "))
        pushed_path = push.split(" ", 3)[2]
        self.assertTrue(pushed_path.endswith("/candidate-oci"), pushed_path)
        self.assertFalse(pushed_path.endswith(".tar"), pushed_path)
        self.assertEqual(json.loads((self.pushed / "oci-layout").read_text())["imageLayoutVersion"], "1.0.0")
        index = json.loads((self.pushed / "index.json").read_text())
        self.assertEqual(index["manifests"][0]["digest"], DIGEST)
        manifest = self.pushed / "blobs/sha256" / DIGEST.removeprefix("sha256:")
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), DIGEST.removeprefix("sha256:"))
        self.assertTrue((self.pushed / "blobs/sha256" / CONFIG_DIGEST).is_file())

    def test_matching_existing_digest_is_reused_after_candidate_build(self) -> None:
        self.state.write_text(DIGEST)
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text()
        self.assertIn("docker buildx build", calls)
        self.assertNotIn("crane push", calls)

    def test_tampered_existing_image_fails_before_push_or_attestation(self) -> None:
        self.state.write_text(OTHER)
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("existing backend image digest differs", result.stdout + result.stderr)
        calls = self.log.read_text()
        self.assertIn("docker buildx build", calls)
        self.assertNotIn("crane push", calls)
        self.assertFalse((self.root / "artifact.json").exists())

    def test_build_uses_source_epoch_and_rewritten_timestamps(self) -> None:
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text()
        build = next(line for line in calls.splitlines() if line.startswith("docker buildx build "))
        self.assertIn("--build-arg SOURCE_DATE_EPOCH=1700000000", build)
        output = next(arg for arg in build.split() if arg.startswith("type=oci,dest="))
        self.assertIn("rewrite-timestamp=true", output)
        git_call = next(line for line in calls.splitlines() if line.startswith("git "))
        self.assertIn("--format=%ct", git_call)
        self.assertIn("a" * 40, git_call)

    def test_source_date_epoch_override_wins(self) -> None:
        self.env["SOURCE_DATE_EPOCH"] = "1800000000"
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text()
        build = next(line for line in calls.splitlines() if line.startswith("docker buildx build "))
        self.assertIn("--build-arg SOURCE_DATE_EPOCH=1800000000", build)
        self.assertNotIn("git ", calls)

    def test_epoch_derivation_failure_fails_closed(self) -> None:
        self.env["FAKE_GIT_FAIL"] = "1"
        result = self.publish()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("SOURCE_DATE_EPOCH", result.stdout + result.stderr)
        self.assertNotIn("docker buildx build", self.log.read_text() if self.log.exists() else "")
        self.assertFalse((self.root / "artifact.json").exists())

    def test_invalid_epoch_rejected(self) -> None:
        self.env["SOURCE_DATE_EPOCH"] = "not-an-epoch"
        result = self.publish()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("SOURCE_DATE_EPOCH", result.stdout + result.stderr)
        self.assertNotIn("docker buildx build", self.log.read_text() if self.log.exists() else "")
        self.assertFalse((self.root / "artifact.json").exists())


if __name__ == "__main__":
    unittest.main()
