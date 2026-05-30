"""Audit job endpoints.

POST /api/audits          — upload actual file, enqueue job, return 202 {job_id}
GET  /api/audits          — list jobs for current user (last 50)
GET  /api/audits/{job_id} — poll job status
GET  /api/audits/{job_id}/download — stream finished report bytes
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime
from typing import Optional

import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rq import Queue
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.dependencies import get_current_user, get_db, get_tenant
from app.models import AuditJob, Tenant, User
from app.services import storage
from app.workers.audit_worker import RETRY, run_audit_job

router = APIRouter(prefix="/api/audits", tags=["audits"])

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Dependency — RQ queue (one Redis connection per request, cheap)
# ---------------------------------------------------------------------------


def get_queue() -> Queue:
    settings = get_settings()
    conn = redis.from_url(settings.redis_url)
    return Queue("audits", connection=conn)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class JobCreatedResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    id: str
    status: str
    check_id: str
    created_at: datetime
    finished_at: Optional[datetime]
    error_message: Optional[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreatedResponse
)
async def create_audit(
    actual_file: UploadFile = File(...),
    check_id: str = Form(...),
    sheet_name: str = Form(""),
    fuzzy_threshold: int = Form(80),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
    queue: Queue = Depends(get_queue),
) -> JobCreatedResponse:
    """Upload the actual file, create an AuditJob, enqueue the RQ task."""
    if not (50 <= fuzzy_threshold <= 100):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fuzzy_threshold must be between 50 and 100.",
        )

    actual_bytes = await actual_file.read()

    if len(actual_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 50 MB limit.",
        )

    settings = get_settings()

    actual_key = f"actuals/{tenant.id}/{uuid.uuid4().hex}/{actual_file.filename or 'actual.xlsx'}"
    storage.save(actual_key, actual_bytes, settings=settings)

    job = AuditJob(
        tenant_id=tenant.id,
        submitted_by=user.id,
        check_id=check_id,
        sheet_name=sheet_name or None,
        actual_key=actual_key,
        fuzzy_threshold=fuzzy_threshold,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    queue.enqueue(run_audit_job, str(job.id), retry=RETRY)

    return JobCreatedResponse(job_id=str(job.id))


@router.get("", response_model=list[JobStatusResponse])
async def list_audits(
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[JobStatusResponse]:
    """Return the 50 most recent jobs for the current user."""
    result = await db.execute(
        select(AuditJob)
        .where(AuditJob.tenant_id == tenant.id, AuditJob.submitted_by == user.id)
        .order_by(desc(AuditJob.created_at))
        .limit(50)
    )
    jobs = result.scalars().all()
    return [
        JobStatusResponse(
            id=str(j.id),
            status=j.status,
            check_id=j.check_id,
            created_at=j.created_at,
            finished_at=j.finished_at,
            error_message=j.error_message,
        )
        for j in jobs
    ]


@router.post(
    "/{job_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobCreatedResponse,
)
async def retry_audit(
    job_id: str,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
    queue: Queue = Depends(get_queue),
) -> JobCreatedResponse:
    """Resubmit a failed job as a new AuditJob. Original job is unchanged."""
    original = await _get_job_or_404(job_id, tenant.id, db)

    if original.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed jobs can be retried.",
        )

    new_job = AuditJob(
        tenant_id=original.tenant_id,
        submitted_by=user.id,
        check_id=original.check_id,
        sheet_name=original.sheet_name,
        actual_key=original.actual_key,
        fuzzy_threshold=original.fuzzy_threshold,
        status="queued",
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)

    queue.enqueue(run_audit_job, str(new_job.id), retry=RETRY)

    return JobCreatedResponse(job_id=str(new_job.id))


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_audit_status(
    job_id: str,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> JobStatusResponse:
    """Return current status for a job that belongs to this tenant."""
    job = await _get_job_or_404(job_id, tenant.id, db)
    return JobStatusResponse(
        id=str(job.id),
        status=job.status,
        check_id=job.check_id,
        created_at=job.created_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
    )


@router.get("/{job_id}/download")
async def download_report(
    job_id: str,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream the finished report .xlsx. 404 if not done or report missing."""
    job = await _get_job_or_404(job_id, tenant.id, db)

    if job.status != "done" or job.report_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not available — job has not completed successfully.",
        )

    settings = get_settings()
    try:
        report_bytes = storage.load(job.report_key, settings=settings)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file missing from storage.",
        )

    filename = f"AuditForge_{job.check_id}_{job_id[:8]}.xlsx"
    return StreamingResponse(
        io.BytesIO(report_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _get_job_or_404(
    job_id: str, tenant_id: uuid.UUID, db: AsyncSession
) -> AuditJob:
    """Fetch AuditJob by id, scoped to tenant. Raises 404 if absent."""
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )

    result = await db.execute(
        select(AuditJob).where(AuditJob.id == uid, AuditJob.tenant_id == tenant_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )
    return job
