"""Send the weekly report to recipients' Gmail inboxes via Gmail SMTP.

Uses an App Password (not the account password). Create one at
https://myaccount.google.com/apppasswords (requires 2-Step Verification).
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import Config

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL


class EmailError(RuntimeError):
    pass


def _credentials(cfg: Config) -> tuple[str, str]:
    addr = cfg.env("GMAIL_ADDRESS")
    pwd = cfg.env("GMAIL_APP_PASSWORD")
    if not addr or not pwd or "@" not in (addr or ""):
        raise EmailError(
            "GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in .env. "
            "Create an App Password at https://myaccount.google.com/apppasswords"
        )
    return addr, pwd.replace(" ", "")  # app passwords are shown with spaces


def send_report(
    cfg: Config,
    subject: str,
    text_body: str,
    html_body: str,
    recipients: list[str] | None = None,
) -> list[str]:
    """Send the report. Returns the list of recipients it was sent to."""
    sender, password = _credentials(cfg)
    recipients = recipients or cfg.report_recipients
    if not recipients:
        raise EmailError("No recipients configured (report.recipients in config.yaml).")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
    except smtplib.SMTPAuthenticationError as e:
        raise EmailError(
            "Gmail login failed. Check GMAIL_ADDRESS and that GMAIL_APP_PASSWORD "
            "is a valid App Password (not your normal password)."
        ) from e
    except Exception as e:  # noqa: BLE001
        raise EmailError(f"Failed to send email: {e}") from e

    return recipients
