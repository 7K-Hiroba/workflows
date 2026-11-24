#!/usr/bin/env python3
"""Derive chart-release evidence requirements from exact consumer source."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.stack_testing import load_stack_plan  # noqa: E402
from lib.chart_testing import lifecycle_artifact, lifecycle_lane, load as load_chart_test  # noqa: E402
from lib.paths import relative_path  # noqa: E402

LANE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--chart", required=True)
    parser.add_argument("--standalone", choices=("true", "false"), required=True)
    parser.add_argument("--required-lanes", required=True)
    args = parser.parse_args()
    try:
        lanes = args.required_lanes.split()
        if not lanes or any(not LANE.fullmatch(lane) for lane in lanes):
            raise ValueError("required lanes must be non-empty valid lane names")
        stack = load_stack_plan(args.root)
        has_stack = bool(stack["enabled"])
        if args.standalone == "true" and has_stack and "stack-lifecycle" not in lanes:
            lanes.append("stack-lifecycle")
        config = yaml.safe_load((args.root / ".hiroba.yaml").read_text(encoding="utf-8"))
        charts_root = config.get("components", {}).get("chartsRoot", "charts")
        chart_path = relative_path(args.root, str(Path(charts_root) / args.chart), "chart")
        chart_test = load_chart_test(args.root, chart_path)
        has_chart_lifecycle = "upgrade" in chart_test
        chart_lane = lifecycle_lane(chart_path) if has_chart_lifecycle else ""
        if chart_lane and chart_lane not in lanes:
            lanes.append(chart_lane)
        output = {
            "hasStackTest": has_stack,
            "hasChartLifecycle": has_chart_lifecycle,
            "chartLifecycleLane": chart_lane,
            "chartLifecycleArtifact": lifecycle_artifact(chart_path) if has_chart_lifecycle else "",
            "chartPath": chart_path,
            "requiredLanes": " ".join(lanes),
        }
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, yaml.YAMLError, jsonschema.SchemaError, jsonschema.ValidationError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
