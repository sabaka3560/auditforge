"""FastAPI application factory."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models import Tenant, User
from app.routes import audit, auth, ideals, users


async def _seed_default_admin() -> None:
    """Create a default admin user + tenant on first boot if the DB is empty."""
    async with AsyncSessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(User))
        if count and count > 0:
            return

        tenant = Tenant(slug="default", name="Default")
        db.add(tenant)
        await db.flush()

        user = User(
            tenant_id=tenant.id,
            email="admin@auditforge.local",
            hashed_pw=hash_password("admin123"),
            role="admin",
        )
        db.add(user)
        await db.commit()

        print("\n" + "=" * 52)
        print("  AuditForge — first-boot seed complete")
        print("  Email:    admin@auditforge.local")
        print("  Password: admin123")
        print("  Change the password after first login.")
        print("=" * 52 + "\n")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await _seed_default_admin()
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="AuditForge", version="2.0.0", lifespan=lifespan)

    @application.get("/health", include_in_schema=False)
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @application.get("/api/checks", include_in_schema=False)
    def list_checks() -> list[dict]:
        """Return available audit checks from the bundled ideals directory."""
        settings = get_settings()
        checks_path = os.path.join(settings.ideals_dir, "checks.json")
        with open(checks_path) as f:
            data: dict = json.load(f)
        return [
            {
                "id": k,
                "name": v["name"],
                "default_sheet": v.get("default_sheet") or "",
                "description": v.get("description") or "",
            }
            for k, v in data.items()
        ]

    application.include_router(auth.router)
    application.include_router(audit.router)
    application.include_router(ideals.router)
    application.include_router(users.router)

    application.mount("/", StaticFiles(directory="static", html=True), name="static")

    return application


app = create_app()
