#!/usr/bin/env python3
"""Select untagged release components and derive required evidence lanes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.metadata import SHA_RE, discover  # noqa: E402


def tag_for(component: dict) -> str:
    if component["kind"] == "extension":
        return f"extension-v{component['version']}"
    if component["kind"] == "ui":
        return f"ui-v{component['version']}"
    return f"{component['name']}-v{component['version']}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--edge", action="store_true")
    parser.add_argument("--changed-files", type=Path)
    parser.add_argument("--repair-tag")
    parser.add_argument("--rehearsal", action="store_true")
    args = parser.parse_args()
    if not SHA_RE.fullmatch(args.source_sha):
        parser.error("source SHA must be full 40 characters")
    root = args.root.resolve()
    plan = discover(root)
    all_components = plan["components"]
    tags = set(subprocess.check_output(["git", "-C", str(root), "tag", "--list"], text=True).splitlines())
    components = []
    if args.rehearsal:
        components = []
    elif args.repair_tag:
        for component in all_components:
            if component["kind"] != "smoke" and tag_for(component) == args.repair_tag:
                components.append(component)
        for component in all_components:
            if component["kind"] == "smoke":
                target = next(item for item in all_components if item["path"] == component["targetComponent"])
                if tag_for(target) == args.repair_tag:
                    components.append(component)
    elif args.edge:
        components = list(all_components)
    else:
        for component in all_components:
            if component["kind"] != "smoke" and tag_for(component) not in tags:
                components.append(component)
        target_tags = {tag_for(component) for component in components}
        for component in all_components:
            if component["kind"] != "smoke":
                continue
            target = next((item for item in all_components if item["path"] == component["targetComponent"]), None)
            if target is None:
                print(f"::error::smoke target component {component['targetComponent']} does not exist", file=sys.stderr)
                return 1
            target_tag = tag_for(target)
            if target_tag not in tags or target_tag in target_tags:
                components.append(component)
        if args.changed_files:
            changed = [line.strip() for line in args.changed_files.read_text().splitlines() if line.strip()]
            for component in all_components:
                if component["kind"] != "smoke":
                    continue
                target = next(item for item in all_components if item["path"] == component["targetComponent"])
                if any(path.startswith(component["path"] + "/") for path in changed) and tag_for(target) in tags and tag_for(target) not in target_tags:
                    print("::error::smoke-only change requires a target component version bump", file=sys.stderr)
                    return 1
    if args.rehearsal:
        publish_components = list(all_components)
    elif args.edge or args.repair_tag:
        publish_components = list(components)
    elif components:
        publish_components = list(all_components)
    else:
        publish_components = []
    kinds = {component["kind"] for component in publish_components}
    has_observability = bool(plan.get("observability")) if "observability" in plan else bool((root / "observability/observability.yaml").is_file())
    required = ["validate"]
    for kind, lane in (("package", "package"), ("extension", "go"), ("ui", "ui"), ("chart", "chart")):
        if kind in kinds:
            required.append(lane)
    if has_observability and components:
        required.append("observability")
    if "extension" in kinds or "ui" in kinds:
        required.append("compat")
    if "ui" in kinds:
        required.append("browser")
    if "smoke" in kinds:
        required.append("runtime-smoke")
    output = {
        **plan,
        "sourceSha": args.source_sha.lower(),
        "components": components,
        "publishComponents": publish_components,
        "count": len(components),
        "shouldPublish": bool(publish_components),
        "repair": bool(args.repair_tag),
        "rehearsal": bool(args.rehearsal),
        "hasExtension": "extension" in kinds,
        "hasUI": "ui" in kinds,
        "hasChart": "chart" in kinds,
        "hasPackages": "package" in kinds,
        "hasTemplates": "template" in kinds,
        "hasSmoke": "smoke" in kinds,
        "hasObservability": has_observability,
        "requiredLanes": required,
    }
    print(json.dumps(output, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
