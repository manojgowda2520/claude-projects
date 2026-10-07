data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "mailer" {
  name               = "email-api-mailer"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role" "authorizer" {
  name               = "email-api-authorizer"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "mailer_basic" {
  role       = aws_iam_role.mailer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "authorizer_basic" {
  role       = aws_iam_role.authorizer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "mailer" {
  statement {
    sid     = "SendThroughOurIdentityOnly"
    actions = ["ses:SendEmail"]
    resources = [
      aws_sesv2_email_identity.root.arn,
      "arn:aws:ses:${var.region}:${data.aws_caller_identity.current.account_id}:configuration-set/${aws_sesv2_configuration_set.main.configuration_set_name}",
    ]
    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      # Every From address the API is allowed to use. Add rows here as you add
      # tenants; this is the hard backstop behind the per-key allowlist.
      values = [
        "noreply@${var.root_domain}",
        "alerts@${var.root_domain}",
        "billing@${var.root_domain}",
        "support@${var.root_domain}",
      ]
    }
  }

  statement {
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.idempotency.arn]
  }
}

resource "aws_iam_role_policy" "mailer" {
  name   = "email-api-mailer"
  role   = aws_iam_role.mailer.id
  policy = data.aws_iam_policy_document.mailer.json
}

data "aws_iam_policy_document" "authorizer" {
  statement {
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.api_keys.arn]
  }
}

resource "aws_iam_role_policy" "authorizer" {
  name   = "email-api-authorizer"
  role   = aws_iam_role.authorizer.id
  policy = data.aws_iam_policy_document.authorizer.json
}
