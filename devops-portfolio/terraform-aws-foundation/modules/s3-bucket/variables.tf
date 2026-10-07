variable "project" {
  description = "Project name."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, prod)."
  type        = string
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name."
  type        = string
}

variable "versioning_enabled" {
  description = "Keep previous versions of objects."
  type        = bool
  default     = true
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete a non-empty bucket. Safe for a lab, dangerous in production."
  type        = bool
  default     = false
}

variable "lifecycle_expiration_days" {
  description = "Days before noncurrent object versions are deleted. Null disables the lifecycle rule."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Extra tags applied to every resource."
  type        = map(string)
  default     = {}
}
