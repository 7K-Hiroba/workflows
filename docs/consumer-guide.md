# Consumer guide

## v2.0.0 breaking migration

Workflows v2.0.0 requires every adopting consumer to migrate to `inari.hiroba.app.v2` and explicitly declare `archetype: stack|non-stack`. A stack must also declare complete install plus same-cluster upgrade lifecycle coverage and pass its immutable lifecycle caller; a non-stack must not acquire that lane. Consumers that are not ready to make those changes must retain their immutable v1.1.0 workflow pin (`b26b53f5ba58a27d1973fec6dfa6469d0b93ba62`) until migration is complete. Do not treat v2.0.0 as a SHA-only or version-comment-only update.

1. Generate the app through the CLI scaffold after the workflow release is approved.
2. Migrate to app config v2 with explicit `archetype: stack|non-stack`. Every stack declares complete `tests/stack` install+upgrade coverage and its immutable caller; non-stack sources never emit them. Follow `docs/stack-testing.md`. Keep `.hiroba.yaml`, extension/package/template manifests, values schemas, canonical observability, generated outputs, and optional `tests/smoke/` synchronized. Chartless observability omits `observability.chart`; runtime smoke declares an explicit `helm` or `manifests` adapter and its allowed `executableProfiles`.
3. Use thin callers from `scaffold/.github/workflows/*.template`. The renderer replaces `__WORKFLOWS_V1_SHA__` with the full approved commit SHA and preserves the version comment. Placeholders, `@v1`, `@main`, and short SHAs fail policy.
4. Use only explicit App credentials for release-please/finalization; never `secrets: inherit`. PR lanes require contents-read only.

Declare `releaseComponents` only for package, template, chart, or standalone-smoke components that need a non-legacy signed Release identity, and remove stale entries when components are removed. Backend/UI identities remain fixed as `extension-vVERSION` and `ui-vVERSION`. Artifact-bound smoke must not have its own entry because it inherits the target. Backend-only repositories require backend compatibility evidence; UI-only repositories require browser evidence; repositories with both retain the combined lanes. The compatibility matrix is valid for any of these selections. Chart repair discovers the configured `releaseComponents` identity, uses legacy `NAME-vVERSION` when no mapping exists, and requires that exact annotated tag.
5. Require the stable `library CI / result` and `scaffold CI / result` checks after verifying the exact names on a completed PR run. Keep matrix summary names stable.
6. Let Renovate propose workflow/action/chart/SDK updates; trusted workflow updates are manually reviewed.

The scaffold is a contract fixture, not a trusted app. Do not register its CI artifacts as a source. Real deployment and environment verification are separate tasks.
