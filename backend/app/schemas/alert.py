from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

ChannelType = Literal["email", "telegram", "webhook"]
MAX_CHANNELS_PER_MONITOR = 10


class ChannelCreate(BaseModel):
    type: ChannelType
    address: EmailStr | None = None  # email channels
    url: str | None = Field(default=None, min_length=1, max_length=2048)  # webhook channels

    @field_validator("address")
    @classmethod
    def lowercase_address(cls, value: str | None) -> str | None:
        return value.lower() if value else value

    @model_validator(mode="after")
    def check_required_fields(self) -> Self:
        if self.type == "email" and self.address is None:
            raise ValueError("address is required for email channels")
        if self.type == "webhook" and self.url is None:
            raise ValueError("url is required for webhook channels")
        return self


class ChannelOut(BaseModel):
    """What the API shows about a channel. The stored config is never returned as it is."""

    id: UUID
    type: str
    target: str  # the email address, the webhook URL, or the Telegram link state
    is_verified: bool
    link_code: str | None  # Telegram only, and only until the channel is linked
    created_at: datetime


class ChannelCreated(ChannelOut):
    # The webhook signing secret. It appears in this response ONLY, so save it now.
    secret: str | None = None


class ChannelList(BaseModel):
    items: list[ChannelOut]
    total: int


class MonitorChannelsUpdate(BaseModel):
    channel_ids: list[UUID] = Field(max_length=MAX_CHANNELS_PER_MONITOR)


class VerifyRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
