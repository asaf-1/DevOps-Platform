# Platform API

FastAPI service that owns the catalog, the resource requests and the audit
trail, plus the apply worker (`worker.py`). The CLI in `../cli` and any UI
talk to it over HTTP; nothing else touches the database.

## Endpoints

| Method | Path | What |
|---|---|---|
| `GET` | `/healthz` | liveness |
| `GET` | `/catalog` | resource types with their input schemas |
| `GET` | `/catalog/{type}` | one type in full, including its README |
| `POST` | `/requests` | validate inputs, store the request, render its `.tf`, push a branch, open the PR |
| `GET` | `/requests` | list, optional `?state=` |
| `GET` | `/requests/{id}` | one request with PR, outputs, error |
| `GET` | `/audit` | audit events, optional `?request=<id>` |

A request moves through `requested`, `pr-opened`, `planned`, `approved`,
`applied`, `deployed` (or `failed`); every move is an audit event with an
actor (`human`, `agent` or `system`).

## Configuration (environment)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./platform.db` | SQLite locally, Postgres in the cluster |
| `PLATFORM_GITHUB_TOKEN` | unset | fine-grained token; without it requests end `failed` with a clear reason |
| `GITHUB_REPO` | `asaf-1/DevOps-Platform` | where requests become PRs |
| `GITHUB_BASE_BRANCH` | `main` | |
| `CATALOG_DIR` | `platform/catalog` | |
| `REPO_ROOT` | repo root | used to compute `infra/terraform/envs/<env>/requests/<id>.tf` |

## Run locally (devcontainer)

```bash
cd platform/api
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" -e "../cli[dev]"
pytest                      # API tests
(cd ../cli && pytest)       # CLI tests
uvicorn platform_api.main:app --reload --port 8000
```

Then, from another terminal: `platform catalog list`,
`platform request s3-bucket --name demo-uploads --team web --cost-center cc-100`.
Set `PLATFORM_GITHUB_TOKEN` in `.env` for the PR step to work.
