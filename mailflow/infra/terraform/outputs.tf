output "dashboard_url" {
  value = "https://${var.app_domain}/"
}

output "send_endpoint" {
  description = "What customers POST to."
  value       = "https://${var.api_domain}/v1/send"
}

output "api_invoke_url" {
  description = "Raw execute-api URL, for testing before the custom domain is mapped."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "cognito_hosted_ui" {
  value = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com"
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "cloudfront_distribution_id" {
  description = "Needed to invalidate the cache after a dashboard deploy."
  value       = aws_cloudfront_distribution.web.id
}
