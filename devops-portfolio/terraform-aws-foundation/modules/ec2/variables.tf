variable "project" {
  description = "Project name."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, prod)."
  type        = string
}

variable "name" {
  description = "Short role name for this instance, e.g. app or runner."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.micro"
}

variable "architecture" {
  description = "CPU architecture used to pick the AMI: x86_64 or arm64."
  type        = string
  default     = "x86_64"

  validation {
    condition     = contains(["x86_64", "arm64"], var.architecture)
    error_message = "architecture must be x86_64 or arm64."
  }
}

variable "subnet_id" {
  description = "Subnet to launch the instance in."
  type        = string
}

variable "security_group_ids" {
  description = "Security groups to attach."
  type        = list(string)
}

variable "root_volume_size" {
  description = "Root EBS volume size in GB. The free tier covers 30 GB total."
  type        = number
  default     = 10
}

variable "user_data" {
  description = "Cloud-init user data script."
  type        = string
  default     = null
}

variable "detailed_monitoring" {
  description = "Enable 1-minute CloudWatch metrics. Not free tier."
  type        = bool
  default     = false
}

variable "additional_policy_arns" {
  description = "Extra IAM policy ARNs to attach to the instance role."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Extra tags applied to every resource."
  type        = map(string)
  default     = {}
}
