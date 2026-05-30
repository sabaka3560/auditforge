from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, decode_token, verify_password
from app.dependencies import get_db
from app.models import User

_REFRESH_COOKIE = "refresh_token"
_REFRESH_DAYS = 30

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
async def login(
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(form.password, user.hashed_pw)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = user.id.hex
    tenant_id = str(user.tenant_id)

    access_token = create_access_token(user_id, tenant_id, user.role)

    # Refresh token reuses the same JWT structure but with a 30-day expiry.
    # It is never accepted by protected endpoints — only by /auth/refresh.
    settings = get_settings()
    refresh_exp = datetime.now(timezone.utc) + timedelta(days=_REFRESH_DAYS)
    refresh_token = jwt.encode(
        {
            "sub": user_id,
            "tenant_id": tenant_id,
            "role": user.role,
            "exp": int(refresh_exp.timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_REFRESH_DAYS * 86_400,
        path="/auth/refresh",
    )

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    raw = request.cookies.get(_REFRESH_COOKIE)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # decode_token raises 401 on invalid/expired
    payload = decode_token(raw)
    user_id: str = str(payload["sub"])
    tenant_id: str = str(payload["tenant_id"])
    role: str = str(payload["role"])

    # Re-check liveness before issuing a new short-lived token
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(access_token=create_access_token(user_id, tenant_id, role))
