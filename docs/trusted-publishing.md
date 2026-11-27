# Trusted publishing

Each publish performs: immutable build/push → registry digest capture and re-resolution → cosign keyless signature → release-linked test predicate → registry SLSA v1 provenance → independent verification → receipt-backed artifact metadata → channel/index/finalization.

- OIDC issuer: `https://token.actions.githubusercontent.com`.
- Expected producer: `7K-Hiroba/workflows` plus the exact release workflow path and resolved workflow SHA. A repository-only regex is insufficient.
- SLSA predicate: `https://slsa.dev/provenance/v1`, attached as a registry referrer.
- Test predicate: `https://inari.dev/attestations/test-evidence/v1`.
- Test predicates bind source repository/SHA, release tag or release-set/CI identity, artifact repository/digest/media type, producer workflow/SHA/run/attempt, required lanes, evidence digest, and completion time.
- Reviewed compat evidence must be passing, source-bound, and at most seven days old. Failed, skipped, missing, stale, or unrelated evidence fails publication.
- Classified stacks additionally require source-bound stack-lifecycle evidence with one fresh cluster, ordered install+upgrade at distinct exact content identities, and cleanup. The release graph consumes the actual stack artifact; fixture-only stack evidence cannot authorize reviewed/official application runtime readiness.
- Every chart declaring `upgrade` adds its derived per-chart lifecycle lane. Coordinated, standalone, and repair publishers consume the actual artifact and verify one fresh cleaned cluster, ordered previous install/current upgrade at revisions 1/2, distinct versions+SHA-256 package digests, stable release/namespace, targeted assertions, exact source/workflow/run identity, `functionalE2E: false`, and `deployedReadiness: not-tested`. Missing or tampered evidence fails closed; install-only chart requirements are unchanged.

Verification uses cosign, `gh attestation verify`, and `verify-test-evidence.py`. Sibling admission work must consume the same OCI referrer and predicate contract. Any producer/admission mismatch stops finalization; never substitute unsigned files or weaken identity checks.

No GHCR operation is performed during repository setup. The protected publish rehearsal and stable release require separate approvals.

## Full-matrix rehearsal

Run exactly one release graph per `workflow_dispatch`; artifact uploads and `artifact-*`/`channel-reconciliation` downloads are scoped to that run. Select the fixture through the validated `fixture` choice. Qualification requires **five full fixture graphs plus one standalone chart graph**, all sequential at the same reviewed merged main SHA. Wait for terminal success and inspect its exact source, signatures, provenance, signed test evidence, indexes/channels, and cleanup before preparing the next dispatch:

```sh
SHA=<reviewed-merged-main-sha>
gh workflow run publish-rehearsal.yml --repo 7K-Hiroba/workflows --ref main -f source_sha="$SHA" -f mode=full -f fixture=scaffold
gh workflow run publish-rehearsal.yml --repo 7K-Hiroba/workflows --ref main -f source_sha="$SHA" -f mode=full -f fixture=chartless-observability
gh workflow run publish-rehearsal.yml --repo 7K-Hiroba/workflows --ref main -f source_sha="$SHA" -f mode=full -f fixture=nonplugin-helm
gh workflow run publish-rehearsal.yml --repo 7K-Hiroba/workflows --ref main -f source_sha="$SHA" -f mode=full -f fixture=chartless-manifests
gh workflow run publish-rehearsal.yml --repo 7K-Hiroba/workflows --ref main -f source_sha="$SHA" -f mode=full -f fixture=artifact-manifests
gh workflow run publish-rehearsal.yml --repo 7K-Hiroba/workflows --ref main -f source_sha="$SHA" -f mode=repair-chart -f fixture=scaffold -f chart=workflows-scaffold -f version=0.1.0
```

This list only prepares the required dispatches in order; it does not authorize them or permit running them without waiting. Do not fan out release graphs inside one run or share evidence/channel artifacts across fixture roots. A later protected library signing dispatch separately requires the release-please-selected version, `expected_source_sha` equal to that same final R, and `update_major=false`; the workflow verifies run SHA, checkout HEAD, and remote main before signing and again immediately before tag creation.
