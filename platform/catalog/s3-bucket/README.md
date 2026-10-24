# s3-bucket

A private S3 bucket with the safe defaults already decided for you:
encryption at rest (AES-256), every form of public access blocked, bucket
owner enforced (no ACLs), versioning on, and old versions expiring after a
retention period you choose.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `name` | yes | | `^[a-z0-9-]{3,40}$`, must be unique |
| `team` | yes | | owning team, becomes the `team` tag |
| `cost_center` | yes | | becomes the `cost-center` tag |
| `versioning` | no | `true` | keep previous object versions |
| `retention` | no | `90d` | `none`, `30d`, `90d`, `365d`: when noncurrent versions expire |

## Outputs

`bucket_name`, `bucket_arn`, `bucket_id`.

## Example

```bash
platform request s3-bucket --name demo-uploads --team web --cost-center cc-100 --retention 30d
```

Opens a pull request with one file,
`infra/terraform/envs/local/requests/<request-id>.tf`. After plan, policy
and cost checks pass and a reviewer approves, the apply worker creates the
bucket and records the outputs.

## Policies that apply

`terraform-default`: encryption required, no public access, the four
mandatory tags, naming regex, only catalog resource types.
