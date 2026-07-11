# ── SnapEvent — Serverless AWS Infrastructure (Dev) ───────────────────────────

terraform {
  backend "s3" {
    bucket       = "snapevent9911-terraform-state"
    key          = "dev/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true # S3 native locking — no DynamoDB table needed
  }
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = "snapevent", Environment = "dev", ManagedBy = "terraform" }
  }
}

# ── DynamoDB ──────────────────────────────────────────────────────────────────
module "dynamodb" {
  source = "../../modules/dynamodb"
  env    = var.env
}

# ── S3 (photos) ──────────────────────────────────────────────────────────────
module "storage" {
  source           = "../../modules/storage"
  env              = var.env
  photo_expiry_days = 30
}

# ── ECR ───────────────────────────────────────────────────────────────────────
module "ecr" {
  source = "../../modules/ecr"
  env    = var.env
}

# ── SES ───────────────────────────────────────────────────────────────────────
module "ses" {
  source       = "../../modules/ses"
  sender_email = var.ses_sender_email
}

# ── Lambda (API + Cleanup) ────────────────────────────────────────────────────
module "lambda" {
  source = "../../modules/lambda"

  env                 = var.env
  aws_region          = var.aws_region
  ecr_repository_url  = module.ecr.repository_url
  image_tag           = var.image_tag
  dynamodb_table_name = module.dynamodb.table_name
  dynamodb_table_arn  = module.dynamodb.table_arn
  s3_bucket_name      = module.storage.bucket_name
  s3_bucket_arn       = module.storage.bucket_arn
  ses_sender_email    = module.ses.sender_email
  ses_sender_arn      = module.ses.sender_arn
  base_url            = module.api_gateway.api_url
}

# ── API Gateway ───────────────────────────────────────────────────────────────
module "api_gateway" {
  source = "../../modules/api-gateway"

  env                  = var.env
  lambda_function_name = module.lambda.api_function_name
  lambda_invoke_arn    = module.lambda.api_invoke_arn
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "api_url"        { value = module.api_gateway.api_url }
output "ecr_repository" { value = module.ecr.repository_url }
output "dynamodb_table" { value = module.dynamodb.table_name }
output "s3_bucket"      { value = module.storage.bucket_name }
