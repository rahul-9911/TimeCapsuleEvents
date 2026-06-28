# ── S3 Bucket ─────────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "photos" {
  bucket        = "snapevent-${var.env}-photos"
  force_destroy = var.env != "prod"
}

resource "aws_s3_bucket_public_access_block" "photos" {
  bucket                  = aws_s3_bucket.photos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id
  rule {
    id     = "expire-old-photos"
    status = "Enabled"
    expiration { days = var.s3_photos_lifecycle_days }
  }
}

resource "aws_s3_bucket_cors_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id
  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = ["*"]
    max_age_seconds = 3600
  }
}

# ── EFS Filesystem ────────────────────────────────────────────────────────────
resource "aws_efs_file_system" "event_data" {
  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"
  encrypted        = true
  tags             = { Name = "snapevent-${var.env}-efs" }

  lifecycle_policy {
    transition_to_ia = "AFTER_7_DAYS"
  }
}

resource "aws_efs_mount_target" "event_data" {
  count           = length(var.private_subnet_ids)
  file_system_id  = aws_efs_file_system.event_data.id
  subnet_id       = var.private_subnet_ids[count.index]
  security_groups = [var.sg_efs_id]
}
