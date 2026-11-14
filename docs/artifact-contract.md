# OCI artifact contract

| Artifact | Repository | Type/layout |
| --- | --- | --- |
| Package | `ghcr.io/7k-hiroba/<app>/catalog/<pkg>` | `application/vnd.inari.catalog.package.v1+yaml`, root-relative ORAS directory |
| Catalog index | `ghcr.io/7k-hiroba/<app>/catalog/index` | `application/vnd.inari.catalog.index.v1+yaml`, raw `catalog.yaml:text/yaml` layer |
| Template | `ghcr.io/7k-hiroba/<app>/templates/<tpl>` | `application/vnd.inari.template.v1`, template/schema/uiSchema/skeleton directory |
| Template index | `ghcr.io/7k-hiroba/<app>/templates/index` | `application/vnd.inari.template.index.v1+yaml`, raw `templates.yaml:text/yaml` |
| Backend | `ghcr.io/7k-hiroba/<app>/extension` | OCI container manifest |
| UI remote | `ghcr.io/7k-hiroba/<app>/extension-ui` | `application/vnd.inari.extension.ui.v1`, flat titled `remoteEntry.js` plus all chunks/assets |
| Chart | `ghcr.io/7k-hiroba/<app>/charts/<chart>` | OCI Helm chart; no classic index |
| Smoke | `ghcr.io/7k-hiroba/<app>/smoke/<target>` | `application/vnd.inari.smoke.suite.v1+yaml`, `tests/smoke` directory |

Deployable artifacts have no `latest`. Packages/templates may move `stable`/`incubating` only after verification. Indexes use immutable source-SHA plus `latest` after all entries verify; edge uses `edge`. Rehearsal uses CI-only source-SHA/prerelease tags and no stable channel.

Release indexes contain exact `repository@sha256:digest`, media type, source SHA, signature/SLSA verification, and test evidence for every entry. Source `catalog.yaml`/`templates.yaml` remain generated projections and are not rewritten after tagging.
