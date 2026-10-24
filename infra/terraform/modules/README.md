# Terraform modules

One module per catalog resource type, plus `iam-role` for the platform's
own use. Rules every module follows:

- No `provider` blocks. The environment (`infra/terraform/envs/<env>`)
  configures providers; modules only declare `required_providers`.
- A `tags` variable with validation: `team`, `cost-center`, `request-id`
  and `managed-by=platform` are mandatory. The same rule is enforced again
  by the OPA policies on the plan, so a hand-edited file cannot slip past.
- Safe defaults are not optional: encryption on, public access blocked,
  versioning and recovery on. There is no input to turn them off.
- Names are validated with the platform regex `^[a-z0-9-]{3,40}$`
  (DNS-label variant for namespaces).
- Enum-style inputs (`size`, `retention`) map to concrete settings inside
  the module, so requesters choose from a short list.

| Module | Creates | Inputs |
|---|---|---|
| `s3-bucket` | bucket, ownership controls, public access block, SSE, versioning, lifecycle | name, versioning, retention, tags |
| `dynamodb-table` | table with SSE and PITR, capacity by size | name, hash_key(+type), range_key(+type), size, ttl_attribute, point_in_time_recovery, tags |
| `iam-role` | role trusted by services, optional inline and managed policies | name, description, trusted_services, managed_policy_arns, inline_policy_json, tags |
| `k8s-namespace` | namespace, ResourceQuota, LimitRange | name, size, tags |
