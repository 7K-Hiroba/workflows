# Admin bootstrap evidence — 2026-11-13

## Repository and tracking

- Existing org: `7K-Hiroba` (org ID 273663275), revalidated with ACTIVE admin membership for `joaodss2` before creation.
- Created only public `https://github.com/7K-Hiroba/workflows` (repo ID 1457054098).
- Default branch: `main`.
- Initial main SHA: `94838195432c96f4839469d6a41e0facf524c2d5`.
- Kandev attachment: task repository `f8db85b9-6b8f-4286-8852-f07f06c58b97`.
- Tracked feature branch: `feature/m1w1-build-workflows-86s`.
- Initial HEAD matched initial main before implementation.

## Teams

- Existing org team `hiroba-maintainers` preserved and not modified.
- `workflows-maintainers`: team ID 20685802; repository permission `maintain`.
- `platform-security`: team ID 20685803; repository permission `push`.
- Both teams are closed and have ACTIVE maintainer membership for `joaodss2` from team creation. No duplicate/renamed/deleted teams.

## Rulesets

- ID 27229314, `Protect main trunk`: active branch ruleset on default branch; deletion and non-fast-forward rules; squash-only PR with one approval, CODEOWNERS, stale-review dismissal, last-push approval, resolved threads; no bypass actors.
- ID 27229315, `Protect version tags`: active `refs/tags/v*`; restricted creation/update/deletion/non-fast-forward; OrganizationAdmin bypass only pending the separately approved release App actor.
- Required status checks are active with strict up-to-date enforcement for `library-ci-result` and `scaffold-ci-result`. The library name was verified on green run 43521941195; the scaffold name is defined in the current PR and must be observed green before completion.

## Actions

Verified effective repository settings:

- `enabled=true`, `allowed_actions=selected`, `sha_pinning_required=true`.
- GitHub-owned actions allowed; verified-Marketplace blanket access disabled.
- Additional patterns: `sigstore/*`, `oras-project/*`, `helm/*`, `azure/*`, `docker/*`, `googleapis/*`, `anchore/*`.
- Default workflow permissions `read`; workflow PR approval disabled.
- Fork contributor approval: `all_external_contributors`.
- Artifact/log retention: 30 days.

## Environments

- `ci-publish` ID 27240309955 and `release` ID 27240309934.
- Both require `platform-security` review, prevent self-review, disallow admin bypass, and use custom branch policy `main`.
- No environment contains production/customer credentials.

## Pending gates

- Release GitHub App registration is explicitly deferred to the parent/user interactive handoff. The exact no-event manifest, least-privilege permissions (`contents: write` and `pull-requests: write` only), single-repository installation, credential handoff, and verification steps are specified in `docs/admin-setup.md`. No new App, credential, or private key was created. Existing broad/unrelated Apps are not used.
- `library release PR` and every App-dependent release/finalization workflow remain blocked until registration, installation, bypass-actor evidence, and separate execution approval are complete.
- No GHCR package, registry rehearsal, git tag, GitHub Release, Pages, stage/prod, or external merge was performed.
- The release App bypass actor must be verified/recorded before release readiness. Required check names are now configured as listed above.
