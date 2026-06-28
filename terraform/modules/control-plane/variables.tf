variable "env"                  { type = string }
variable "aws_region"           { type = string; default = "us-east-1" }
variable "cluster_arn"          { type = string }
variable "cluster_name"         { type = string }
variable "execution_role_arn"   { type = string }
variable "task_role_arn"        { type = string }
variable "private_subnet_ids"   { type = list(string) }
variable "sg_control_plane_id"  { type = string }
variable "sg_rds_id"            { type = string }
variable "target_group_arn"     { type = string }
variable "s3_bucket"            { type = string }
variable "efs_id"               { type = string }
variable "image_url"            { type = string }
variable "image_tag"            { type = string; default = "latest" }
variable "db_instance_class"    { type = string; default = "db.t3.micro" }
variable "base_url"             { type = string }
variable "smtp_user"            { type = string; sensitive = true }
variable "smtp_pass"            { type = string; sensitive = true }
variable "event_task_definition"{ type = string }
variable "event_sg_id"          { type = string }
