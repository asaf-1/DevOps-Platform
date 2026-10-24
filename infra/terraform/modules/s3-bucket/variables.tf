variable "name" {
  description = "Bucket name. Lowercase letters, digits and hyphens, 3 to 40 characters."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{3,40}$", var.name))
    error_message = "name must match ^[a-z0-9-]{3,40}$."
  }
}

variable "versioning" {
  description = "Keep previous versions of overwritten and deleted objects."
  type        = bool
  default     = true
}

variable "retention" {
  description = "How long noncurrent object versions are kept: none, 30d, 90d or 365d."
  type        = string
  default     = "90d"

  validation {
    condition     = contains(["none", "30d", "90d", "365d"], var.retention)
    error_message = "retention must be one of none, 30d, 90d, 365d."
  }
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
