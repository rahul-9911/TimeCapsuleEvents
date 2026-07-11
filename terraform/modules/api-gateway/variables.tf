variable "env" {
  type = string
}

variable "lambda_function_name" {
  type        = string
  description = "Name of the Lambda function to integrate with"
}

variable "lambda_invoke_arn" {
  type        = string
  description = "Invoke ARN of the Lambda function"
}
