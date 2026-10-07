output "state_bucket" {
  description = "Bucket name to put in each environment's backend.tf."
  value       = aws_s3_bucket.state.id
}

output "lock_table" {
  description = "DynamoDB table name to put in each environment's backend.tf."
  value       = aws_dynamodb_table.locks.name
}

output "backend_config" {
  description = "Ready-to-paste backend block."
  value       = <<-EOT
    terraform {
      backend "s3" {
        bucket         = "${aws_s3_bucket.state.id}"
        key            = "<env>/terraform.tfstate"
        region         = "${var.region}"
        dynamodb_table = "${aws_dynamodb_table.locks.name}"
        encrypt        = true
      }
    }
  EOT
}

output "github_actions_role_arn" {
  description = "Set this as the AWS_ROLE_ARN repository secret in GitHub."
  value       = aws_iam_role.github_actions.arn
}
