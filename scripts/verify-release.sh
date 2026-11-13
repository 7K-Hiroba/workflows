#!/usr/bin/env bash
set -euo pipefail
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
: "${ARTIFACT_REF:?}" "${ARTIFACT_DIGEST:?}" "${SOURCE_REPOSITORY:?}" "${SOURCE_SHA:?}"
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
python3 "$LIBRARY/scripts/verify-test-evidence.py" \
  --predicate "$WORK/test-evidence.json" --source-sha "$SOURCE_SHA" --workflow-path "$WORKFLOW_PATH" \
  --artifact-digest "$ARTIFACT_DIGEST" --release-tag "$RELEASE_TAG"
echo "verified signature, SLSA provenance, and release-linked test evidence for $ARTIFACT_REF"
