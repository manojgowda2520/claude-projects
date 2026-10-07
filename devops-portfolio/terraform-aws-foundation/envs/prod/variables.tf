variable "project" {
  description = "Project name used as a prefix for every resource."
  type        = string
  default     = "tf-foundation"
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "ap-south-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
}

variable "availability_zones" {
  description = "AZs to spread subnets across."
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "CIDRs for public subnets."
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "CIDRs for private subnets."
  type        = list(string)
}

variable "enable_nat_gateway" {
  description = "Create a NAT gateway. Costs money; keep false unless needed."
  type        = bool
  default     = false
}

variable "enable_flow_logs" {
  description = "Ship VPC flow logs to CloudWatch."
  type        = bool
  default     = false
}

variable "instance_type" {
  description = "EC2 instance type for the app node."
  type        = string
  default     = "t3.micro"
}

variable "instance_count" {
  description = "How many app instances to run."
  type        = number
  default     = 1
}

variable "admin_cidr" {
  description = "Your public IP as a /32, allowed to reach HTTP on the app node."
  type        = string
}
