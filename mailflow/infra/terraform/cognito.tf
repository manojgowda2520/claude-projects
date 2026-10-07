# ---------------------------------------------------------------------------
# Passwordless sign-in. There is no password and no sign-up form: a customer
# types their email, we email a code, they type it back. The first login
# creates the account.
#
# Cognito's built-in email sender is unbranded, rate-limited and lands in spam,
# so it sends nothing here - the CreateAuthChallenge trigger delivers the code
# through our own SES identity instead.
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool" "main" {
  name                     = "mailflow"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = "ACTIVE"

  # Never used - every account is created by the auth service with a random
  # permanent password that nobody, including the account owner, ever sees.
  password_policy {
    minimum_length    = 16
    require_lowercase = true
    require_numbers   = true
    require_uppercase = true
    require_symbols   = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  lambda_config {
    define_auth_challenge          = aws_lambda_function.svc["authtriggers"].arn
    create_auth_challenge          = aws_lambda_function.svc["authtriggers"].arn
    verify_auth_challenge_response = aws_lambda_function.svc["authtriggers"].arn
  }

  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }
}

resource "aws_lambda_permission" "cognito_triggers" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.svc["authtriggers"].function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.main.arn
}

resource "aws_cognito_user_pool_domain" "main" {
  # Must be globally unique across all of Cognito.
  domain       = "mailflow-${local.account_id}"
  user_pool_id = aws_cognito_user_pool.main.id
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "mailflow-web"
  user_pool_id = aws_cognito_user_pool.main.id

  # Public SPA client, no secret. CUSTOM_AUTH is the only sign-in path;
  # USER_PASSWORD_AUTH is deliberately absent so a leaked random password
  # cannot be used even if one were somehow discovered.
  generate_secret = false
  explicit_auth_flows = [
    "ALLOW_CUSTOM_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  supported_identity_providers = ["COGNITO"]

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}
