# Linux toolchain for the repo. Everything the Makefile and scripts/ need
# that is not provided by a devcontainer feature (see devcontainer.json for
# Node, Docker, kubectl, Helm, Terraform and the AWS CLI).
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ARG PULUMI_VERSION=3.272.0
ARG CONFTEST_VERSION=0.71.1
ARG INFRACOST_VERSION=0.10.47
ARG ARGOCD_VERSION=3.5.6
ARG TRIVY_VERSION=0.76.1
ARG KIND_VERSION=0.33.0
ARG CHECKOV_VERSION=3.3.30

# Set by BuildKit; defaults to amd64 for the classic builder.
ARG TARGETARCH=amd64

# The base image ships a Yarn apt source whose signing key is no longer
# available, which makes apt-get update fail. Yarn is not needed here.
RUN rm -f /etc/apt/sources.list.d/yarn* \
    && apt-get update \
    && apt-get install -y --no-install-recommends make jq unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) PULUMI_ARCH=x64;   CONFTEST_ARCH=x86_64; TRIVY_ARCH=64bit;  GO_ARCH=amd64 ;; \
      arm64) PULUMI_ARCH=arm64; CONFTEST_ARCH=arm64;  TRIVY_ARCH=ARM64;  GO_ARCH=arm64 ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    tmp="$(mktemp -d)"; cd "$tmp"; \
    # Pulumi
    curl -fsSL "https://get.pulumi.com/releases/sdk/pulumi-v${PULUMI_VERSION}-linux-${PULUMI_ARCH}.tar.gz" | tar -xz; \
    install -m 0755 pulumi/* /usr/local/bin/; \
    # Conftest (OPA policies on Terraform plans)
    curl -fsSL "https://github.com/open-policy-agent/conftest/releases/download/v${CONFTEST_VERSION}/conftest_${CONFTEST_VERSION}_Linux_${CONFTEST_ARCH}.tar.gz" | tar -xz conftest; \
    install -m 0755 conftest /usr/local/bin/conftest; \
    # Infracost
    curl -fsSL "https://github.com/infracost/infracost/releases/download/v${INFRACOST_VERSION}/infracost-linux-${GO_ARCH}.tar.gz" | tar -xz; \
    install -m 0755 "infracost-linux-${GO_ARCH}" /usr/local/bin/infracost; \
    # ArgoCD CLI
    curl -fsSL -o argocd "https://github.com/argoproj/argo-cd/releases/download/v${ARGOCD_VERSION}/argocd-linux-${GO_ARCH}"; \
    install -m 0755 argocd /usr/local/bin/argocd; \
    # Trivy
    curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-${TRIVY_ARCH}.tar.gz" | tar -xz trivy; \
    install -m 0755 trivy /usr/local/bin/trivy; \
    # kind (talks to the host Docker daemon through docker-outside-of-docker)
    curl -fsSL -o kind "https://kind.sigs.k8s.io/dl/v${KIND_VERSION}/kind-linux-${GO_ARCH}"; \
    install -m 0755 kind /usr/local/bin/kind; \
    cd /; rm -rf "$tmp"; \
    pulumi version; conftest --version; infracost --version; argocd version --client --short; trivy --version; kind version

# Checkov (static IaC security). Pinned; installed into the image's Python.
RUN pip install --no-cache-dir "checkov==${CHECKOV_VERSION}" && checkov --version
