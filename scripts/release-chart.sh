#!/usr/bin/env bash
set -euo pipefail
ROOT=""
CHART=""
VERSION=""
REPOSITORY_BASE=""
SOURCE_SHA=""
OUTPUT=""
REPAIR=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT=$2; shift 2 ;;
    --chart) CHART=$2; shift 2 ;;
    --version) VERSION=$2; shift 2 ;;
    --repository-base) REPOSITORY_BASE=$2; shift 2 ;;
    --source-sha) SOURCE_SHA=$2; shift 2 ;;
    --output) OUTPUT=$2; shift 2 ;;
    --repair) REPAIR=$2; shift 2 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done
[[ "$CHART" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "invalid chart name" >&2; exit 2; }
[[ "$VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$ ]] || { echo "chart version must be SemVer" >&2; exit 2; }
[[ "$SOURCE_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "source SHA must be full 40 characters" >&2; exit 2; }
CHART_DIR="$ROOT/charts/$CHART"
CHART_YAML="$CHART_DIR/Chart.yaml"
[[ -f "$CHART_YAML" ]] || { echo "missing $CHART_YAML" >&2; exit 2; }
${HIROBA_PYTHON:-python3} -c 'import sys,yaml; data=yaml.safe_load(open(sys.argv[1])); assert data["name"] == sys.argv[2]; assert str(data["version"]) == sys.argv[3]' "$CHART_YAML" "$CHART" "$VERSION"
TAG="$CHART-v$VERSION"
if [[ "$REPAIR" == true ]]; then
  TAG_SHA=$(git -C "$ROOT" rev-parse "refs/tags/$TAG^{commit}" 2>/dev/null) || { echo "repair requires existing tag $TAG" >&2; exit 2; }
  HEAD_SHA=$(git -C "$ROOT" rev-parse HEAD)
  [[ "$TAG_SHA" == "$HEAD_SHA" ]] || { echo "repair tag $TAG does not point at current source" >&2; exit 2; }
fi
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/new"
helm package "$CHART_DIR" --destination "$WORK/new"
PACKAGE="$WORK/new/$CHART-$VERSION.tgz"
[[ -f "$PACKAGE" ]] || { echo "Helm package missing: $PACKAGE" >&2; exit 1; }
REPOSITORY="$REPOSITORY_BASE/$CHART"
DIGEST=$(crane digest "$REPOSITORY:$VERSION" 2>/dev/null || true)
if [[ -n "$DIGEST" ]]; then
  mkdir -p "$WORK/existing"
  helm pull "oci://$REPOSITORY" --version "$VERSION" --destination "$WORK/existing"
  cmp "$PACKAGE" "$WORK/existing/$CHART-$VERSION.tgz" || { echo "existing chart package differs for $REPOSITORY@$DIGEST" >&2; exit 1; }
else
  helm push "$PACKAGE" "oci://$REPOSITORY_BASE"
  DIGEST=$(crane digest "$REPOSITORY:$VERSION")
fi
RESOLVED=$(crane digest "$REPOSITORY:$VERSION")
[[ "$RESOLVED" == "$DIGEST" ]] || { echo "chart digest mismatch after publish" >&2; exit 1; }
mkdir -p "$(dirname "$OUTPUT")"
jq -n --arg repository "$REPOSITORY" --arg digest "$DIGEST" --arg sourceSha "$SOURCE_SHA" --arg tag "$TAG" \
  '{repository:$repository,digest:$digest,ref:($repository+"@"+$digest),mediaType:"application/vnd.cncf.helm.chart.v1",sourceSha:$sourceSha,tag:$tag,channel:"",signature:{verified:false},provenance:{verified:false},testEvidence:{status:"pending"}}' > "$OUTPUT"
echo "published or verified chart $REPOSITORY@$DIGEST"
