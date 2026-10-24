# The four mandatory tags on every primary resource.
package main

import rego.v1

required_tags := {"team", "cost-center", "request-id", "managed-by"}

deny contains msg if {
	some rc in input.resource_changes
	creates(rc)
	rc.type in primary_types
	not tags_of(rc)
	msg := sprintf("%s: has no tags; required: %v", [rc.address, sort(required_tags)])
}

deny contains msg if {
	some rc in input.resource_changes
	creates(rc)
	rc.type in primary_types
	tags := tags_of(rc)
	missing := required_tags - {k | some k, _ in tags}
	count(missing) > 0
	msg := sprintf("%s: missing mandatory tags %v", [rc.address, sort(missing)])
}

deny contains msg if {
	some rc in input.resource_changes
	creates(rc)
	rc.type in primary_types
	tags := tags_of(rc)
	tags["managed-by"] != "platform"
	msg := sprintf("%s: tag managed-by must be \"platform\", got %q", [rc.address, tags["managed-by"]])
}
