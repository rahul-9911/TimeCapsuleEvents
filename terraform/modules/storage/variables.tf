variable "env"                 { type = string }
variable "vpc_id"              { type = string }
variable "private_subnet_ids"  { type = list(string) }
variable "sg_efs_id"           { type = string }
variable "s3_photos_lifecycle_days" { type = number; default = 90 }
