# Platform naming rule: lowercase letters, digits and hyphens, 3 to 40 characters.
package main

import rego.v1

name_pattern := `^[a-z0-9-]{3,40}$`

deny contains msg if {
	some rc in input.resource_changes
	creates(rc)
	name := name_of(rc)
	not regex.match(name_pattern, name)
	msg := sprintf("%s: name %q does not match %s", [rc.address, name, name_pattern])
}
