# ---------------------------------------------------------------------------
# Lambdas. Each bundle is the service directory plus the shared modules, which
# build.sh stages into build/<service>/ before terraform runs.
# ---------------------------------------------------------------------------

locals {
  services = ["console", "authorizer", "mailer", "otp", "auth", "authtriggers"]
}

# Rotating this invalidates every outstanding OTP, which is the correct
# behaviour if it is ever suspected of leaking.
resource "random_password" "otp_secret" {
  length  = 48
  special = false
}

data "archive_file" "svc" {
  for_each    = toset(local.services)
  type        = "zip"
  source_dir  = "${local.build_dir}/${each.key}"
  output_path = "${local.build_dir}/${each.key}.zip"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "svc" {
  for_each           = toset(local.services)
  name               = "mf-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "basic" {
  for_each   = toset(local.services)
  role       = aws_iam_role.svc[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- console: owns accounts, keys and credit grants ------------------------
data "aws_iam_policy_document" "console" {
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.accounts.arn, aws_dynamodb_table.keys.arn,
    aws_dynamodb_table.credits.arn, aws_dynamodb_table.ledger.arn]
  }
  statement {
    actions = ["dynamodb:Query"]
    resources = ["${aws_dynamodb_table.keys.arn}/index/by-account",
      aws_dynamodb_table.activity.arn, aws_dynamodb_table.ledger.arn]
  }
}

# --- authorizer: reads only what it needs to answer yes or no --------------
data "aws_iam_policy_document" "authorizer" {
  statement {
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.keys.arn, aws_dynamodb_table.accounts.arn]
  }
}

# --- mailer: sends, spends credits, logs. Cannot touch accounts or keys ----
data "aws_iam_policy_document" "mailer" {
  statement {
    sid     = "SendAsOurAddressOnly"
    actions = ["ses:SendEmail"]
    resources = [
      "arn:aws:ses:${var.region}:${local.account_id}:identity/${var.root_domain}",
      "arn:aws:ses:${var.region}:${local.account_id}:configuration-set/${var.config_set}",
    ]
    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.from_address]
    }
  }
  statement {
    actions   = ["dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.idempotency.arn, aws_dynamodb_table.activity.arn]
  }
  # No PutItem on the ledger: spending must never be able to forge a grant.
  statement {
    actions   = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
    resources = [aws_dynamodb_table.credits.arn]
  }
}

# --- otp: same sending rights, plus its own two tables ---------------------
data "aws_iam_policy_document" "otp" {
  statement {
    sid     = "SendAsOurAddressOnly"
    actions = ["ses:SendEmail"]
    resources = [
      "arn:aws:ses:${var.region}:${local.account_id}:identity/${var.root_domain}",
      "arn:aws:ses:${var.region}:${local.account_id}:configuration-set/${var.config_set}",
    ]
    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.from_address]
    }
  }
  statement {
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.otp.arn, aws_dynamodb_table.otp_rate.arn]
  }
  statement {
    actions   = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
    resources = [aws_dynamodb_table.credits.arn]
  }
}

# --- auth: creates Cognito users on first sign-in, nothing else -----------
data "aws_iam_policy_document" "auth" {
  statement {
    actions = ["cognito-idp:AdminGetUser", "cognito-idp:AdminCreateUser",
    "cognito-idp:AdminSetUserPassword"]
    resources = [aws_cognito_user_pool.main.arn]
  }
  statement {
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.otp_rate.arn]
  }
}

# --- authtriggers: may only email the login code --------------------------
data "aws_iam_policy_document" "authtriggers" {
  statement {
    sid     = "SendLoginCodesOnly"
    actions = ["ses:SendEmail"]
    resources = [
      "arn:aws:ses:${var.region}:${local.account_id}:identity/${var.root_domain}",
      "arn:aws:ses:${var.region}:${local.account_id}:configuration-set/${var.config_set}",
    ]
    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.from_address]
    }
  }
}

resource "aws_iam_role_policy" "svc" {
  for_each = {
    console      = data.aws_iam_policy_document.console.json
    authorizer   = data.aws_iam_policy_document.authorizer.json
    mailer       = data.aws_iam_policy_document.mailer.json
    otp          = data.aws_iam_policy_document.otp.json
    auth         = data.aws_iam_policy_document.auth.json
    authtriggers = data.aws_iam_policy_document.authtriggers.json
  }
  name   = "mf-${each.key}"
  role   = aws_iam_role.svc[each.key].id
  policy = each.value
}

locals {
  credit_env = {
    CREDITS_TABLE = aws_dynamodb_table.credits.name
    LEDGER_TABLE  = aws_dynamodb_table.ledger.name
  }

  env = {
    console = merge(local.credit_env, {
      ACCOUNTS_TABLE = aws_dynamodb_table.accounts.name
      KEYS_TABLE     = aws_dynamodb_table.keys.name
      ACTIVITY_TABLE = aws_dynamodb_table.activity.name
      API_BASE       = "https://${var.api_domain}"
      FROM_ADDRESS   = var.from_address
      ROOT_DOMAIN    = var.root_domain
    })
    authorizer = {
      KEYS_TABLE     = aws_dynamodb_table.keys.name
      ACCOUNTS_TABLE = aws_dynamodb_table.accounts.name
    }
    mailer = merge(local.credit_env, {
      IDEMPOTENCY_TABLE = aws_dynamodb_table.idempotency.name
      ACTIVITY_TABLE    = aws_dynamodb_table.activity.name
      FROM_ADDRESS      = var.from_address
      CONFIG_SET        = var.config_set
    })
    otp = merge(local.credit_env, {
      OTP_TABLE      = aws_dynamodb_table.otp.name
      OTP_RATE_TABLE = aws_dynamodb_table.otp_rate.name
      OTP_SECRET     = random_password.otp_secret.result
      FROM_ADDRESS   = var.from_address
      CONFIG_SET     = var.config_set
    })
    auth = {
      USER_POOL_ID   = aws_cognito_user_pool.main.id
      OTP_RATE_TABLE = aws_dynamodb_table.otp_rate.name
      OTP_SECRET     = random_password.otp_secret.result
    }
    authtriggers = {
      FROM_ADDRESS = var.from_address
      CONFIG_SET   = var.config_set
      OTP_SECRET   = random_password.otp_secret.result
    }
  }
  timeouts = { console = 15, authorizer = 5, mailer = 15, otp = 15, auth = 10, authtriggers = 10 }
  memory   = { console = 512, authorizer = 256, mailer = 512, otp = 512, auth = 256, authtriggers = 256 }
}

resource "aws_lambda_function" "svc" {
  for_each         = toset(local.services)
  function_name    = "mf-${each.key}"
  role             = aws_iam_role.svc[each.key].arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  timeout          = local.timeouts[each.key]
  memory_size      = local.memory[each.key]
  filename         = data.archive_file.svc[each.key].output_path
  source_code_hash = data.archive_file.svc[each.key].output_base64sha256

  environment {
    variables = local.env[each.key]
  }
}

resource "aws_cloudwatch_log_group" "svc" {
  for_each          = toset(local.services)
  name              = "/aws/lambda/mf-${each.key}"
  retention_in_days = 30
}
