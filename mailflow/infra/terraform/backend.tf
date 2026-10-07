# State lives in S3, never on the machine running terraform. CloudShell wipes
# its home directory after 120 days of inactivity, and local state lost is
# infrastructure terraform can no longer manage.
#
# The bucket name is supplied at init time so this file holds no account id:
#   terraform init -backend-config="bucket=mailflow-tfstate-<account-id>"
terraform {
  backend "s3" {
    key          = "mailflow/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true # S3-native locking; no DynamoDB lock table needed
  }
}
