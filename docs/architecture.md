# Architecture

Reusable workflows check out caller source into `consumer/` and the workflow repository into `.hiroba/workflows/` using `job.workflow_repository` and `job.workflow_sha`. Scripts execute only from that resolved commit. Nested calls use `$/.github/workflows/...`, which GitHub resolves at the caller workflow's commit. This is GitHub.com-specific; GHES is unsupported and must fail rather than fall back to a branch.

`.hiroba.yaml` is declarative. Component discovery, release-please metadata, source indexes, release evidence, and publication descriptors share `scripts/lib/metadata.py`. Tests run with contents-read only. Publish jobs alone receive packages/id-token/attestations permissions.

A release plans untagged finalization components separately from the full publish/evidence set. Existing artifacts are pulled/reused without overwrite. All current publishable artifacts are verified so index entries never depend on missing evidence. Channels move only after verification. Protected tags/Releases are last.

Stable, edge, repair, and rehearsal are distinct. Rehearsal uses `ghcr.io/7k-hiroba/workflows/ci/`, CI/source-SHA tags, no stable channels, and no git tags/Releases. Real stage/prod verification is outside this repository.
