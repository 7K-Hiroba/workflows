from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from lib.release_contract import artifact_key, contract, validate_artifact  # noqa: E402

SOURCE = "a" * 40
DIGEST = "sha256:" + "b" * 64


class ReleaseContractTests(unittest.TestCase):
    def test_every_component_kind_has_bound_repository_tag_and_signed_release(self) -> None:
        components = [
            ({"kind": "package", "name": "app", "version": "1.2.3"}, "catalog/app", "app-v1.2.3"),
            ({"kind": "template", "name": "service", "version": "1.2.3"}, "templates/service", "service-v1.2.3"),
            ({"kind": "chart", "name": "app", "version": "1.2.3"}, "charts/app", "app-v1.2.3"),
            ({"kind": "smoke", "name": "app", "version": "1.2.3"}, "smoke/app", "app-v1.2.3"),
            ({"kind": "extension", "name": "extension", "version": "1.2.3"}, "extension", "extension-v1.2.3"),
            ({"kind": "ui", "name": "ui", "version": "1.2.3"}, "extension-ui", "ui-v1.2.3"),
        ]
        for component, suffix, signed_tag in components:
            with self.subTest(kind=component["kind"]):
                expected = contract(component, "app", "ghcr.io/7k-hiroba", SOURCE, "normal")
                self.assertEqual(expected["repository"], f"ghcr.io/7k-hiroba/app/{suffix}")
                self.assertEqual(expected["artifactTag"], "1.2.3")
                self.assertEqual(expected["releaseTag"], signed_tag)
                media = "application/vnd.oci.image.manifest.v1+json" if component["kind"] == "extension" else expected["mediaType"]
                artifact = {
                    "repository": expected["repository"],
                    "digest": DIGEST,
                    "mediaType": media,
                    "tag": "1.2.3",
                    "sourceSha": SOURCE,
                    "signature": {"verified": True},
                    "provenance": {"verified": True},
                    "testEvidence": {"status": "passed", "releaseTag": signed_tag},
                }
                self.assertEqual(validate_artifact(artifact, component, "app", "ghcr.io/7k-hiroba", SOURCE, "normal"), expected)

    def test_template_artifact_key_uses_canonical_plural(self) -> None:
        component = {"kind": "template", "name": "service", "version": "1.2.3"}
        self.assertEqual(artifact_key(component), "templates-service")
        self.assertEqual(contract(component, "app", "ghcr.io/7k-hiroba", SOURCE, "normal")["key"], "templates-service")

    def test_index_and_rehearsal_contracts_use_source_and_ci_identities(self) -> None:
        for name in ("catalog", "template"):
            component = {"kind": "index", "name": name}
            expected = contract(component, "app", "ghcr.io/7k-hiroba", SOURCE, "normal")
            self.assertEqual(expected["artifactTag"], SOURCE)
            self.assertEqual(expected["releaseTag"], f"release-set-{SOURCE[:12]}")
        chart = {"kind": "chart", "name": "app", "version": "1.2.3"}
        expected = contract(chart, "app", "ghcr.io/7k-hiroba", SOURCE, "rehearsal")
        self.assertEqual(expected["artifactTag"], f"1.2.3-ci.{SOURCE[:12]}")
        self.assertEqual(expected["releaseTag"], f"ci-{SOURCE[:12]}")


if __name__ == "__main__":
    unittest.main()
