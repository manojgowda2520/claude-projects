terraform {
  required_version = ">= 1.6"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.60" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "mailflow", ManagedBy = "terraform" }
  }
}

variable "region" {
  description = "Must be the region SES production access was granted in."
  type        = string
  default     = "us-east-1"
}

variable "root_domain" {
  type    = string
  default = "ohteapea.com"
}

variable "api_domain" {
  # Deliberately not api.ohteapea.com - that hostname already serves the
  # internal email-api and the teams using it.
  description = "Product API hostname."
  type        = string
  default     = "send.ohteapea.com"
}

variable "app_domain" {
  description = "Where the customer dashboard is served."
  type        = string
  default     = "app.ohteapea.com"
}

variable "from_address" {
  description = "Every customer's mail is sent from this address."
  type        = string
  default     = "no-reply@ohteapea.com"
}

variable "config_set" {
  description = "Existing SES configuration set to send through."
  type        = string
  default     = "email-api"
}

data "aws_caller_identity" "current" {}

data "aws_route53_zone" "root" {
  name         = "${var.root_domain}."
  private_zone = false
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  # Shared code copied into each bundle at build time; see build.sh.
  build_dir = "${path.module}/build"
}
