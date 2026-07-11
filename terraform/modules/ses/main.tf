# ── SES — Email sending for magic links ───────────────────────────────────────

# Email identity — the "from" address
# NOTE: SES starts in sandbox mode. You must verify sender + recipient emails.
# Request production access via AWS Console after MVP testing.
resource "aws_ses_email_identity" "sender" {
  email = var.sender_email
}
