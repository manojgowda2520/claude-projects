# GitHub Actions authenticates to AWS through OIDC. GitHub mints a short-lived
# token, AWS trades it for temporary credentials, and no long-lived access key
# ever exists to be leaked from repository secrets.

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  # AWS verifies GitHub's certificate against its own trust store, but the
  # provider API still requires a thumbprint to be present.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scope the trust to this repository only. Without this condition any
    # GitHub Actions workflow in the world could assume the role.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for ref in var.github_allowed_refs : "repo:${var.github_repository}:${ref}"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project}-github-actions"
  description        = "Assumed by GitHub Actions to plan and apply Terraform"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json

  max_session_duration = 3600
}

# Terraform needs broad rights to build a VPC, EC2 and S3, so this is scoped by
# service rather than by action. Tightening it further is tracked in the README.
resource "aws_iam_role_policy_attachment" "github_actions" {
  for_each = toset(var.github_role_policy_arns)

  role       = aws_iam_role.github_actions.name
  policy_arn = each.value
}

# Access to the state backend is granted explicitly rather than inherited.
data "aws_iam_policy_document" "state_access" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
    ]
    resources = [aws_dynamodb_table.locks.arn]
  }
}

resource "aws_iam_role_policy" "state_access" {
  name   = "${var.project}-tfstate-access"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.state_access.json
}
