# Glossary

Every term used in this repository, in plain language, with the example
from this platform where there is one. Grouped by topic; within a group,
roughly in the order you meet the terms.

## Containers and the machine

- **Container**: a process packaged with everything it needs, isolated from the rest of the machine. Starts in a second, throwaway.
- **Image**: the frozen template a container starts from. `kindest/node:v1.37.0` is an image; a running copy of it is a container.
- **Docker / Docker Desktop**: the program that builds images and runs containers. On Windows it runs them inside a small Linux virtual machine (WSL).
- **WSL**: Windows Subsystem for Linux, the Linux VM Windows provides. Docker Desktop uses it.
- **Devcontainer**: a container prepared as a development environment; VS Code opens the project inside it so everyone has the same tools. Ours is `.devcontainer/`, with every tool pinned.
- **Dockerfile**: the recipe for building an image, line by line.
- **Bind mount**: a folder of the host made visible inside a container. The repo folder is mounted into the devcontainer.
- **Port / host port**: a numbered door for network traffic. "Map container port 80 to host port 8080" means traffic to the laptop's 8080 goes to the container's 80.
- **localhost / 127.0.0.1**: "this machine". Inside a container it means the container, which is why the devcontainer needs `host.docker.internal` to reach the laptop.
- **host.docker.internal**: a name Docker provides inside containers that means "the laptop". The agent reaches Ollama through it.
- **CIDR** (for example `10.244.0.0/16`): a range of IP addresses written compactly.

## Kubernetes

- **Kubernetes (k8s)**: a system that runs containers across machines, restarts them when they die, and exposes them on the network, all described in YAML files.
- **Cluster**: one Kubernetes installation. Ours is named `platform`.
- **Node**: a machine in the cluster. With kind, a node is a Docker container. The control-plane node runs the brain; worker nodes run the applications.
- **kind**: Kubernetes IN Docker. Builds a cluster from containers. Good for laptops and CI.
- **Pod**: the smallest unit Kubernetes runs: one or more containers that live and die together. "Pod is Running" is the basic sign of health.
- **Namespace**: a folder-like grouping inside the cluster (`argocd`, `observability`, `platform`, `demo`, `bank`). Names only need to be unique within a namespace.
- **Deployment**: "run N copies of this pod and keep them running".
- **ReplicaSet**: the object a Deployment creates for one version of the pod template; a rollout is a new ReplicaSet replacing the old one.
- **StatefulSet**: like a Deployment, for things that keep data on disk (Loki, Tempo, Postgres).
- **DaemonSet**: "run one copy of this pod on every node" (the network plugin, node-exporter).
- **Job / CronJob**: a pod that runs once to completion; a CronJob runs one on a schedule (the nightly audit export).
- **Service**: a stable name and address for a set of pods, for example `loki.observability.svc.cluster.local`. Its **selector** picks the pods by label; its **targetPort** is the container port it forwards to.
- **Endpoints**: the list of pod addresses a Service currently points at. `<none>` means the Service reaches nothing.
- **NodePort**: a Service type that opens a port on every node. LocalStack uses NodePort 30566, mapped to the laptop's 4566.
- **Ingress**: a rule "requests for hostname X go to service Y". **ingress-nginx** is the program that enforces those rules; ours listens on the laptop's 8080 and 8443.
- **ConfigMap / Secret**: key-value objects that hold configuration; Secrets are for passwords and tokens. We keep Secrets out of git.
- **TLS Secret**: a Secret of type `kubernetes.io/tls` holding a certificate and its key; an Ingress names one to serve HTTPS. A certificate has a `notAfter` date; after it, browsers refuse the site.
- **PersistentVolume / PVC / StorageClass**: disk space a pod can keep across restarts; the StorageClass `standard` is how kind hands out local disk.
- **CRD (Custom Resource Definition)**: a new kind of object taught to the cluster, for example `Application` (ArgoCD), `Cluster` (CloudNativePG), `PrometheusRule`.
- **Operator**: a program in the cluster that watches a CRD and does the work. CloudNativePG watches `Cluster` objects and runs Postgres for them.
- **kubectl**: the Kubernetes command-line tool. `get` lists, `describe` explains, `logs` shows output, `apply -f` creates or updates from a file.
- **kubeconfig / context**: the file (and the entry in it) that tells kubectl which cluster to talk to and with which credentials. Ours is `kind-platform`.
- **Taint / toleration**: a node can say "nothing runs here unless it tolerates this"; the control-plane node has such a taint, and a node under memory pressure gets one.
- **CNI / kindnet**: the network plugin that gives pods addresses and lets them talk. Without it, nodes are `NotReady`.
- **RBAC / ServiceAccount / Role**: who may do what. A ServiceAccount is an identity for a program; a Role lists allowed verbs (`get`, `list`, `watch`, `create`, `delete`). The agent's ServiceAccount gets read-only verbs.
- **Admission policy / Kyverno**: rules checked at the moment something is created or changed in the cluster, before it is accepted. Ours live in `infra/policies/kyverno/`; one of them refuses any write from the agent's identity.
- **Probe (readiness, liveness)**: a check Kubernetes runs against a container; failing readiness takes the pod out of the Service, failing liveness restarts it. `initialDelaySeconds` is how long to wait before the first check.
- **HPA (HorizontalPodAutoscaler)**: adds or removes replicas to keep a metric (CPU) near a target, between `minReplicas` and `maxReplicas`.
- **Requests and limits**: the CPU and memory a container reserves (request) and may not exceed (limit).
- **CrashLoopBackOff**: the container keeps exiting and Kubernetes restarts it with growing delays. The cause is in the last exit, shown by `kubectl logs --previous`.
- **OOMKilled**: a container used more memory than its limit and the kernel killed it (exit code 137).
- **ImagePullBackOff / ErrImagePull**: the node cannot download the container image (a tag that does not exist, a private registry, no network).
- **Eviction**: the node ran out of a resource (memory, disk) and killed pods to recover; the pod shows `Evicted` and the node `MemoryPressure`.
- **Events**: the timeline Kubernetes keeps for each object (pulled image, started container, failed scheduling). `kubectl describe` prints them at the bottom.

## Helm and GitOps

- **Helm**: installs software into Kubernetes from packages.
- **Chart**: a Helm package (templates of Kubernetes YAML). Pinned by version, for example `kube-prometheus-stack 92.13.1`.
- **Values**: the settings for a chart, a YAML file. Ours live in `gitops/clusters/local/values/`.
- **Release**: one installed instance of a chart in a namespace. `helm list -A` shows them.
- **Kustomize**: a tool that takes Kubernetes YAML files and changes some fields with patches, without templates. `kubectl kustomize <folder>` prints the result.
- **Kustomize overlay**: a folder that takes someone else's Kubernetes files (the base) and changes only some fields. The Playground Bank overlay reads the app's own manifests from its repository at a pinned commit.
- **Base vs overlay**: base = the app's own manifests; overlay = the platform's decisions on top (namespace, image, database, ingress host, resources, labels).
- **Pin**: a fixed commit or image tag the overlay points at, so what runs is exactly known and only changes in a reviewed commit.
- **ConfigMap generator**: kustomize writes the ConfigMap itself and adds a hash of its content to the name, so a settings change restarts the Deployment (a plain ConfigMap change would not).
- **GitOps**: the cluster's desired state lives in git; a tool continuously makes the cluster match. Changing the cluster = making a commit.
- **ArgoCD**: the GitOps tool used here. It polls the repository every few minutes and applies what changed.
- **Application** (ArgoCD): "take this source (a chart or a folder in git) and keep this namespace in sync with it".
- **AppProject**: a group of Applications with limits on allowed sources and destinations. Ours: `platform`.
- **App of apps / root Application**: one Application whose source is a folder of other Application files. Install the root, get everything.
- **Sync / Synced / OutOfSync**: making the cluster match git / it matches / it differs.
- **Healthy / Progressing / Degraded / Missing**: the state of an Application's resources (running / still starting / broken / not created yet).
- **Automated sync, prune, self-heal**: sync without clicking; delete what git no longer has; revert manual edits. Self-heal is why a `kubectl edit` by hand disappears.
- **Sync wave**: a number that orders Applications (an operator before its custom resources).
- **Server-side apply**: a way of applying large objects (big CRDs) that avoids a size limit in the older method.
- **Multi-source Application**: chart from a Helm repository plus values from our git repository, in one Application.
- **Egress / network policy**: rules for what a pod may talk to. The bank's own rules allowed DNS only; the overlay adds its database.

## Observability

- **Observability**: being able to see what a system is doing from the outside: metrics, logs and traces.
- **Metric**: a number over time (CPU, requests per second, memory). **Prometheus** stores metrics and evaluates rules on them.
- **Series / label**: one metric line with its labels, for example `agent_runs{status="done", pod="agent-runtime-abc"}`. A new pod starts a new series, which is why dashboards aggregate over pods.
- **PromQL**: Prometheus's query language. `max by (status) (agent_runs)` takes the highest value per status across pods.
- **Instant query vs range query**: "the value now" versus "the values over the last N hours". Stat panels here use instant queries, so a series that stopped days ago does not reappear.
- **Scrape / ServiceMonitor**: Prometheus pulls `/metrics` from each service on an interval; a ServiceMonitor is the CRD that tells it which services.
- **Alert / Alertmanager / webhook**: a rule that fired; Alertmanager groups alerts and sends them to receivers, for example an HTTP call (webhook) to the agent runtime.
- **Alert rule `for:`**: how long a condition must hold before the alert fires (one to three minutes here).
- **PrometheusRule**: the CRD that holds alert and recording rules; ours are in the kube-prometheus-stack values.
- **SLO (service level objective)**: a target such as "the agent's first tool call within three minutes of the alert, most of the time"; the `platform-slo` rules alert when it is missed.
- **Log**: a text line written by a program. **Loki** stores logs; **LogQL** is its query language.
- **Trace / span**: the record of one request or one agent run as a tree of timed steps (spans). **Tempo** stores traces; each run's trace is one click from its row in the API.
- **OpenTelemetry (OTel)**: the standard for emitting metrics, logs and traces. **OTLP** is its wire protocol. The **Collector** receives OTLP and forwards to backends via **exporters**.
- **Grafana**: the UI that queries Prometheus, Loki and Tempo. A **datasource** is one such backend; a **dashboard** is a saved page of panels.
- **Dashboards as code**: the two dashboards are JSON inside ConfigMaps generated by `scripts/dashboards.py`; the Grafana **sidecar** loads every ConfigMap labelled `grafana_dashboard=1`. Edit the script and regenerate; never edit in the UI.
- **Stat / bar gauge / time series panel**: one big number; one bar per series; a line over time.
- **p50 / p95**: the median and the value 95 percent of samples stay under. "Request to deployed, p95" is how long the slow requests took.
- **Remote write**: pushing metrics into Prometheus from outside (the Collector does this).
- **Datadog**: a commercial observability product. We keep an exporter block for it, off, to show vendor independence.

## Cloud and infrastructure as code

- **AWS**: Amazon's cloud. **S3** (file storage), **DynamoDB** (key-value database), **IAM** (identities and permissions), **STS** (temporary credentials), **SQS** (queues), **CloudWatch** (AWS monitoring).
- **LocalStack**: a program that imitates AWS services on your machine. The community edition is free; everything in it is forgotten on `make down`.
- **EKS**: AWS's managed Kubernetes. Costs money per hour; we use kind instead.
- **Terraform**: reads `.tf` files describing resources and creates them. **plan** shows what would change; **apply** does it; **state** is Terraform's record of what exists (ours in Postgres); a **module** is a reusable bundle; a **provider** is the plugin for one platform (AWS, GitHub).
- **Backend**: where Terraform keeps its state. The `pg` backend keeps it in Postgres inside the cluster.
- **Pulumi**: like Terraform but in a programming language (TypeScript here). The **Automation API** lets a program drive Pulumi.
- **OPA / Rego / Conftest**: a policy engine, its language, and a CLI that checks files (Terraform plans) against policies: mandatory tags, naming, no public buckets.
- **Checkov / Trivy**: scanners for security mistakes in infrastructure files and images.
- **Infracost**: estimates the monthly cost of a Terraform plan and posts it on the PR.
- **Drift**: the real world no longer matches the code.
- **OIDC (for CI)**: a way for GitHub Actions to log in to AWS without stored keys.
- **IRSA / Pod Identity**: AWS ways to give a pod a cloud identity (EKS only).

## GitHub and workflow

- **Pull request (PR)**: a proposed change to a repository, reviewed before merging.
- **CI / GitHub Actions / workflow**: automated checks that run on every PR or push, defined in `.github/workflows/` (`iac-pr`, `iac-approve`, `build`, `build-tenant`, `agents-eval`).
- **Auto-merge (the platform's)**: the platform API merges a request's PR itself once every check is green; nobody clicks merge.
- **Repository environment**: a named deployment target on GitHub (`production`) that can require a reviewer before a workflow continues; the one human click of the golden path lives there.
- **Required reviewer / approval gate**: the GitHub setting that makes a workflow pause until a named person approves.
- **Branch protection**: rules GitHub enforces on a branch, here that `main` cannot be deleted or force-pushed.
- **PAT (personal access token)**: a password-like token for scripts to act on GitHub. **Fine-grained** = limited to one repository and named permissions.
- **Scope** (`repo`, `workflow`): what a token is allowed to do.
- **Credential helper**: how git gets your GitHub login (here: `gh`).
- **Force-push / rewriting history**: replacing past commits. Done once to remove private files; now forbidden on `main`.
- **ADR (architecture decision record)**: a short document in `docs/adr/`: context, decision, consequences, alternatives.
- **Makefile / target**: `make up` runs the recipe named `up`. Targets here are thin wrappers over `scripts/*.sh`, and each prints what it is about to do.
- **bash / script / `set -euo pipefail`**: the Linux shell; a file of commands; the line that makes a script stop at the first error.
- **YAML**: the indentation-based text format Kubernetes, Helm and ArgoCD use.
- **Front matter**: the small YAML block between `---` lines at the top of a Markdown file (title, tags); the runbook loader reads it.
- **Pinned version / digest**: an exact version (or an exact content hash) so a rebuild gives the same result.
- **GHCR**: GitHub Container Registry, where our images live (`ghcr.io/asaf-1/devops-platform/...`). Public, so the cluster pulls them without a login.
- **Image tag bump**: after a build, the workflow edits the manifests to the new `sha-<7 chars>` tag and commits; ArgoCD sees the commit and rolls the new image out.
- **Import block**: Terraform's way to adopt something that already exists (the repository, the environment, a label) into its state instead of creating a duplicate.
- **Check block**: a Terraform assertion that only warns (a missing optional secret), unlike a failed resource.

## The platform's own code

- **API / endpoint**: a program that answers HTTP requests; an endpoint is one URL it answers, for example `POST /requests`. **FastAPI** is the Python library we build it with.
- **CLI**: a command-line program; ours is `platform` (`request`, `status`, `list`, `audit`), built with **Typer**.
- **Catalog / resource type**: the folder under `platform/catalog/` that defines one thing a developer can ask for (`s3-bucket`, `dynamodb-table`, `k8s-namespace`): its schema, template, owner and policy set.
- **JSON Schema**: a file describing which inputs a request accepts (names, types, allowed values). The API validates every request against it.
- **Template (Jinja2)**: a file with placeholders (`{{ inputs.name }}`) that the API fills in to produce the one Terraform file for a request.
- **Request**: one developer ask, with an id like `r-60c80a`, a state, and a timeline.
- **State machine**: the fixed list of states a request moves through (`requested`, `pr-opened`, `planned`, `approved`, `applied`, `deployed`, `failed`) and the allowed moves between them.
- **Apply worker**: the loop in the API pod that watches GitHub for approved requests and is the only thing that runs `terraform apply`. It polls every 30 seconds.
- **Audit event / audit trail**: a database row recording who did what, when, with what result, for requests and agent runs alike; the table is append-only (a database trigger refuses updates) and exported nightly as JSONL.
- **DX metrics**: numbers about the developer experience (request to deployed, approval wait, requests by state), computed from the audit trail on every scrape.
- **Smoke test**: the few requests that prove an app is basically alive (health, a list, one item, orders). The API runs it over HTTP at `GET /smoke/<app>`; the agent reads the result through a read-only tool.
- **SQLite / Postgres / SQLAlchemy**: the file database used when running the API on a laptop, the real database in the cluster, and the Python library that talks to both.
- **Golden path**: the one recommended way to get something done, here request, PR, checks, approval, apply, running app.
- **Tenant**: an application owned by another team or repository that runs on the platform. The platform provides namespace, database, ingress and guardrails; the tenant provides the app (Playground Bank).

## AI agents

- **LLM / model**: the AI that reads text and writes text. `qwen3:4b-instruct` is a small one that runs on a laptop's CPU; Claude is a large one reached over the internet.
- **Instruct vs thinking model**: an instruct model answers directly; a thinking model reasons in a hidden block first, which on a CPU can take fifteen minutes per step. Agents here use the instruct flavour.
- **Ollama**: the program that runs models locally and offers them on `http://localhost:11434`.
- **Token**: a piece of a word; models read and write tokens; speed is tokens per second (a laptop CPU: a handful).
- **Tool calling**: the model asks to run a named tool ("get pods in namespace demo") and gets the result back, instead of guessing.
- **MCP (Model Context Protocol)**: a standard way to offer tools to models. An **MCP server** is a program exposing tools (Kubernetes, GitHub, Grafana).
- **stdio transport**: how the runtime talks to an MCP server it started as a subprocess (over its standard input and output), no network port involved.
- **Agent**: a loop: the model thinks, calls a tool, reads the result, repeats, then answers.
- **Agent runtime**: our program that runs agents, enforces their manifests, records audit and traces, and exposes `GET /runs`.
- **Run**: one execution of an agent for one alert: its steps, tool calls, report and pull request. Closed when the alert resolves.
- **Manifest** (agent): a YAML file declaring an agent's allowed tools, namespaces, budget, knowledge tags, and that it is propose-only.
- **Propose-only**: the agent may only suggest changes (open a PR), never make them. Three independent locks enforce it: the tool allowlist, read-only RBAC, and a Kyverno policy.
- **Capability label** (read / write / delete): what a tool can do and on what; used to refuse write and delete tools to propose-only agents at startup.
- **Allowlist**: the explicit list of tools an agent may use; anything not on it does not exist for that agent.
- **Guard**: the one piece of code every tool call goes through, so rules (namespace, branch) are checked in a single place and every call is logged.
- **`replace_line`**: the only way the agent changes a file: it names one line and the new text; the runtime edits the file on the agent's branch, only under `gitops/apps/`. One line in, one line out, because a small model cannot rewrite a whole file reliably.
- **Pydantic AI**: the Python library used to build the agents; model-agnostic.
- **Report (IncidentReport)**: the agent's typed final answer: symptoms, evidence, root cause, proposed change, confidence, not verified.
- **Runbook**: the how-to text the agent reads to diagnose a known kind of problem. One file, `docs/runbooks/incidents.md`: the rules once, then a section per alert family; the loader sends the rules plus the section whose tags match the alert name.
- **Knowledge tags**: the tags an agent's manifest allows; a runbook section reaches the prompt only if its tags intersect them.
- **Token budget / max steps**: limits on how much an agent may think and how many tool calls it may make; overrunning ends the run as failed with the steps so far recorded.
- **Alertmanager route / receiver**: a rule saying which alerts go where; the receiver `agent-runtime` is the agent's webhook URL, and only `DemoApp*` and `BankApp*` alerts are routed to it.
- **Fingerprint**: Alertmanager's stable id for one alert instance; the runtime uses it to avoid handling the same alert twice.
- **Triage window / backoff**: one run per namespace per 30 minutes, and a failed run is not retried for the same alert for 10 minutes; each run costs minutes of CPU on a local model.
- **Prompt injection**: text inside data (an alert description, a log line) that tries to give the agent new orders. The agent must treat it as data; the safety scenarios test that.
- **Service account token (Grafana)**: a password-like key for a non-human user; ours lets the agent query metrics and logs as a Viewer.

## Evals

- **Eval (evaluation)**: a test for an AI agent. Instead of "does this function return 4", it asks "given this alert and these tool outputs, does the agent find the cause, change the right line, and nothing else".
- **Fixture / recorded scenario**: the data one eval runs on: the alert, the files, the canned command outputs and the answer key. Thirteen live in `agents/evals/fixtures/`, several recorded from real incidents.
- **Expect block**: the answer key inside a fixture: words the report must contain, the one file that may change, tools that must never be called, how many steps at most.
- **EVAL_MODE**: the switch that makes the agent's tools answer from a fixture instead of the real cluster. The agent cannot tell the difference.
- **Verdict**: the list of ways a run missed its expect block; empty means PASS.
- **Dry run** (`agents/dryrun.py`): the real prompt and model against a fixture's fake tools, printing every model turn as it happens. Minutes instead of a fifteen-minute live run.
- **Promptfoo**: the tool that runs many evals, shows a table of PASS/FAIL, and keeps history. Think "pytest for prompts". `make evals` runs it.
- **Provider / assertion (Promptfoo)**: the small script Promptfoo calls to get an answer (`provider.py`, which runs our agent on a fixture), and the check applied to it (`asserts.py`, which applies the verdict).
- **Eval score**: the share of scenarios that pass for a given prompt; the agent chart carries the score of the deployed prompt and the Agents dashboard shows it.
- **Deterministic check**: a test with the same result every time (lint, schema, unit tests), as opposed to a model run, which can vary.
- **CI gate**: a check that must pass before a pull request can merge.
- **Spend cap**: a monthly limit set in the model provider's console so API use cannot exceed a chosen amount.

## Product and polish

- **Golden-path GIF**: `docs/images/golden-path.gif`, four real frames (terminal, PR, approval, app) assembled by `scripts/golden-path-gif.py`.
- **Playwright**: a browser automation library; `scripts/screenshots.py` uses it to log in to Grafana and photograph the dashboards, so no Grafana setting is opened up for pictures.
- **Roadmap**: `docs/roadmap.md`, what exists, what comes next, what is deliberately later.
- **Demo script**: `docs/demo-script.md`, the exact commands and clicks of a five-minute walkthrough with the waits marked.
- **Issue template**: `.github/ISSUE_TEMPLATE/feedback.yml`, the form GitHub shows when someone opens an issue.
- **GitHub settings as code**: the repository's own settings (environment, reviewer, branch rules, label, merge behaviour) as Terraform under `infra/terraform/github/`, applied with `make github-settings`.
