variable "project" {
  description = "Project name, used to name the state bucket and lock table."
  type        = string
  default     = "tf-foundation"
}

variable "region" {
  description = "AWS region for the state backend."
  type        = string
  default     = "ap-south-1"
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set false if the account already has one - AWS allows only a single provider per URL."
  type        = bool
  default     = true
}

variable "github_repository" {
  description = "Repository allowed to assume the CI role, as owner/name."
  type        = string
  default     = "OWNER/terraform-aws-foundation"
}

variable "github_allowed_refs" {
  description = "Which refs of that repository may assume the role."
  type        = list(string)
  default     = ["ref:refs/heads/main", "pull_request"]
}

variable "github_role_policy_arns" {
  description = "Managed policies attached to the CI role."
  type        = list(string)
  default = [
    "arn:aws:iam::aws:policy/AmazonVPCFullAccess",
    "arn:aws:iam::aws:policy/AmazonEC2FullAccess",
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "arn:aws:iam::aws:policy/IAMFullAccess",
  ]
}
