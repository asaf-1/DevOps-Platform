variable "name" {
  description = "Namespace name. DNS label, 3 to 40 characters."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{1,38}[a-z0-9])$", var.name))
    error_message = "name must be a DNS label of 3 to 40 characters."
  }
}

variable "size" {
  description = "Quota size: small, medium or large."
  type        = string
  default     = "small"

  validation {
    condition     = contains(["small", "medium", "large"], var.size)
    error_message = "size must be small, medium or large."
  }
}

variable "tags" {
  description = "Applied as labels. The platform sets team, cost-center, request-id and managed-by."
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
