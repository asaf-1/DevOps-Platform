variable "name" {
  description = "Table name. Lowercase letters, digits and hyphens, 3 to 40 characters."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{3,40}$", var.name))
    error_message = "name must match ^[a-z0-9-]{3,40}$."
  }
}

variable "hash_key" {
  description = "Partition key attribute name."
  type        = string
}

variable "hash_key_type" {
  description = "Partition key type: S or N."
  type        = string
  default     = "S"

  validation {
    condition     = contains(["S", "N"], var.hash_key_type)
    error_message = "hash_key_type must be S or N."
  }
}

variable "range_key" {
  description = "Optional sort key attribute name."
  type        = string
  default     = null
}

variable "range_key_type" {
  description = "Sort key type: S or N."
  type        = string
  default     = "S"

  validation {
    condition     = contains(["S", "N"], var.range_key_type)
    error_message = "range_key_type must be S or N."
  }
}

variable "size" {
  description = "small: on-demand. medium: provisioned 5/5. large: provisioned 25/25."
  type        = string
  default     = "small"

  validation {
    condition     = contains(["small", "medium", "large"], var.size)
    error_message = "size must be small, medium or large."
  }
}

variable "ttl_attribute" {
  description = "Optional attribute holding an expiry epoch."
  type        = string
  default     = null
}

variable "point_in_time_recovery" {
  description = "Enable point-in-time recovery."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags on every resource. The platform sets team, cost-center, request-id and managed-by."
  type        = map(string)

  validation {
    condition     = alltrue([for k in ["team", "cost-center", "request-id", "managed-by"] : contains(keys(var.tags), k)])
    error_message = "tags must include team, cost-center, request-id and managed-by."
  }

  validation {
    condition     = lookup(var.tags, "managed-by", "") == "platform"
    error_message = "tags[\"managed-by\"] must be \"platform\"."
  }
}
