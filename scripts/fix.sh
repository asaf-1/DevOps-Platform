#!/usr/bin/env bash
# fix: revert the last [break] commit on the demo app and push, so ArgoCD
# restores the healthy Deployment. Use this when you do not merge the
# agent's PR (the demo's happy path is merging that PR instead).
source "$(dirname "$0")/lib.sh"

need git kubectl
FILE="$REPO_ROOT/gitops/apps/demo-app/deployment.yaml"
TOKEN="$(grep -E '^PLATFORM_GITHUB_TOKEN=' "$REPO_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d '[:space:]' || true)"
[ -n "$TOKEN" ] || die "PLATFORM_GITHUB_TOKEN missing in .env"

cd "$REPO_ROOT"
git pull -q --rebase --autostash origin main
sha="$(git log -1 --format=%H --grep='^\[break\]' -- "$FILE")"
[ -n "$sha" ] || die "no [break] commit found on $FILE; nothing to fix"
if git log --format=%s "$sha"..HEAD -- "$FILE" | grep -qE 'agent|revert'; then
  say "a later commit already changed $FILE (agent PR merged?); showing it instead of reverting"
  git log --oneline "$sha"..HEAD -- "$FILE"
  exit 0
fi

say "reverting $(git log -1 --format='%h %s' "$sha")"
git -c user.name="${GIT_USER_NAME:-$(git config user.name || whoami)}" \
    -c user.email="${GIT_USER_EMAIL:-$(git config user.email || echo "$(whoami)@users.noreply.github.com")}" \
    revert --no-edit "$sha" >/dev/null
git push -q "https://x-access-token:${TOKEN}@github.com/asaf-1/DevOps-Platform.git" HEAD:main
say "pushed $(git rev-parse --short HEAD)"
kubectl -n argocd annotate application demo-app argocd.argoproj.io/refresh=normal --overwrite >/dev/null 2>&1 || true
say "ArgoCD will restore the demo app within ~2 minutes; the alert resolves after that"
