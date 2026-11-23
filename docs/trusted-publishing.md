# Trusted publishing

Each publish performs: immutable build/push → registry digest capture and re-resolution → cosign keyless signature → release-linked test predicate → registry SLSA v1 provenance → independent verification → receipt-backed artifact metadata → channel/index/finalization.

- OIDC issuer: `https://token.actions.githubusercontent.com`.
- Expected producer: `7K-Hiroba/workflows` plus the exact release workflow path and resolved workflow SHA. A repository-only regex is insufficient.
- SLSA predicate: `https://slsa.dev/provenance/v1`, attached as a registry referrer.
- Test predicate: `https://inari.dev/attestations/test-evidence/v1`.
- Test predicates bind source repository/SHA, release tag or release-set/CI identity, artifact repository/digest/media type, producer workflow/SHA/run/attempt, required lanes, evidence digest, and completion time.
- Reviewed compat evidence must be passing, source-bound, and at most seven days old. Failed, skipped, missing, stale, or unrelated evidence fails publication.
- Classified stacks additionally require source-bound stack-lifecycle evidence with one fresh cluster, ordered install+upgrade at distinct exact content identities, and cleanup. The release graph consumes the actual stack artifact; fixture-only stack evidence cannot authorize reviewed/official application runtime readiness.

Verification uses cosign, `gh attestation verify`, and `verify-test-evidence.py`. Sibling admission work must consume the same OCI referrer and predicate contract. Any producer/admission mismatch stops finalization; never substitute unsigned files or weaken identity checks.

No GHCR operation is performed during repository setup. The protected publish rehearsal and stable release require separate approvals.

## Full-matrix rehearsal

Run exactly one fixture release graph per `workflow_dispatch`; artifact uploads and `artifact-*`/`channel-reconciliation` downloads are scoped to that run. Select the fixture through the validated `fixture` choice. Coordinate all five fixtures at the same reviewed merged main SHA, waiting for each result before proceeding:

```sh
SHA=<reviewed-merged-main-sha>
for FIXTURE in scaffold chartless-observability nonplugin-helm chartless-manifests artifact-manifests; do
  gh workflow run publish-rehearsal.yml --repo 7K-Hiroba/workflows --ref main \
    -f source_sha="$SHA" -f mode=full -f fixture="$FIXTURE"
done
```

This list only prepares the required dispatches; it does not authorize them. Do not fan out release graphs inside one run or share evidence/channel artifacts across fixture roots.
