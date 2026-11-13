# Workflows agent guide

- Keep all reusable workflow/action references immutable: full 40-character commit SHA plus a version comment. Nested library calls use `$/.github/workflows/...`; scripts load from `job.workflow_repository` at `job.workflow_sha`.
- Use TDD for scripts and workflow policy. Add positive and expected-negative fixtures, run the complete unit suite, and commit each focused behavior.
- CI test jobs never receive package/OIDC/attestation write permissions. No `pull_request_target`, secrets inheritance, mutable tool downloads, or caller-authored test predicates.
- Publish by OCI digest; sign, attach SLSA and signed test evidence, verify, then move channels/indexes/tags. Never use deployable `latest`, classic Helm indexes, UI Release assets, or inari-operator inputs.
- Real stage/prod runs, GHCR rehearsal, tags, Releases, Pages, and external merges require their explicit gates. Existing Inari repos are read-only test inputs.
- Generated observability chart/pack outputs are committed and checked with fail-on-diff. Keep the representative scaffold CI-only.
