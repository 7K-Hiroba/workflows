# Runtime smoke fixture

One Argo WorkflowTemplate checks the already deployed synthetic service's health and read-only ping endpoint. CI creates a temporary kind cluster, deploys the chart, installs pinned Argo Workflows, runs the suite, collects diagnostics, and deletes the cluster.

The stage/prod declarations are read-only metadata only. This repository never executes them; real-environment policy, rendering, and status reporting belong to the dedicated environment-verification task and its external renderer gate.
