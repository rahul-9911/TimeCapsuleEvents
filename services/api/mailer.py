"""
SnapEvent — Email sender (AWS SES)
Supports two modes:
  - Console (dev): prints the link to stdout — no SES config needed
  - SES (prod): sends real emails via AWS SES
"""
import os
import logging

import boto3

logger = logging.getLogger(__name__)

SES_SENDER = os.getenv("SES_SENDER_EMAIL", "")
ENV = os.getenv("ENV", "dev")
_ses = None


def _get_ses():
    global _ses
    if _ses is None:
        _ses = boto3.client("ses", region_name=os.getenv("S3_REGION", "us-east-1"))
    return _ses


def send_magic_link(to_email: str, magic_link: str) -> None:
    """Send a magic login link — console fallback if SES not configured."""
    if ENV == "dev" or not SES_SENDER:
        _console_fallback(to_email, magic_link)
        return
    _send_via_ses(to_email, magic_link)


def _console_fallback(to_email: str, magic_link: str) -> None:
    """Print the magic link to stdout (for local dev)."""
    banner = "\n" + "=" * 60
    banner += f"\n  🔗 MAGIC LINK (console mode — no email sent)"
    banner += f"\n  To:   {to_email}"
    banner += f"\n  Link: {magic_link}"
    banner += "\n" + "=" * 60
    logger.warning(banner)
    print(banner, flush=True)


def _send_via_ses(to_email: str, magic_link: str) -> None:
    """Send via AWS SES."""
    text_body = (
        f"Log in to SnapEvent\n\n"
        f"Click the link below to access your dashboard:\n{magic_link}\n\n"
        f"This link expires in 15 minutes and can only be used once.\n"
        f"If you didn't request this, ignore this email."
    )

    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;background:#0f0f0f;color:#e5e5e5;padding:40px;">
  <div style="max-width:480px;margin:0 auto;background:#1a1a1a;border-radius:12px;padding:40px;">
    <h1 style="color:#ffffff;font-size:24px;margin-bottom:8px;">SnapEvent</h1>
    <p style="color:#a0a0a0;margin-bottom:32px;">Your magic login link is ready.</p>
    <a href="{magic_link}"
       style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;
              padding:14px 28px;border-radius:8px;font-weight:600;font-size:16px;">
      Log in to Dashboard →
    </a>
    <p style="color:#666;font-size:13px;margin-top:32px;">
      This link expires in <strong>15 minutes</strong> and works only once.<br>
      If you didn't request this, you can safely ignore it.
    </p>
  </div>
</body>
</html>"""

    ses = _get_ses()
    ses.send_email(
        Source=f"SnapEvent <{SES_SENDER}>",
        Destination={"ToAddresses": [to_email]},
        Message={
            "Subject": {"Data": "Your SnapEvent login link", "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": text_body, "Charset": "UTF-8"},
                "Html": {"Data": html_body, "Charset": "UTF-8"},
            },
        },
    )
