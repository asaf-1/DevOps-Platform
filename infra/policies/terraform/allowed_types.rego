# Only resource types the catalog modules create may appear in a plan. A
# hand-edited request file that adds anything else is rejected.
package main

import rego.v1

allowed_types := {
	"aws_s3_bucket",
	"aws_s3_bucket_ownership_controls",
	"aws_s3_bucket_public_access_block",
	"aws_s3_bucket_server_side_encryption_configuration",
	"aws_s3_bucket_versioning",
	"aws_s3_bucket_lifecycle_configuration",
	"aws_dynamodb_table",
	"aws_iam_role",
	"aws_iam_role_policy",
	"aws_iam_role_policy_attachment",
	"kubernetes_namespace_v1",
	"kubernetes_resource_quota_v1",
	"kubernetes_limit_range_v1",
}

deny contains msg if {
	some rc in input.resource_changes
	rc.mode == "managed"
	creates(rc)
	not rc.type in allowed_types
	msg := sprintf("%s: resource type %s is not in the catalog", [rc.address, rc.type])
}
