# Request r-8f0d8f: k8s-namespace "bank" for team bank.
# Rendered by the platform API from platform/catalog/k8s-namespace/request.tf.j2.
# Do not edit by hand: change the request, or the module, and re-render.
module "r-8f0d8f" {
  source = "../../../modules/k8s-namespace"

  name = "bank"
  size = "small"

  tags = {
    "team"        = "bank"
    "cost-center" = "cc-200"
    "request-id"  = "r-8f0d8f"
    "managed-by"  = "platform"
  }
}

output "r-8f0d8f" {
  description = "Outputs of request r-8f0d8f"
  value       = module.r-8f0d8f
}
