import smtplib
from email.message import EmailMessage
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings


def send_email(*, recipient: str, subject: str, text_body: str | None, html_body: str | None) -> str:
    settings = get_settings()
    if not (settings.smtp_host and settings.email_user and settings.email_password):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SMTP email delivery is not configured.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.email_from or settings.email_user
    message["To"] = recipient
    message["Message-ID"] = f"<{uuid4()}@drivewell.local>"
    message.set_content(text_body or "")
    if html_body:
        message.add_alternative(html_body, subtype="html")
    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.login(settings.email_user, settings.email_password.get_secret_value())
                server.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.starttls()
                server.login(settings.email_user, settings.email_password.get_secret_value())
                server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The email provider could not deliver this message.") from exc
    return message["Message-ID"]


def close_client() -> None:
    return None
