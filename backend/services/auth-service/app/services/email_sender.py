import smtplib
from email.message import EmailMessage

from fastapi import HTTPException

from app.core.config import get_settings
from app.services.email_templates import render_code_email


def send_verification_code(recipient: str, code: str) -> None:
    _send_code(recipient, code, "Verify your Drivewell account", "verification")


def send_password_reset_code(recipient: str, code: str) -> None:
    _send_code(recipient, code, "Reset your Drivewell password", "password reset")


def _send_code(recipient: str, code: str, subject: str, purpose: str) -> None:
    settings = get_settings()
    if not settings.smtp_configured:
        raise HTTPException(status_code=503, detail="Email verification is not configured.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.email_from or settings.email_user
    message["To"] = recipient
    text_body, html_body = render_code_email(purpose=purpose, code=code)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.login(settings.email_user, settings.email_password.get_secret_value())
                server.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(settings.email_user, settings.email_password.get_secret_value())
                server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(status_code=502, detail="The verification email could not be sent.") from exc
