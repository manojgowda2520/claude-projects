# ---------------------------------------------------------------------------
# All tables on-demand. At product scale these cost pennies; revisit only if a
# single account starts driving sustained six-figure daily volume.
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "accounts" {
  name         = "mf-accounts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "account_id"

  attribute {
    name = "account_id"
    type = "S"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

resource "aws_dynamodb_table" "keys" {
  name         = "mf-keys"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "key_hash"

  attribute {
    name = "key_hash"
    type = "S"
  }
  attribute {
    name = "account_id"
    type = "S"
  }

  # Lets the dashboard list one customer's keys without scanning the table.
  global_secondary_index {
    name            = "by-account"
    hash_key        = "account_id"
    projection_type = "ALL"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

# The customer's balance. One row per account, mutated only by conditional
# atomic updates so concurrent sends cannot overdraw it.
resource "aws_dynamodb_table" "credits" {
  name         = "mf-credits"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "account_id"

  attribute {
    name = "account_id"
    type = "S"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

# Every credit that ever enters an account. Append-only, never expires - this
# is the record an invoice or a dispute is settled from.
resource "aws_dynamodb_table" "ledger" {
  name         = "mf-ledger"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "account_id"
  range_key    = "sk" # <iso timestamp>#<random>

  attribute {
    name = "account_id"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

# Outstanding one-time codes. Holds an HMAC of the code, never the code.
resource "aws_dynamodb_table" "otp" {
  name         = "mf-otp"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "request_id"

  attribute {
    name = "request_id"
    type = "S"
  }

  # TTL reclaims rows, but expiry is enforced on read as well - TTL deletion
  # can lag by minutes and must never be the only check.
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  server_side_encryption { enabled = true }
}

# Per-recipient send counters, the anti-OTP-bombing control. Recipient
# addresses are hashed, so this table holds no readable contact list.
resource "aws_dynamodb_table" "otp_rate" {
  name         = "mf-otp-rate"
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
  server_side_encryption { enabled = true }
}

resource "aws_dynamodb_table" "idempotency" {
  name         = "mf-idempotency"
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
  server_side_encryption { enabled = true }
}

resource "aws_dynamodb_table" "activity" {
  name         = "mf-activity"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk" # acct#<account_id>#<YYYY-MM-DD>
  range_key    = "sk" # <epoch_ms>#<msgid>

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  server_side_encryption { enabled = true }
}
