# Thin wrappers over scripts/. Run inside the devcontainer (bash). Every
# target prints what it is about to do before doing it.
SHELL := bash
.DEFAULT_GOAL := help

.PHONY: help up down status request apply-local break fix evals lint

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{ printf "  %-12s %s\n", $$1, $$2 }'

up: ## Create the kind cluster and install ArgoCD, which syncs everything else
	@echo "==> make up: create kind cluster 'platform' if missing, install ingress-nginx and ArgoCD, apply the root Application, wait for sync"
	@bash scripts/up.sh

down: ## Delete the kind cluster
	@echo "==> make down: delete kind cluster 'platform'"
	@bash scripts/down.sh

status: ## Show cluster, ArgoCD application and pod health
	@echo "==> make status: cluster nodes, ArgoCD applications, pods not Running"
	@bash scripts/status.sh

request: ## Open a resource request through the platform CLI (Phase 1)
	@echo "==> make request: create a ResourceRequest via the CLI and open its PR"
	@bash scripts/request.sh

apply-local: ## Apply an approved request against LocalStack (Phase 1)
	@echo "==> make apply-local: run the apply worker once against LocalStack"
	@bash scripts/apply-local.sh

break: ## Break the demo app (or BREAK_TARGET=bank) in git so a real alert fires (Phase 2)
	@echo "==> make break: commit a bad image tag and a tiny memory limit for the demo app, push, let ArgoCD roll it out"
	@bash scripts/break.sh

fix: ## Revert the break commit (Phase 2)
	@echo "==> make fix: revert the break commit and push"
	@bash scripts/fix.sh

evals: ## Run the agent eval suite with Promptfoo over recorded scenarios (Phase 3)
	@echo "==> make evals: run promptfoo over agents/evals"
	@bash scripts/evals.sh

github-settings: ## Plan (APPLY=1: apply) the repository's own GitHub settings as Terraform (Phase 4)
	@echo "==> make github-settings: terraform plan/apply of infra/terraform/github against GitHub"
	@bash scripts/github-settings.sh

lint: ## Everything that must be green before a push
	@echo "==> make lint: ruff + pytest (api, cli), terraform fmt -check + validate, conftest verify, bash -n"
	@bash scripts/lint.sh
