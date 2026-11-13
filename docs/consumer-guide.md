# Consumer guide

1. Generate the app through the CLI scaffold after the workflow release is approved.
2. Keep `.hiroba.yaml`, extension/package/template manifests, values schemas, canonical observability, generated outputs, and optional `tests/smoke/` synchronized.
3. Use thin callers from `scaffold/.github/workflows/*.template`. The renderer replaces `__WORKFLOWS_V1_SHA__` with the full approved commit SHA and preserves the version comment. Placeholders, `@v1`, `@main`, and short SHAs fail policy.
4. Use only explicit App credentials for release-please/finalization; never `secrets: inherit`. PR lanes require contents-read only.
5. Require the stable `library CI / result` and `scaffold CI / result` checks after verifying the exact names on a completed PR run. Keep matrix summary names stable.
6. Let Renovate propose workflow/action/chart/SDK updates; trusted workflow updates are manually reviewed.

The scaffold is a contract fixture, not a trusted app. Do not register its CI artifacts as a source. Real deployment and environment verification are separate tasks.
