variable "project" {
  description = "Project name, used as a prefix for all resource names."
  type        = string
}

variable "environment" {
  description = "Environment this VPC belongs to (dev, prod)."
  type        = string
}

variable "cidr_block" {
  description = "CIDR block for the VPC."
  type        = string

  validation {
    condition     = can(cidrhost(var.cidr_block, 0))
    error_message = "cidr_block must be a valid IPv4 CIDR, e.g. 10.0.0.0/16."
  }
}

variable "availability_zones" {
  description = "AZs to spread subnets across."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) > 0
    error_message = "At least one availability zone is required."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDRs for public subnets, one per subnet."
  type        = list(string)
  default     = []
}

variable "private_subnet_cidrs" {
  description = "CIDRs for private subnets, one per subnet."
  type        = list(string)
  default     = []
}

variable "enable_nat_gateway" {
  description = "Create a NAT gateway so private subnets reach the internet. Costs roughly USD 32/month, so it is off by default."
  type        = bool
  default     = false
}

variable "enable_flow_logs" {
  description = "Ship rejected-traffic VPC flow logs to CloudWatch."
  type        = bool
  default     = false
}

variable "flow_logs_retention_days" {
  description = "CloudWatch retention for VPC flow logs."
  type        = number
  default     = 7
}

variable "tags" {
  description = "Extra tags applied to every resource."
  type        = map(string)
  default     = {}
}
