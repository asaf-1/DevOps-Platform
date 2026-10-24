variable "name" {
  description = "Role name. Lowercase letters, digits and hyphens, 3 to 40 characters."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{3,40}$", var.name))
    error_message = "name must match ^[a-z0-9-]{3,40}$."
  }
}

variable "description" {
  description = "What the role is for."
  type        = string
  default     = "Managed by the platform"
}

variable "trusted_services" {
  description = "AWS service principals allowed to assume the role, e.g. lambda.amazonaws.com."
  type        = list(string)

  validation {
    condition     = length(var.trusted_services) > 0
    error_message = "trusted_services must name at least one service principal."
  }
}

variable "managed_policy_arns" {
  description = "Managed policies to attach."
  type        = list(string)
  default     = []
}

variable "inline_policy_json" {
  description = "Optional inline policy document (JSON)."
  type        = string
  default     = null
}

variable "max_session_duration" {
  description = "Maximum session duration in seconds."
  type        = number
  default     = 3600
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
