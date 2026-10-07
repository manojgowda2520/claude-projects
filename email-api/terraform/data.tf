# ---------------------------------------------------------------------------
# API key registry. One row per key. The raw key is never stored - only its
# SHA-256 hash - so a table dump does not let anyone send mail.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "api_keys" {
  name         = "email-api-keys"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "key_hash"

  attribute {
    name = "key_hash"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# ---------------------------------------------------------------------------
# Idempotency ledger. A retried request with the same key is acknowledged but
# not re-sent. Rows self-expire after 24h.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "idempotency" {
  name         = "email-api-idempotency"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }
}
