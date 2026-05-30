"""RQ task: execute one AuditJob end-to-end.

Enqueued by POST /api/audits. Runs synchronously inside the RQ worker process.
Uses SyncSessionLocal (psycopg2) — never AsyncSession.

Retry policy: max 2 retries, 10 s delay, only on transient network errors.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from rq import Retry

from app.core.config import get_settings
from app.core.database import SyncSessionLocal
from app.models import AuditJob
from app.services import audit_service, storage
from app.services.ideals_loader import IdealsLoader

# Exported so rq can reference it:  queue.enqueue(run_audit_job, ...)
RETRY = Retry(max=2, interval=10)


def run_audit_job(job_id: str) -> None:
    """RQ task entry point. job_id is a UUID string."""
    settings = get_settings()

    with SyncSessionLocal() as db:
        job: AuditJob | None = db.get(AuditJob, uuid.UUID(job_id))
        if job is None:
            # Nothing we can update — log and bail.
            raise ValueError(f"AuditJob {job_id} not found in database")

        job.status = "running"
        db.commit()

        try:
            # Load actual file bytes from storage.
            actual_bytes = storage.load(job.actual_key, settings=settings)

            # Load ideal bytes via IdealsLoader (async → run in fresh event loop).
            ideal_bytes = asyncio.run(
                _load_ideal(str(job.tenant_id), job.check_id, settings)
            )

            # Resolve sheet name and ideal display name.
            sheet = job.sheet_name or ""
            ideal_name = job.check_id  # human label written to summary sheet

            excel_bytes, ideal_sha256 = asyncio.run(
                audit_service.run_audit(
                    actual_bytes=actual_bytes,
                    ideal_bytes=ideal_bytes,
                    check_id=job.check_id,
                    actual_filename=job.actual_key.split("/")[-1],
                    ideal_name=ideal_name,
                    sheet_name=sheet,
                    fuzzy_threshold=job.fuzzy_threshold,
                )
            )

            # Persist the report.
            report_key = f"reports/{job.tenant_id}/{job_id}.xlsx"
            storage.save(report_key, excel_bytes, settings=settings)

            job.status = "done"
            job.report_key = report_key
            job.ideal_hash = ideal_sha256
            job.finished_at = datetime.now(timezone.utc)

        except (ConnectionError, TimeoutError):
            # Transient — allow RQ to retry.
            job.status = "failed"
            job.error_message = "Transient error — will retry"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            raise  # re-raise so RQ knows to retry

        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)

        db.commit()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _load_ideal(tenant_id: str, check_id: str, settings) -> bytes:
    """Open a short-lived async DB session just to load ideal bytes."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as async_db:
        loader = IdealsLoader(db=async_db, settings=settings)
        return await loader.load(tenant_id, check_id)
