# Policy set `terraform-default`

OPA/Rego rules evaluated with Conftest against `terraform show -json` of a
plan. They run in CI on every request PR and can run locally. They are the
second enforcement of what the modules already refuse, so a hand-edited
request file cannot get around the module.

| File | Rule |
|---|---|
| `tags.rego` | every primary resource (bucket, table, role, namespace) carries `team`, `cost-center`, `request-id`, `managed-by=platform` |
| `naming.rego` | names match `^[a-z0-9-]{3,40}$` |
| `allowed_types.rego` | only resource types the catalog modules create; anything else (an EC2 instance, a security group) is denied |
| `s3.rego` | server-side encryption present; public access block present with all four settings on; no public ACL, website hosting or `Principal: *` policy |
| `dynamodb.rego` | server-side encryption enabled |

Deletions are not policed: removing a request file is the legitimate way
to decommission a resource.

## Run

```bash
# unit tests, with the real plan fixtures under tests/fixtures
conftest verify -p infra/policies/terraform -d infra/policies/terraform/tests/fixtures

# a plan
terraform plan -out plan.out && terraform show -json plan.out > plan.json
conftest test plan.json -p infra/policies/terraform
```

`tests/fixtures/good/plan.json` is the plan of one request of each type;
`bad/plan.json` is the same plan with six violations.
