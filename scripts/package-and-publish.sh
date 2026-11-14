#!/usr/bin/env bash
set -euo pipefail
SOURCE=""
FILE=""
REPOSITORY=""
TAG=""
MEDIA_TYPE=""
CHANNEL=""
SOURCE_SHA=""
OUTPUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE=$2; shift 2 ;;
    --file) FILE=$2; shift 2 ;;
    --repository) REPOSITORY=$2; shift 2 ;;
    --tag) TAG=$2; shift 2 ;;
    --artifact-type) MEDIA_TYPE=$2; shift 2 ;;
    --channel) CHANNEL=$2; shift 2 ;;
    --source-sha) SOURCE_SHA=$2; shift 2 ;;
    --output) OUTPUT=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -d "$SOURCE" && -n "$REPOSITORY" && -n "$TAG" && -n "$MEDIA_TYPE" && -n "$OUTPUT" ]] || { echo "source, repository, tag, artifact-type, and output are required" >&2; exit 2; }
[[ "$TAG" != latest && "$TAG" != main && "$TAG" != stable && "$TAG" != incubating ]] || { echo "mutable or channel tag is not a version/source tag: $TAG" >&2; exit 2; }
[[ "$TAG" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$ || "$TAG" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "tag must be SemVer, prerelease edge version, or full source SHA" >&2; exit 2; }
[[ -z "$CHANNEL" || "$CHANNEL" == stable || "$CHANNEL" == incubating || "$CHANNEL" == edge ]] || { echo "invalid channel" >&2; exit 2; }
[[ "$SOURCE_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "source SHA must be full 40 characters" >&2; exit 2; }
if [[ -n "$FILE" ]]; then
  [[ "$FILE" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ && -f "$SOURCE/$FILE" ]] || { echo "invalid --file" >&2; exit 2; }
fi
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
DIGEST=$(crane digest "$REPOSITORY:$TAG" 2>/dev/null || true)
if [[ -n "$DIGEST" ]]; then
  mkdir -p "$WORK/existing"
  oras pull --output "$WORK/existing" "$REPOSITORY@$DIGEST"
  if [[ -n "$FILE" ]]; then
    cmp "$SOURCE/$FILE" "$WORK/existing/$FILE" || { echo "existing artifact bytes differ for $REPOSITORY@$DIGEST" >&2; exit 1; }
  else
    diff -r "$SOURCE" "$WORK/existing" || { echo "existing artifact bytes differ for $REPOSITORY@$DIGEST" >&2; exit 1; }
  fi
else
  if [[ -n "$FILE" ]]; then
    PUSH_OUTPUT=$(cd "$SOURCE" && oras push "$REPOSITORY:$TAG" --artifact-type "$MEDIA_TYPE" "$FILE:text/yaml")
  else
    PUSH_OUTPUT=$(cd "$SOURCE" && oras push "$REPOSITORY:$TAG" --artifact-type "$MEDIA_TYPE" .)
  fi
  printf '%s\n' "$PUSH_OUTPUT"
  DIGEST=$(grep -oE 'sha256:[0-9a-fA-F]{64}' <<< "$PUSH_OUTPUT" | tail -n 1)
  [[ -n "$DIGEST" ]] || { echo "registry did not return an OCI digest" >&2; exit 1; }
fi
RESOLVED=$(crane digest "$REPOSITORY:$TAG")
[[ "$RESOLVED" == "$DIGEST" ]] || { echo "resolved digest mismatch: $RESOLVED != $DIGEST" >&2; exit 1; }
mkdir -p "$(dirname "$OUTPUT")"
jq -n --arg repository "$REPOSITORY" --arg digest "$DIGEST" --arg mediaType "$MEDIA_TYPE" \
  --arg sourceSha "$SOURCE_SHA" --arg tag "$TAG" --arg channel "$CHANNEL" \
  '{repository:$repository,digest:$digest,ref:($repository+"@"+$digest),mediaType:$mediaType,sourceSha:$sourceSha,tag:$tag,channel:$channel,signature:{verified:false},provenance:{verified:false},testEvidence:{status:"pending"}}' > "$OUTPUT"
echo "published or verified immutable artifact $REPOSITORY@$DIGEST"
