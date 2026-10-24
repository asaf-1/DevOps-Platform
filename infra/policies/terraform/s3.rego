# S3: encrypted at rest, never public.
package main

import rego.v1

public_acls := {"public-read", "public-read-write", "authenticated-read"}

# Every bucket needs a server-side encryption configuration in its module.
has_sse(mod) if {
	some o in input.resource_changes
	o.type == "aws_s3_bucket_server_side_encryption_configuration"
	module_of(o) == mod
	some rule in o.change.after.rule
	rule.apply_server_side_encryption_by_default[0].sse_algorithm in {"AES256", "aws:kms"}
}

deny contains msg if {
	some rc in input.resource_changes
	rc.type == "aws_s3_bucket"
	creates(rc)
	not has_sse(module_of(rc))
	msg := sprintf("%s: bucket has no server-side encryption (AES256 or aws:kms)", [rc.address])
}

# Every bucket needs a public access block with all four settings on.
has_public_access_block(mod) if {
	some o in input.resource_changes
	o.type == "aws_s3_bucket_public_access_block"
	module_of(o) == mod
}

deny contains msg if {
	some rc in input.resource_changes
	rc.type == "aws_s3_bucket"
	creates(rc)
	not has_public_access_block(module_of(rc))
	msg := sprintf("%s: bucket has no public access block", [rc.address])
}

pab_settings := {"block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets"}

deny contains msg if {
	some rc in input.resource_changes
	rc.type == "aws_s3_bucket_public_access_block"
	creates(rc)
	some setting in pab_settings
	rc.change.after[setting] != true
	msg := sprintf("%s: %s must be true", [rc.address, setting])
}

# No public ACLs, no website hosting, no wildcard principals in bucket policies.
deny contains msg if {
	some rc in input.resource_changes
	rc.type == "aws_s3_bucket_acl"
	creates(rc)
	rc.change.after.acl in public_acls
	msg := sprintf("%s: public ACL %q is not allowed", [rc.address, rc.change.after.acl])
}

deny contains msg if {
	some rc in input.resource_changes
	rc.type == "aws_s3_bucket_website_configuration"
	creates(rc)
	msg := sprintf("%s: website hosting makes a bucket public", [rc.address])
}

deny contains msg if {
	some rc in input.resource_changes
	rc.type == "aws_s3_bucket_policy"
	creates(rc)
	regex.match(`"Principal"\s*:\s*("\*"|\{\s*"AWS"\s*:\s*"\*"\s*\})`, rc.change.after.policy)
	msg := sprintf("%s: bucket policy grants access to everyone (Principal *)", [rc.address])
}
