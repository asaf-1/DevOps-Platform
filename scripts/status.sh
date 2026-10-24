#!/usr/bin/env bash
# status: nodes, ArgoCD Applications, and any pod that is not Running or
# Completed. Read-only.
source "$(dirname "$0")/lib.sh"

need kind kubectl

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  die "no kind cluster named '$CLUSTER_NAME'; run make up"
fi

say "nodes"
kubectl get nodes -o wide

say "ArgoCD Applications"
# Multi-source Applications report revisions[], single-source ones revision;
# the ArgoCD UI shows both, so the table keeps to sync and health.
kubectl -n argocd get applications -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status' 2>/dev/null \
  || warn "ArgoCD not installed yet"

say "pods not Running or Succeeded"
not_ready="$(kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers 2>/dev/null || true)"
if [ -n "$not_ready" ]; then
  printf '%s\n' "$not_ready"
else
  say "none"
fi
