#!/usr/bin/env python3
"""Fetch exact Helm dependencies without changing chart metadata."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


def prepare(chart: Path) -> None:
    chart_yaml = chart / "Chart.yaml"
    chart_lock = chart / "Chart.lock"
    if not chart.is_dir() or not chart_yaml.is_file():
        raise ValueError("chart directory must contain Chart.yaml")
    document = yaml.safe_load(chart_yaml.read_text())
    if not isinstance(document, dict):
        raise ValueError("Chart.yaml must contain a mapping")
    dependencies = document.get("dependencies") or []
    if not isinstance(dependencies, list):
        raise ValueError("Chart.yaml dependencies must be a list")
    if not dependencies:
        return
    if not chart_lock.is_file():
        raise ValueError("chart dependencies require Chart.lock")
    metadata = {path: path.read_bytes() for path in (chart_yaml, chart_lock)}
    subprocess.run(["helm", "dependency", "update", str(chart)], check=True)
    if any(path.read_bytes() != original for path, original in metadata.items()):
        raise ValueError("locked chart metadata drift after dependency resolution")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chart", type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.chart)
    except (OSError, ValueError, yaml.YAMLError, subprocess.CalledProcessError) as error:
        print(f"chart dependency preparation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
