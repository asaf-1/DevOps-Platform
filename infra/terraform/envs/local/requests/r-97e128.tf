# Request r-97e128: s3-bucket "demo-uploads" for team web.
# Rendered by the platform API from platform/catalog/s3-bucket/request.tf.j2.
# Do not edit by hand: change the request, or the module, and re-render.
module "r-97e128" {
  source = "../../../modules/s3-bucket"

  name       = "demo-uploads"
  versioning = true
  retention  = "90d"

  tags = {
    "team"        = "web"
    "cost-center" = "cc-100"
    "request-id"  = "r-97e128"
    "managed-by"  = "platform"
  }
}

output "r-97e128" {
  description = "Outputs of request r-97e128"
  value       = module.r-97e128
}
