#!/usr/bin/env bash
set -euo pipefail

LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
PINS="$LIBRARY/pins/stack-testing.json"
INSTALL_DIR=${HIROBA_INSTALL_DIR:-${RUNNER_TEMP:-/tmp}/hiroba-bin}
CACHE_DIR=${HIROBA_CACHE_DIR:-${GITHUB_WORKSPACE:-$PWD}/.hiroba-cache}
MODE=install
TOOLS=()
PROFILES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profiles)
      IFS=',' read -ra supplied <<< "$2"
      for profile in "${supplied[@]}"; do
        [[ -n "$profile" ]] || continue
        [[ $(jq -r --arg profile "$profile" '.profiles | has($profile)' "$PINS") == true ]] || { echo "unknown stack setup profile: $profile" >&2; exit 2; }
        PROFILES+=("$profile")
        while read -r tool; do [[ -n "$tool" ]] && TOOLS+=("$tool"); done < <(jq -r --arg profile "$profile" '.profiles[$profile][]' "$PINS")
      done
      shift 2
      ;;
    --cache-key) MODE=key; shift ;;
    *) TOOLS+=("$1"); shift ;;
  esac
done
if [[ ${#PROFILES[@]} -gt 0 ]]; then TOOLS+=(kind helm kubectl); fi
if [[ ${#TOOLS[@]} -eq 0 ]]; then echo "at least one CI tool or setup profile is required" >&2; exit 2; fi
mapfile -t TOOLS < <(printf '%s\n' "${TOOLS[@]}" | sort -u)

CACHE_KEY=$(python3 - "$LIBRARY/scripts" "$PINS" "${PROFILES[@]}" -- "${TOOLS[@]}" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
from lib.pin_cache import cache_key
with open(sys.argv[2]) as source:
    pins = json.load(source)
args = sys.argv[3:]
separator = args.index("--")
profiles = [item for item in args[:separator] if item]
tools = args[separator + 1:]
print(cache_key(pins, tools, profiles))
PY
)
if [[ "$MODE" == key ]]; then
  printf '%s\n' "$CACHE_KEY"
  exit 0
fi

mkdir -p "$INSTALL_DIR" "$CACHE_DIR"
if [[ -n "${GITHUB_PATH:-}" ]]; then echo "$INSTALL_DIR" >> "$GITHUB_PATH"; fi
export PATH="$INSTALL_DIR:$PATH"

for tool in "${TOOLS[@]}"; do
  record=$(jq -e --arg tool "$tool" '.tools[$tool]' "$PINS") || { echo "unsupported CI tool: $tool" >&2; exit 2; }
  url=$(jq -r .url <<< "$record")
  expected=$(jq -r .sha256 <<< "$record")
  format=$(jq -r .format <<< "$record")
  member=$(jq -r '.path // ""' <<< "$record")
  archive="$CACHE_DIR/$tool-$expected.archive"
  if [[ -f "$archive" ]] && ! printf '%s  %s\n' "$expected" "$archive" | sha256sum -c - >/dev/null 2>&1; then
    rm -f "$archive"
  fi
  if [[ ! -f "$archive" ]]; then
    temporary="$archive.tmp.$$"
    curl -fsSL --retry 3 "$url" -o "$temporary"
    printf '%s  %s\n' "$expected" "$temporary" | sha256sum -c -
    mv "$temporary" "$archive"
  fi
  printf '%s  %s\n' "$expected" "$archive" | sha256sum -c - >/dev/null

  work=$(mktemp -d)
  case "$format" in
    binary)
      install -m 0755 "$archive" "$work/$tool"
      ;;
    gzip)
      gunzip -c "$archive" > "$work/$tool"
      chmod 0755 "$work/$tool"
      ;;
    tar)
      tar -xf "$archive" -C "$work" "$member"
      install -m 0755 "$work/$member" "$INSTALL_DIR/$tool"
      rm -rf "$work"
      continue
      ;;
    zip)
      python3 - "$archive" "$work" "$member" <<'PY'
import sys, zipfile
archive, work, member = sys.argv[1:]
with zipfile.ZipFile(archive) as source:
    source.extract(member, work)
PY
      install -m 0755 "$work/$member" "$INSTALL_DIR/$tool"
      rm -rf "$work"
      continue
      ;;
    *) echo "unsupported tool archive format: $format" >&2; rm -rf "$work"; exit 2 ;;
  esac
  install -m 0755 "$work/$tool" "$INSTALL_DIR/$tool"
  rm -rf "$work"
done

REPORT=${HIROBA_TOOL_CACHE_REPORT:-${RUNNER_TEMP:-/tmp}/hiroba-tool-cache.json}
jq -n --arg cacheKey "$CACHE_KEY" --arg cacheHit "${HIROBA_CACHE_HIT:-false}" \
  --arg cacheDir "$CACHE_DIR" --argjson tools "$(printf '%s\n' "${TOOLS[@]}" | jq -R . | jq -s .)" \
  '{schema:"inari.tool-cache.v1",cacheKey:$cacheKey,cacheHit:($cacheHit == "true"),cacheDir:$cacheDir,tools:$tools,clusterState:false}' > "$REPORT"
