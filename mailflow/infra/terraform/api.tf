# ---------------------------------------------------------------------------
# One HTTP API, two authorizers. Console routes take a Cognito JWT; the send
# route takes an API key. A dashboard session can never send mail, and an API
# key can never reach account settings.
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "main" {
  name          = "mailflow"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["https://${var.app_domain}", "http://localhost:8000"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["content-type", "authorization", "x-api-key"]
    max_age       = 3600
  }
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.web.id]
    issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  }
}

resource "aws_apigatewayv2_authorizer" "api_key" {
  api_id                            = aws_apigatewayv2_api.main.id
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.svc["authorizer"].invoke_arn
  identity_sources                  = ["$request.header.x-api-key"]
  name                              = "api-key"
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
  authorizer_result_ttl_in_seconds  = 300
}

resource "aws_apigatewayv2_integration" "console" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.svc["console"].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "mailer" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.svc["mailer"].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 20000
}

resource "aws_apigatewayv2_integration" "otp" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.svc["otp"].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 20000
}

locals {
  console_routes = [
    "GET /v1/console/me",
    "POST /v1/console/account",
    "GET /v1/console/credits",
    "POST /v1/console/checkout",
    "GET /v1/console/keys",
    "POST /v1/console/keys",
    "POST /v1/console/keys/toggle",
    "GET /v1/console/activity",
  ]
  otp_routes = ["POST /v1/otp/send", "POST /v1/otp/verify"]
}

resource "aws_apigatewayv2_route" "console" {
  for_each           = toset(local.console_routes)
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.console.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

resource "aws_apigatewayv2_route" "send" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /v1/send"
  target             = "integrations/${aws_apigatewayv2_integration.mailer.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.api_key.id
}

resource "aws_apigatewayv2_route" "otp" {
  for_each           = toset(local.otp_routes)
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.otp.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.api_key.id
}

# The only unauthenticated route in the product. Rate limited inside the
# handler, and it returns the same response whether or not the user existed.
resource "aws_apigatewayv2_integration" "auth" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.svc["auth"].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "auth_start" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /v1/auth/start"
  target    = "integrations/${aws_apigatewayv2_integration.auth.id}"
}

resource "aws_lambda_permission" "apigw" {
  for_each      = toset(["console", "mailer", "otp", "auth"])
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.svc[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_authorizer" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.svc["authorizer"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.api_key.id}"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/mailflow"
  retention_in_days = 30
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = 50
    throttling_burst_limit = 100
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId = "$context.requestId"
      routeKey  = "$context.routeKey"
      status    = "$context.status"
      latency   = "$context.responseLatency"
      account   = "$context.authorizer.account_id"
      error     = "$context.integrationErrorMessage"
    })
  }
}

# ---------------------------------------------------------------------------
# Custom domain for the product API. Regional certificate, same region as the
# API - unlike CloudFront, which insists on us-east-1.
# ---------------------------------------------------------------------------

resource "aws_acm_certificate" "api" {
  domain_name       = var.api_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "api_cert" {
  for_each = {
    for d in aws_acm_certificate.api.domain_validation_options :
    d.domain_name => { name = d.resource_record_name, type = d.resource_record_type, value = d.resource_record_value }
  }
  zone_id         = data.aws_route53_zone.root.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.value]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for r in aws_route53_record.api_cert : r.fqdn]
}

resource "aws_apigatewayv2_domain_name" "api" {
  domain_name = var.api_domain

  domain_name_configuration {
    certificate_arn = aws_acm_certificate_validation.api.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "api" {
  api_id      = aws_apigatewayv2_api.main.id
  domain_name = aws_apigatewayv2_domain_name.api.id
  stage       = aws_apigatewayv2_stage.default.id
}

resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = var.api_domain
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}
