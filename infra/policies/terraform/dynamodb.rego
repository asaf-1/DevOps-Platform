# DynamoDB: encrypted at rest.
package main

import rego.v1

deny contains msg if {
	some rc in input.resource_changes
	rc.type == "aws_dynamodb_table"
	creates(rc)
	not rc.change.after.server_side_encryption[0].enabled == true
	msg := sprintf("%s: server_side_encryption must be enabled", [rc.address])
}
