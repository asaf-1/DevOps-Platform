#!/usr/bin/env bash
# apply-local: run one pass of the apply worker inside the cluster. The
# worker already loops every 30 seconds; this is for impatience and demos.
# Nothing is applied from this machine: the pod has the state, the
# credentials and LocalStack.
source "$(dirname "$0")/lib.sh"

need kubectl

say "one worker pass in platform/deploy/platform-api (container worker)"
kubectl -n platform exec deploy/platform-api -c worker -- python -m platform_api.worker --once
