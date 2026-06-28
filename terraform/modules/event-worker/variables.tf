variable "env"                { type = string }
variable "aws_region"         { type = string; default = "us-east-1" }
variable "execution_role_arn" { type = string }
variable "task_role_arn"      { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "sg_event_worker_id" { type = string }
variable "s3_bucket"          { type = string }
variable "efs_id"             { type = string }
variable "image_url"          { type = string }
variable "image_tag"          { type = string; default = "latest" }
