"""Data models for newsletter publishing state."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel


class PublishStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    FAILED = "failed"


class PublishRecord(BaseModel):
    """Tracks the publishing state of a single newsletter issue."""

    issue_date: date
    title: str
    status: PublishStatus
    buttondown_email_id: str | None = None
    created_at: datetime
    sent_at: datetime | None = None
    strategy_name: str
    model_used: str | None = None
    word_count: int
    error_message: str | None = None
