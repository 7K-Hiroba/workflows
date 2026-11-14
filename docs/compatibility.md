# Plugin compatibility

PR/release lanes execute public pluginsdk testkit Info/Capabilities/Invoke/Health against the pinned stable and previous-stable contract matrix. UI remotes build with the supported public SDK flow and mount in a real stable UI host. Every declared slot requires a passing Playwright spec named `slot <kind>:<name>`.

Nightly resolves inari-server/inari-ui edge to full commits, records them in `compat-report.json`, reruns backend/browser suites, and opens or updates one early-warning issue on failure. Reviewed evidence freshness is seven days.

The scaffold uses the stable `@7k-inari/ui-plugin-sdk@0.1.8` registry release and the existing `ApiClient.invokeExtension`. It never recreates those APIs. Production build uses canonical `inari-ui-ext build`; clone/postinstall/custom-webpack workarounds remain prohibited.

Core registration, contract metadata, degraded state, and UI preflight belong to the dedicated core-contract task.
