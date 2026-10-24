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

need kind kubectl helm docker

say "1/6 kind cluster '$CLUSTER_NAME'"
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  say "cluster exists, reusing it"
else
  if in_container; then
    # kind creates the 'kind' docker network on first use. Create it up front
    # so this container can join it (step 2) and reach the API server.
    docker network inspect kind >/dev/null 2>&1 || docker network create kind >/dev/null
  fi
  kind create cluster --name "$CLUSTER_NAME" --config "$KIND_CONFIG" --wait 120s
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

say "3/6 ingress-nginx (chart $INGRESS_NGINX_CHART_VERSION)"
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx --force-update >/dev/null
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --version "$INGRESS_NGINX_CHART_VERSION" \
  --values "$VALUES_DIR/ingress-nginx.yaml" \
  --wait --timeout 5m

say "4/6 ArgoCD (chart $ARGOCD_CHART_VERSION)"
helm repo add argo https://argoproj.github.io/argo-helm --force-update >/dev/null
helm upgrade --install argocd argo/argo-cd \
  --namespace argocd --create-namespace \
  --version "$ARGOCD_CHART_VERSION" \
  --values "$VALUES_DIR/argocd.yaml" \
  --wait --timeout 10m

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
