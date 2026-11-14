#!/usr/bin/env bash
set -euo pipefail
CONTEXT=""
REPOSITORY=""
TAG=""
SOURCE_SHA=""
OUTPUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --context) CONTEXT=$2; shift 2 ;;
    --repository) REPOSITORY=$2; shift 2 ;;
    --tag) TAG=$2; shift 2 ;;
    --source-sha) SOURCE_SHA=$2; shift 2 ;;
    --output) OUTPUT=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -d "$CONTEXT" && -n "$REPOSITORY" && -n "$OUTPUT" ]] || { echo "context, repository, and output are required" >&2; exit 2; }
[[ "$TAG" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$ || "$TAG" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "backend tag must be SemVer, a prerelease, or a full source SHA" >&2; exit 2; }
[[ "$SOURCE_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "source SHA must be full 40 characters" >&2; exit 2; }
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
CANDIDATE_ARCHIVE="$WORK/candidate.tar"
# Always build the exact checked-out source. Never attest an existing tag without a candidate comparison.
docker buildx build --output "type=oci,dest=$CANDIDATE_ARCHIVE" --tag "$REPOSITORY:$TAG" --provenance=false --sbom=false "$CONTEXT"
DESCRIPTOR=$(python3 - "$CANDIDATE_ARCHIVE" <<'PY'
import json, sys, tarfile
with tarfile.open(sys.argv[1]) as archive:
    index = json.load(archive.extractfile("index.json"))
manifests = index.get("manifests", [])
if len(manifests) != 1:
    raise SystemExit("backend candidate must contain exactly one image manifest")
descriptor = manifests[0]
digest = descriptor.get("digest", "")
media_type = descriptor.get("mediaType", "")
if not digest.startswith("sha256:") or len(digest) != 71 or not media_type.startswith("application/vnd.oci.image."):
    raise SystemExit("invalid backend OCI manifest descriptor")
print(digest)
print(media_type)
PY
)
mapfile -t DESCRIPTOR_LINES <<< "$DESCRIPTOR"
CANDIDATE_DIGEST=${DESCRIPTOR_LINES[0]}
MEDIA_TYPE=${DESCRIPTOR_LINES[1]}
EXISTING=$(crane digest "$REPOSITORY:$TAG" 2>/dev/null || true)
if [[ -n "$EXISTING" ]]; then
  [[ "$EXISTING" == "$CANDIDATE_DIGEST" ]] || { echo "existing backend image digest differs for $REPOSITORY:$TAG" >&2; exit 1; }
else
  crane push "$CANDIDATE_ARCHIVE" "$REPOSITORY:$TAG"
fi
RESOLVED=$(crane digest "$REPOSITORY:$TAG")
[[ "$RESOLVED" == "$CANDIDATE_DIGEST" ]] || { echo "resolved backend digest differs from candidate" >&2; exit 1; }
mkdir -p "$(dirname "$OUTPUT")"
jq -n --arg repository "$REPOSITORY" --arg digest "$CANDIDATE_DIGEST" --arg mediaType "$MEDIA_TYPE" --arg sourceSha "$SOURCE_SHA" --arg tag "$TAG" \
  '{repository:$repository,digest:$digest,ref:($repository+"@"+$digest),mediaType:$mediaType,sourceSha:$sourceSha,tag:$tag,channel:"",signature:{verified:false},provenance:{verified:false},testEvidence:{status:"pending"}}' > "$OUTPUT"
echo "published or verified immutable backend $REPOSITORY@$CANDIDATE_DIGEST"
