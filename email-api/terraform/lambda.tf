data "archive_file" "mailer" {
  type        = "zip"
  source_dir  = "${path.module}/../src/mailer"
  output_path = "${path.module}/build/mailer.zip"
}

data "archive_file" "authorizer" {
  type        = "zip"
  source_dir  = "${path.module}/../src/authorizer"
  output_path = "${path.module}/build/authorizer.zip"
}

resource "aws_lambda_function" "mailer" {
  function_name    = "email-api-mailer"
  role             = aws_iam_role.mailer.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  timeout          = 15
  memory_size      = 512
  filename         = data.archive_file.mailer.output_path
  source_code_hash = data.archive_file.mailer.output_base64sha256

  environment {
    variables = {
      IDEMPOTENCY_TABLE = aws_dynamodb_table.idempotency.name
      CONFIG_SET        = aws_sesv2_configuration_set.main.configuration_set_name
      ROOT_DOMAIN       = var.root_domain
    }
  }
}

resource "aws_lambda_function" "authorizer" {
  function_name    = "email-api-authorizer"
  role             = aws_iam_role.authorizer.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  timeout          = 5
  memory_size      = 256
  filename         = data.archive_file.authorizer.output_path
  source_code_hash = data.archive_file.authorizer.output_base64sha256

  environment {
    variables = {
      KEYS_TABLE = aws_dynamodb_table.api_keys.name
    }
  }
}

resource "aws_cloudwatch_log_group" "mailer" {
  name              = "/aws/lambda/${aws_lambda_function.mailer.function_name}"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "authorizer" {
  name              = "/aws/lambda/${aws_lambda_function.authorizer.function_name}"
  retention_in_days = 30
}
