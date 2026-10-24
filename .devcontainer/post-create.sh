#!/usr/bin/env bash
# Runs once, inside the container, after it is created. Installs the npm
# tools (Node comes from a devcontainer feature, so npm is not available at
# image build time) and writes the AWS CLI profile that points at LocalStack.
set -euo pipefail

echo "==> npm global tools: promptfoo, Claude Code CLI"
npm install -g promptfoo@0.125.0 @anthropic-ai/claude-code@2.1.310

echo "==> AWS CLI profile 'localstack' (dummy credentials, endpoint on the host)"
# Scripts use AWS_PROFILE=localstack explicitly. Nothing here touches the
# default profile, so a real AWS profile can coexist for REAL_AWS=1 runs.
aws configure set aws_access_key_id test --profile localstack
aws configure set aws_secret_access_key test --profile localstack
aws configure set region us-east-1 --profile localstack
aws configure set endpoint_url "${LOCALSTACK_ENDPOINT:-http://host.docker.internal:4566}" --profile localstack

echo "==> Pulumi: file backend, no Pulumi Cloud account needed"
pulumi login --local >/dev/null

echo "==> versions"
for t in python node npm terraform pulumi kubectl helm kind conftest checkov infracost trivy promptfoo aws docker; do
  printf '%-10s %s\n' "$t" "$("$t" --version 2>/dev/null | head -1 || echo missing)"
done
printf '%-10s %s\n' argocd "$(argocd version --client --short 2>/dev/null || echo missing)"
