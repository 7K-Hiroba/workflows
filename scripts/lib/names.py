"""Deterministic Kubernetes/Helm resource names for registry-length app IDs."""

from __future__ import annotations

import hashlib


def bounded_resource_name(name: str, max_length: int) -> str:
    """Mirror inari-cli's boundedResourceName; the shared test vector prevents drift."""
    if len(name) <= max_length:
        return name
    if max_length < 10:
        raise ValueError("bounded resource names require a positive prefix and hash")
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    prefix = name[: max_length - 9].rstrip("-")
    return f"{prefix}-{digest}"
