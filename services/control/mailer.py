"""
Control Plane — Magic link sender
Supports two modes:
  - Console (default / dev): prints the link to stdout — no email config needed
  - Gmail SMTP: set SMTP_USER + SMTP_PASS in .env to enable real emails
"""
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_PLACEHOLDER = "your-gmail@gmail.com"


def _is_smtp_configured() -> bool:
    user = os.getenv("SMTP_USER", "")
    pw   = os.getenv("SMTP_PASS", "")
    return bool(user and pw and user != _PLACEHOLDER and pw != "your-gmail-app-password")


def send_magic_link(to_email: str, magic_link: str) -> None:
    """Send a magic login link — console fallback if SMTP not configured."""
    if not _is_smtp_configured():
        _console_fallback(to_email, magic_link)
        return
    _send_via_smtp(to_email, magic_link)


def _console_fallback(to_email: str, magic_link: str) -> None:
    """Print the magic link to stdout (visible in `docker compose logs control`)."""
    banner = "\n" + "="*60
    banner += f"\n  🔗 MAGIC LINK (console mode — no email sent)"
    banner += f"\n  To:   {to_email}"
    banner += f"\n  Link: {magic_link}"
    banner += "\n" + "="*60
    logger.warning(banner)
    print(banner, flush=True)


def _send_via_smtp(to_email: str, magic_link: str) -> None:
    """Send via Gmail SMTP SSL."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your SnapEvent login link"
    msg["From"] = f"SnapEvent <{smtp_from}>"
    msg["To"] = to_email

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

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_from, to_email, msg.as_string())
