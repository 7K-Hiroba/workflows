# Admin setup and effective-setting verification

The existing `7K-Hiroba` org is used; no second org is created. Only `7K-Hiroba/workflows` is in scope. Repository creation and CI admin setup require approval; GHCR, tags/Releases, Pages, stage/prod, and external merges remain separate gates.

Required controls:

- Teams: `workflows-maintainers` and `platform-security`, with repository-scoped maintain/write access and CODEOWNERS.
- Active main ruleset: PR, one approval, CODEOWNERS, stale-review dismissal, last-push approval, resolved threads, no deletion/force-push. Add verified required check contexts after the first CI run.
- Active `v*` tag ruleset: restricted creation/update/deletion/non-fast-forward; only approved release identity/admins bypass. GitHub tag UI alone does not verify gitsign.
- `ci-publish` and `release` environments: platform-security reviewer, main-only custom branch policy, prevent self-review, no admin bypass.
- Actions: selected publishers, mandatory full-SHA actions, read-only default workflow token, no workflow PR approval, approval for all external contributors, 30-day evidence retention.
- A dedicated release App with only contents/pull-requests write on this repo. Existing broad or unrelated Apps are not substitutes. Store its private key only as `HIROBA_RELEASE_PRIVATE_KEY` and its ID as `HIROBA_RELEASE_APP_ID`.

## Deferred release App registration and handoff

App registration and all App-dependent execution are deferred. Do not run `library release PR`, release finalization, tags, Releases, or publication until the App is installed, its bypass actor is recorded, and the relevant release gate is separately approved.

An organization owner must use GitHub's interactive organization manifest flow at `https://github.com/organizations/7K-Hiroba/settings/apps/new` with this exact JSON manifest (posted as the `manifest` field with a fresh random `state`):

```json
{
  "name": "7K-Hiroba workflows release",
  "url": "https://github.com/7K-Hiroba/workflows",
  "description": "Release PR and protected release automation for 7K-Hiroba/workflows only.",
  "public": false,
  "default_permissions": {
    "contents": "write",
    "pull_requests": "write"
  },
  "default_events": []
}
```

Handoff requirements:

1. The owner verifies that the registration is owned by `7K-Hiroba`, is private, subscribes to no events, and grants only the two permissions above. Complete GitHub's manifest conversion in the owner's secured session within one hour. Never send the temporary code, PEM, webhook secret, or client secret to an agent or commit them.
2. Install the App with **Only select repositories** → `7K-Hiroba/workflows`; never use **All repositories**. Reject the handoff if GitHub displays any additional permission.
3. In this repository's GitHub settings, store the PEM only as repository secret `HIROBA_RELEASE_PRIVATE_KEY` and the public App ID as repository variable `HIROBA_RELEASE_APP_ID`. Do not place credentials in CI logs, artifacts, this repository, or another repository.
4. Record the non-secret App ID, installation ID, effective permissions, installation repository selection, and verified ruleset bypass actor in `docs/evidence/admin-bootstrap.md`. Confirm the installation with the verification command below.
5. Keep the App and release gate pending until the owner explicitly authorizes App-dependent execution. The protected `release` environment approval remains an additional gate, not a substitute for registration or authorization.

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
gh api repos/7K-Hiroba/workflows/installation
```

Record actual output in `docs/evidence/admin-bootstrap.md`. HTTP 403/404 is unresolved, not success. No Pages setting is needed by this task.
