"""
Thin filesystem abstraction for blob storage.

All paths are relative keys (e.g. "ideals/tenant_abc/inv.xlsx").
The base root is Settings.storage_path.

Future S3 drop-in: replace the four _fs_* helpers with boto3 equivalents
behind the same public interface — callers are unaffected.
"""

from pathlib import Path

from app.config import Settings


def storage_key(tenant_id: str, check_id: str) -> str:
    """Canonical key for a tenant-scoped ideal file."""
    return f"ideals/{tenant_id}/{check_id}.xlsx"


# ---------------------------------------------------------------------------
# Internal helpers — local filesystem only
# ---------------------------------------------------------------------------


def _resolve(base: Path, relative_key: str) -> Path:
    # Normalise separators; guard against path traversal.
    clean = Path(relative_key.replace("\\", "/"))
    resolved = (base / clean).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError(f"Key '{relative_key}' escapes storage root.")
    return resolved


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save(relative_key: str, data: bytes, *, settings: Settings) -> str:
    """
    Write *data* to storage under *relative_key*.
    Creates parent directories as needed.
    Returns the key (unchanged) so callers can store it.
    """
    # S3 future: s3_client.put_object(Bucket=settings.s3_bucket, Key=relative_key, Body=data)
    dest = _resolve(Path(settings.storage_path), relative_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return relative_key


def load(relative_key: str, *, settings: Settings) -> bytes:
    """
    Read and return bytes stored at *relative_key*.
    Raises FileNotFoundError if the key does not exist.
    """
    # S3 future: return s3_client.get_object(Bucket=settings.s3_bucket, Key=relative_key)["Body"].read()
    path = _resolve(Path(settings.storage_path), relative_key)
    if not path.is_file():
        raise FileNotFoundError(f"Storage key not found: '{relative_key}'")
    return path.read_bytes()


def exists(relative_key: str, *, settings: Settings) -> bool:
    """Return True if *relative_key* points to an existing file."""
    # S3 future: use s3_client.head_object() wrapped in a try/except ClientError
    try:
        path = _resolve(Path(settings.storage_path), relative_key)
    except ValueError:
        return False
    return path.is_file()


def delete(relative_key: str, *, settings: Settings) -> None:
    """
    Remove the file at *relative_key*.
    Silent no-op if the key does not exist (idempotent).
    """
    # S3 future: s3_client.delete_object(Bucket=settings.s3_bucket, Key=relative_key)
    try:
        path = _resolve(Path(settings.storage_path), relative_key)
    except ValueError:
        return
    path.unlink(missing_ok=True)
