# ── RDS PostgreSQL ────────────────────────────────────────────────────────────
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "snapevent-${var.env}"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "control" {
  identifier             = "snapevent-${var.env}-ctrl"
  engine                 = "postgres"
  engine_version         = "16.2"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  db_name                = "snapevent"
  username               = "snapevent"
  password               = random_password.db.result
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.sg_rds_id]
  skip_final_snapshot    = var.env != "prod"
  deletion_protection    = var.env == "prod"
  backup_retention_period = var.env == "prod" ? 7 : 1
  tags = { Name = "snapevent-${var.env}-rds" }
}
