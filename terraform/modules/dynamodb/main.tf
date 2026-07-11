# ── DynamoDB — Single table for all SnapEvent data ────────────────────────────

resource "aws_dynamodb_table" "main" {
  name         = "snapevent-${var.env}"
  billing_mode = "PAY_PER_REQUEST" # On-demand — $0 when idle

  hash_key  = "PK"
  range_key = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  # GSI for organiser → events lookup
  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  # Enable TTL for auto-expiry of sessions and auth tokens
  ttl {
    attribute_name = "ttl_epoch"
    enabled        = true
  }

  tags = {
    Name = "snapevent-${var.env}"
  }
}
