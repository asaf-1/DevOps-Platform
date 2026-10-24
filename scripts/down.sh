#!/usr/bin/env bash
# down: delete the kind cluster. Everything in it is recreated by make up
# from git, so nothing is lost except the generated passwords.
source "$(dirname "$0")/lib.sh"

need kind

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  say "deleting kind cluster '$CLUSTER_NAME'"
  kind delete cluster --name "$CLUSTER_NAME"
else
  say "no kind cluster named '$CLUSTER_NAME'; nothing to do"
fi
