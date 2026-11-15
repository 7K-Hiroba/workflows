# Artifact-bound runtime smoke

This suite applies `packages/runtime-fixture/manifests.yaml`, waits for its Deployment, and asserts the package Service response through Argo Workflows. The `manifests` adapter binds `target.component` and `artifactPath`; fixture-only mode is disabled.

Only local CI executes here. Stable OCI verification requires exact package and suite digests.
