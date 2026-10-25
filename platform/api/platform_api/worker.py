"""The apply worker: the only thing that ever runs `terraform apply`.

Every 30 seconds it looks at requests that are waiting on GitHub and moves
them along:

  pr-opened  --(iac-pr run succeeded)-->        audit events plan-ok, policy-ok
  pr-opened  --(PR merged, iac-approve ok)-->    approved
  approved   --(terraform apply, outputs)-->     applied
  applied    --(outputs committed to gitops)-->  deployed
  anything   --(error)-->                        failed

It runs inside the cluster, next to the API, so cloud credentials and the
Terraform state (Postgres) never leave the cluster. GitHub, Terraform and
the repo download are injectable so the state machine is unit-tested
without any of them.

    python -m platform_api.worker          # loop
    python -m platform_api.worker --once   # one pass (make apply-local)
"""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
import tarfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
import yaml

from .catalog import Catalog
from .github import GitHubClient, GitHubError
from .models import RequestState, ResourceRequest
from .settings import Settings
from .storage import Store, make_engine

log = logging.getLogger("platform.worker")

PR_LABEL = "platform-request"
PR_WORKFLOW = "iac-pr.yml"
APPROVE_WORKFLOW = "iac-approve.yml"
DEMO_CONFIGMAP_PATH = "gitops/apps/demo-app/configmap.yaml"
ACTOR = "apply-worker"


class WorkerGitHub(Protocol):
    def get_pull_request(self, number: int) -> dict[str, Any]: ...

    def merge_pull_request(self, number: int, title: str, method: str = "squash") -> str: ...

    def workflow_run_conclusion(self, workflow_file: str, head_sha: str) -> str | None: ...

    def get_file(self, path: str, ref: str) -> tuple[str, str]: ...

    def put_file(
        self, path: str, content: str, message: str, branch: str, sha: str | None
    ) -> str: ...


@dataclass
class TerraformResult:
    ok: bool
    outputs: dict[str, Any] = field(default_factory=dict)
    log: str = ""


# Callables the worker is built from, so tests can replace them.
FetchRepo = Callable[[str], Path]  # commit sha -> directory with the repo at that commit
RunApply = Callable[[Path, str, str], TerraformResult]  # repo dir, environment, request id


@dataclass
class WorkerConfig:
    interval_seconds: int = 30
    workdir: Path = Path("/work")
    terraform_bin: str = "terraform"
    pg_conn_str: str | None = None
    localstack_endpoint: str = "http://localstack.localstack.svc.cluster.local:4566"
    base_branch: str = "main"

    @classmethod
    def from_env(cls) -> WorkerConfig:
        env = os.environ
        return cls(
            interval_seconds=int(env.get("WORKER_INTERVAL", "30")),
            workdir=Path(env.get("WORKER_WORKDIR", "/work")),
            terraform_bin=env.get("TERRAFORM_BIN", "terraform"),
            pg_conn_str=env.get("PG_CONN_STR") or None,
            localstack_endpoint=env.get("TF_VAR_localstack_endpoint", cls.localstack_endpoint),
            base_branch=env.get("GITHUB_BASE_BRANCH", "main"),
        )


class Worker:
    def __init__(
        self,
        store: Store,
        github: WorkerGitHub,
        fetch_repo: FetchRepo,
        run_apply: RunApply,
        *,
        base_branch: str = "main",
        auto_merge_types: set[str] | None = None,
    ) -> None:
        self.store = store
        self.github = github
        self.fetch_repo = fetch_repo
        self.run_apply = run_apply
        self.base_branch = base_branch
        # Catalog types whose PRs the platform merges itself once CI is green.
        self.auto_merge_types = auto_merge_types or set()

    # one pass

    def run_once(self) -> list[str]:
        """Process every open request once. Returns the ids that changed state."""
        changed: list[str] = []
        for req in self.store.list_requests(state=RequestState.PR_OPENED, limit=200):
            if self._check_pull_request(req):
                changed.append(req.id)
        for req in self.store.list_requests(state=RequestState.PLANNED, limit=200):
            if self._check_pull_request(req):
                changed.append(req.id)
        for req in self.store.list_requests(state=RequestState.APPROVED, limit=50):
            self._apply(req)
            changed.append(req.id)
        for req in self.store.list_requests(state=RequestState.APPLIED, limit=50):
            self._publish_outputs(req)
            changed.append(req.id)
        return list(dict.fromkeys(changed))  # unique, in order

    def run_forever(self, interval_seconds: int) -> None:
        log.info("apply worker started, interval %ss", interval_seconds)
        while True:
            try:
                changed = self.run_once()
                if changed:
                    log.info("changed: %s", ", ".join(changed))
            except Exception:  # keep the loop alive; the next pass retries
                log.exception("worker pass failed")
            time.sleep(interval_seconds)

    # pr-opened / planned -> approved

    def _check_pull_request(self, req: ResourceRequest) -> bool:
        if req.pr_number is None:
            return False
        try:
            pr = self.github.get_pull_request(req.pr_number)
        except GitHubError as e:
            log.warning("%s: cannot read PR #%s: %s", req.id, req.pr_number, e)
            return False

        changed = False
        head_sha = pr.get("head", {}).get("sha")
        if req.state == RequestState.PR_OPENED and head_sha:
            if self.github.workflow_run_conclusion(PR_WORKFLOW, head_sha) == "success":
                changed = True
                self.store.add_event(
                    "plan-ok",
                    actor="github-actions/iac-pr",
                    request_id=req.id,
                    details={"head_sha": head_sha},
                )
                self.store.add_event(
                    "policy-ok",
                    actor="github-actions/iac-pr",
                    request_id=req.id,
                    details={"head_sha": head_sha},
                )
                self.store.transition(
                    req.id, RequestState.PLANNED, actor=ACTOR, details={"head_sha": head_sha}
                )
                req = self.store.get_request(req.id) or req

        # CI is green and the PR is still open: merge it if the type allows.
        if (
            req.state == RequestState.PLANNED
            and pr.get("state") == "open"
            and not pr.get("merged_at")
            and req.type in self.auto_merge_types
        ):
            title = f"[{req.type}] {req.inputs.get('name', req.id)} (request {req.id})"
            try:
                merge_sha = self.github.merge_pull_request(req.pr_number, title)
            except GitHubError as e:
                log.warning("%s: auto-merge of PR #%s refused: %s", req.id, req.pr_number, e)
            else:
                self.store.add_event(
                    "merged",
                    actor="platform-auto-merge",
                    approval_ref=merge_sha,
                    request_id=req.id,
                    details={"pr_number": req.pr_number, "merge_commit_sha": merge_sha},
                )
                changed = True
                pr = self.github.get_pull_request(req.pr_number)

        if pr.get("state") == "closed" and not pr.get("merged_at"):
            self.store.transition(
                req.id,
                RequestState.FAILED,
                actor=ACTOR,
                details={"reason": "pull request closed without merging"},
                error="pull request closed without merging",
            )
            return True

        if not pr.get("merged_at"):
            return changed
        merge_sha = pr.get("merge_commit_sha")
        if not merge_sha:
            return changed
        conclusion = self.github.workflow_run_conclusion(APPROVE_WORKFLOW, merge_sha)
        if conclusion == "success":
            self.store.transition(
                req.id,
                RequestState.APPROVED,
                actor="github/iac-approve",
                actor_type="human",
                approval_ref=merge_sha,
                details={
                    "merge_commit_sha": merge_sha,
                    "merged_by": (pr.get("merged_by") or {}).get("login"),
                },
            )
            return True
        if conclusion in ("failure", "cancelled", "timed_out"):
            self.store.transition(
                req.id,
                RequestState.FAILED,
                actor=ACTOR,
                details={"reason": f"iac-approve run {conclusion}", "merge_commit_sha": merge_sha},
                error=f"approval workflow {conclusion}",
            )
            return True
        return changed  # not approved yet

    def retry(self, request_id: str, *, actor: str = "operator") -> ResourceRequest:
        """Put a failed request back to approved so the next pass applies it again.

        Only for requests that were approved once: the human decision stands,
        the machinery is what is retried.
        """
        req = self.store.get_request(request_id)
        if req is None:
            raise KeyError(request_id)
        if req.state != RequestState.FAILED:
            raise ValueError(f"{request_id} is {req.state}, not failed")
        merge_sha = self._merge_sha(request_id)
        if not merge_sha:
            raise ValueError(f"{request_id} was never approved; open a new request instead")
        return self.store.transition(
            request_id,
            RequestState.APPROVED,
            actor=actor,
            actor_type="human",
            details={
                "reason": "manual retry after failure",
                "previous_error": req.error,
                "merge_commit_sha": merge_sha,
            },
            error=None,
        )

    def _merge_sha(self, request_id: str) -> str | None:
        """The merge commit from the latest approved event that recorded one."""
        for e in reversed(self.store.list_events(request_id)):
            if e.event == "approved" and e.details.get("merge_commit_sha"):
                return str(e.details["merge_commit_sha"])
        return None

    # approved -> applied

    def _apply(self, req: ResourceRequest) -> None:
        merge_sha = self._merge_sha(req.id)
        if not merge_sha:
            self.store.transition(
                req.id,
                RequestState.FAILED,
                actor=ACTOR,
                details={"reason": "no merge commit recorded"},
                error="no merge commit recorded",
            )
            return
        reason = "terraform apply failed"
        try:
            try:
                repo_dir = self.fetch_repo(merge_sha)
            except Exception as e:
                reason = "repo download failed"
                raise RuntimeError(f"{merge_sha}: {e}") from e
            result = self.run_apply(repo_dir, req.environment, req.id)
        except Exception as e:  # download or subprocess failure
            result = TerraformResult(ok=False, log=str(e))
        if not result.ok:
            self.store.transition(
                req.id,
                RequestState.FAILED,
                actor=ACTOR,
                details={"reason": reason, "log_tail": result.log[-2000:]},
                error=reason,
            )
            return
        self.store.transition(
            req.id,
            RequestState.APPLIED,
            actor=ACTOR,
            details={"outputs": result.outputs, "merge_commit_sha": merge_sha},
            outputs=result.outputs,
        )

    # applied -> deployed

    def _publish_outputs(self, req: ResourceRequest) -> None:
        """Write the request's outputs into the demo app ConfigMap on the base branch."""
        outputs = req.outputs or {}
        try:
            current, sha = self.github.get_file(DEMO_CONFIGMAP_PATH, self.base_branch)
        except GitHubError as e:
            self.store.transition(
                req.id,
                RequestState.FAILED,
                actor=ACTOR,
                details={"reason": f"cannot read {DEMO_CONFIGMAP_PATH}: {e}"},
                error="cannot read demo app ConfigMap",
            )
            return
        updated = merge_outputs_into_configmap(current, req, outputs)
        label = (
            outputs.get("bucket_name")
            or outputs.get("table_name")
            or outputs.get("namespace")
            or req.id
        )
        if updated == current:
            commit = None
        else:
            try:
                commit = self.github.put_file(
                    DEMO_CONFIGMAP_PATH,
                    updated,
                    f"{req.type} {label}: outputs of request {req.id}",
                    self.base_branch,
                    sha,
                )
            except GitHubError as e:
                self.store.transition(
                    req.id,
                    RequestState.FAILED,
                    actor=ACTOR,
                    details={"reason": f"cannot commit outputs: {e}"},
                    error="cannot commit outputs to gitops",
                )
                return
        self.store.transition(
            req.id,
            RequestState.DEPLOYED,
            actor=ACTOR,
            details={
                "path": DEMO_CONFIGMAP_PATH,
                "commit": commit,
                "note": "ArgoCD rolls the ConfigMap out from main",
            },
        )


def merge_outputs_into_configmap(text: str, req: ResourceRequest, outputs: dict[str, Any]) -> str:
    """Return the ConfigMap YAML with this request's outputs merged into .data."""
    doc = yaml.safe_load(text) or {}
    data = doc.setdefault("data", {}) or {}
    for key, value in outputs.items():
        data[f"{req.id}.{key}"] = str(value)
    if req.type == "s3-bucket" and "bucket_name" in outputs:
        data["BUCKET_NAME"] = str(outputs["bucket_name"])
        data["BUCKET_ARN"] = str(outputs.get("bucket_arn", ""))
        data["BUCKET_REQUEST_ID"] = req.id
    doc["data"] = dict(sorted(data.items()))
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)


# production implementations


def tarball_url(base_url: Any, sha: str) -> str:
    """httpx normalises base_url with a trailing slash; do not double it."""
    return f"{str(base_url).rstrip('/')}/tarball/{sha}"


def github_fetch_repo(github: GitHubClient, workdir: Path) -> FetchRepo:
    """Download the repo tarball at a commit into workdir/<sha>; no git needed in the image."""

    def fetch(sha: str) -> Path:
        target = workdir / sha
        if (target / "infra").is_dir():
            return target
        workdir.mkdir(parents=True, exist_ok=True)
        url = tarball_url(github._client.base_url, sha)
        with httpx.Client(
            headers=dict(github._client.headers), follow_redirects=True, timeout=120
        ) as c:
            resp = c.get(url)
            resp.raise_for_status()
        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
            members = tar.getmembers()
            prefix = members[0].name.split("/")[0] if members else ""
            tar.extractall(workdir, filter="data")
        (workdir / prefix).rename(target)
        return target

    return fetch


def terraform_apply(cfg: WorkerConfig) -> RunApply:
    """Real `terraform init && apply` in envs/<environment> of a repo checkout."""

    def run(repo_dir: Path, environment: str, request_id: str) -> TerraformResult:
        env_dir = repo_dir / "infra" / "terraform" / "envs" / environment
        env = {
            **os.environ,
            "TF_IN_AUTOMATION": "true",
            "TF_INPUT": "0",
            "TF_VAR_localstack_endpoint": cfg.localstack_endpoint,
        }
        if cfg.pg_conn_str:
            env["PG_CONN_STR"] = cfg.pg_conn_str
        log_text = ""

        def tf(*args: str) -> subprocess.CompletedProcess[str]:
            nonlocal log_text
            proc = subprocess.run(
                [cfg.terraform_bin, *args], cwd=env_dir, env=env, capture_output=True, text=True
            )
            log_text += f"$ terraform {' '.join(args)}\n{proc.stdout}{proc.stderr}\n"
            return proc

        init_args = ["init", "-input=false", "-no-color"]
        if not cfg.pg_conn_str:
            (env_dir / "backend_override.tf").write_text(
                'terraform {\n  backend "local" {\n    path = ".terraform/worker.tfstate"\n  }\n}\n'
            )
        if tf(*init_args).returncode != 0:
            return TerraformResult(ok=False, log=log_text)
        if tf("apply", "-auto-approve", "-input=false", "-no-color").returncode != 0:
            return TerraformResult(ok=False, log=log_text)
        out = tf("output", "-json", "-no-color")
        if out.returncode != 0:
            return TerraformResult(ok=False, log=log_text)
        all_outputs = json.loads(out.stdout or "{}")
        requests_out = (all_outputs.get("requests") or {}).get("value") or {}
        mine = requests_out.get(request_id)
        if mine is None:
            log_text += f"no output named {request_id} in `requests`\n"
            return TerraformResult(ok=False, log=log_text)
        return TerraformResult(ok=True, outputs=mine, log=log_text)

    return run


class NotConfigured(RuntimeError):
    """The worker cannot work yet (no GitHub token); not a crash."""


def build_worker(settings: Settings | None = None, cfg: WorkerConfig | None = None) -> Worker:
    settings = settings or Settings.from_env()
    cfg = cfg or WorkerConfig.from_env()
    if not settings.github_token:
        raise NotConfigured(
            "PLATFORM_GITHUB_TOKEN is not set: put it in .env and run `make up` "
            "(PLAN.md 8.4 step 5)"
        )
    github = GitHubClient(
        settings.github_repo,
        settings.github_token,
        base_branch=settings.github_base_branch,
        api_url=settings.github_api_url,
    )
    store = Store(make_engine(settings.database_url))
    catalog = Catalog(settings.catalog_dir)
    auto_merge_types = {t.type for t in catalog.types.values() if t.auto_merge}
    return Worker(
        store,
        github,
        github_fetch_repo(github, cfg.workdir),
        terraform_apply(cfg),
        base_branch=cfg.base_branch,
        auto_merge_types=auto_merge_types,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = argv if argv is not None else sys.argv[1:]
    cfg = WorkerConfig.from_env()
    try:
        worker = build_worker(cfg=cfg)
    except NotConfigured as e:
        if "--once" in args:
            print(f"worker not configured: {e}", file=sys.stderr)
            return 2
        # Stay up and quiet so the pod is healthy; the secret arrives with
        # `make up`, which restarts the deployment.
        while True:
            log.warning("worker idle: %s", e)
            time.sleep(300)
    if "--retry" in args:
        request_id = args[args.index("--retry") + 1]
        req = worker.retry(request_id, actor=os.environ.get("PLATFORM_USER", "operator"))
        print(f"{req.id}: {req.state}; the next pass applies it")
        return 0
    if "--once" in args:
        changed = worker.run_once()
        print(f"changed: {', '.join(changed) if changed else 'nothing'}")
        return 0
    worker.run_forever(cfg.interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
