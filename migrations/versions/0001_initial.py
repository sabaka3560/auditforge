"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'associate')")
    op.execute(
        "CREATE TYPE audit_job_status AS ENUM ('queued', 'running', 'done', 'failed')"
    )

    op.execute("""
        CREATE TABLE tenants (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug        VARCHAR(64)  NOT NULL UNIQUE,
            name        VARCHAR(256) NOT NULL,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE users (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID         NOT NULL REFERENCES tenants(id),
            email       VARCHAR(256) NOT NULL UNIQUE,
            hashed_pw   VARCHAR(256) NOT NULL,
            role        user_role    NOT NULL,
            is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE ideal_files (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id     UUID         NOT NULL REFERENCES tenants(id),
            check_id      VARCHAR(64)  NOT NULL,
            storage_key   VARCHAR(512) NOT NULL,
            content_hash  VARCHAR(64)  NOT NULL,
            version       INTEGER      NOT NULL DEFAULT 1,
            is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
            uploaded_by   UUID         REFERENCES users(id),
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE audit_jobs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID              NOT NULL REFERENCES tenants(id),
            submitted_by     UUID              NOT NULL REFERENCES users(id),
            check_id         VARCHAR(64)       NOT NULL,
            sheet_name       VARCHAR(128),
            actual_key       VARCHAR(512)      NOT NULL,
            report_key       VARCHAR(512),
            ideal_hash       VARCHAR(64),
            status           audit_job_status  NOT NULL DEFAULT 'queued',
            fuzzy_threshold  INTEGER           NOT NULL DEFAULT 80,
            error_message    TEXT,
            created_at       TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
            finished_at      TIMESTAMPTZ
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_jobs")
    op.execute("DROP TABLE IF EXISTS ideal_files")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS tenants")
    op.execute("DROP TYPE IF EXISTS audit_job_status")
    op.execute("DROP TYPE IF EXISTS user_role")
