"""Ideal file management endpoints.

GET    /api/ideals                      — list active ideal configs for this tenant
GET    /api/ideals/{check_id}/download  — download active ideal file bytes
POST   /api/ideals/{check_id}           — upload new ideal (admin only)
DELETE /api/ideals/{check_id}           — revert to bundled default (admin only)
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.dependencies import get_current_user, get_db, get_tenant, require_admin
from app.models import IdealFile, Tenant, User
from app.services.ideals_loader import IdealsLoader

router = APIRouter(prefix="/api/ideals", tags=["ideals"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class IdealFileInfo(BaseModel):
    check_id: str
    version: int
    content_hash: str
    created_at: datetime
    uploaded_by: Optional[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[IdealFileInfo])
async def list_ideals(
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[IdealFileInfo]:
    """Return all active ideal files for the current tenant."""
    result = await db.execute(
        select(IdealFile).where(
            IdealFile.tenant_id == tenant.id,
            IdealFile.is_active.is_(True),
        )
    )
    rows = result.scalars().all()
    return [
        IdealFileInfo(
            check_id=r.check_id,
            version=r.version,
            content_hash=r.content_hash,
            created_at=r.created_at,
            uploaded_by=str(r.uploaded_by) if r.uploaded_by else None,
        )
        for r in rows
    ]


@router.get("/{check_id}/download")
async def download_ideal(
    check_id: str,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download the active ideal file for check_id as an .xlsx attachment."""
    settings = get_settings()
    loader = IdealsLoader(db=db, settings=settings)

    try:
        data = await loader.load(str(tenant.id), check_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ideal file found for check '{check_id}'",
        )

    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{check_id}_ideal.xlsx"'
        },
    )


@router.post("/{check_id}", status_code=status.HTTP_201_CREATED)
async def upload_ideal(
    check_id: str,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> IdealFileInfo:
    """Replace the active ideal file for check_id. Admin only."""
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )

    settings = get_settings()
    loader = IdealsLoader(db=db, settings=settings)
    row = await loader.save(
        tenant_id=str(tenant.id),
        check_id=check_id,
        data=data,
        uploaded_by_id=str(admin.id),
    )

    return IdealFileInfo(
        check_id=row.check_id,
        version=row.version,
        content_hash=row.content_hash,
        created_at=row.created_at,
        uploaded_by=str(row.uploaded_by) if row.uploaded_by else None,
    )


@router.delete(
    "/{check_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_ideal(
    check_id: str,
    admin: User = Depends(require_admin),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deactivate the tenant's custom ideal for check_id, reverting to bundled default."""
    result = await db.execute(
        select(IdealFile).where(
            IdealFile.tenant_id == tenant.id,
            IdealFile.check_id == check_id,
            IdealFile.is_active.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No custom ideal active for check '{check_id}'",
        )
    row.is_active = False
    await db.commit()
