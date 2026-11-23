# Stack testing contract

Hiroba stack CI optimizes for maintained wiring and addon compatibility. It does not recreate upstream functional E2E suites and never claims deployed production readiness.

## Required classification

Every consumer adopting this workflow version uses `inari.hiroba.app.v2` and explicitly declares:

```yaml
archetype: stack # or non-stack
```

This classification is independent of repository type and component presence. A chart or KRO package does not implicitly make a repository a stack. Missing or unknown archetypes fail validation and direct component discovery. Old consumers retain their old immutable workflow pin until deliberately migrating to app config v2; the new validator does not silently default a missing classification to non-stack.

- `stack` requires `stackTest: {path: tests/stack}` and an immutable `test-stack.yml` caller.
- `non-stack` must not declare stackTest and receives no stack cluster or release-lane cost.
- A stack suite covers every chart and kro-rgd component, with no silent omissions. Platform-app, policy, manifests, extension, UI, observability, compatibility, and runtime-smoke components retain their existing independent lanes.
- `fixtureOnly: true` is allowed only with `covers: []`. It is CI-only, has no release component, and is not reviewed/official application runtime evidence.

The community registry intentionally remains an identity/ownership registry. It cannot validate a source SHA offline and does not carry archetype or test predicates. App config, workflow validation/discovery, release evidence, and exact-head onboarding checks are the enforceable path.

## Suite declaration

```yaml
schema: inari.stack-test.v1
setupProfiles: [kro, argocd, oci-registry]
covers:
  - charts/example
  - packages/example
install: {script: install.sh, timeout: 15m}
upgrade: {script: upgrade.sh, timeout: 15m}
diagnostics: diagnostics.sh
```

Both phase scripts must be confined executable files. The shared runner exports the consumer root, workflow root, work directory, unique cluster name, kubeconfig, and phase. Each phase writes a schema-valid result containing its version, exact `sha256:` content digest, and `converged: true`. Install and upgrade content identities must differ. Consumer phases never create another cluster or select their own infrastructure versions.

## Central setup and cache ownership

`pins/stack-testing.json` is the reviewed source for kind/node, KRO chart version+digest, ArgoCD/Argo Workflows commits and manifest checksums, disposable registry/Redis images, and CI tool archives/checksums. Profile membership determines the tools installed; consumers cannot supply alternate tool URLs or versions.

- `kro`: verify the exact KRO OCI digest and install with bounded readiness.
- `argocd`: apply the checksum-verified core manifest, create disposable server credentials, use the pinned Redis image, and wait for CRDs/controllers.
- `argo-workflows`: apply checksum-verified quick-start/executor resources and use the existing artifactless controller setup.
- `oci-registry`: run a fresh in-cluster registry and a bounded local port-forward, then export its connection identity to the lifecycle phases.

The installer caches only immutable downloaded tool/archive content under a key derived from canonical pins, selected profiles/tools, and content hashes. There are no restore-key or branch fallbacks. Every cached or downloaded archive is SHA-256 verified before extraction. Kubeconfig, etcd, kind nodes, containers, namespaces, port-forwards, and cluster state are never cached or shared. A warm tool cache still creates a fresh cluster.

## Lifecycle and diagnostics

`test-stack.yml` validates before setup, creates one unique kind cluster, installs only declared profiles, runs install and then upgrade against that same cluster, and emits evidence on both success and failure. Setup/readiness and phases are bounded. The job has a 45-minute hard limit. Failure collects consumer and generic diagnostics; every exit stops port-forwards and attempts cluster deletion.

Covered charts still run lint/schema/locked-dependency/render checks but skip duplicate kind installation. Covered KRO packages skip the separate package kind matrix. Argo runtime smoke remains a separate suite and fresh cluster; it never shares stack state.

## Evidence and timing

`stack-lifecycle-evidence` contains the actual lane result and phase results, source/workflow SHAs, run ID/attempt, covered components, pin/cache identity and hit state, fresh/create/delete/cleanup fields, per-phase and total durations, and timestamps. It explicitly records `functionalE2E: false` and `deployedReadiness: not-tested`.

For a pull-request caller that leaves `source-sha` empty, the check's `head_sha` remains associated with the reviewed PR head while Actions checks out the exact merge tree. The artifact's `sourceSha` (and a nested reusable call's `workflowSha`) records that tested merge tree, not a different or unreviewed change. Record both identities when presenting PR evidence. Release and repair callers pass their exact release/tag source explicitly, so signed evidence remains bound to the published commit.

Release planning adds `stack-lifecycle` to required signed evidence for every classified stack being published. Release and standalone chart repair consume the actual artifact; they never fabricate a passing lane. Missing, failed, wrong-SHA, incomplete, multi-cluster, reused, or same-content upgrade evidence fails closed.

For rollout, record a cold cache-miss run and a same-source warm cache-hit run with run IDs/attempts. Compare setup, install, upgrade, cleanup, and total durations against the previous consumer baseline. A cache hit is a timing measurement, never evidence of cluster reuse.

## Ownership and rollout

- workflows owns the archetype/schema, pins, setup helpers, runner, reusable workflow, and release evidence enforcement.
- Stack repositories own their archetype, component coverage, fixtures, phase assertions, and targeted kind-less behavior.
- Community onboarding requires the exact-head stack result for stack activation; where supported, require the stable result check. Missing technical branch protection uses the existing documented fallback but does not waive evidence.
- Deployed GitOps, stage/prod verification, and production readiness remain separate approval-gated layers.

Migrate a consumer by selecting its archetype, adding the complete suite and immutable caller for stack, migrating to app config v2, and rerunning all applicable hosted lanes at the exact new source SHA. Do not move tags or infer a signed release from a candidate commit.
