variable "project" {
  description = "Project name, used as a prefix."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, prod)."
  type        = string
}

variable "name" {
  description = "Short name for this security group, e.g. web or bastion."
  type        = string
}

variable "description" {
  description = "Human-readable purpose of the security group."
  type        = string
  default     = "Managed by Terraform"
}

variable "vpc_id" {
  description = "VPC the security group belongs to."
  type        = string
}

variable "ingress_rules" {
  description = "Inbound rules. Each entry opens one port range to one CIDR."
  type = list(object({
    description = string
    from_port   = number
    to_port     = number
    protocol    = string
    cidr_ipv4   = string
  }))
  default = []

  validation {
    condition     = alltrue([for r in var.ingress_rules : r.cidr_ipv4 != "0.0.0.0/0" || r.from_port != 22])
    error_message = "Refusing to open SSH (port 22) to 0.0.0.0/0. Pass your own IP as a /32 instead."
  }
}

variable "tags" {
  description = "Extra tags applied to every resource."
  type        = map(string)
  default     = {}
}
