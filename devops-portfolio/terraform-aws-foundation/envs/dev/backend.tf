# Partial backend configuration. The bucket name contains the AWS account ID,
# so it is supplied at init time instead of being hardcoded:
#
#   terraform init -backend-config=backend.hcl
terraform {
  backend "s3" {
    key            = "dev/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "tf-foundation-tfstate-locks"
    encrypt        = true
  }
}
