# Contributing

Use Conventional Commits and open a draft PR. Add failing tests before implementation, include expected-negative security cases, and record exact commands/run URLs. Workflow/release/schema/runtime-smoke changes require workflows-maintainers and platform-security review. Do not commit credentials, customer data, diagnostics with secrets, or untracked generated output. External contributions follow the org CLA process when enabled.

Run the real non-publishing release-please 17.6.0 contract suite with the exact locked dependency graph and install scripts disabled:

```sh
npm ci --prefix tests/release-please-contract --ignore-scripts --no-audit --no-fund
make test-release-please
```

The harness uses local files and injected read-only APIs; it must never receive release credentials or create remote branches, PRs, tags, Releases, artifacts, channels, or deployments.
