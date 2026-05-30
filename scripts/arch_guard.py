#!/usr/bin/env python3
"""Architecture guard — runs after every Python file edit via Claude Code hook.

Enforces the layered architecture defined in PROGRESS.md. Prints violations
immediately so bad directions are caught at save time, not review time.
Never blocks — exit 0 always.
"""

import re
import sys
from pathlib import Path

if len(sys.argv) < 2:
    sys.exit(0)

path = Path(sys.argv[1]).resolve()
if not path.exists() or path.suffix != ".py":
    sys.exit(0)

try:
    src = path.read_text(encoding="utf-8")
except Exception:
    sys.exit(0)

parts = [p.lower() for p in path.parts]
name = path.name
violations: list[str] = []

# ── Rule 1 ──────────────────────────────────────────────────────────────────
# engine/ is only imported from app/services/audit_service.py
# (also allowed in: engine/ itself, tests/, main.py shim)
if re.search(r"from engine[\. ]|import engine", src):
    allowed = (
        "audit_service.py" in name
        or "engine" in parts[:-1]
        or "tests" in parts
        or name == "main.py"
    )
    if not allowed:
        violations.append(
            "engine/ imported outside audit_service.py\n"
            "    → move the call into app/services/audit_service.py"
        )

# ── Rule 2 ──────────────────────────────────────────────────────────────────
# Route files must not import ORM models or SQLAlchemy directly.
# DB access goes through Depends(get_db) → service layer only.
if "routes" in parts:
    if re.search(r"from app\.models|from sqlalchemy", src):
        violations.append(
            "Direct ORM/SQLAlchemy import in a route file\n"
            "    → inject via Depends(get_db) and call a service function"
        )

# ── Rule 3 ──────────────────────────────────────────────────────────────────
# JWT encode/decode lives only in app/core/security.py.
# dependencies.py may call those functions but must not re-implement them.
if name not in ("security.py", "dependencies.py"):
    if re.search(r"jwt\.encode|jwt\.decode|\.sign\(|\.verify\(", src):
        violations.append(
            "JWT logic outside app/core/security.py\n"
            "    → move encode/decode to security.py, call from dependencies.py"
        )

# ── Rule 4 ──────────────────────────────────────────────────────────────────
# SHA-256 hashing of ideal files belongs in audit_service.py only.
if "routes" in parts or "workers" in parts:
    if re.search(r"hashlib\.sha256", src):
        violations.append(
            "hashlib.sha256 in route or worker\n"
            "    → compute ideal_hash in audit_service.py, pass as argument"
        )

# ── Rule 5 ──────────────────────────────────────────────────────────────────
# No global mutable state. _pending dict pattern must not reappear.
if re.search(r"^_pending\s*[:=]\s*\{", src, re.MULTILINE):
    violations.append(
        "Global _pending dict — this is the v1 desktop pattern\n"
        "    → use AuditJob table (status column) instead"
    )

# ── Rule 6 ──────────────────────────────────────────────────────────────────
# Business logic (engine calls, DB writes) must not live in route handlers.
# Routes should be thin: validate → call service → return schema.
if "routes" in parts:
    if re.search(r"build_mapping|build_report|read_actual|read_ideal|compare\(", src):
        violations.append(
            "Engine function called directly in a route\n"
            "    → delegate to app/services/audit_service.py"
        )

# ── Rule 7 ──────────────────────────────────────────────────────────────────
# Passwords must never be compared or stored in plain text.
if re.search(r'== password|password ==|"password"', src, re.IGNORECASE):
    if not re.search(r"verify|hash|bcrypt|passlib", src, re.IGNORECASE):
        violations.append(
            "Possible plain-text password comparison\n"
            "    → use passlib.context.verify() from app/core/security.py"
        )

# ── Rule 8 ──────────────────────────────────────────────────────────────────
# Tenant isolation: every DB query in service/route files must reference tenant_id.
# Flag service files that query IdealFile or AuditJob without tenant_id filter.
if "services" in parts or "routes" in parts:
    has_tenant_model = re.search(r"IdealFile|AuditJob", src)
    has_tenant_filter = re.search(r"tenant_id", src)
    if has_tenant_model and not has_tenant_filter:
        violations.append(
            "Query on IdealFile or AuditJob without tenant_id filter\n"
            "    → every query must scope to current_user.tenant_id"
        )

# ── Output ───────────────────────────────────────────────────────────────────
if violations:
    print(f"\n⚠  ARCH GUARD — {path.name}")
    for i, v in enumerate(violations, 1):
        print(f"  [{i}] {v}")
    print()

sys.exit(0)
