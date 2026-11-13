#!/usr/bin/env python3
"""Validate and checksum a flat OCI Module Federation remote bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_ENTRY = 5 << 20
MAX_ASSET = 8 << 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_for(dist: Path, output: Path | None) -> dict:
    files = []
    excluded = output.resolve() if output else None
    for path in sorted(dist.rglob("*")):
        if not path.is_file():
            continue
        if excluded is not None and path.resolve() == excluded:
            continue
        relative = path.relative_to(dist)
        if len(relative.parts) != 1:
            raise ValueError(f"UI OCI bundle must be flat: {relative}")
        name = relative.name
        if ".." in name or not SAFE_NAME.fullmatch(name):
            raise ValueError(f"unsafe UI asset name: {name!r}")
        size = path.stat().st_size
        limit = MAX_ENTRY if name == "remoteEntry.js" else MAX_ASSET
        if size > limit:
            raise ValueError(f"UI asset {name} exceeds {limit} byte limit")
        files.append({"name": name, "size": size, "sha256": sha256(path)})
    if not any(entry["name"] == "remoteEntry.js" for entry in files):
        raise ValueError("remoteEntry.js is required")
    return {"schema": "inari.ui.bundle.v1", "files": files}


def verify_oci(oci: Path, expected: dict) -> None:
    actual_files = {path.relative_to(oci).as_posix(): path for path in oci.rglob("*") if path.is_file()}
    expected_files = {entry["name"]: entry for entry in expected["files"]}
    missing = sorted(set(expected_files) - set(actual_files))
    extra = sorted(set(actual_files) - set(expected_files))
    if missing or extra:
        raise ValueError(f"OCI asset mismatch; missing={missing}, extra={extra}")
    for name, entry in expected_files.items():
        if actual_files[name].stat().st_size != entry["size"] or sha256(actual_files[name]) != entry["sha256"]:
            raise ValueError(f"OCI asset checksum mismatch: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--oci-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    try:
        expected = manifest_for(args.dist, args.output)
        if args.output:
            args.output.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.oci_dir:
            if not args.manifest:
                raise ValueError("--manifest is required with --oci-dir")
            packaged = json.loads(args.manifest.read_text(encoding="utf-8"))
            if packaged != expected:
                raise ValueError("manifest differs from current dist")
            verify_oci(args.oci_dir, packaged)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"UI bundle passed: {len(expected['files'])} asset(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
