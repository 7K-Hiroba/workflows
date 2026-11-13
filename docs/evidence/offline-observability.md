# Offline observability direction and limitation

The coordinator superseded live container verification on 2026-11-13. The task now uses only version-pinned `gcx dev lint run`, Alloy `fmt --test`, Alloy `validate` with runtime-matching flags, JSON/schema/UID/datasource-variable checks, reviewed/versioned post-Alloy fixtures, and promtool tests.

No Grafana or Alloy container, daemon, Compose stack, or real telemetry-pipeline integration is used. `gcx resources validate` is excluded because it requires a Grafana server.

Accepted limitation: offline CI does not prove live provisioning, plugin/datasource resolution, or post-pipeline series semantics. Deployment-time target-side readiness remains separate and gated. The earlier local Docker mount reproduction and cleanup history are superseded; no container work continues.
