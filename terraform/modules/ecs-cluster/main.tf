# ── ECS Cluster ───────────────────────────────────────────────────────────────
resource "aws_ecs_cluster" "main" {
  name = "snapevent-${var.env}"
  setting { name = "containerInsights"; value = "enabled" }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
  default_capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
    base              = 0
  }
}

# ── ECR Repositories ──────────────────────────────────────────────────────────
resource "aws_ecr_repository" "control" {
  name                 = "snapevent-control"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "event" {
  name                 = "snapevent-event"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# ECR lifecycle: keep only last 10 images
resource "aws_ecr_lifecycle_policy" "control" {
  repository = aws_ecr_repository.control.name
  policy = jsonencode({
    rules = [{ rulePriority = 1, description = "Keep last 10",
      selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 },
      action = { type = "expire" } }]
  })
}

resource "aws_ecr_lifecycle_policy" "event" {
  repository = aws_ecr_repository.event.name
  policy = jsonencode({
    rules = [{ rulePriority = 1, description = "Keep last 10",
      selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 },
      action = { type = "expire" } }]
  })
}
