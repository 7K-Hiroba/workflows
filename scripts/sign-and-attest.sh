#!/usr/bin/env bash
set -euo pipefail
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
: "${ARTIFACT_REF:?}" "${ARTIFACT_REPOSITORY:?}" "${ARTIFACT_DIGEST:?}" "${MEDIA_TYPE:?}"
: "${APP:?}" "${COMPONENT:?}" "${TRUST_TIER:?}" "${SOURCE_REPOSITORY:?}" "${SOURCE_SHA:?}"
: "${WORKFLOW_SHA:?}" "${WORKFLOW_PATH:?}" "${RUN_ID:?}" "${RUN_ATTEMPT:?}" "${RELEASE_TAG:?}" "${EVIDENCE_DIR:?}"
[[ "$ARTIFACT_REF" == "$ARTIFACT_REPOSITORY@$ARTIFACT_DIGEST" ]] || { echo "artifact ref/repository/digest mismatch" >&2; exit 2; }
PREDICATE_OUT=${PREDICATE_OUT:-$EVIDENCE_DIR/test-predicate.json}
mkdir -p "$(dirname "$PREDICATE_OUT")"
read -r -a required <<< "${REQUIRED_LANES:-validate}"
args=()
for lane in "${required[@]}"; do args+=(--required-lane "$lane"); done
python3 "$LIBRARY/scripts/build-test-evidence.py" \
  --evidence-dir "$EVIDENCE_DIR" --output "$PREDICATE_OUT" \
  --app "$APP" --component "$COMPONENT" --trust-tier "$TRUST_TIER" \
  --source-repository "$SOURCE_REPOSITORY" --source-sha "$SOURCE_SHA" \
  --workflow-sha "$WORKFLOW_SHA" --workflow-path "$WORKFLOW_PATH" \
  --run-id "$RUN_ID" --run-attempt "$RUN_ATTEMPT" \
  --artifact-repository "$ARTIFACT_REPOSITORY" --artifact-digest "$ARTIFACT_DIGEST" \
  --media-type "$MEDIA_TYPE" --release-tag "$RELEASE_TAG" "${args[@]}"
cosign sign --yes "$ARTIFACT_REF"
cosign attest --yes --predicate "$PREDICATE_OUT" --type https://inari.dev/attestations/test-evidence/v1 "$ARTIFACT_REF"
