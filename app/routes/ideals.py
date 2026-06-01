"""Ideal file management endpoints.

GET    /api/ideals                      — list active ideal configs for this tenant
GET    /api/ideals/{check_id}/download  — download active ideal file bytes
POST   /api/ideals/{check_id}           — upload new ideal (admin only)
DELETE /api/ideals/{check_id}           — revert to bundled default (admin only)
POST   /api/ideals/admin/checks         — create a new check entry (admin only)
"""

from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
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


# ---------------------------------------------------------------------------
# Admin: create a new custom check
# ---------------------------------------------------------------------------


class CheckCreatedResponse(BaseModel):
    id: str
    name: str
    process_type: str
    erp: str
    category: str
    default_sheet: str
    description: str


@router.post(
    "/admin/checks",
    status_code=status.HTTP_201_CREATED,
    response_model=CheckCreatedResponse,
)
async def create_check(
    check_id: str = Form(...),
    name: str = Form(...),
    process_type: str = Form(...),
    erp: str = Form(...),
    category: str = Form(...),
    default_sheet: str = Form(""),
    description: str = Form(""),
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> CheckCreatedResponse:
    """Create a new audit check with uploaded ideal file. Admin only."""
    # Validate slug: lowercase alphanumeric + underscores only
    if not re.match(r"^[a-z0-9_]{2,64}$", check_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="check_id must be 2–64 lowercase alphanumeric characters or underscores.",
        )

    valid_process = {"itgc", "itac"}
    valid_erp = {"oracle", "sap", "generic"}
    valid_category = {"configurations", "detailed"}
    if process_type not in valid_process:
        raise HTTPException(422, f"process_type must be one of {valid_process}")
    if erp not in valid_erp:
        raise HTTPException(422, f"erp must be one of {valid_erp}")
    if category not in valid_category:
        raise HTTPException(422, f"category must be one of {valid_category}")

    data = await file.read()
    if not data:
        raise HTTPException(422, "Ideal file is empty.")

    settings = get_settings()

    # Save ideal file via the existing versioned loader
    loader = IdealsLoader(db=db, settings=settings)
    await loader.save(
        tenant_id=str(tenant.id),
        check_id=check_id,
        data=data,
        uploaded_by_id=str(admin.id),
    )

    # Write metadata to custom_checks.json in the persistent storage volume
    custom_path = os.path.join(settings.storage_path, "custom_checks.json")
    os.makedirs(settings.storage_path, exist_ok=True)
    existing: dict = {}
    if os.path.isfile(custom_path):
        with open(custom_path) as f:
            existing = json.load(f)

    existing[check_id] = {
        "name": name,
        "process_type": process_type,
        "erp": erp,
        "category": category,
        "default_sheet": default_sheet,
        "description": description,
    }
    with open(custom_path, "w") as f:
        json.dump(existing, f, indent=2)

    return CheckCreatedResponse(
        id=check_id,
        name=name,
        process_type=process_type,
        erp=erp,
        category=category,
        default_sheet=default_sheet,
        description=description,
    )
