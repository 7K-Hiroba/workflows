# Hiroba workflows

Immutable reusable CI/CD, trusted OCI publishing, observability, plugin compatibility, and Argo runtime-smoke workflows for 7K-Hiroba community applications.

## Consumer rule

External consumers call workflows only by a full 40-character commit SHA with a human-readable version comment. `@v1`, `@main`, short SHAs, and release branches are forbidden. The `v1` tag is documentation-only.

```yaml
jobs:
  validate:
    uses: 7K-Hiroba/workflows/.github/workflows/validate-packages.yml@<full-40-character-commit-sha> # v1.0.0
    with: {root: .}
```

The CLI scaffold renderer resolves the approved tagged commit; users never select a mutable alias. Every third-party action is also full-SHA pinned and covered by Renovate review.

## Lanes

- Typed package validation and kind/kro, CEL admission, and platform-app tests.
- Public-SDK Go and UI extension CI; UI remotes are complete OCI directory artifacts, never GitHub Release assets.
- Independent chart-testing lint/kind install and OCI Helm publication with an admin-gated repair path.
- Canonical observability generation, fail-on-diff, gcx dashboard lint, Alloy fmt/validate, and reviewed fixture-derived promtool tests.
- Stable/previous backend compat and real stable-host browser slot tests; nightly immutable-resolved edge runs.
- One signed target-scoped Argo suite for ephemeral CI and later policy-gated environment verification. Only kind-based `ci` executes here.
- Digest-based cosign signatures, registry SLSA v1 provenance, release-linked signed test evidence, signed indexes, and protected finalization.

See `docs/architecture.md`, `docs/consumer-guide.md`, and `docs/trusted-publishing.md`. The `scaffold/` tree is CI-only and is never a trusted source or production application.

## Release status

No tag or GitHub Release is created by repository setup. `v1.0.0` requires review, QA, complete CI evidence, and explicit admin approval. GHCR rehearsal is a separate approval gate.
