#!/usr/bin/env python3
"""Validate and emit a consumer-owned chart kind-test declaration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import yaml

from lib.chart_testing import load


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--chart", required=True)
    args = parser.parse_args()
    try:
        result = load(args.root, args.chart)
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError, jsonschema.ValidationError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
