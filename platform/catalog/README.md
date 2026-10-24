# Resource catalog

One folder per resource type a developer can request. Adding a type is a
pull request that adds a folder with these four files:

| File | Purpose |
|---|---|
| `type.yaml` | Which Terraform module implements it, who owns it, which policy set applies, whether approval is required. |
| `schema.json` | JSON Schema for the request inputs. The API validates requests against it; enums keep choices small (`size: small/medium/large`). |
| `request.tf.j2` | Jinja2 template the API renders into `infra/terraform/envs/<env>/requests/<request-id>.tf`: one module call, nothing else. |
| `README.md` | What a developer gets, the inputs, an example `platform request` command. |

Every type gets the same four mandatory tags, set by the platform, never by
the requester: `team`, `cost-center`, `request-id`, `managed-by=platform`.
Policies in `infra/policies/terraform/` reject plans that lack them.
