#!/usr/bin/env python3
"""Emit a deterministic release/CI component plan as JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import discover, filter_changed  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--all", action="store_true", help="Include every component (the default)")
    parser.add_argument("--changed-files", type=Path)
    parser.add_argument("--source-sha")
    args = parser.parse_args()
    plan = discover(args.root)
    if args.changed_files:
        changed = [line.strip() for line in args.changed_files.read_text(encoding="utf-8").splitlines() if line.strip()]
        plan = filter_changed(plan, changed)
    if args.source_sha:
        if len(args.source_sha) != 40 or any(character not in "0123456789abcdefABCDEF" for character in args.source_sha):
            parser.error("--source-sha must be a full 40-character commit SHA")
        plan["sourceSha"] = args.source_sha.lower()
    print(json.dumps(plan, indent=2, sort_keys=True) + "\n", end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
