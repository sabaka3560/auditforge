from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditJob(Base):
    __tablename__ = "audit_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    check_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actual_key: Mapped[str] = mapped_column(String(512), nullable=False)
    report_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ideal_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("queued", "running", "done", "failed", name="audit_job_status"),
        nullable=False,
        default="queued",
    )
    fuzzy_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
