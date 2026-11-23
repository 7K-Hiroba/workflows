# CI-only stack lifecycle

This representative stack uses one fresh kind cluster and the central KRO setup profile. Install deploys a CI-only prerelease chart package and the canonical observability pack. Upgrade packages the current chart, converges the same Helm release and KRO resources, and preserves the generated dashboard ConfigMap UID. Distinct package SHA-256 identities are recorded in the phase evidence.

This proves install/upgrade wiring only. It is not functional upstream E2E, deployed readiness, or a trusted application release. The scaffold remains CI-only.
