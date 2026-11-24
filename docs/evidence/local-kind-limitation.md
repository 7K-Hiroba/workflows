# Local kind verification limitation

Two local `hiroba-chart-ci` attempts were deleted before readiness. The first used a read-only `/etc/kandev/kubeconfig.lock`; the second used an explicit writable temporary kubeconfig but still failed to find the expected kind readiness/cgroup log line. No external cluster or service was touched.

I stopped after the environment-specific attempts. Chart-testing lint and Chart.yaml schema validation pass locally. GitHub-hosted kind has already created clusters in the PR, and the required chart/package/runtime checks must pass there before completion. This is not a skipped or mocked lane.

The same limitation applies to the classified stack lifecycle: use the hosted stack-lifecycle run and never change host sysctls or attach a shared cluster. Stubbed unit tests prove runner control flow only and are not hosted install/upgrade evidence.

The opt-in chart lifecycle follows the same rule: fake Helm/kind tests and local package preflight verify control flow, provenance, and exact bytes only. The hosted non-plugin chart run must demonstrate the real previous install, same-release current upgrade, targeted assertions, ordered evidence, and cleanup before release qualification.
