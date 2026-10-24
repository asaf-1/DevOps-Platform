# Agent runtime image: the Python runtime plus the three MCP servers it
# starts as subprocesses (Kubernetes via npm, GitHub and Grafana as Go
# binaries) and kubectl, which the Kubernetes MCP server shells out to.
FROM python:3.12-slim

ARG NODE_MAJOR=22
ARG KUBECTL_VERSION=1.36.1
ARG GITHUB_MCP_VERSION=2.0.3
ARG GRAFANA_MCP_VERSION=2.1.1
ARG K8S_MCP_VERSION=4.1.9
ARG TARGETARCH=amd64

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg git \
    && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH}" in amd64) GOARCH=x86_64 ;; arm64) GOARCH=arm64 ;; *) exit 1 ;; esac; \
    curl -fsSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && chmod 0755 /usr/local/bin/kubectl; \
    curl -fsSL "https://github.com/github/github-mcp-server/releases/download/v${GITHUB_MCP_VERSION}/github-mcp-server_Linux_${GOARCH}.tar.gz" \
      | tar -xz -C /usr/local/bin github-mcp-server; \
    curl -fsSL "https://github.com/grafana/mcp-grafana/releases/download/v${GRAFANA_MCP_VERSION}/mcp-grafana_Linux_${GOARCH}.tar.gz" \
      | tar -xz -C /usr/local/bin mcp-grafana; \
    npm install -g "mcp-server-kubernetes@${K8S_MCP_VERSION}"; \
    kubectl version --client; github-mcp-server --version || true; mcp-grafana --version || true

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --uid 10001 --create-home agent
WORKDIR /app

COPY agents/pyproject.toml /app/
COPY agents/runtime /app/runtime
COPY agents/tools /app/tools
COPY agents/incident_triage /app/incident_triage
COPY docs/runbooks /app/runbooks
RUN pip install .

USER 10001
ENV AGENTS_DIR=/app RUNBOOKS_DIR=/app/runbooks
EXPOSE 8080
CMD ["uvicorn", "runtime.server:app", "--host", "0.0.0.0", "--port", "8080"]
