#!/usr/bin/env bash
set -euo pipefail
INSTALL_DIR=${RUNNER_TEMP:-/tmp}/hiroba-bin
mkdir -p "$INSTALL_DIR"
if [[ -n "${GITHUB_PATH:-}" ]]; then echo "$INSTALL_DIR" >> "$GITHUB_PATH"; fi
export PATH="$INSTALL_DIR:$PATH"
for tool in "$@"; do
  case "$tool" in
    kind)
      url='https://github.com/kubernetes-sigs/kind/releases/download/v0.30.0/kind-linux-amd64'
      expected='517ab7fc89ddeed5fa65abf71530d90648d9638ef0c4cde22c2c11f8097b8889'
      curl -fsSL "$url" -o "$INSTALL_DIR/kind"
      echo "$expected  $INSTALL_DIR/kind" | sha256sum -c -
      chmod +x "$INSTALL_DIR/kind"
      ;;
    argo)
      url='https://github.com/argoproj/argo-workflows/releases/download/v4.1.6/argo-linux-amd64.gz'
      expected='885f886a338d7e7c0fd4a681152770fb54df1847f8fc55eaed788d661c0304e0'
      curl -fsSL "$url" -o "$INSTALL_DIR/argo.gz"
      echo "$expected  $INSTALL_DIR/argo.gz" | sha256sum -c -
      gunzip -f "$INSTALL_DIR/argo.gz"
      chmod +x "$INSTALL_DIR/argo"
      ;;
    crane)
      GOBIN="$INSTALL_DIR" go install github.com/google/go-containerregistry/cmd/crane@v0.20.7
      ;;
    promtool)
      url='https://github.com/prometheus/prometheus/releases/download/v3.5.0/prometheus-3.5.0.linux-amd64.tar.gz'
      expected='e811827af26d822afb09a4f28314f61b618b12cff5369835a67f674d8b46f39a'
      archive="$INSTALL_DIR/prometheus.tar.gz"
      curl -fsSL "$url" -o "$archive"
      echo "$expected  $archive" | sha256sum -c -
      tar -xzf "$archive" -C "$INSTALL_DIR" prometheus-3.5.0.linux-amd64/promtool --strip-components=1
      chmod +x "$INSTALL_DIR/promtool"
      ;;
    gcx)
      url='https://github.com/grafana/gcx/releases/download/v1.7.1/gcx_1.7.1_linux_amd64.tar.gz'
      expected='5f1601feac13d850017064a9b556f11983de6def2986ba0bee402a947659c3e9'
      archive="$INSTALL_DIR/gcx.tar.gz"
      curl -fsSL "$url" -o "$archive"
      echo "$expected  $archive" | sha256sum -c -
      tar -xzf "$archive" -C "$INSTALL_DIR" gcx
      chmod +x "$INSTALL_DIR/gcx"
      ;;
    alloy)
      url='https://github.com/grafana/alloy/releases/download/v1.13.0/alloy-linux-amd64.zip'
      expected='1e4e809917e2a0395b7027012379103fc9112731832508b03ff8aeffa041c977'
      archive="$INSTALL_DIR/alloy.zip"
      curl -fsSL "$url" -o "$archive"
      echo "$expected  $archive" | sha256sum -c -
      python3 -c 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$archive" "$INSTALL_DIR"
      mv -f "$INSTALL_DIR/alloy-linux-amd64" "$INSTALL_DIR/alloy"
      chmod +x "$INSTALL_DIR/alloy"
      ;;
    shellcheck)
      url='https://github.com/koalaman/shellcheck/releases/download/v0.11.0/shellcheck-v0.11.0.linux.x86_64.tar.xz'
      expected='8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198'
      archive="$INSTALL_DIR/shellcheck.tar.xz"
      curl -fsSL "$url" -o "$archive"
      echo "$expected  $archive" | sha256sum -c -
      tar -xJf "$archive" -C "$INSTALL_DIR" shellcheck-v0.11.0/shellcheck --strip-components=1
      chmod +x "$INSTALL_DIR/shellcheck"
      ;;
    ct)
      GOBIN="$INSTALL_DIR" go install github.com/helm/chart-testing/v3/ct@v3.14.0
      ;;
    *) echo "unsupported CI tool: $tool" >&2; exit 2 ;;
  esac
done
