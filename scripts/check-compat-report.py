#!/usr/bin/env python3
"""Reject stale, failed, incomplete, or unrelated compatibility evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SHA = set("0123456789abcdef")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--max-age-days", type=int, default=7)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if report.get("status") != "passed" or not report.get("entries"):
            raise ValueError("compatibility report is not a non-empty passing report")
        if any(entry.get("status") != "passed" for entry in report["entries"]):
            raise ValueError("compatibility report contains a failed lane")
        expected = args.source_sha.lower()
        if len(expected) != 40 or set(expected) - SHA or report.get("sourceSha", "").lower() != expected:
            raise ValueError("compatibility report sourceSha does not match required source")
        completed = datetime.fromisoformat(report["completedAt"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if completed > now + timedelta(minutes=5):
            raise ValueError("compatibility report completion is in the future")
        if completed < now - timedelta(days=args.max_age_days):
            raise ValueError(f"compatibility evidence is older than {args.max_age_days} days")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print("compatibility report is passing, source-bound, and fresh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
