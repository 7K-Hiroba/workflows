#!/usr/bin/env python3
"""Verify ephemeral Grafana folder/dashboard/datasource and panel queries."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def request(url: str, method: str = "GET", body: dict | None = None) -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def run(base: str, uid: str, app: str) -> None:
    health = request(base + "/api/health")
    if health.get("database") != "ok":
        raise ValueError("Grafana database is not ready")
    found = request(base + "/api/search?query=" + uid)
    matches = [entry for entry in found if entry.get("uid") == uid]
    if not matches:
        raise ValueError(f"dashboard {uid} is not provisioned")
    folder = matches[0].get("folderTitle", "")
    if folder != app and not folder.startswith(app + "/"):
        raise ValueError(f"dashboard folder {folder!r} does not match app {app!r}")
    dashboard = request(base + f"/api/dashboards/uid/{uid}")["dashboard"]
    panels = dashboard.get("panels", [])
    if not panels:
        raise ValueError("dashboard has no panels")
    variables = dashboard.get("templating", {}).get("list", [])
    for panel in panels:
        datasource = panel.get("datasource", {})
        variable = datasource.get("uid", "")
        if not variable.startswith("${DS_"):
            raise ValueError("panel datasource is not a declared variable")
        name = variable[2:-1]
        current = next((item.get("current", {}).get("value") for item in variables if item.get("name") == name), None)
        if not current:
            raise ValueError(f"dashboard datasource variable {name} has no current value")
        resolved = request(base + f"/api/datasources/uid/{current}")
        for target in panel.get("targets", []):
            expr = target.get("expr")
            if not expr:
                continue
            response = request(base + "/api/ds/query", "POST", {
                "from": "now-5m",
                "to": "now",
                "queries": [{
                    "refId": "A",
                    "datasource": {"type": resolved["type"], "uid": resolved["uid"]},
                    "expr": expr,
                    "intervalMs": 1000,
                    "maxDataPoints": 100,
                }],
            })
            result = response.get("results", {}).get("A", {})
            if result.get("status") != 200 or not result.get("frames"):
                raise ValueError(f"panel query failed for {expr}: {result}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--uid", required=True)
    parser.add_argument("--app", required=True)
    args = parser.parse_args()
    try:
        run(args.url.rstrip("/"), args.uid, args.app)
    except (ValueError, KeyError, TypeError, urllib.error.URLError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"Grafana dashboard {args.uid} and all panel queries are ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
