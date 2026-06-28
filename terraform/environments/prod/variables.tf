variable "env"         { type = string; default = "prod" }
variable "aws_region"  { type = string; default = "us-east-1" }
variable "image_tag"   { type = string }
variable "domain_name" { type = string }
variable "smtp_user"   { type = string; sensitive = true }
variable "smtp_pass"   { type = string; sensitive = true }
