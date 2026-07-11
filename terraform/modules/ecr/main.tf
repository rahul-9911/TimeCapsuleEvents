# ── ECR — Single repository for the Lambda container image ───────────────────

resource "aws_ecr_repository" "app" {
  name                 = "snapevent-${var.env}"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.env != "prod"

  image_scanning_configuration {
    scan_on_push = false # Save cost — enable in prod later
  }

  tags = {
    Name = "snapevent-${var.env}"
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 3 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 3
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
