# Every developer request is one file under requests/. That folder is a
# child module so Terraform loads all of them; providers are inherited.
module "requests" {
  source = "./requests"
}

output "requests" {
  description = "Outputs of every applied request, keyed by request id."
  value       = module.requests
}
