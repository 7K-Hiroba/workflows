#!/usr/bin/env bash
set -euo pipefail
ROOT=""
CHART=""
VERSION=""
REPOSITORY_BASE=""
SOURCE_SHA=""
OUTPUT=""
CHANNEL=""
REPAIR=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT=$2; shift 2 ;;
    --chart) CHART=$2; shift 2 ;;
    --version) VERSION=$2; shift 2 ;;
    --repository-base) REPOSITORY_BASE=$2; shift 2 ;;
    --source-sha) SOURCE_SHA=$2; shift 2 ;;
    --channel) CHANNEL=$2; shift 2 ;;
    --output) OUTPUT=$2; shift 2 ;;
    --repair) REPAIR=$2; shift 2 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done
[[ "$CHART" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "invalid chart name" >&2; exit 2; }
[[ "$VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$ ]] || { echo "chart version must be SemVer" >&2; exit 2; }
[[ "$SOURCE_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "source SHA must be full 40 characters" >&2; exit 2; }
[[ -z "$CHANNEL" || "$CHANNEL" == edge ]] || { echo "chart channel may only be edge" >&2; exit 2; }
[[ "$REPAIR" != true || -z "$CHANNEL" ]] || { echo "chart repair cannot move a channel" >&2; exit 2; }
CHARTS_ROOT=charts
if [[ -f "$ROOT/.hiroba.yaml" ]]; then
  LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
  CHARTS_ROOT=$(${HIROBA_PYTHON:-python3} -c 'import sys,yaml; from pathlib import Path; sys.path.insert(0,sys.argv[2]); from lib.paths import relative_path; data=yaml.safe_load(open(sys.argv[1])); print(relative_path(Path(sys.argv[3]), data["components"].get("chartsRoot", "charts"), "components.chartsRoot"))' "$ROOT/.hiroba.yaml" "$LIBRARY/scripts" "$ROOT")
fi
CHART_DIR="$ROOT/$CHARTS_ROOT/$CHART"
CHART_YAML="$CHART_DIR/Chart.yaml"
[[ -f "$CHART_YAML" ]] || { echo "missing $CHART_YAML" >&2; exit 2; }
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
${HIROBA_PYTHON:-python3} -c 'import re,sys,yaml; data=yaml.safe_load(open(sys.argv[1])); assert data["name"] == sys.argv[2]; assert re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?", str(data["version"]))' "$CHART_YAML" "$CHART"
if [[ "$CHANNEL" == edge ]]; then
  mkdir -p "$WORK/chart"
  cp -R "$CHART_DIR/." "$WORK/chart/"
  CHART_DIR="$WORK/chart"
  CHART_YAML="$CHART_DIR/Chart.yaml"
  ${HIROBA_PYTHON:-python3} -c 'import sys,yaml; p=sys.argv[1]; data=yaml.safe_load(open(p)); data["version"]=sys.argv[2]; open(p,"w").write(yaml.safe_dump(data, sort_keys=False))' "$CHART_YAML" "$VERSION"
fi
${HIROBA_PYTHON:-python3} -c 'import sys,yaml; data=yaml.safe_load(open(sys.argv[1])); assert data["name"] == sys.argv[2]; assert str(data["version"]) == sys.argv[3]' "$CHART_YAML" "$CHART" "$VERSION"
TAG="$CHART-v$VERSION"
if [[ "$REPAIR" == true ]]; then
  TAG_SHA=$(git -C "$ROOT" rev-parse "refs/tags/$TAG^{commit}" 2>/dev/null) || { echo "repair requires existing tag $TAG" >&2; exit 2; }
  HEAD_SHA=$(git -C "$ROOT" rev-parse HEAD)
  [[ "$TAG_SHA" == "$HEAD_SHA" ]] || { echo "repair tag $TAG does not point at current source" >&2; exit 2; }
fi
mkdir -p "$WORK/new"
helm package "$CHART_DIR" --destination "$WORK/new"
PACKAGE="$WORK/new/$CHART-$VERSION.tgz"
[[ -f "$PACKAGE" ]] || { echo "Helm package missing: $PACKAGE" >&2; exit 1; }
REPOSITORY="$REPOSITORY_BASE/$CHART"
crane_login() {
  [[ -n "${GHCR_ACTOR:-}" && -n "${GHCR_TOKEN:-}" ]] || { echo "GHCR_ACTOR and GHCR_TOKEN are required for crane authentication" >&2; return 1; }
  if ! crane auth login ghcr.io -u "$GHCR_ACTOR" -p "$GHCR_TOKEN" >/dev/null 2>&1; then
    echo "crane login failed for ghcr.io" >&2
    return 1
  fi
}
crane_login
DIGEST=$(crane digest "$REPOSITORY:$VERSION" 2>/dev/null || true)
if [[ -z "$DIGEST" ]]; then
  helm push "$PACKAGE" "oci://$REPOSITORY_BASE"
  crane_login
  DIGEST=$(crane digest "$REPOSITORY:$VERSION")
fi
crane_login
RESOLVED=$(crane digest "$REPOSITORY:$VERSION")
[[ "$RESOLVED" == "$DIGEST" ]] || { echo "chart digest mismatch after publish" >&2; exit 1; }
mkdir -p "$WORK/exact"
oras copy "$REPOSITORY@$DIGEST" --to-oci-layout "$WORK/exact"
CHART_BLOB=$(${HIROBA_PYTHON:-python3} - "$WORK/exact" "$DIGEST" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected = sys.argv[2].lower()
content_media = "application/vnd.cncf.helm.chart.content.v1.tar+gzip"
manifest_media = "application/vnd.oci.image.manifest.v1+json"
index_media = "application/vnd.oci.image.index.v1+json"


def blob(descriptor):
    if not isinstance(descriptor, dict):
        raise ValueError("invalid OCI descriptor")
    digest = descriptor.get("digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("invalid or unsafe OCI blob digest")
    path = root / "blobs" / "sha256" / digest.removeprefix("sha256:")
    if not path.is_file():
        raise ValueError("OCI blob is missing")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError("OCI blob digest mismatch")
    return data, path


def load_document(descriptor, media_type):
    data, _ = blob(descriptor)
    document = json.loads(data)
    if document.get("schemaVersion") != 2 or document.get("mediaType") != media_type:
        raise ValueError("invalid OCI index/manifest chain")
    return document


def only_descriptor(document):
    manifests = document.get("manifests")
    if not isinstance(manifests, list) or len(manifests) != 1:
        raise ValueError("expected exactly one OCI manifest descriptor")
    return manifests[0]


index = json.loads((root / "index.json").read_bytes())
if index.get("schemaVersion") != 2 or index.get("mediaType", index_media) != index_media:
    raise ValueError("invalid OCI layout index")
descriptor = only_descriptor(index)
if not isinstance(descriptor, dict) or descriptor.get("digest", "").lower() != expected:
    raise ValueError("layout root digest does not match requested exact digest")
while True:
    media_type = descriptor.get("mediaType")
    if media_type == index_media:
        descriptor = only_descriptor(load_document(descriptor, index_media))
        continue
    if media_type != manifest_media:
        raise ValueError("unexpected media type in OCI index/manifest chain")
    manifest = load_document(descriptor, manifest_media)
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise ValueError("invalid Helm chart layer list")
    selected = [layer for layer in layers if isinstance(layer, dict) and layer.get("mediaType") == content_media]
    if len(selected) != 1:
        raise ValueError("expected exactly one Helm chart content layer")
    _, chart_blob = blob(selected[0])
    print(chart_blob)
    break
PY
)
cmp "$PACKAGE" "$CHART_BLOB" || { echo "packaged chart differs for $REPOSITORY@$DIGEST" >&2; exit 1; }
mkdir -p "$(dirname "$OUTPUT")"
jq -n --arg repository "$REPOSITORY" --arg digest "$DIGEST" --arg sourceSha "$SOURCE_SHA" --arg tag "$VERSION" --arg releaseTag "$TAG" --arg channel "$CHANNEL" \
  '{repository:$repository,digest:$digest,ref:($repository+"@"+$digest),mediaType:"application/vnd.cncf.helm.chart.v1",sourceSha:$sourceSha,tag:$tag,releaseTag:$releaseTag,channel:$channel,signature:{verified:false},provenance:{verified:false},testEvidence:{status:"pending"}}' > "$OUTPUT"
echo "published or verified chart $REPOSITORY@$DIGEST"
