variable "owner" {
  description = "GitHub user or organisation that owns the repository."
  type        = string
  default     = "asaf-1"
}

variable "repository" {
  description = "Repository name (without the owner)."
  type        = string
  default     = "DevOps-Platform"
}

variable "reviewer" {
  description = "GitHub login that must approve deployments to the production environment."
  type        = string
  default     = "asaf-1"
}

variable "topics" {
  description = "Repository topics shown on GitHub."
  type        = list(string)
  default = [
    "platform-engineering",
    "internal-developer-platform",
    "kubernetes",
    "terraform",
    "argocd",
    "ai-agents",
    "mcp",
    "pydantic-ai",
    "kyverno",
    "opentelemetry",
  ]
}

variable "optional_secrets" {
  description = "Repository secrets that unlock optional features; their absence is reported, not fatal."
  type        = list(string)
  default     = ["ANTHROPIC_API_KEY", "INFRACOST_API_KEY"]
}
