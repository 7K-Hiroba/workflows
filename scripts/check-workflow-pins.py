#!/usr/bin/env python3
"""Fail closed on mutable or unsafe GitHub Actions workflow references."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)(.*)$")
VERSION_COMMENT_RE = re.compile(r"#\s*v\d+(?:\.\d+){0,2}(?:[-+][0-9A-Za-z.-]+)?(?:\s|$)")
FORBIDDEN_RE = (
    re.compile(r"^\s*pull_request_target\s*:"),
    re.compile(r"^\s*secrets\s*:\s*inherit\s*(?:#.*)?$"),
)
WORKFLOW_SUFFIXES = (".yml", ".yaml", ".yml.template", ".yaml.template")
PLACEHOLDER = "__WORKFLOWS_V1_SHA__"


def workflow_files(root: Path) -> list[Path]:
    directory = root / ".github" / "workflows"
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and any(path.name.endswith(suffix) for suffix in WORKFLOW_SUFFIXES)
    )


def check_file(path: Path, root: Path, require_rendered: bool) -> list[str]:
    errors: list[str] = []
    is_template = path.name.endswith(".template")
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        location = f"{path.relative_to(root)}:{number}"
        if line.startswith("#"):
            continue
        if any(pattern.match(raw_line) for pattern in FORBIDDEN_RE):
            errors.append(f"{location}: forbidden workflow trigger or secrets inheritance")

        match = USES_RE.match(raw_line)
        if not match:
            continue
        target, comment = match.groups()
        target = target.strip("\"'")
        if target.startswith(("./", "$/")):
            continue
        if "@" not in target:
            errors.append(f"{location}: external action/workflow must include an immutable ref")
            continue
        _, ref = target.rsplit("@", 1)
        if ref == PLACEHOLDER:
            if require_rendered:
                errors.append(f"{location}: scaffold placeholder remains in rendered consumer")
            elif not is_template:
                errors.append(f"{location}: scaffold placeholder is only valid in .template callers")
            continue
        if target.startswith("docker://"):
            if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", ref):
                errors.append(f"{location}: container action must use a full sha256 digest")
        elif not SHA_RE.fullmatch(ref):
            errors.append(f"{location}: {target} must use a full 40-character commit SHA")
        if not VERSION_COMMENT_RE.search(comment):
            errors.append(f"{location}: {target} requires a human-readable version comment")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--require-rendered", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    files = workflow_files(root)
    errors = [error for path in files for error in check_file(path, root, args.require_rendered)]
    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    print(f"workflow pin policy passed: {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
