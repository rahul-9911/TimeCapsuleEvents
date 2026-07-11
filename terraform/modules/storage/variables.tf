variable "env" {
  type        = string
  description = "Environment name"
}

variable "photo_expiry_days" {
  type        = number
  description = "Days after which photos in S3 are auto-deleted by lifecycle policy"
  default     = 30
}
