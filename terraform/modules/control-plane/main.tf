resource "aws_cloudwatch_log_group" "control" {
  name              = "/snapevent/${var.env}/control"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "control" {
  family                   = "snapevent-control-${var.env}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name      = "control"
    image     = "${var.image_url}:${var.image_tag}"
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "ENV",                    value = var.env },
      { name = "BASE_URL",               value = var.base_url },
      { name = "SMTP_HOST",              value = "smtp.gmail.com" },
      { name = "SMTP_PORT",              value = "465" },
      { name = "SMTP_USER",              value = var.smtp_user },
      { name = "S3_BUCKET",             value = var.s3_bucket },
      { name = "S3_REGION",             value = var.aws_region },
      { name = "ECS_CLUSTER",           value = var.cluster_name },
      { name = "EVENT_TASK_DEFINITION", value = var.event_task_definition },
      { name = "ECS_SUBNETS",           value = join(",", var.private_subnet_ids) },
      { name = "EVENT_SECURITY_GROUP",  value = var.event_sg_id },
      { name = "AWS_REGION",            value = var.aws_region },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_url.arn },
      { name = "SMTP_PASS",    valueFrom = aws_secretsmanager_secret.smtp_pass.arn },
      { name = "SECRET_KEY",   valueFrom = aws_secretsmanager_secret.jwt_secret.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.control.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "control"
      }
    }
  }])

  volume {
    name = "efs-data"
    efs_volume_configuration {
      file_system_id = var.efs_id
      root_directory = "/"
    }
  }
}

resource "aws_ecs_service" "control" {
  name            = "snapevent-control-${var.env}"
  cluster         = var.cluster_arn
  task_definition = aws_ecs_task_definition.control.arn
  desired_count   = 1

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1   # Always keep at least 1 FARGATE (not Spot) for the control plane
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.sg_control_plane_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = "control"
    container_port   = 8000
  }

  lifecycle { ignore_changes = [task_definition, desired_count] }
}
