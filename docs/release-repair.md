# Release and chart repair

Normal releases are PR-only and never triggered by tag push. Publish jobs are idempotent: existing OCI content is pulled and byte-compared where supported, and a different digest/content fails rather than overwriting.

Chart repair runs `release-chart.yml` from an existing `<chart>-vX.Y.Z` tag at the matching source commit. It requires the release environment, reruns chart CI, verifies the existing package/digest, and can restore missing signature/provenance/test evidence. It never creates a new version, moves a channel, or changes the tag.

Rehearsal chart mode proves idempotent existing-digest reuse without a git tag. Actual signed-tag repair remains separately authorized. To repair after approval, use the consumer's chart-repair dispatch at the existing tag, record before/after digest, and verify they match. Any source/tag/content mismatch is a stop condition.

Disable release workflows and remove App installation/repository access to contain a suspected compromise; preserve artifacts and evidence for investigation rather than deleting audit history.
