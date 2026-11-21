from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.names import bounded_resource_name  # noqa: E402


class BoundedResourceNameTests(unittest.TestCase):
    def test_short_and_boundary_names_are_unchanged(self) -> None:
        for name in ("a", "matrix-app", "a" * 53):
            with self.subTest(name=name):
                self.assertEqual(bounded_resource_name(name, 53), name)

    def test_long_name_matches_cli_contract(self) -> None:
        name = "a" + "b" * 61 + "c"
        self.assertEqual(bounded_resource_name(name, 53), "abbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb-00bdc0e0")
        self.assertEqual(len(bounded_resource_name(name, 53)), 53)

    def test_long_names_are_deterministic_bounded_and_distinct(self) -> None:
        first = "a" + "b" * 61 + "c"
        second = "a" + "b" * 61 + "d"
        for limit in (53, 55, 57):
            with self.subTest(limit=limit):
                left = bounded_resource_name(first, limit)
                self.assertEqual(left, bounded_resource_name(first, limit))
                self.assertLessEqual(len(left), limit)
                self.assertNotEqual(left, bounded_resource_name(second, limit))
                self.assertFalse(left.endswith("-"))

    def test_tiny_limit_fails_instead_of_truncating_unsafely(self) -> None:
        with self.assertRaises(ValueError):
            bounded_resource_name("long-name-exceeds", 9)


if __name__ == "__main__":
    unittest.main()
