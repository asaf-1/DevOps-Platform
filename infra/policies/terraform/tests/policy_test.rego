# Run with:  conftest verify -p infra/policies/terraform -d infra/policies/terraform/tests/fixtures
# Fixtures are real `terraform show -json` output (resource_changes only):
# good/ is the plan of one request of each type; bad/ is the same plan with
# a public access block switched off, a missing tag, a bad name, a public
# ACL, a bucket without encryption and a rogue EC2 instance.
package main

import rego.v1

test_good_plan_has_no_denials if {
	count(deny) == 0 with input as data.good
}

test_bad_plan_is_denied if {
	msgs := deny with input as data.bad
	count(msgs) >= 6
}

test_bad_plan_public_access_block if {
	msgs := deny with input as data.bad
	some m in msgs
	contains(m, "block_public_acls must be true")
}

test_bad_plan_missing_tag if {
	msgs := deny with input as data.bad
	some m in msgs
	contains(m, "missing mandatory tags [\"cost-center\"]")
}

test_bad_plan_bad_name if {
	msgs := deny with input as data.bad
	some m in msgs
	contains(m, "name \"Bad_Name\" does not match")
}

test_bad_plan_public_acl if {
	msgs := deny with input as data.bad
	some m in msgs
	contains(m, "public ACL \"public-read\"")
}

test_bad_plan_no_encryption if {
	msgs := deny with input as data.bad
	some m in msgs
	contains(m, "no server-side encryption")
}

test_bad_plan_rogue_type if {
	msgs := deny with input as data.bad
	some m in msgs
	contains(m, "aws_instance is not in the catalog")
}

test_wrong_managed_by_value if {
	plan := {"resource_changes": [{
		"address": "module.x.aws_s3_bucket.this",
		"module_address": "module.x",
		"mode": "managed",
		"type": "aws_s3_bucket",
		"change": {"actions": ["create"], "after": {
			"bucket": "ok-name",
			"tags": {"team": "web", "cost-center": "cc-1", "request-id": "r-1", "managed-by": "hand"},
		}},
	}]}
	msgs := deny with input as plan
	some m in msgs
	contains(m, "managed-by must be \"platform\"")
}

test_untagged_namespace if {
	plan := {"resource_changes": [{
		"address": "module.x.kubernetes_namespace_v1.this",
		"module_address": "module.x",
		"mode": "managed",
		"type": "kubernetes_namespace_v1",
		"change": {"actions": ["create"], "after": {"metadata": [{"name": "team-a", "labels": null}]}},
	}]}
	msgs := deny with input as plan
	some m in msgs
	contains(m, "has no tags")
}

test_deletes_are_not_policed if {
	plan := {"resource_changes": [{
		"address": "aws_instance.old",
		"mode": "managed",
		"type": "aws_instance",
		"change": {"actions": ["delete"], "before": {"ami": "x"}, "after": null},
	}]}
	count(deny) == 0 with input as plan
}
