#!/usr/bin/env python3
"""Validate and emit a consumer's classified stack-lifecycle plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.stack_testing import load_stack_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        plan = load_stack_plan(args.root)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, yaml.YAMLError, jsonschema.SchemaError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(json.dumps(plan, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
