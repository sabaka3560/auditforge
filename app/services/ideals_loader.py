"""
Resolves ideal file bytes for a (tenant_id, check_id) pair.

Resolution order:
  1. Active row in IdealFile DB table  →  read from filesystem storage
  2. Bundled default in Settings.ideals_dir/{check_id}.xlsx
  3. Neither found  →  ValueError

The save() method versions ideal files: old active row is deactivated,
a new row with version+1 is inserted, and bytes are written to storage.
"""

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import IdealFile
from app.services import storage


class IdealsLoader:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def load(self, tenant_id: str, check_id: str) -> bytes:
        """
        Return the active ideal file bytes for (tenant_id, check_id).

        Tries the DB-tracked tenant file first, then falls back to the
        bundled default shipped with the application.
        """
        row = await self._active_row(tenant_id, check_id)

        if row is not None:
            # Tenant has a custom (or previously uploaded) ideal on disk.
            return storage.load(row.storage_key, settings=self._settings)

        # Fall back to the bundled default for new / uninitialized tenants.
        bundled = Path(self._settings.ideals_dir) / f"{check_id}.xlsx"
        if bundled.is_file():
            return bundled.read_bytes()

        raise ValueError(f"No ideal file found for check '{check_id}'")

    async def save(
        self,
        tenant_id: str,
        check_id: str,
        data: bytes,
        uploaded_by_id: str,
    ) -> IdealFile:
        """
        Persist a new ideal file version for (tenant_id, check_id).

        Steps:
          1. Compute SHA-256 of the incoming bytes.
          2. Deactivate the current active row (if any).
          3. Write bytes to storage at the canonical key.
          4. Insert a new IdealFile row with version+1 and commit.
        """
        content_hash = hashlib.sha256(data).hexdigest()

        # Deactivate old active row and determine next version number.
        old = await self._active_row(tenant_id, check_id)
        next_version = 1
        if old is not None:
            old.is_active = False
            next_version = old.version + 1

        # Write bytes before touching the DB so a filesystem error does
        # not leave a committed row pointing at missing data.
        key = storage.storage_key(tenant_id, check_id)
        storage.save(key, data, settings=self._settings)

        new_row = IdealFile(
            tenant_id=tenant_id,
            check_id=check_id,
            storage_key=key,
            content_hash=content_hash,
            version=next_version,
            is_active=True,
            uploaded_by=uploaded_by_id,
        )
        self._db.add(new_row)
        await self._db.commit()
        await self._db.refresh(new_row)
        return new_row

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _active_row(self, tenant_id: str, check_id: str) -> IdealFile | None:
        """Return the single active IdealFile row, or None if absent."""
        stmt = select(IdealFile).where(
            IdealFile.tenant_id == tenant_id,
            IdealFile.check_id == check_id,
            IdealFile.is_active.is_(True),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
