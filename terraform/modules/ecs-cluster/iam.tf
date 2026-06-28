data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals { type = "Service"; identifiers = ["ecs-tasks.amazonaws.com"] }
  }
}

# ── ECS Task Execution Role (shared) ─────────────────────────────────────────
resource "aws_iam_role" "execution" {
  name               = "snapevent-${var.env}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_basic" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ── Control Plane Task Role ───────────────────────────────────────────────────
resource "aws_iam_role" "control_task" {
  name               = "snapevent-${var.env}-control-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "control_task_policy" {
  name = "snapevent-${var.env}-control-task-policy"
  role = aws_iam_role.control_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Spawn/stop event tasks
      { Effect = "Allow", Action = ["ecs:RunTask", "ecs:StopTask", "ecs:DescribeTasks",
        "ecs:ListTasks"], Resource = "*" },
      # Pass IAM role to event tasks
      { Effect = "Allow", Action = "iam:PassRole", Resource = "*" },
      # S3 full access to photos bucket
      { Effect = "Allow", Action = "s3:*", Resource = "*" },
      # SES for magic link emails
      { Effect = "Allow", Action = "ses:SendEmail", Resource = "*" },
      # Secrets Manager
      { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = "*" },
      # CloudWatch logs
      { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream",
        "logs:PutLogEvents"], Resource = "*" },
    ]
  })
}

# ── Event Worker Task Role ────────────────────────────────────────────────────
resource "aws_iam_role" "event_task" {
  name               = "snapevent-${var.env}-event-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "event_task_policy" {
  name = "snapevent-${var.env}-event-task-policy"
  role = aws_iam_role.event_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 access scoped to events prefix
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
        Resource = "arn:aws:s3:::snapevent-${var.env}-photos/events/*" },
      { Effect = "Allow", Action = "s3:ListBucket",
        Resource = "arn:aws:s3:::snapevent-${var.env}-photos",
        Condition = { StringLike = { "s3:prefix" = ["events/*"] } } },
      # CloudWatch logs
      { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream",
        "logs:PutLogEvents"], Resource = "*" },
    ]
  })
}
