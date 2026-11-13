# Observability

Canonical assets live in `observability/`. Dashboard UIDs are `<app>-<slug>` and use templated `${DS_*}` datasource variables. Rules declare local/central evaluation and promtool tests. Scrape topology stays in charts/RGDs, not canonical observability assets.

`render-observability.py` generates chart ConfigMaps/PrometheusRules, chart capability metadata, and the KRO observability-pack. PR validation uses `--check` and fails without writing on drift. Release rebuilds and verifies packaged output.

Offline CI uses checksum-pinned `gcx dev lint run`, Alloy `fmt --test`, and Alloy `validate` with the same generally-available/community-component flags intended at runtime. It validates reviewed, versioned post-Alloy fixtures and derives central promtool inputs from those fixtures. `gcx resources validate` is forbidden offline because it requires a Grafana server.

Accepted limitation: offline CI does not prove live provisioning, plugin/datasource resolution, or post-pipeline series semantics. Deployment-time target-side readiness must prove those separately after the renderer gate. No Grafana/Alloy container, daemon, Compose stack, or live telemetry pipeline is run in CI.
