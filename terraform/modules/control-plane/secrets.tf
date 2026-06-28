resource "aws_secretsmanager_secret" "db_url" {
  name = "snapevent/${var.env}/db_url"
}

resource "aws_secretsmanager_secret_version" "db_url" {
  secret_id     = aws_secretsmanager_secret.db_url.id
  secret_string = "postgresql://${aws_db_instance.control.username}:${random_password.db.result}@${aws_db_instance.control.endpoint}/snapevent"
  depends_on    = [aws_db_instance.control]
}

resource "aws_secretsmanager_secret" "smtp_pass" {
  name = "snapevent/${var.env}/smtp_pass"
}

resource "aws_secretsmanager_secret_version" "smtp_pass" {
  secret_id     = aws_secretsmanager_secret.smtp_pass.id
  secret_string = var.smtp_pass
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  name = "snapevent/${var.env}/jwt_secret"
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = random_password.jwt_secret.result
}
