# Admin setup and effective-setting verification

The existing `7K-Hiroba` org is used; no second org is created. Only `7K-Hiroba/workflows` is in scope. Repository creation and CI admin setup require approval; GHCR, tags/Releases, Pages, stage/prod, and external merges remain separate gates.

Required controls:

- Teams: `workflows-maintainers` and `platform-security`, with repository-scoped maintain/write access and CODEOWNERS.
- Active main ruleset: PR, one approval, CODEOWNERS, stale-review dismissal, last-push approval, resolved threads, no deletion/force-push. Add verified required check contexts after the first CI run.
- Active `v*` tag ruleset: restricted creation/update/deletion/non-fast-forward; only approved release identity/admins bypass. GitHub tag UI alone does not verify gitsign.
- `ci-publish` and `release` environments: platform-security reviewer, main-only custom branch policy, prevent self-review, no admin bypass.
- Actions: selected publishers, mandatory full-SHA actions, read-only default workflow token, no workflow PR approval, approval for all external contributors, 30-day evidence retention.
- A dedicated release App with only contents/pull-requests write on this repo. Existing broad or unrelated Apps are not substitutes. Store its private key only as `HIROBA_RELEASE_PRIVATE_KEY` and its ID as `HIROBA_RELEASE_APP_ID`.

Verification commands:

```sh
gh api repos/7K-Hiroba/workflows
gh api repos/7K-Hiroba/workflows/rulesets?includes_parents=true
gh api repos/7K-Hiroba/workflows/rules/branches/main
gh api repos/7K-Hiroba/workflows/actions/permissions
gh api repos/7K-Hiroba/workflows/actions/permissions/selected-actions
gh api repos/7K-Hiroba/workflows/actions/permissions/workflow
gh api repos/7K-Hiroba/workflows/actions/permissions/fork-pr-contributor-approval
gh api repos/7K-Hiroba/workflows/environments
```

Record actual output in `docs/evidence/admin-bootstrap.md`. HTTP 403/404 is unresolved, not success. No Pages setting is needed by this task.
