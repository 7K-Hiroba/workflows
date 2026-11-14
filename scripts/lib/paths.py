"""Consumer-root path confinement shared by validation and release discovery."""

from __future__ import annotations

from pathlib import Path


def confined_path(root: Path, value: str, label: str = "path") -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} uses an unsafe path outside the consumer root: {value!r}")
    root = root.resolve()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{label} escapes the consumer root: {value!r}")
    return resolved


def relative_path(root: Path, value: str, label: str = "path") -> str:
    return confined_path(root, value, label).relative_to(root.resolve()).as_posix()
