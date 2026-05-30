"""User management endpoints (admin only).

GET  /api/users          — list users in the current tenant
POST /api/users          — create a new user (admin only)
DELETE /api/users/{id}   — deactivate a user (admin only)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.dependencies import get_db, get_tenant, require_admin
from app.models import Tenant, User

router = APIRouter(prefix="/api/users", tags=["users"])


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class CreateUserIn(BaseModel):
    email: str
    password: str
    role: str = "associate"


@router.get("", response_model=list[UserOut])
async def list_users(
    admin: User = Depends(require_admin),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    result = await db.execute(
        select(User).where(User.tenant_id == tenant.id).order_by(User.created_at)
    )
    users = result.scalars().all()
    return [
        UserOut(
            id=str(u.id),
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserOut)
async def create_user(
    body: CreateUserIn,
    admin: User = Depends(require_admin),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    if body.role not in ("admin", "associate"):
        raise HTTPException(
            status_code=422, detail="role must be 'admin' or 'associate'"
        )

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        hashed_pw=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.delete(
    "/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def deactivate_user(
    user_id: str,
    admin: User = Depends(require_admin),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(User).where(User.id == uid, User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user.id) == str(admin.id):
        raise HTTPException(
            status_code=400, detail="Cannot deactivate your own account"
        )

    user.is_active = False
    await db.commit()
