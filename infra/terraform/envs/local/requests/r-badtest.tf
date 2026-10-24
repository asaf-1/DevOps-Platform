# Negative check for the policy gate: a hand-edited request that makes the
# bucket public. CI must refuse it. This PR is never merged.
module "r-badtest" {
  source     = "../../../modules/s3-bucket"
  name       = "badtest-public"
  versioning = true
  retention  = "30d"
  tags = {
    "team"        = "web"
    "cost-center" = "cc-100"
    "request-id"  = "r-badtest"
    "managed-by"  = "platform"
  }
}

resource "aws_s3_bucket_acl" "badtest_public" {
  bucket = module.r-badtest.bucket_id
  acl    = "public-read"
}

output "r-badtest" {
  value = module.r-badtest
}
