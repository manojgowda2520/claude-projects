output "instance_id" {
  description = "ID of the EC2 instance."
  value       = aws_instance.this.id
}

output "private_ip" {
  description = "Private IP of the instance."
  value       = aws_instance.this.private_ip
}

output "public_ip" {
  description = "Public IP of the instance, if the subnet assigns one."
  value       = aws_instance.this.public_ip
}

output "iam_role_name" {
  description = "Name of the instance IAM role."
  value       = aws_iam_role.this.name
}
