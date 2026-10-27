from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Window = Literal["24h", "7d", "30d", "90d"]
Bucket = Literal["hour", "day"]


class SummaryOut(BaseModel):
    window: str
    status: str
    checks: int
    failures: int
    uptime_percent: float | None  # null means "no data", not "100%"
    avg_ms: float | None
    # Over several hours these are check-weighted averages of hourly percentiles (approximate).
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None


class PointOut(BaseModel):
    time: datetime
    checks: int
    failures: int
    uptime_percent: float | None
    avg_ms: float | None
    p95_ms: float | None


class TimeseriesOut(BaseModel):
    window: str
    bucket: str
    points: list[PointOut]
