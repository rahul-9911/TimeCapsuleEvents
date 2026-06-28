resource "aws_cloudwatch_log_group" "event" {
  name              = "/snapevent/${var.env}/event"
  retention_in_days = 7
}

# This is a TASK DEFINITION only — no ECS Service.
# The control plane calls ecs:RunTask with this definition when a new event is created.
resource "aws_ecs_task_definition" "event" {
  family                   = "snapevent-event-${var.env}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name      = "event"
    image     = "${var.image_url}:${var.image_tag}"
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp", name = "event-http" }]

    # EVENT_CODE is injected at runtime via RunTask containerOverrides
    environment = [
      { name = "EVENT_CODE",   value = "PLACEHOLDER" },
      { name = "ENV",          value = var.env },
      { name = "S3_BUCKET",    value = var.s3_bucket },
      { name = "S3_REGION",    value = var.aws_region },
      { name = "EFS_MOUNT",    value = "/data" },
    ]
    mountPoints = [{
      sourceVolume  = "efs-event-data"
      containerPath = "/data"
      readOnly      = false
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.event.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "event"
      }
    }
  }])

  volume {
    name = "efs-event-data"
    efs_volume_configuration {
      file_system_id     = var.efs_id
      root_directory     = "/"
      transit_encryption = "ENABLED"
    }
  }
}
