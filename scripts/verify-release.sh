#!/usr/bin/env bash
set -euo pipefail
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
: "${ARTIFACT_REF:?}" "${ARTIFACT_REPOSITORY:?}" "${ARTIFACT_DIGEST:?}" "${MEDIA_TYPE:?}"
: "${SOURCE_REPOSITORY:?}" "${SOURCE_SHA:?}" "${WORKFLOW_SHA:?}" "${REQUIRED_LANES:?}"
: "${EXPECTED_PUBLISHER:?}" "${WORKFLOW_PATH:?}" "${RELEASE_TAG:?}"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cosign verify "$ARTIFACT_REF" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp "$EXPECTED_PUBLISHER" >/dev/null
gh attestation verify "oci://$ARTIFACT_REF" --repo "$SOURCE_REPOSITORY" --format json > "$WORK/provenance.json"
grep -q 'https://slsa.dev/provenance/v1' "$WORK/provenance.json" || { echo "SLSA v1 provenance missing" >&2; exit 1; }
cosign verify-attestation "$ARTIFACT_REF" --type https://inari.dev/attestations/test-evidence/v1 \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp "$EXPECTED_PUBLISHER" > "$WORK/test-evidence.json"
read -r -a required <<< "$REQUIRED_LANES"
args=()
for lane in "${required[@]}"; do args+=(--required-lane "$lane"); done
python3 "$LIBRARY/scripts/verify-test-evidence.py" \
  --predicate "$WORK/test-evidence.json" --source-repository "$SOURCE_REPOSITORY" --source-sha "$SOURCE_SHA" \
  --workflow-sha "$WORKFLOW_SHA" --workflow-path "$WORKFLOW_PATH" \
  --artifact-repository "$ARTIFACT_REPOSITORY" --artifact-digest "$ARTIFACT_DIGEST" --media-type "$MEDIA_TYPE" \
  --release-tag "$RELEASE_TAG" "${args[@]}"
if [[ -n "${VERIFICATION_RECEIPT:-}" ]]; then
  jq -n --arg ref "$ARTIFACT_REF" --arg repository "$ARTIFACT_REPOSITORY" --arg digest "$ARTIFACT_DIGEST" \
    --arg sourceRepository "$SOURCE_REPOSITORY" --arg sourceSha "$SOURCE_SHA" --arg workflowSha "$WORKFLOW_SHA" \
    --arg workflowPath "$WORKFLOW_PATH" --arg releaseTag "$RELEASE_TAG" --arg mediaType "$MEDIA_TYPE" --arg required "$REQUIRED_LANES" \
    '{status:"verified",artifactRef:$ref,artifactRepository:$repository,digest:$digest,sourceRepository:$sourceRepository,sourceSha:$sourceSha,workflowSha:$workflowSha,workflowPath:$workflowPath,releaseTag:$releaseTag,mediaType:$mediaType,requiredLanes:($required|split(" ")|map(select(length>0)))}' > "$VERIFICATION_RECEIPT"
fi
echo "verified signature, SLSA provenance, and fully bound test evidence for $ARTIFACT_REF"
