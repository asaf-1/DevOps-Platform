# 0005. One Terraform file per request

- Status: accepted
- Date: 2026-10-24
- Deciders: Asaf

## Context

Requests arrive one at a time and each must be reviewable on its own.
Rendering them into a shared file (a list of module calls) would make every
PR touch the same file, create merge conflicts between concurrent requests,
and make it hard to see what one request changed.

## Decision

The API renders each request into exactly one file,
`infra/terraform/envs/<env>/requests/<request-id>.tf`, from the catalog's
Jinja template: a single module call with the inputs and the four mandatory
tags, plus one output named after the request id. The `requests/` folder is
a child module included from the environment's `main.tf`, because Terraform
only loads `.tf` files from the root directory. Request ids are short
(`r-` and six hex digits) and double as Terraform identifiers.

## Consequences

- A PR diff is one new file; reviewers see the whole request.
- Concurrent requests never conflict in git.
- Removing a resource is deleting its file, which plans as a destroy and
  goes through the same review; deletions are not policed by OPA.
- All requests of an environment share one Terraform state, so one apply
  covers everything that was merged since the last one. The worker reads
  only its request's output from `terraform output -json requests`.
- A hand edit to a request file is possible and expected to be caught: the
  module's variable validation and the OPA policy set both reject public
  access, missing tags, bad names and foreign resource types.

## Alternatives considered

- One state per request (a root module per request): perfect isolation,
  but N states, N inits and N provider downloads per apply.
- One shared `requests.tf` with a generated list: smaller tree, constant
  merge conflicts.
- Rendering at apply time from the database instead of committing files:
  nothing to review in the PR; the file is the contract.
