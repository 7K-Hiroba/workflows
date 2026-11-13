# Observability

Canonical assets live in `observability/`. Dashboard UIDs are `<app>-<slug>` and use templated `${DS_*}` datasource variables. Rules declare local/central evaluation and promtool tests. Scrape topology stays in charts/RGDs, not canonical observability assets.

`render-observability.py` generates chart ConfigMaps/PrometheusRules, chart capability metadata, and the KRO observability-pack. PR validation uses `--check` and fails without writing on drift. Release rebuilds and verifies packaged output.

CI also runs representative metrics through real Alloy configuration, checks the post-Alloy label contract, derives central promtool fixtures from the observed series, and provisions ephemeral Grafana with a Prometheus datasource. Dashboard readiness requires folder/UID, datasource resolution, and successful panel queries. These are isolated containers, not central/tenant Grafana writes.
