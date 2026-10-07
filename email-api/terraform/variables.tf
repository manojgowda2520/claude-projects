variable "region" {
  description = "Region for API Gateway, Lambda and SES. Must match where SES production access was granted."
  type        = string
  default     = "ap-south-1"
}

variable "root_domain" {
  description = "Domain verified in SES and used for the From addresses."
  type        = string
  default     = "ohteapea.com"
}

variable "api_domain" {
  description = "Public hostname of the email API."
  type        = string
  default     = "api.ohteapea.com"
}

variable "mail_from_subdomain" {
  description = "Custom MAIL FROM subdomain. Keeps bounce reputation off the apex."
  type        = string
  default     = "mail"
}

variable "throttle_rate" {
  description = "Steady-state requests/sec across all callers."
  type        = number
  default     = 25
}

variable "throttle_burst" {
  description = "Burst capacity across all callers."
  type        = number
  default     = 50
}

variable "tags" {
  type = map(string)
  default = {
    Project = "email-api"
    Owner   = "platform"
  }
}
