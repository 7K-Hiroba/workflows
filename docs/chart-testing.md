# Chart install and upgrade testing

Hiroba chart CI always runs locked dependency preparation, chart-testing lint, and the declared install checks. A chart may additionally opt into a same-release previous-package install and distinct-current-package upgrade. This is a targeted wiring/compatibility gate, not upstream functional E2E and not deployed readiness verification.

## Backward-compatible declaration

`charts/<name>/ci/test.yaml` remains `inari.chart-test.v1`. With no `upgrade` property, behavior is unchanged: chart-testing installs and uninstalls the current chart in a fresh kind cluster. `ct install` alone does not prove an upgrade.

```yaml
schema: inari.chart-test.v1
install:
  timeout: 5m
  values:
    - charts/example/ci/kind-values.yaml
upgrade:
  previousPackage: tests/chart-lifecycle/example/previous.tgz
  currentPackage: tests/chart-lifecycle/example/current.tgz
  timeout: 5m
  assertions: tests/chart-lifecycle/example/assert.sh
```

The strict object permits no other fields. Packages and the executable assertion script must be consumer-root-relative, confined files outside the packaged chart directory. URLs, OCI references, parent traversal, escaping symlinks, missing files, and in-chart archives fail validation. Existing `install.values` apply to both phases.

Both archives must have the current chart's name, different versions and SHA-256 package digests, and the current version must equal the reviewed `Chart.yaml`. The current archive must also byte-match the deterministic package of prepared current source. Package hashes are checked again after execution. No mutable chart ref, Git dependency, third-party archive, or install hook is accepted.

A stack-covered chart cannot declare this separate lane: the runner fails rather than silently skipping it. Non-stack charts do not need and must not acquire `stackTest` to use this feature. Runtime smoke remains independent.

## Reproducible packages and provenance

Package only reviewed local chart source with the checksum-verified Helm version in `pins/stack-testing.json`. Helm writes package-time tar metadata, so source mtime normalization alone is insufficient. After `helm package`, canonicalize the archive with the shared helper:

```sh
PYTHONPATH=<workflow-root>/scripts python3 -m lib.chart_lifecycle canonicalize-package \
  --input <raw-helm-package.tgz> --output <deterministic-package.tgz>
```

Canonicalization sorts members, normalizes tar ownership/mtime/PAX metadata, and sets the gzip timestamp to zero without changing chart content. Keep previous source available for review and never download a prebuilt previous/current fixture. Two independent generations must produce identical bytes.

The non-plugin fixture contains reviewed previous source, current source identity, an executable generator, and `provenance.json`. Regenerate it from the workflows root with the pinned tools installed:

```sh
PYTHON=.venv/bin/python HELM=<checksum-verified-pinned-helm> \
  tests/fixtures/non-plugin-runtime/tests/chart-lifecycle/hiroba-nonplugin-smoke/generate.sh
```

The manifest records the pinned Helm/archive identity, deterministic algorithm, source paths, versions, filenames, and exact SHA-256 digests. The lane's `sourceSha` binds those files to the actual reviewed checkout or PR merge tree; provenance never substitutes a generated identity for source or PR-head identity.

## Ordered shared lifecycle

For an opted chart, the shared runner performs, in order:

1. Validate declaration and exact package bytes before creating infrastructure.
2. Create one unique kind cluster with the central node-image pin.
3. Build/load the optional declared image and apply declared dependency manifests.
4. Verify no matching Helm release exists; `helm install` the previous package with bounded `--wait`/`--wait-for-jobs` convergence.
5. Verify deployed Helm revision 1, previous chart version, stable release name/namespace, then run targeted install assertions.
6. Run plain `helm upgrade` to the current package in the same release and `default` namespace. There is no `--install`, `--atomic`, uninstall, or automatic rollback.
7. Verify deployed revision 2, current chart version and convergence, run targeted upgrade assertions, and verify release/resource stability again.
8. Reject changed package bytes, emit ordered evidence, and delete the cluster.

Install failure prevents upgrade and records it as `not-run`. Upgrade, convergence, or assertion failure collects Helm/Kubernetes/kind diagnostics before deletion. Every post-create exit attempts one deletion; deletion failure fails the run and records `cleanedUp: false`. Assertion scripts must not create clusters or write authoritative evidence.

## Assertion environment

The required phase-aware script runs after both Helm phases and must perform targeted Kubernetes checks such as `kubectl wait/get`. It receives:

| Variable | Meaning |
| --- | --- |
| `HIROBA_CHART_PHASE` | `install` or `upgrade` |
| `HIROBA_CHART_ROOT`, `HIROBA_CHART_PATH`, `HIROBA_CHART_WORK` | Consumer root, chart path, and temporary phase state |
| `HIROBA_CHART_PACKAGE`, `HIROBA_CHART_VERSION`, `HIROBA_CHART_DIGEST` | Exact package path, version, and `sha256:` identity |
| `HIROBA_CHART_RELEASE`, `HIROBA_CHART_NAMESPACE`, `HIROBA_CHART_CLUSTER` | Stable release, namespace, and unique cluster identity |

The CI-only non-plugin assertions check previous/current ConfigMap content, current Deployment availability, package digest identity, and stable Service UID. They do not reproduce application functional E2E.

## Evidence and signed releases

Each opted chart emits `chart-lifecycle-<chart-name>` in `chart-lifecycle-evidence-<chart-name>`. It records exact package versions/digests, ordered phase status/convergence/assertions/revisions/durations, release/namespace/cluster identity, create/delete counts, cleanup, and run timing.

`sourceSha` is the actual tested checkout (the PR merge tree for PR callers); optional `prHeadSha` is read from the trusted GitHub event and remains separate. `workflowSha`, run ID, and run attempt bind the result to the resolved workflows implementation and producer run.

Passing evidence requires exactly one fresh cleaned cluster, install then upgrade at revisions 1 and 2, distinct versions/package digests, passing targeted assertions, and stable identities. It always declares:

```yaml
fixtureOnly: false
evidenceScope: application
appEvidenceEligible: true
functionalE2E: false
deployedReadiness: not-tested
```

Coordinated releases download the actual per-chart artifacts. Standalone chart release/repair derives the requirement from selected tagged source and downloads the same artifact. Missing, failed, reordered, incomplete, duplicate, wrong-source, wrong-producer, same-content, or tampered evidence fails predicate construction and independent verification. Existing install-only releases retain their existing `chart` lane with no new requirement.

## Verification and limits

Run `make test-chart-contract` for focused control-flow, schema, provenance, and evidence tests, then the complete local suite. Stubbed tests are not real kind evidence; inspect the hosted non-plugin run for actual lifecycle execution and cleanup. See `docs/evidence/local-kind-limitation.md`.

This lane never claims upstream functional E2E, deployed/stage/prod readiness, or production approval. Stable consumer publication and ArgoCD adoption remain separate gated tasks.

## Fixture provenance snapshot

The reviewed non-plugin fixture generated twice with byte-identical results:

- Previous `0.0.9`: `sha256:c3612f04ac1d62e1edbc4409ed61603c3b2a540e82d97fce8da7ee853d0a2afe`
- Current `0.1.0`: `sha256:e132b21d48d57234f49fff57f4807840d5b564029eaf132cb53385d882984592`

Regeneration after any reviewed source change must update both packages and provenance, repeat the byte-identity check, and use the new exact digests in PR/QA evidence.
