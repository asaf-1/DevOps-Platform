# k8s-namespace

A namespace in the platform's Kubernetes cluster, labelled with the four
mandatory tags, with a ResourceQuota and a LimitRange chosen by size so
that one team cannot starve the others.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `name` | yes | | DNS label, 3 to 40 characters |
| `team` | yes | | becomes the `team` label |
| `cost_center` | yes | | becomes the `cost-center` label |
| `size` | no | `small` | quota: `small` 2 CPU / 4Gi / 20 pods, `medium` 4 / 8Gi / 50, `large` 8 / 16Gi / 100 |

Containers without explicit resources get a default request of 50m CPU and
64Mi memory and a default limit of 250m and 256Mi.

## Outputs

`namespace`.

## Example

```bash
platform request k8s-namespace --name team-web-dev --team web --cost-center cc-100 --size small
```
