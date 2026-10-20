from email import policy
from email.parser import Parser

from app.services import email_sender
from app.services.email_templates import render_code_email


def test_verification_template_has_plain_text_and_escaped_html():
    text, html = render_code_email(purpose="verification", code="<123456>")

    assert "Verify your email address" in text
    assert "<123456>" in text
    assert "&lt;123456&gt;" in html
    assert "expires in 15 minutes" in html
    assert "Drivewell" in html


def test_password_reset_template_has_reset_specific_copy():
    text, html = render_code_email(purpose="password reset", code="654321")

    assert "Reset your password" in text
    assert "password reset" in text
    assert "Reset your password" in html


def test_auth_email_sender_attaches_html_alternative(monkeypatch):
    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def login(self, *_args):
            pass

        def send_message(self, message):
            self.message = message
            messages.append(message)

    messages = []
    settings = type("Settings", (), {
        "smtp_configured": True,
        "smtp_port": 465,
        "smtp_host": "smtp.example.com",
        "email_user": "sender@example.com",
        "email_password": type("Password", (), {"get_secret_value": lambda self: "secret"})(),
        "email_from": None,
    })()
    monkeypatch.setattr(email_sender, "get_settings", lambda: settings)
    monkeypatch.setattr(email_sender.smtplib, "SMTP_SSL", FakeSMTP)

    email_sender.send_verification_code("customer@example.com", "123456")

    message = Parser(policy=policy.default).parsestr(messages[0].as_string())
    assert message.get_content_type() == "multipart/alternative"
    assert "123456" in message.get_body(preferencelist=("plain",)).get_content()
    assert "Verify your email address" in message.get_body(preferencelist=("html",)).get_content()
