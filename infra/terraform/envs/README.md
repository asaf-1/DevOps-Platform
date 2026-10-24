# Terraform environments

| Env | Cloud | Cluster | State | When |
|---|---|---|---|---|
| `local` | LocalStack (`var.localstack_endpoint`) | kind, via kubeconfig or in-cluster | Postgres (`pg` backend, schema `terraform_local`) | always |
| `dev` | real AWS (`var.region`) | none | S3 bucket + lock, configured at init | only with `REAL_AWS=1`, Phase 4 |

## One file per request

`envs/<env>/requests/<request-id>.tf` is the whole footprint of a request:
one `module` call with the inputs, one `output` named after the request
id. The platform API renders it from the catalog template; CI plans it;
after approval the apply worker applies the environment and reads
`terraform output -json requests` to find that request's outputs.

Why: the PR diff is one small file, reviews stay readable, and a request
can be removed by deleting its file. The `requests/` folder is a child
module (`main.tf` includes it) because Terraform only loads `.tf` files
from the root directory.

## Running by hand (devcontainer)

The real backend is Postgres, which a plan does not need. Override it with
a throwaway local backend (the override file is gitignored):

```bash
cd infra/terraform/envs/local
printf 'terraform {\n  backend "local" {\n    path = ".terraform/plan-only.tfstate"\n  }\n}\n' > backend_override.tf
terraform init -input=false
terraform validate
TF_VAR_localstack_endpoint=http://host.docker.internal:4566 \
KUBE_CONFIG_PATH=$HOME/.kube/config terraform plan
rm backend_override.tf
```

CI does the same in `iac-pr.yml`.

Applies are the worker's job (`make apply-local`), so there is exactly one
owner of state.
