#!/usr/bin/env bash
# break: damage the demo app in git, not live, so ArgoCD rolls the damage out
# and a real alert fires: a nonexistent image tag and a 16Mi memory limit.
# Pushes one commit to main (tagged "[break]" so fix.sh can revert it) using
# the platform token from .env. ArgoCD syncs within ~3 minutes; the script
# nudges it.
source "$(dirname "$0")/lib.sh"

need git kubectl sed
FILE="$REPO_ROOT/gitops/apps/demo-app/deployment.yaml"
TOKEN="$(grep -E '^PLATFORM_GITHUB_TOKEN=' "$REPO_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d '[:space:]' || true)"
[ -n "$TOKEN" ] || die "PLATFORM_GITHUB_TOKEN missing in .env (needed to push the break commit)"

cd "$REPO_ROOT"
[ -z "$(git status --porcelain -- "$FILE")" ] || die "$FILE has uncommitted changes; commit or stash first"
if git log -1 --format=%s -- "$FILE" | grep -q '^\[break\]'; then
  die "the demo app is already broken (last commit on $FILE is a [break]); run make fix first"
fi

git pull -q --rebase --autostash origin main
say "breaking $FILE: image tag -> does-not-exist, memory limit -> 16Mi"
sed -i -E 's#(ghcr.io/[^/]+/devops-platform/demo-app:)[^"'"'"' ]+#\1does-not-exist#' "$FILE"
# Both request and limit: a request above the limit is rejected by the API
# server, and then nothing would roll out at all.
sed -i -E 's#^(              memory: )64Mi$#\116Mi#' "$FILE"
sed -i -E 's#^(              memory: )32Mi$#\116Mi#' "$FILE"
git diff --stat -- "$FILE"
git diff -- "$FILE" | grep -E '^[-+] ' | grep -vE '^(---|\+\+\+)'

git add "$FILE"
# Identity: the container may have none; fall back to the OS user.
git -c user.name="${GIT_USER_NAME:-$(git config user.name || whoami)}" \
    -c user.email="${GIT_USER_EMAIL:-$(git config user.email || echo "$(whoami)@users.noreply.github.com")}" \
    commit -q -m "[break] demo-app: nonexistent image tag and 16Mi memory limit (make break)"
say "pushing to main"
git push -q "https://x-access-token:${TOKEN}@github.com/asaf-1/DevOps-Platform.git" HEAD:main
say "pushed $(git rev-parse --short HEAD)"

say "asking ArgoCD to sync demo-app now"
kubectl -n argocd annotate application demo-app argocd.argoproj.io/refresh=normal --overwrite >/dev/null 2>&1 || true
cat <<EOF

Within ~2 minutes: the new pod fails (ImagePullBackOff), the alert fires,
Alertmanager calls the agent runtime, and a PR labelled agent-proposal opens.
Watch:  make status          kubectl -n demo get pods -w
        platform agent runs   (or: kubectl -n platform port-forward svc/agent-runtime 8081:8080; curl localhost:8081/runs)
Undo:   make fix
EOF
