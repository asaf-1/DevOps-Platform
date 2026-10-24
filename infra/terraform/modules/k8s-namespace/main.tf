# A namespace with a ResourceQuota and a LimitRange sized by t-shirt size.
# Labels carry the same four mandatory keys as cloud resources carry tags.

locals {
  quota = {
    small  = { cpu = "2", memory = "4Gi", pods = "20" }
    medium = { cpu = "4", memory = "8Gi", pods = "50" }
    large  = { cpu = "8", memory = "16Gi", pods = "100" }
  }[var.size]
}

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name   = var.name
    labels = var.tags
  }
}

resource "kubernetes_resource_quota_v1" "this" {
  metadata {
    name      = "platform-quota"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  spec {
    hard = {
      "requests.cpu"    = local.quota.cpu
      "requests.memory" = local.quota.memory
      "limits.cpu"      = local.quota.cpu
      "limits.memory"   = local.quota.memory
      "pods"            = local.quota.pods
    }
  }
}

resource "kubernetes_limit_range_v1" "this" {
  metadata {
    name      = "platform-defaults"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  spec {
    limit {
      type = "Container"
      default = {
        cpu    = "250m"
        memory = "256Mi"
      }
      default_request = {
        cpu    = "50m"
        memory = "64Mi"
      }
    }
  }
}
