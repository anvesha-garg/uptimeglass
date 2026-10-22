from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_INTERVAL_SECONDS = 60
MAX_INTERVAL_SECONDS = 86400  # one day

Method = Literal["GET", "HEAD"]


class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    method: Method = "GET"
    interval_seconds: int = Field(default=300, ge=MIN_INTERVAL_SECONDS, le=MAX_INTERVAL_SECONDS)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    expected_status: int = Field(default=200, ge=100, le=599)
    keyword: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def timeout_below_interval(self) -> "MonitorCreate":
        if self.timeout_seconds >= self.interval_seconds:
            raise ValueError("timeout_seconds must be less than interval_seconds")
        return self


class MonitorUpdate(BaseModel):
    """Every field is optional. Only the fields that are sent get changed."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    method: Method | None = None
    interval_seconds: int | None = Field(
        default=None, ge=MIN_INTERVAL_SECONDS, le=MAX_INTERVAL_SECONDS
    )
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    # Sending "keyword": null removes the keyword check.
    keyword: str | None = Field(default=None, min_length=1, max_length=200)


class MonitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    url: str
    method: str
    interval_seconds: int
    timeout_seconds: int
    expected_status: int
    keyword: str | None
    is_paused: bool
    status: str
    consecutive_failures: int
    consecutive_successes: int
    next_check_at: datetime
    last_checked_at: datetime | None
    ssl_expires_at: datetime | None
    created_at: datetime


class MonitorList(BaseModel):
    items: list[MonitorOut]
    total: int
    limit: int
    offset: int
