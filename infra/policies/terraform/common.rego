# Helpers shared by the terraform-default policy set. Input is the JSON of
# `terraform show -json <plan>`; every rule reads input.resource_changes.
package main

import rego.v1

# A resource change that creates or updates something.
creates(rc) if "create" in rc.change.actions

creates(rc) if "update" in rc.change.actions

# Module path of a change ("" for root resources).
module_of(rc) := object.get(rc, "module_address", "")

# The "primary" resource of each catalog type, which must carry the tags
# and a platform-conformant name.
primary_types := {
	"aws_s3_bucket",
	"aws_dynamodb_table",
	"aws_iam_role",
	"kubernetes_namespace_v1",
}

tags_of(rc) := t if {
	not startswith(rc.type, "kubernetes_")
	t := rc.change.after.tags
	t != null
}

tags_of(rc) := t if {
	startswith(rc.type, "kubernetes_")
	t := rc.change.after.metadata[0].labels
	t != null
}

name_of(rc) := rc.change.after.bucket if rc.type == "aws_s3_bucket"

name_of(rc) := rc.change.after.name if rc.type in {"aws_dynamodb_table", "aws_iam_role"}

name_of(rc) := rc.change.after.metadata[0].name if rc.type == "kubernetes_namespace_v1"
