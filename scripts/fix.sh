#!/usr/bin/env bash
# fix: restore the demo app Deployment in git to its known-good shape: the
# image tag the build workflow last published (or main) and 32Mi/64Mi
# memory. Sets the values directly rather than reverting a commit, so it
# works even when a tag bump landed on top of the break. Use it when you do
# not merge the agent's PR (the demo's happy path is merging that PR).
source "$(dirname "$0")/lib.sh"

need git kubectl awk sed
FILE="$REPO_ROOT/gitops/apps/demo-app/deployment.yaml"
TOKEN="$(grep -E '^PLATFORM_GITHUB_TOKEN=' "$REPO_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d '[:space:]' || true)"
[ -n "$TOKEN" ] || die "PLATFORM_GITHUB_TOKEN missing in .env"

cd "$REPO_ROOT"
git pull -q --rebase --autostash origin main

# Last tag the build workflow wrote (it bumps every chart on each build).
good_tag="$(git log -30 --format=%s -- gitops/charts/platform-api/values.yaml | grep -oE 'sha-[0-9a-f]{7}' | head -1)"
good_tag="${good_tag:-main}"

sed -i -E "s#(ghcr.io/[^/]+/devops-platform/demo-app:)does-not-exist#\1${good_tag}#" "$FILE"
# first memory line is the request (32Mi), second is the limit (64Mi)
awk 'BEGIN{n=0} /^              memory: 16Mi$/ { n++; sub(/16Mi/, (n==1 ? "32Mi" : "64Mi")) } { print }' "$FILE" > "$FILE.tmp" && mv "$FILE.tmp" "$FILE"

if git diff --quiet -- "$FILE"; then
  say "demo app Deployment is already healthy in git; nothing to fix"
  exit 0
fi
git diff -- "$FILE" | grep -E '^[-+] ' | grep -vE '^(---|\+\+\+)'
git add "$FILE"
git -c user.name="${GIT_USER_NAME:-$(git config user.name || whoami)}" \
    -c user.email="${GIT_USER_EMAIL:-$(git config user.email || echo "$(whoami)@users.noreply.github.com")}" \
    commit -q -m "[fix] demo-app: restore image tag ${good_tag} (make fix)"
git push -q "https://x-access-token:${TOKEN}@github.com/asaf-1/DevOps-Platform.git" HEAD:main
say "pushed $(git rev-parse --short HEAD)"
kubectl -n argocd patch application demo-app --type json -p '[{"op":"remove","path":"/operation"}]' >/dev/null 2>&1 || true
kubectl -n argocd annotate application demo-app argocd.argoproj.io/refresh=hard --overwrite >/dev/null 2>&1 || true
say "ArgoCD restores the demo app within ~2 minutes; the alert resolves after that"
