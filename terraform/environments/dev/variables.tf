variable "env"        { type = string; default = "dev" }
variable "aws_region" { type = string; default = "us-east-1" }
variable "image_tag"  { type = string; default = "latest" }
variable "smtp_user"  { type = string; sensitive = true }
variable "smtp_pass"  { type = string; sensitive = true }
