output "sender_email" {
  value = aws_ses_email_identity.sender.email
}

output "sender_arn" {
  value = aws_ses_email_identity.sender.arn
}
