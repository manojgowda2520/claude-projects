# terraform init -backend-config=backend.hcl
# Bucket name comes from `terraform output state_bucket` in ../../bootstrap.
bucket = "tf-foundation-tfstate-REPLACE_WITH_ACCOUNT_ID"
