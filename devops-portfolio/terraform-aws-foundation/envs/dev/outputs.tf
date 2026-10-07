output "vpc_id" {
  description = "ID of the VPC."
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = module.vpc.public_subnet_ids
}

output "app_public_ips" {
  description = "Public IPs of the application instances."
  value       = module.app[*].public_ip
}

output "app_instance_ids" {
  description = "Instance IDs, useful for aws ssm start-session."
  value       = module.app[*].instance_id
}

output "artifacts_bucket" {
  description = "Name of the artifacts bucket."
  value       = module.artifacts.bucket_id
}
