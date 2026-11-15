# Runtime smoke

`tests/smoke/suite.yaml` binds one target identity/version, compatibility range, parameter contract, dependencies, timeout, ci/stage/prod profile declarations, side effects, cleanup, and RBAC requirements. WorkflowTemplate and fixture images are full sha256-pinned. Suite-created Roles/Bindings/ClusterRoles/ClusterRoleBindings, privileged containers, and real endpoint fields are forbidden.

## Target adapters

Every new suite declares `target.adapter` and explicit readiness resources:

- `helm`: `target.component` and `.hiroba.yaml smoke.targetComponent` identify a real chart. Local CI reuses the chart's generic `ci/test.yaml` image build declaration when present; no extension component is assumed. OCI mode verifies and deploys the exact chart and suite digests.
- `manifests`: `adapter.path` is a confined directory of local manifests. Artifact-bound suites also identify a package component and confined `adapter.artifactPath`; OCI mode verifies/pulls the exact package and suite digests before applying it.

An omitted adapter and `executableProfiles` retain the legacy helm behavior so v1.0.0 consumers remain valid.

## Fixture-only suites

A chartless synthetic suite uses `fixtureOnly: true`, no `target.component`, a collision-free `<app>-smoke` target ID, independent `tests/smoke` release metadata, and exactly `executableProfiles: [ci]`. Its manifests must deploy and assert a meaningful workload, not skip the journey.

Schema, repository validation, the runtime driver, release planning, and signed evidence verification enforce these restrictions. Evidence includes `evidenceScope: fixture` and `appEvidenceEligible: false`. Fixture-only evidence cannot satisfy reviewed/official application runtime evidence and cannot be used for real stage/prod application verification. Maintainers must replace it with an artifact-bound target for those purposes.

## Execution contexts

PR CI uses local packaging, pinned kind and Argo Workflows, `argo lint`, the selected entrypoint, wait/assertions, diagnostics, and guaranteed cluster deletion. Stable OCI mode requires exact app and suite digests and verifies signature/SLSA/test evidence before use. The driver rejects a profile excluded by `executableProfiles` before applying application fixtures.

Only `profile=ci` executes in this repository. Stage/prod declarations are validated but never run here. Real rendering, policy, triggers, promotion, and outbound agent status belong to the environment-verification task and its multi-repo gate. Failure never triggers automatic rollback.
