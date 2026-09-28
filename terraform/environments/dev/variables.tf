variable "env" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "image_tag" {
  type    = string
  default = "v6"
}

variable "ses_sender_email" {
  type        = string
  description = "Verified SES sender email for magic links"
}

variable "worker_api_key" {
  type        = string
  description = "Static API key for the local ComfyUI worker"
  sensitive   = true
}
