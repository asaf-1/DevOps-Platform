#!/usr/bin/env bash
# up: create the kind cluster if missing, install ingress-nginx and ArgoCD
# with Helm, create the one secret that must not live in git, apply the
# ArgoCD AppProject and root Application, then wait for every Application
# to be Synced and Healthy. Idempotent: safe to run again.
#
# Env: KIND_CLUSTER_NAME (default platform), UP_WAIT_TIMEOUT (default 15m,
# set 0 to skip the wait).
source "$(dirname "$0")/lib.sh"

INGRESS_NGINX_CHART_VERSION=4.15.1
ARGOCD_CHART_VERSION=10.11.1
KIND_CONFIG="$REPO_ROOT/gitops/clusters/local/kind.yaml"
VALUES_DIR="$REPO_ROOT/gitops/clusters/local/values"
ARGOCD_DIR="$REPO_ROOT/gitops/argocd"
WAIT_TIMEOUT="${UP_WAIT_TIMEOUT:-15m}"

need kind kubectl helm docker jq

say "1/6 kind cluster '$CLUSTER_NAME'"
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  say "cluster exists, reusing it"
else
  if in_container; then
    # kind creates the 'kind' docker network on first use. Create it up front
    # so this container can join it (step 2) and reach the API server.
    docker network inspect kind >/dev/null 2>&1 || docker network create kind >/dev/null
  fi
  # 5m: a laptop needs more than kind's default to get the control plane Ready.
  kind create cluster --name "$CLUSTER_NAME" --config "$KIND_CONFIG" --wait 5m
fi

say "2/6 kubeconfig"
if in_container; then
  # The default kubeconfig says https://127.0.0.1:<port>, which inside this
  # container is the container itself. Join the kind network and use the
  # internal endpoint (https://<cluster>-control-plane:6443) instead.
  docker network connect kind "$(hostname)" >/dev/null 2>&1 || true
  mkdir -p "$HOME/.kube"
  kind get kubeconfig --name "$CLUSTER_NAME" --internal > "$HOME/.kube/config"
  chmod 600 "$HOME/.kube/config"
else
  kind export kubeconfig --name "$CLUSTER_NAME"
fi
kubectl cluster-info --request-timeout=15s >/dev/null
say "API server reachable, context $(kubectl config current-context)"

# kind installs its CNI (kindnet) and a default StorageClass right after
# kubeadm. On this laptop that step has been seen to report success and leave
# nothing behind, which keeps every node NotReady. Re-apply from the node's
# own manifests when the DaemonSet is missing; harmless when it is there.
if ! kubectl -n kube-system get daemonset kindnet >/dev/null 2>&1; then
  warn "kindnet DaemonSet missing; re-applying kind's CNI and storage manifests"
  node="${CLUSTER_NAME}-control-plane"
  subnet="$(docker exec "$node" sh -c 'grep -A3 "^networking:" /kind/kubeadm.conf | grep podSubnet' | awk '{print $2}' | tr -d '"')"
  docker exec "$node" sh -c "sed 's#{{ *\.PodSubnet *}}#${subnet:-10.244.0.0/16}#g' /kind/manifests/default-cni.yaml | kubectl --kubeconfig=/etc/kubernetes/admin.conf apply -f -" >/dev/null
  docker exec "$node" kubectl --kubeconfig=/etc/kubernetes/admin.conf apply -f /kind/manifests/default-storage.yaml >/dev/null
fi
say "waiting for nodes to be Ready"
kubectl wait --for=condition=Ready nodes --all --timeout=5m >/dev/null

# helm_install <release> <chart> <namespace> <version> <values>: upgrade or
# install, after removing a release left in a failed or pending state by an
# earlier interrupted run (helm refuses to upgrade those).
helm_install() {
  local release="$1" chart="$2" ns="$3" version="$4" values="$5" status
  # .info.status is "deployed", "failed", "pending-install", ... (empty if absent).
  status="$(helm status "$release" -n "$ns" -o json 2>/dev/null | jq -r '.info.status // empty' 2>/dev/null || true)"
  if [ -n "$status" ] && [ "$status" != "deployed" ]; then
    warn "release $release is '$status' from an earlier run; uninstalling before reinstall"
    helm uninstall "$release" -n "$ns" --wait >/dev/null 2>&1 || true
  fi
  helm upgrade --install "$release" "$chart" \
    --namespace "$ns" --create-namespace \
    --version "$version" --values "$values" \
    --wait --timeout 10m
}

say "3/6 ingress-nginx (chart $INGRESS_NGINX_CHART_VERSION)"
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx --force-update >/dev/null
helm_install ingress-nginx ingress-nginx/ingress-nginx ingress-nginx \
  "$INGRESS_NGINX_CHART_VERSION" "$VALUES_DIR/ingress-nginx.yaml"

say "4/6 ArgoCD (chart $ARGOCD_CHART_VERSION)"
helm repo add argo https://argoproj.github.io/argo-helm --force-update >/dev/null
helm_install argocd argo/argo-cd argocd \
  "$ARGOCD_CHART_VERSION" "$VALUES_DIR/argocd.yaml"

say "5/6 secrets that stay out of git, then the ArgoCD project and root Application"
# Grafana admin password: generated once per cluster, read by the
# kube-prometheus-stack values through grafana.admin.existingSecret.
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f - >/dev/null
if ! kubectl -n observability get secret grafana-admin >/dev/null 2>&1; then
  pw="$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 20)"
  kubectl -n observability create secret generic grafana-admin \
    --from-literal=admin-user=admin --from-literal=admin-password="$pw" >/dev/null
  say "created secret observability/grafana-admin"
fi
# GitHub token for the platform API and apply worker, from .env (never git).
# Without it the API still runs; requests end "failed" with a clear reason.
kubectl create namespace platform --dry-run=client -o yaml | kubectl apply -f - >/dev/null
token="$(grep -E '^PLATFORM_GITHUB_TOKEN=' "$REPO_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)"
if [ -n "$token" ]; then
  kubectl -n platform create secret generic platform-github --from-literal=token="$token" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  say "secret platform/platform-github set from .env"
  # Env vars are read at container start; pick the token up if already running.
  kubectl -n platform rollout restart deployment/platform-api >/dev/null 2>&1 || true
else
  warn "PLATFORM_GITHUB_TOKEN not in .env; requests will fail until it is set (PLAN.md 8.4 step 5), then run make up again"
fi
# Pods must reach Ollama on the laptop at host.docker.internal. The kind
# nodes resolve it (Docker Desktop writes it into their /etc/hosts) but pods
# use CoreDNS, so teach CoreDNS the same address. Idempotent.
# IPv4 only: the pod network is IPv4 and getent lists the IPv6 address first.
gateway="$(docker exec "${CLUSTER_NAME}-control-plane" getent ahostsv4 host.docker.internal 2>/dev/null | awk '{print $1}' | head -1 || true)"
if [ -n "$gateway" ]; then
  corefile="$(kubectl -n kube-system get configmap coredns -o jsonpath='{.data.Corefile}')"
  if ! printf '%s' "$corefile" | grep -q "$gateway host.docker.internal"; then
    say "CoreDNS: host.docker.internal -> $gateway for pods"
    # drop any earlier hosts block, then add ours after the ready plugin
    stripped="$(printf '%s' "$corefile" | sed '/^\s*hosts {/,/^\s*}/d')"
    patched="$(printf '%s' "$stripped" | sed "s/^\(\s*\)ready$/\1ready\n\1hosts {\n\1   $gateway host.docker.internal\n\1   fallthrough\n\1}/")"
    kubectl -n kube-system create configmap coredns --from-literal=Corefile="$patched" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    kubectl -n kube-system rollout restart deployment/coredns >/dev/null
  fi
else
  warn "host.docker.internal not resolvable on the kind node; the agent cannot reach Ollama"
fi

# Grafana service account token for the agent's Grafana MCP server (read
# only: role Viewer). Created once through Grafana's API; never in git.
if ! kubectl -n platform get secret agent-grafana >/dev/null 2>&1; then
  gpw="$(kubectl -n observability get secret grafana-admin -o jsonpath='{.data.admin-password}' 2>/dev/null | base64 -d || true)"
  if [ -n "$gpw" ] && kubectl -n observability get svc kps-grafana >/dev/null 2>&1; then
    say "creating the Grafana service account token for the agent (Viewer)"
    kubectl -n observability port-forward svc/kps-grafana 13000:80 >/dev/null 2>&1 &
    gpf=$!; sleep 3
    sa_id="$(curl -s -u "admin:$gpw" -H 'Content-Type: application/json' -X POST http://localhost:13000/api/serviceaccounts -d '{"name":"agent-runtime","role":"Viewer"}' | sed -n 's/.*"id":\([0-9]*\).*/\1/p')"
    [ -z "$sa_id" ] && sa_id="$(curl -s -u "admin:$gpw" 'http://localhost:13000/api/serviceaccounts/search?query=agent-runtime' | sed -n 's/.*"id":\([0-9]*\).*/\1/p' | head -1)"
    gtoken="$(curl -s -u "admin:$gpw" -H 'Content-Type: application/json' -X POST "http://localhost:13000/api/serviceaccounts/$sa_id/tokens" -d "{\"name\":\"agent-$(date +%s)\"}" | sed -n 's/.*"key":"\([^"]*\)".*/\1/p')"
    kill $gpf 2>/dev/null || true
    if [ -n "$gtoken" ]; then
      kubectl -n platform create secret generic agent-grafana --from-literal=token="$gtoken" >/dev/null
      say "secret platform/agent-grafana created"
    else
      warn "could not create the Grafana token; the agent's Grafana tools will be unavailable (run make up again later)"
    fi
  fi
fi
kubectl apply -f "$ARGOCD_DIR/project.yaml" -f "$ARGOCD_DIR/root.yaml"

say "6/6 waiting up to $WAIT_TIMEOUT for all Applications to be Synced and Healthy"
to_seconds() {
  case "$1" in
    *h) echo $(( ${1%h} * 3600 )) ;;
    *m) echo $(( ${1%m} * 60 )) ;;
    *s) echo "${1%s}" ;;
    *)  echo "$1" ;;
  esac
}
if [ "$WAIT_TIMEOUT" != "0" ]; then
  deadline=$(( $(date +%s) + $(to_seconds "$WAIT_TIMEOUT") ))
  while :; do
    # name sync health, one per line; the root app lists the others once it syncs.
    rows="$(kubectl -n argocd get applications -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.sync.status}{" "}{.status.health.status}{"\n"}{end}' 2>/dev/null || true)"
    total=$(printf '%s' "$rows" | grep -c . || true)
    ok=$(printf '%s' "$rows" | grep -cE ' Synced Healthy$' || true)
    if [ "$total" -gt 1 ] && [ "$ok" -eq "$total" ]; then
      say "all $total Applications Synced and Healthy"
      break
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      warn "timed out; current state:"
      kubectl -n argocd get applications 2>/dev/null || true
      warn "if the root app cannot fetch the repo, push it to GitHub first (PLAN.md 8.4 step 3), then run make up again"
      exit 1
    fi
    printf '   %s/%s healthy, waiting...\n' "$ok" "$total"
    sleep 15
  done
fi

cat <<EOF

ArgoCD   http://argocd.localhost:8080    user admin, password:
         $(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo '(not yet created)')
Grafana  http://grafana.localhost:8080   user admin, password:
         $(kubectl -n observability get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d)
LocalStack  http://localhost:4566 on the host, ${LOCALSTACK_ENDPOINT:-http://host.docker.internal:4566} in the devcontainer

Next: make status
EOF
