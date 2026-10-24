#!/usr/bin/env bash
# request: open a resource request through the platform CLI against the API
# running in the cluster. Port-forwards the API Service for the duration.
#
#   make request                                   # s3-bucket demo-uploads for team web
#   REQUEST_TYPE=dynamodb-table REQUEST_NAME=orders REQUEST_EXTRA="-i hash_key=order_id" make request
source "$(dirname "$0")/lib.sh"

need kubectl
PLATFORM="$REPO_ROOT/platform/api/.venv/bin/platform"
[ -x "$PLATFORM" ] || die "CLI not installed; see platform/api/README.md (pip install -e platform/cli)"

TYPE="${REQUEST_TYPE:-s3-bucket}"
NAME="${REQUEST_NAME:-demo-uploads}"
TEAM="${REQUEST_TEAM:-web}"
COST_CENTER="${REQUEST_COST_CENTER:-cc-100}"
PORT="${REQUEST_PORT:-18000}"
# Who asks: PLATFORM_USER, else the git identity, else the OS user.
REQUESTED_BY="${PLATFORM_USER:-$(git -C "$REPO_ROOT" config user.name 2>/dev/null || whoami)}"

say "port-forward platform/svc/platform-api -> localhost:$PORT"
kubectl -n platform port-forward svc/platform-api "$PORT:80" >/dev/null 2>&1 &
pf=$!
trap 'kill $pf 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  curl -sf "http://localhost:$PORT/healthz" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "http://localhost:$PORT/healthz" >/dev/null || die "platform API not reachable through the port-forward"

say "platform request $TYPE --name $NAME --team $TEAM --cost-center $COST_CENTER --as $REQUESTED_BY ${REQUEST_EXTRA:-}"
# shellcheck disable=SC2086
PLATFORM_API_URL="http://localhost:$PORT" "$PLATFORM" request "$TYPE" \
  --name "$NAME" --team "$TEAM" --cost-center "$COST_CENTER" --as "$REQUESTED_BY" ${REQUEST_EXTRA:-}
