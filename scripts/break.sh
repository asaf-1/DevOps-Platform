#!/usr/bin/env bash
# break: damage an app in git, not live, so ArgoCD rolls the damage out and
# a real alert fires. BREAK_TARGET=demo (default): the demo app's image tag
# becomes nonexistent. BREAK_TARGET=bank: Playground Bank's HOST setting
# becomes an invalid address, so the app logs a real startup error and its
# health check fails. Both are one-line typos in git.
# Pushes one commit to main (tagged "[break]" so fix.sh can revert it) using
# the platform token from .env. ArgoCD syncs within ~3 minutes; the script
# nudges it.
source "$(dirname "$0")/lib.sh"

need git kubectl sed
TARGET="${BREAK_TARGET:-demo}"
case "$TARGET" in
  demo) FILE="$REPO_ROOT/gitops/apps/demo-app/deployment.yaml"; APP=demo-app ;;
  bank) FILE="$REPO_ROOT/gitops/apps/playground-bank/kustomization.yaml"; APP=playground-bank ;;
  *) die "BREAK_TARGET must be demo or bank" ;;
esac
TOKEN="$(grep -E '^PLATFORM_GITHUB_TOKEN=' "$REPO_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d '[:space:]' || true)"
[ -n "$TOKEN" ] || die "PLATFORM_GITHUB_TOKEN missing in .env (needed to push the break commit)"

cd "$REPO_ROOT"
[ -z "$(git status --porcelain -- "$FILE")" ] || die "$FILE has uncommitted changes; commit or stash first"
if git log -1 --format=%s -- "$FILE" | grep -q '^\[break\]'; then
  die "$APP is already broken (last commit on $FILE is a [break]); run make fix first"
fi

git pull -q --rebase --autostash origin main
if [ "$TARGET" = demo ]; then
  say "breaking $FILE: image tag -> does-not-exist"
  sed -i -E 's#(ghcr.io/[^/]+/devops-platform/demo-app:)[^"'"'"' ]+#\1does-not-exist#' "$FILE"
  MSG="[break] demo-app: nonexistent image tag (make break)"
else
  say "breaking $FILE: HOST -> 0.0.0.0.1 (the app cannot bind it)"
  sed -i -E 's#^(      - HOST=)0\.0\.0\.0$#\10.0.0.0.1#' "$FILE"
  MSG="[break] playground-bank: invalid HOST setting (make break BREAK_TARGET=bank)"
fi
git diff --stat -- "$FILE"
git diff -- "$FILE" | grep -E '^[-+] ' | grep -vE '^(---|\+\+\+)'

git add "$FILE"
# Identity: the container may have none; fall back to the OS user.
git -c user.name="${GIT_USER_NAME:-$(git config user.name || whoami)}" \
    -c user.email="${GIT_USER_EMAIL:-$(git config user.email || echo "$(whoami)@users.noreply.github.com")}" \
    commit -q -m "$MSG"
say "pushing to main"
git push -q "https://x-access-token:${TOKEN}@github.com/asaf-1/DevOps-Platform.git" HEAD:main
say "pushed $(git rev-parse --short HEAD)"

say "asking ArgoCD to sync $APP now"
# A sync that is still retrying an older failure would delay this one.
kubectl -n argocd patch application "$APP" --type json -p '[{"op":"remove","path":"/operation"}]' >/dev/null 2>&1 || true
kubectl -n argocd annotate application "$APP" argocd.argoproj.io/refresh=hard --overwrite >/dev/null 2>&1 || true
cat <<EOF

Within ~2 minutes: the new pod fails (ImagePullBackOff for the demo app, a startup error in the logs for the bank), the alert fires,
Alertmanager calls the agent runtime, and a PR from a branch agent/incident-<fingerprint> opens.
Watch:  make status          kubectl -n demo get pods -w
        platform agent runs   (or: kubectl -n platform port-forward svc/agent-runtime 8081:8080; curl localhost:8081/runs)
Undo:   make fix
EOF
