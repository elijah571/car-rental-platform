"""Optional legacy Amazon SES sender retained for a future cloud integration."""

from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from app.core.config import get_settings


@lru_cache
def _client():
    return boto3.client("sesv2", region_name=get_settings().aws_region)


def send_email(*, recipient: str, subject: str, text_body: str | None, html_body: str | None) -> str:
    sender = get_settings().ses_from_email
    if not sender:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SES sender is not configured.")
    body: dict[str, dict[str, str]] = {}
    if text_body:
        body["Text"] = {"Data": text_body, "Charset": "UTF-8"}
    if html_body:
        body["Html"] = {"Data": html_body, "Charset": "UTF-8"}
    try:
        response = _client().send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": [recipient]},
            Content={"Simple": {"Subject": {"Data": subject, "Charset": "UTF-8"}, "Body": body}},
        )
    except (ClientError, BotoCoreError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="SES could not deliver this message.") from exc
    message_id = response.get("MessageId")
    if not message_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="SES returned no message identifier.")
    return message_id


def close_client() -> None:
    if _client.cache_info().currsize:
        _client().close()
    _client.cache_clear()
