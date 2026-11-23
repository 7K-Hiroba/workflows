"""Standard-library exact-content cache keys shared by bootstrap and planners."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def cache_key(pins: dict[str, Any], tools: list[str], profiles: list[str]) -> str:
    selected_tools = set(tools)
    for profile in profiles:
        selected_tools.update(pins["profiles"].get(profile, []))
    unknown = sorted(selected_tools - set(pins["tools"]))
    if unknown:
        raise ValueError(f"unknown CI tools: {', '.join(unknown)}")
    selected = {
        "kind": pins["kind"],
        "kro": pins["kro"],
        "profiles": {profile: pins["profiles"].get(profile) for profile in sorted(profiles)},
        "tools": {name: pins["tools"][name] for name in sorted(selected_tools)},
    }
    encoded = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
