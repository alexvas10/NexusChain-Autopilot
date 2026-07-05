import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Exception_(Base):
    """A pending or resolved human-in-the-loop checkpoint raised by a workflow."""

    __tablename__ = "exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workflow: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "rfq" or "disruption"
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text)  # raw input JSON/text that triggered the exception
    decision: Mapped[str] = mapped_column(String(32))  # "autonomous" | "human_review"
    reasoning: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|approved|rejected
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob: quote draft / cost delta / etc.
    action_log: Mapped[str | None] = mapped_column(Text, nullable=True)  # what the agent executed post-decision
    payload_archive_uri: Mapped[str | None] = mapped_column(Text, nullable=True)  # OSS (or local) archive of raw payload
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
