# ── S3 Bucket — Single bucket for all event photos ────────────────────────────

resource "aws_s3_bucket" "photos" {
  bucket        = "snapevent-${var.env}-photos"
  force_destroy = var.env != "prod"

  tags = {
    Name = "snapevent-${var.env}-photos"
  }
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
    id     = "expire-old-event-photos"
    status = "Enabled"

    filter {
      prefix = "events/"
    }

    expiration {
      days = var.photo_expiry_days
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = ["*"] # Tighten in production
    max_age_seconds = 3600
  }
}
