# A DynamoDB table with encryption at rest and point-in-time recovery.
# Capacity comes from the size, so a first table needs no tuning.

locals {
  capacity = {
    small  = { billing = "PAY_PER_REQUEST", read = null, write = null }
    medium = { billing = "PROVISIONED", read = 5, write = 5 }
    large  = { billing = "PROVISIONED", read = 25, write = 25 }
  }[var.size]
}

resource "aws_dynamodb_table" "this" {
  name           = var.name
  billing_mode   = local.capacity.billing
  read_capacity  = local.capacity.read
  write_capacity = local.capacity.write
  hash_key       = var.hash_key
  range_key      = var.range_key

  attribute {
    name = var.hash_key
    type = var.hash_key_type
  }

  dynamic "attribute" {
    for_each = var.range_key == null ? [] : [var.range_key]
    content {
      name = attribute.value
      type = var.range_key_type
    }
  }

  dynamic "ttl" {
    for_each = var.ttl_attribute == null ? [] : [var.ttl_attribute]
    content {
      attribute_name = ttl.value
      enabled        = true
    }
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  server_side_encryption {
    enabled = true
  }

  tags = var.tags
}
