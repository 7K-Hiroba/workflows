# Release and chart repair

Normal releases are PR-only and never triggered by tag push. Publish jobs are idempotent: existing OCI content is pulled and byte-compared where supported, and a different digest/content fails rather than overwriting.

Chart repair runs `release-chart.yml` from an existing `<chart>-vX.Y.Z` tag at the matching source commit. It requires the release environment, reruns chart CI, verifies the existing package/digest, and can restore missing signature/provenance/test evidence. For a chart with an `upgrade` declaration, the required-lane policy and actual per-chart lifecycle artifact are derived from that tagged source; missing or non-matching lifecycle evidence fails repair. It never creates a new version, moves a channel, or changes the tag.

Rehearsal chart mode proves idempotent existing-digest reuse without a git tag. Actual signed-tag repair remains separately authorized. To repair after approval, use the consumer's chart-repair dispatch at the existing tag, record before/after digest, and verify they match. Any source/tag/content mismatch is a stop condition.

Disable release workflows and remove App installation/repository access to contain a suspected compromise; preserve artifacts and evidence for investigation rather than deleting audit history.

## Channel recovery evidence

Only the post-index coordinator moves package, template, extension, UI, chart, smoke, and index channels. It validates every planned artifact and snapshots every destination before the first move. The `channel-reconciliation` artifact records `completed`, `blocked`, `rolled-back`, or `reconciliation-required`; finalization and edge Git tagging remain blocked unless coordination completes.

After a mid-move failure, the coordinator restores previous digests and verifies them. A channel that did not exist previously cannot be safely untagged through portable OCI tooling without risking immutable manifest deletion, so it is explicitly reported as `reconciliation-required`. Restore only the reported channel tag using the recorded previous/target digests under separate registry-admin approval; never delete the immutable artifact manifest or its signatures/attestations.
