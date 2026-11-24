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

Backend images build reproducibly: every build pins `SOURCE_DATE_EPOCH` to the exact source commit timestamp (overridable only explicitly) and exports with rewritten layer timestamps, so identical source bytes yield an identical digest and a rerun of the same source satisfies the immutable-digest check instead of colliding with it. Changed source always yields a different digest and still fails closed.

Signed Git Release identities default to the legacy component name (`NAME-vVERSION`, `extension-vVERSION`, or `ui-vVERSION`). New repositories may declare `releaseComponents` to use identities such as `package-NAME-vVERSION`, `template-NAME-vVERSION`, `chart-NAME-vVERSION`, and `smoke-NAME-vVERSION`. Release-please, OCI descriptors, signed evidence, repair, finalization, and runtime verification all enforce the same identity. Standalone fixture-only smoke finalizes its own Release; artifact-bound smoke shares only its target's Release.

Release indexes contain exact `repository@sha256:digest`, media type, source SHA, signature/SLSA verification, and test evidence for every entry. Source `catalog.yaml`/`templates.yaml` remain generated projections and are not rewritten after tagging.

Artifact-bound smoke follows its target's tag. Standalone fixture-only smoke uses a collision-free `<app>-smoke` target and its own version. Its signed evidence carries `evidenceScope: fixture`, `appEvidenceEligible: false`, and `executableProfiles: [ci]`; it cannot satisfy reviewed/official application evidence or real stage/prod verification.
