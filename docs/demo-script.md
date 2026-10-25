# Demo script: five minutes, two stories

The recording shows the two things this repo claims: a developer gets
cloud and Kubernetes resources through one reviewed path, and an AI agent
turns an alert into a reviewed pull request without ever touching the
cluster. Five minutes of screen time; the real waits (CI, the approval,
the model) are cut and labelled on screen, not hidden.

Every command below runs in the devcontainer terminal unless it says
"browser". Timings are recording time; "cut" tells you what to skip and
how long it really takes on the laptop this was built on.

## Before you press record (15 minutes, off camera)

1. Cluster up and green, Ollama serving `qwen3:4b-instruct` on the host:

   ```bash
   make status                      # every ArgoCD app Synced and Healthy, no pod not Running
   curl -s http://host.docker.internal:11434/api/tags | grep -o 'qwen3:4b-instruct'
   ```

2. Nothing broken in git: `make fix` prints "already healthy in git".
3. A second terminal with the platform API reachable for the CLI:

   ```bash
   kubectl -n platform port-forward svc/platform-api 18000:80
   ```

   In the first terminal: `export PLATFORM_API_URL=http://localhost:18000`
   and `alias platform=platform/api/.venv/bin/platform`.
4. Browser tabs, in this order, logged in where needed:
   - the repository on GitHub: **Pull requests**, **Actions**
   - http://demo.localhost:8080 (the demo app)
   - http://bank.localhost:8080 (Playground Bank)
   - http://argocd.localhost:8080 (user `admin`, password printed by `make up`)
   - http://grafana.localhost:8080/d/platform-dx and
     http://grafana.localhost:8080/d/platform-agents (user `admin`, the
     password: `kubectl -n observability get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d`)
5. Terminal font at 16 pt or larger, window 1600 by 900, dark theme.
   Record with OBS or the Windows Game Bar (Win+G) at 1080p.
6. Pick a bucket name that does not exist yet (`team-photos` below). The
   worker writes the newest bucket's name into the demo app's ConfigMap,
   so the page will show it.

## Scene 1. What this is (0:00 to 0:30)

Browser: the README, top of the page. Read the first two sentences, then
scroll to the status table. Say: "two stories, one path for each: a
request becomes a pull request, an alert becomes a pull request. People
approve both."

## Scene 2. A developer asks for a bucket (0:30 to 1:40)

Terminal:

```bash
platform request s3-bucket --name team-photos --team web --cost-center cc-100
```

It prints the request id (`r-xxxxxx`) and the pull request URL. Open the
URL in the browser. Show the diff: one file, `requests/r-xxxxxx.tf`, one
module call. Say: "the API validated the inputs against the type's schema
and rendered this; nobody wrote Terraform."

**Cut: about 3 minutes.** CI (`iac-pr`) plans, runs the OPA policies,
Checkov, Trivy and Infracost, then comments on the PR and merges it.

Back on the PR: scroll the bot comment: the plan (`6 to add`), the policy
result, the cost. The PR is merged. Terminal:

```bash
platform status r-xxxxxx
```

Read the timeline: `requested`, `pr-opened`, `plan-ok`, `policy-ok`,
`planned`. Say: "this timeline is the audit trail; every row has who,
what and when."

## Scene 3. One click, then the worker (1:40 to 2:30)

Browser: **Actions** tab, the `iac-approve` run waiting on the
`production` environment. Click **Review deployments**, tick
`production`, **Approve and deploy**. Say: "the only human step, and it
is the one GitHub already knows how to audit."

**Cut: about 2 minutes.** The apply worker inside the cluster polls every
30 seconds, runs Terraform against LocalStack with state in Postgres,
writes `applied` and `deployed`, and commits the outputs to the GitOps
folder; ArgoCD rolls the ConfigMap out within 3 minutes.

Terminal: `platform status r-xxxxxx` again: `approved`, `applied`,
`deployed`, the bucket name in the `applied` row. Browser: the demo app
tab, refresh: it shows `team-photos`. Say: "request to running app, one
file reviewed, one click."

## Scene 4. Break the tenant app, let the agent find it (2:30 to 3:50)

Terminal:

```bash
make break BREAK_TARGET=bank
```

Read what it prints: it changes one setting line in git
(`HOST=0.0.0.0` to `0.0.0.0.1`), pushes, and asks ArgoCD to sync. Say:
"this is someone else's app, Playground Bank, from its own repository;
the platform only pins a version and a few settings."

**Cut: about 4 minutes.** The pod crash-loops within a minute; the alert
`BankAppCrashLooping` needs three restarts and one more minute; Alertmanager
posts it to the agent runtime, which starts a run.

Terminal, show the run exists:

```bash
kubectl -n platform logs deploy/agent-runtime --since=5m | grep -E "run-|tool"
```

Say: "the agent reads the pod, the GitOps folder, the logs. Its
Kubernetes account can only read; it cannot change this cluster even if
the model wanted to." Prove it in one line:

```bash
kubectl auth can-i delete pods --as=system:serviceaccount:platform:agent-runtime -n bank
```

`no`.

**Cut: 10 to 15 minutes on the local 4B model** (about a minute on
Claude). Say so on screen; the honesty is part of the pitch.

Browser: **Pull requests**: the agent's PR, title from the run. Show the
diff: `+1 / -1`, the HOST line. Scroll the body: symptoms, evidence (the
exact log line `getaddrinfo ENOTFOUND 0.0.0.0.1`), root cause, the
proposed change, confidence, what it could not verify. Say: "a one-line
fix with its evidence; the tool only lets it change one line, under
`gitops/apps/`, on a branch named `agent/`."

Click **Merge pull request**.

**Cut: about 3 minutes.** ArgoCD syncs; the app is Ready in seconds.

Browser: the bank tab, refresh: products load. Terminal:

```bash
curl -s http://localhost:18000/smoke/bank
```

`4 of 4 passed`. Say: "the same smoke test the agent can run as a
read-only tool."

## Scene 5. The trust layer (3:50 to 4:40)

Browser, Grafana, the **Agents** dashboard: runs, success rate, tool calls
by outcome, the eval score of the deployed prompt. Say: "the model is
small and wrong a quarter of the time; the point is that it cannot be
dangerous, and every wrong answer becomes a recorded scenario." Switch to
the **Platform DX** dashboard: request to deployed, approval wait.

Terminal, the recorded scenarios and the policy as code, one `ls` each:

```bash
ls agents/evals/fixtures/      # 13 scenarios, incidents and safety traps
ls docs/runbooks/              # seven runbooks the agent reads, one per alert family
ls infra/policies/kyverno/     # the third lock: the cluster refuses writes from the agent
```

Say: "`make evals` scores a prompt change against all 13 before it ships;
the score on the dashboard is from the last run."

## Scene 6. Close (4:40 to 5:00)

Browser: the README's "Add a resource type in 10 minutes" and "Add an
agent in 20 minutes" headings, then `docs/adr/`. Say: "twelve decision
records explain the why; the roadmap says what is next. Clone it, run
`make up`, and the README is the only guide you need."

## After recording

- `make fix` if you did not merge the agent's PR (it did nothing if you
  did). Delete the demo request's bucket only by closing its PR before
  merge next time; LocalStack forgets everything on `make down` anyway.
- Put the video next to the README (a link under the golden-path GIF).

## What the README claims and where the recording shows it

| Claim | Scene |
|---|---|
| One command opens a request and a pull request with one Terraform file | 2 |
| CI comments plan, policy, security and cost; green PRs merge themselves | 2 |
| One human click on the `production` environment | 3 |
| A worker inside the cluster applies; the audit trail shows every step | 3 |
| The app reads its new resource from a ConfigMap the worker committed | 3 |
| A tenant app from its own repository runs on the platform | 4 |
| An alert becomes an agent run with real logs | 4 |
| The agent cannot write to the cluster (RBAC answer `no`) | 4 |
| A one-line pull request with evidence; a human merges | 4 |
| The app heals from the merged change | 4 |
| Dashboards: runs, tool outcomes, eval score, request to deployed | 5 |
| Recorded scenarios, runbooks and Kyverno policies live in git | 5 |
| ADRs, roadmap, the two how-to sections | 6 |
