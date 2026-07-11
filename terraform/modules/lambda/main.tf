# ── Lambda — API function + Cleanup function ──────────────────────────────────

# ── IAM Role for Lambda execution ─────────────────────────────────────────────

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "snapevent-${var.env}-lambda"
  assume_role_policy  = data.aws_iam_policy_document.lambda_assume.json

  tags = {
    Name = "snapevent-${var.env}-lambda"
  }
}

# Policy: DynamoDB full access to our table
data "aws_iam_policy_document" "lambda_permissions" {
  # DynamoDB
  statement {
    sid = "DynamoDB"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:BatchWriteItem",
    ]
    resources = [
      var.dynamodb_table_arn,
      "${var.dynamodb_table_arn}/index/*",
    ]
  }

  # S3
  statement {
    sid = "S3"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      var.s3_bucket_arn,
      "${var.s3_bucket_arn}/*",
    ]
  }

  # SES
  statement {
    sid       = "SES"
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = [var.ses_sender_arn]
  }

  # SSM Parameter Store (read-only)
  statement {
    sid     = "SSM"
    actions = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:parameter/snapevent/${var.env}/*",
    ]
  }

  # CloudWatch Logs (provisioned but we control writing in app code)
  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "snapevent-${var.env}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# ── CloudWatch Log Group (provisioned, writing controlled by app) ─────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/snapevent-${var.env}-api"
  retention_in_days = 7 # Minimal retention to save cost if logs are written

  tags = {
    Name = "snapevent-${var.env}-api-logs"
  }
}

resource "aws_cloudwatch_log_group" "cleanup" {
  name              = "/aws/lambda/snapevent-${var.env}-cleanup"
  retention_in_days = 7

  tags = {
    Name = "snapevent-${var.env}-cleanup-logs"
  }
}

# ── Main API Lambda ───────────────────────────────────────────────────────────

resource "aws_lambda_function" "api" {
  function_name = "snapevent-${var.env}-api"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repository_url}:${var.image_tag}"
  timeout       = 30
  memory_size   = 512

  image_config {
    command = ["main.handler"]
  }

  environment {
    variables = {
      ENV              = var.env
      DYNAMODB_TABLE   = var.dynamodb_table_name
      S3_BUCKET        = var.s3_bucket_name
      S3_REGION        = var.aws_region
      SES_SENDER_EMAIL = var.ses_sender_email
      BASE_URL         = var.base_url
      LOG_LEVEL        = "WARNING" # Suppress most logging to avoid CloudWatch costs
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  tags = {
    Name = "snapevent-${var.env}-api"
  }
}

# ── Cleanup Lambda ────────────────────────────────────────────────────────────

resource "aws_lambda_function" "cleanup" {
  function_name = "snapevent-${var.env}-cleanup"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repository_url}:${var.image_tag}"
  timeout       = 60
  memory_size   = 128

  image_config {
    command = ["cleanup.handler"]
  }

  environment {
    variables = {
      ENV            = var.env
      DYNAMODB_TABLE = var.dynamodb_table_name
      S3_BUCKET      = var.s3_bucket_name
      S3_REGION      = var.aws_region
      LOG_LEVEL      = "WARNING"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.cleanup.name
  }

  tags = {
    Name = "snapevent-${var.env}-cleanup"
  }
}

# ── EventBridge: Hourly schedule for cleanup Lambda ───────────────────────────

resource "aws_scheduler_schedule" "cleanup" {
  name       = "snapevent-${var.env}-cleanup-hourly"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(1 hour)"

  target {
    arn      = aws_lambda_function.cleanup.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}

# IAM role for EventBridge Scheduler to invoke Lambda
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "snapevent-${var.env}-scheduler"
  assume_role_policy  = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler_invoke" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.cleanup.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "snapevent-${var.env}-scheduler-invoke"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_invoke.json
}
