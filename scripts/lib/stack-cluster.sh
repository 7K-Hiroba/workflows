#!/usr/bin/env bash
# Shared lock-driven setup for disposable Hiroba CI clusters.

STACK_LIBRARY=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
STACK_PINS="$STACK_LIBRARY/pins/stack-testing.json"
declare -ag STACK_PORT_FORWARD_PIDS=()

stack_pin() {
  jq -r "$1" "$STACK_PINS"
}

stack_download() {
  local record=$1 destination=$2 url expected
  url=$(jq -r .url <<< "$record")
  expected=$(jq -r .sha256 <<< "$record")
  mkdir -p "$(dirname "$destination")"
  curl -fsSL --retry 3 "$url" -o "$destination"
  printf '%s  %s\n' "$expected" "$destination" | sha256sum -c - >/dev/null
}

create_kind_cluster() {
  local cluster=$1
  kind create cluster --name "$cluster" --image "$(stack_pin .kind.nodeImage)" --wait 120s
}

setup_kro() {
  local repository version expected actual
  repository=$(stack_pin .kro.repository)
  version=$(stack_pin .kro.version)
  expected=$(stack_pin .kro.digest)
  actual=$(crane digest "$repository:$version")
  [[ "$actual" == "$expected" ]] || { echo "KRO chart digest mismatch" >&2; return 1; }
  helm upgrade --install kro "oci://$repository@$expected" --namespace kro-system --create-namespace \
    --wait --timeout 180s
}

setup_argocd() {
  [[ -n "${HIROBA_STACK_WORK:-}" ]] || { echo "HIROBA_STACK_WORK is required" >&2; return 2; }
  stack_download "$(stack_pin .argoCd.coreInstall)" "$HIROBA_STACK_WORK/argocd-core-install.yaml"
  kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply -n argocd -f "$HIROBA_STACK_WORK/argocd-core-install.yaml"
  local server_secret
  server_secret=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
  kubectl create secret generic argocd-secret --namespace argocd --dry-run=client -o yaml \
    --from-literal server.secretkey="$server_secret" | kubectl apply -f -
  unset server_secret
  kubectl set image deployment/argocd-redis redis="$(stack_pin .argoCd.redisImage)" --namespace argocd
  kubectl wait --for=condition=Established crd/applications.argoproj.io --timeout=60s
  kubectl wait --for=condition=Established crd/appprojects.argoproj.io --timeout=60s
  kubectl wait --for=condition=Available deployment -n argocd --all --timeout=300s
}

setup_argo_workflows() {
  [[ -n "${HIROBA_STACK_WORK:-}" ]] || { echo "HIROBA_STACK_WORK is required" >&2; return 2; }
  for name in quickStart executorRole executorRoleBinding; do
    stack_download "$(stack_pin ".argoWorkflows.manifests.$name")" "$HIROBA_STACK_WORK/argo-$name.yaml"
  done
  kubectl create namespace argo --dry-run=client -o yaml | kubectl apply -f -
  kubectl create -n argo -f "$HIROBA_STACK_WORK/argo-quickStart.yaml"
  kubectl create --namespace default -f "$HIROBA_STACK_WORK/argo-executorRole.yaml"
  kubectl create --namespace default -f "$HIROBA_STACK_WORK/argo-executorRoleBinding.yaml"
  kubectl patch configmap workflow-controller-configmap --namespace argo --type=json \
    --patch='[{"op":"remove","path":"/data/artifactRepository"}]'
  kubectl rollout restart deployment/workflow-controller --namespace argo
  kubectl wait --for=condition=Available deployment -n argo --all --timeout=180s
}

setup_oci_registry() {
  [[ -n "${HIROBA_STACK_WORK:-}" ]] || { echo "HIROBA_STACK_WORK is required" >&2; return 2; }
  local image registry_port
  image=$(stack_pin .registryImage)
  kubectl create namespace hiroba-registry --dry-run=client -o yaml | kubectl apply -f -
  cat > "$HIROBA_STACK_WORK/registry.yaml" <<EOF
apiVersion: apps/v1
kind: Deployment
metadata: {name: hiroba-registry, namespace: hiroba-registry}
spec:
  replicas: 1
  selector: {matchLabels: {app: hiroba-registry}}
  template:
    metadata: {labels: {app: hiroba-registry}}
    spec:
      containers:
        - name: registry
          image: $image
          ports: [{containerPort: 5000}]
          resources:
            requests: {cpu: 50m, memory: 64Mi}
            limits: {cpu: 200m, memory: 256Mi}
---
apiVersion: v1
kind: Service
metadata: {name: hiroba-registry, namespace: hiroba-registry}
spec:
  selector: {app: hiroba-registry}
  ports: [{port: 5000, targetPort: 5000}]
EOF
  kubectl apply -f "$HIROBA_STACK_WORK/registry.yaml"
  kubectl wait --for=condition=Available deployment/hiroba-registry -n hiroba-registry --timeout=180s
  registry_port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
  kubectl port-forward svc/hiroba-registry -n hiroba-registry "$registry_port:5000" > "$HIROBA_STACK_WORK/registry-port-forward.log" 2>&1 &
  STACK_PORT_FORWARD_PIDS+=("$!")
  for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$registry_port/v2/" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  curl -fsS "http://127.0.0.1:$registry_port/v2/" >/dev/null
  cat > "$HIROBA_STACK_WORK/registry.env" <<EOF
HIROBA_REGISTRY_PORT=$registry_port
HIROBA_REGISTRY_HOST=hiroba-registry.hiroba-registry.svc:5000
HIROBA_REGISTRY_URL=oci://hiroba-registry.hiroba-registry.svc:5000
HIROBA_REGISTRY_LOCAL=127.0.0.1:$registry_port
EOF
}

run_stack_setup_profiles() {
  local profile
  for profile in "$@"; do
    case "$profile" in
      kro) setup_kro ;;
      argocd) setup_argocd ;;
      argo-workflows) setup_argo_workflows ;;
      oci-registry) setup_oci_registry ;;
      *) echo "unknown stack setup profile: $profile" >&2; return 2 ;;
    esac
  done
}

stop_stack_port_forwards() {
  if [[ ${#STACK_PORT_FORWARD_PIDS[@]} -gt 0 ]]; then
    kill "${STACK_PORT_FORWARD_PIDS[@]}" >/dev/null 2>&1 || true
  fi
}

stack_generic_diagnostics() {
  local destination=$1
  {
    kubectl get all -A -o wide || true
    kubectl get rgd -A -o yaml || true
    kubectl get applications -A -o yaml || true
    kubectl get events -A --sort-by=.lastTimestamp || true
    kubectl logs -n kro-system deploy/kro --tail=200 || true
    kubectl logs -n argocd deploy/argocd-repo-server --tail=200 || true
    kubectl logs -n argocd statefulset/argocd-application-controller --tail=200 || true
    kind export logs "$HIROBA_STACK_WORK/kind-logs" --name "$HIROBA_STACK_CLUSTER" || true
  } > "$destination" 2>&1
}
