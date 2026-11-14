# Runtime smoke

`tests/smoke/suite.yaml` binds one target component/version, compatibility range, parameter contract, dependencies, timeout, ci/stage/prod profiles, side effects, cleanup, and RBAC requirements. WorkflowTemplate images are full sha256-pinned. Suite-created Roles/Bindings/ClusterRoles/ClusterRoleBindings and privileged containers are forbidden.

PR CI uses local packaging, pinned kind and Argo Workflows, `argo lint`, the selected entrypoint, wait/assertions, diagnostics, and guaranteed cluster deletion. Stable OCI mode requires exact app and suite digests and verifies signature/SLSA/test evidence before use.

Only `profile=ci` executes in this repository. Stage/prod declarations are validated but never run here. Real rendering, policy, triggers, promotion, and outbound agent status belong to the environment-verification task and its multi-repo gate. Failure never triggers automatic rollback.
