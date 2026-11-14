# Trusted publishing

Each publish performs: immutable build/push → registry digest capture and re-resolution → cosign keyless signature → release-linked test predicate → registry SLSA v1 provenance → independent verification → receipt-backed artifact metadata → channel/index/finalization.

- OIDC issuer: `https://token.actions.githubusercontent.com`.
- Expected producer: `7K-Hiroba/workflows` plus the exact release workflow path and resolved workflow SHA. A repository-only regex is insufficient.
- SLSA predicate: `https://slsa.dev/provenance/v1`, attached as a registry referrer.
- Test predicate: `https://inari.dev/attestations/test-evidence/v1`.
- Test predicates bind source repository/SHA, release tag or release-set/CI identity, artifact repository/digest/media type, producer workflow/SHA/run/attempt, required lanes, evidence digest, and completion time.
- Reviewed compat evidence must be passing, source-bound, and at most seven days old. Failed, skipped, missing, stale, or unrelated evidence fails publication.

Verification uses cosign, `gh attestation verify`, and `verify-test-evidence.py`. Sibling admission work must consume the same OCI referrer and predicate contract. Any producer/admission mismatch stops finalization; never substitute unsigned files or weaken identity checks.

No GHCR operation is performed during repository setup. The protected publish rehearsal and stable release require separate approvals.
