# Observability

Canonical assets live in `observability/`. Dashboard UIDs are `<app>-<slug>` and use templated `${DS_*}` datasource variables. Rules declare local/central evaluation and promtool tests. Scrape topology stays in charts/RGDs, not canonical observability assets.

`render-observability.py` always generates the KRO observability-pack and full `observability.yaml` in every package that declares observability. When `observability.chart` is set, it also generates that chart's ConfigMaps/PrometheusRules and `inari/observability.yaml` capability metadata. Omitting `chart` produces no chart files or directories; the pack and signed package metadata remain available for the approved central/local companion path. A configured chart must contain `Chart.yaml`.

The pack declares `metadata.annotations[inari.dev/observability-render-contract]=inari.observability-pack/v2`. Dashboards require `render=all|dashboards`; each rule group requires its evaluation's render selection AND `rulesCentral`/`rulesLocal`. Each rule file also generates a same-gated `<app>-<evaluation>-rules` ConfigMap containing the exact canonical YAML, allowing Mimir's existing filesystem `ruler.rule_path` to load it through a reviewed volume mount; no API writer is introduced. Component templates may add a confined `observability.manifest` declaration and the exact manifest bytes. GitOps-repo templates and nonexistent/traversing manifests are rejected.

PR validation uses `--check` and fails without writing or creating directories on drift. Removing `observability.chart` makes validation reject stale generated chart outputs; regeneration removes only the three known generated files and preserves unrelated chart content. Release rebuilds and verifies packaged output. Existing chart-backed output is unchanged.

Offline CI uses checksum-pinned `gcx dev lint run`, Alloy `fmt --test`, and Alloy `validate` with the same generally-available/community-component flags intended at runtime. It validates reviewed, versioned post-Alloy fixtures and derives central promtool inputs from those fixtures. `gcx resources validate` is forbidden offline because it requires a Grafana server.

Accepted limitation: offline CI does not prove live provisioning, plugin/datasource resolution, or post-pipeline series semantics. Deployment-time target-side readiness must prove those separately after the renderer gate. No Grafana/Alloy container, daemon, Compose stack, or live telemetry pipeline is run in CI.
