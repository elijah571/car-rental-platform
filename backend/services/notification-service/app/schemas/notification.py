from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class EmailNotificationCreate(BaseModel):
    recipient: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    text_body: str | None = Field(default=None, max_length=100_000)
    html_body: str | None = Field(default=None, max_length=100_000)

    @model_validator(mode="after")
    def require_body(self):
        if not self.text_body and not self.html_body:
            raise ValueError("Provide text_body, html_body, or both")
        return self


class NotificationRead(BaseModel):
    id: UUID
    recipient: EmailStr
    subject: str
    status: Literal["pending", "sending", "sent", "failed"]
    provider_message_id: str | None
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
