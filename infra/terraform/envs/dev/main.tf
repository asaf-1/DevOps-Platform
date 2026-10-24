module "requests" {
  source = "./requests"
}

output "requests" {
  description = "Outputs of every applied request, keyed by request id."
  value       = module.requests
}
