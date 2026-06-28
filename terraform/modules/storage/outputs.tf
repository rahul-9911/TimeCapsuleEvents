output "bucket_name"  { value = aws_s3_bucket.photos.bucket }
output "bucket_arn"   { value = aws_s3_bucket.photos.arn }
output "efs_id"       { value = aws_efs_file_system.event_data.id }
output "efs_arn"      { value = aws_efs_file_system.event_data.arn }
