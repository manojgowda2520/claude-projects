output "endpoint" {
  value = "https://${var.api_domain}/v1/send"
}

output "api_keys_table" {
  value = aws_dynamodb_table.api_keys.name
}

output "raw_invoke_url" {
  description = "Direct execute-api URL, useful before DNS propagates."
  value       = aws_apigatewayv2_stage.default.invoke_url
}
