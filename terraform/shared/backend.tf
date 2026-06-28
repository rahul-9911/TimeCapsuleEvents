# Remote state — run `terraform init` in each environment to initialise.
# Pre-requisite: create the S3 bucket and DynamoDB table manually once:
#   aws s3 mb s3://snapevent-terraform-state
#   aws dynamodb create-table --table-name snapevent-terraform-locks \
#     --attribute-definitions AttributeName=LockID,AttributeType=S \
#     --key-schema AttributeName=LockID,KeyType=HASH \
#     --billing-mode PAY_PER_REQUEST

terraform {
  backend "s3" {
    bucket         = "snapevent-terraform-state"
    key            = "placeholder"    # overridden per environment
    region         = "us-east-1"
    dynamodb_table = "snapevent-terraform-locks"
    encrypt        = true
  }
}
