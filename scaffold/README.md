# Hiroba workflow scaffold

This CI-only representative app exercises the workflow v1 contract: public Go/UI SDK extension, first-party OCI chart, three package types, an OCI scaffold template, canonical observability, and one signed Argo smoke suite.

It is never registered as a trusted catalog source and never targets stage/prod. Workflow caller templates contain `__WORKFLOWS_V1_SHA__`; the CLI or renderer must replace it with the full commit SHA of the approved workflow release. Never substitute `@v1`, `@main`, or another mutable ref.

The UI uses the stable `@7k-inari/ui-plugin-sdk@0.1.8` registry release and `ApiClient.invokeExtension` remains the supported invocation flow. Production build uses the canonical `inari-ui-ext build`; no clone/postinstall/custom-webpack workaround is allowed.
