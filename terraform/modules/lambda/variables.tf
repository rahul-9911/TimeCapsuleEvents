variable "env" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "ecr_repository_url" {
  type        = string
  description = "ECR repository URL for Lambda container image"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "dynamodb_table_name" {
  type = string
}

variable "dynamodb_table_arn" {
  type = string
}

variable "s3_bucket_name" {
  type = string
}

variable "s3_bucket_arn" {
  type = string
}

variable "ses_sender_email" {
  type = string
}

variable "ses_sender_arn" {
  type = string
}

variable "base_url" {
  type        = string
  description = "Public-facing base URL (API Gateway invoke URL)"
}
