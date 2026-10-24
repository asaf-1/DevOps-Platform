# dynamodb-table

A DynamoDB table with encryption at rest and point-in-time recovery on.
Capacity is chosen by size so nobody has to think about read and write
units for a first table.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `name` | yes | | `^[a-z0-9-]{3,40}$` |
| `team` | yes | | becomes the `team` tag |
| `cost_center` | yes | | becomes the `cost-center` tag |
| `hash_key` | yes | | partition key attribute |
| `hash_key_type` | no | `S` | `S` or `N` |
| `range_key` | no | none | sort key attribute |
| `range_key_type` | no | `S` | `S` or `N` |
| `size` | no | `small` | `small` on-demand, `medium` 5/5, `large` 25/25 provisioned units |
| `ttl_attribute` | no | none | attribute with an expiry epoch |
| `point_in_time_recovery` | no | `true` | |

## Outputs

`table_name`, `table_arn`, `table_id`.

## Example

```bash
platform request dynamodb-table --name orders --team web --cost-center cc-100 --hash-key order_id --size small
```
