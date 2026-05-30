# AuditForge — Progress & Architecture

---

## Current Version: v1.001 (Desktop Exe — Shipped)
## Target: v2.0 Web App — Scalable, Multi-Tenant, 100% Reliable

---

## File Structure — Current

```
AuditForge/
├── engine/                         # Core audit logic — pure Python, zero side effects
│   ├── __init__.py                 # Public API (only import from here)
│   ├── types.py                    # MappingResult, AuditRow dataclasses
│   ├── aliases.py                  # MANUAL_ALIASES: Oracle column renames
│   ├── normalizer.py               # strip_header(), normalize_value(), is_capture()
│   ├── reader.py                   # read_actual(), read_ideal()
│   ├── matcher.py                  # build_mapping() — 4-stage waterfall
│   ├── comparator.py               # compare() — deterministic BU × config classification
│   ├── styles.py                   # openpyxl style constants
│   └── writer.py                   # build_report() — 5-sheet Excel builder
├── ideals/                         # Benchmark files (admin-controlled)
│   ├── checks.json                 # Registry: {check_id: {name, file, default_sheet}}
│   ├── inv_organization_parameters.xlsx
│   ├── receiving_parameters.xlsx
│   ├── invoice_options.xlsx
│   ├── invoice_tolerances.xlsx
│   └── common_pay_proc_options.xlsx
├── static/index.html               # Vanilla HTML/JS frontend
├── tests/                          # pytest suite (47+ tests)
├── findings/                       # Analysis docs (dev reference)
├── main.py                         # FastAPI + uvicorn + pywebview (desktop)
├── requirements.txt
├── build_exe.bat
├── .mcp.json                       # MCP docs: 15 server-side libraries
└── .claude/settings.json           # 6 hooks: ruff, pytest, pip, JSON lint, pre-commit
```

---

## File Structure — Target (v2.0 Web App)

```
AuditForge/
├── engine/                         # UNTOUCHED — clean, tested, stateless
│
├── app/                            # New web-app layer
│   ├── main.py                     # create_app() factory
│   ├── core/
│   │   ├── config.py               # Settings (pydantic-settings, .env-backed)
│   │   ├── security.py             # JWT encode/decode, bcrypt hashing
│   │   └── database.py             # SQLAlchemy async engine + session factory
│   ├── dependencies.py             # ALL Depends() providers: db, user, tenant, ideals
│   ├── models/
│   │   ├── user.py                 # User, Role enum
│   │   └── tenant.py               # Tenant
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── audit.py
│   │   └── tenant.py
│   ├── routes/
│   │   ├── auth.py                 # POST /auth/token, POST /auth/refresh
│   │   ├── audit.py                # POST /audit/run, GET /audit/{job_id}
│   │   ├── checks.py               # GET /checks, GET /checks/{id}/download
│   │   └── admin.py                # admin-only ideal file management
│   ├── services/
│   │   ├── audit_service.py        # ONLY place engine/ is called from
│   │   ├── ideals_loader.py        # git-backed ideal file resolver
│   │   ├── rule_registry.py        # extensible value comparison rules
│   │   └── job_service.py          # RQ enqueue/poll
│   └── workers/
│       └── audit_worker.py         # RQ task → calls audit_service
│
├── ideals/                         # Bundled defaults (git-synced at runtime)
├── static/index.html               # Updated for JWT auth + job polling
├── tests/                          # Expanded (see test strategy)
├── alembic/                        # DB migrations
├── .env                            # NEVER committed
├── .env.example                    # Committed — no secrets
└── main.py                         # Thin shim: from app.main import app
```

**Rule:** `engine/` is never imported directly from `app/routes/` or `app/workers/`. All engine calls go through `app/services/audit_service.py` — the single translation layer between HTTP and engine.

---

## Version History

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-05-27 | Core engine: read → match → compare → report |
| v0.2 | 2026-05-27 | Modular refactor, 8 engine modules, 47 tests |
| v1.0 | 2026-05-29 | Desktop exe: PyInstaller + pywebview, admin panel, 5 Oracle modules |
| v1.001 | 2026-05-29 | Fix: force edgechromium GUI, HTTP bypass for binary ops in exe |

---

## Architecture

### Current (Desktop Exe)
```
pywebview (Edge WebView2)
  │  window.pywebview.api (direct — no HTTP for binary ops)
  ▼
_DesktopApi: run_audit(), download_ideal(), upload_ideal()
  │
  ▼
engine/  →  ideals/ (local, bundled in exe)
  │
FastAPI + uvicorn (127.0.0.1:7373) — HTTP endpoints for dev mode only
```

### Target Phase 2 (Web App, Single Team)
```
Browser  ──HTTPS──►  FastAPI (app/)
                         │  JWT: {sub, tenant_id, role, exp}
                     Depends() tree:
                         get_db → AsyncSession
                         get_current_user → User
                         require_admin → User (role=admin only)
                         get_tenant → Tenant
                         get_ideals_loader → IdealsLoader
                         │
                     app/services/audit_service.py
                         │  (ONLY caller of engine/)
                     engine/: read → match → compare → build_report
                         │
                     ideals/ (git-synced on startup)
```

### Target Phase 3 (Multi-Tenant, Async)
```
Browser  ──HTTPS──►  FastAPI (stateless, horizontally scalable)
                         │
              ┌──────────┴────────────────────────┐
              │                                   │
         PostgreSQL                          Redis + RQ
         ├── tenants                         (audit job queue)
         ├── users (role: admin|associate)        │
         ├── ideal_files (per-tenant)        audit_worker.py
         └── audit_jobs (history + hash)     calls engine/
                                                   │
                                           S3 / Azure Blob
                                           (ideal files + reports)
```

---

## Implementation Roadmap

### Pre-flight Fixes (do before v2.0 — reliability)

These are silent bugs in the current codebase, ordered by severity:

1. **Add 50 MB file size gate** — `main.py` before `read_actual()`:
   ```python
   if len(actual_bytes) > 50 * 1024 * 1024:
       raise ValueError("File exceeds 50 MB limit.")
   ```

2. **Add empty ideal guard** — top of `build_mapping()` in `engine/matcher.py`:
   ```python
   if ideal_df.empty:
       raise ValueError("Ideal file has no config rows.")
   ```

3. **Fix `_pending` TTL** — in `main.py`, evict tokens older than 5 minutes on each `/api/audit` call. Without this, abandoned sessions leak memory indefinitely in hosted mode.

4. **Write 5 missing test cases** in `tests/test_oracle_audit_scenarios.py`:
   - `TestIntegerLOVCodes` — `"1"→"y"` bool map creates false CIPs on `NegativeInvReceiptCode` (LOV code 1/2, not boolean)
   - `TestUnicodeBUNames` — Arabic/APAC BU names must survive stringify
   - `TestDuplicateBURows` — same BU appearing twice must produce two independent findings
   - `TestFuzzyFalsePositiveBoundary` — short config name matched above threshold must carry a 'verify' remark
   - `TestAllNullActualColumn` — all-null column must produce all gaps, not CIP

5. **Add property-based tests** (`tests/test_properties.py`) with Hypothesis:
   - `normalize_value` is idempotent: `normalize(normalize(x)) == normalize(x)` for all strings
   - `compare()` row count invariant: `len(cip) + len(gaps) + len(extra) == n_bus × n_matched_configs`

6. **Add performance benchmarks** (`tests/test_benchmark.py`) with pytest-benchmark:
   - Thresholds: 100 BU < 0.5s, 500 BU < 2s, 1000 BU < 5s
   - If 500 BU breaches 2s: vectorize `comparator.py` (replace `iterrows()` with pandas vectorized ops)

7. **Ship GitHub Actions CI** (`.github/workflows/ci.yml`):
   - Triggers: push to main/feat/fix, PR to main
   - Stages: ruff lint, ruff format check, pyright type check, pytest + coverage (fail below 85%), Hypothesis properties
   - Benchmarks run on main only (informational, never block merge)

---

### v2.0 — Web App, Single Team

**Auth:**
```python
# JWT payload
{"sub": "<user.id>", "tenant_id": "<tenant.id>", "role": "admin|associate", "exp": <unix>}

# Dependencies (app/dependencies.py)
get_current_user   # reads Bearer token → User
require_admin      # get_current_user + assert role == "admin", else 403
get_tenant         # get_current_user + load Tenant row
get_ideals_loader  # IdealsLoader(db_session, storage_path) — resolves per-tenant ideal from DB
```

**Database schema:**
```python
# 4 tables — SQLAlchemy 2.0 async mapped columns
Tenant:    id, slug, name, created_at
User:      id, tenant_id→Tenant, email, hashed_pw, role(admin|associate), is_active, created_at
IdealFile: id, tenant_id→Tenant, check_id, storage_key, uploaded_by→User, created_at
           UniqueConstraint(tenant_id, check_id)
AuditJob:  id, tenant_id, submitted_by→User, check_id, actual_key, report_key,
           status(queued|running|done|failed), fuzzy_threshold, error_message,
           created_at, finished_at
```

**API surface:**
```
# Auth (public)
POST   /auth/token                        # {email, password} → {access_token}
POST   /auth/refresh                      # HttpOnly cookie → {access_token}
POST   /auth/logout

# Audits (JWT required)
POST   /api/audits                        # multipart: actual_file, check_id → 202 {job_id}
GET    /api/audits                        # list user's jobs (paginated)
GET    /api/audits/{job_id}               # poll: {status, created_at, finished_at, error_message}
GET    /api/audits/{job_id}/download      # stream report xlsx (status must be "done")
POST   /api/audits/{job_id}/retry         # resubmit failed job (new job, original unchanged)

# Ideal files (JWT required; upload/delete require admin)
GET    /api/ideals                        # list ideals for tenant
GET    /api/ideals/{check_id}/download    # stream ideal xlsx
POST   /api/ideals/{check_id}             # require_admin — upload new ideal
DELETE /api/ideals/{check_id}             # require_admin — revert to bundled default

# Admin (require_admin)
GET    /api/admin/users
POST   /api/admin/users                   # {email, role, password}
PATCH  /api/admin/users/{user_id}         # change role, deactivate
```

**Settings (app/core/config.py):**
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    host: str = "0.0.0.0"
    port: int = 7373
    database_url: str          # required — no default
    jwt_secret: str            # required — no default
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    ideals_dir: str = "ideals"       # bundled defaults (fallback for new tenants)
    storage_path: str = "storage"    # where uploaded ideal files and reports are written
    fuzzy_threshold_default: int = 80
```

**Migration sequence:**
1. Add `app/core/config.py`, `app/core/database.py`, `app/models/` — no behaviour change
2. Run Alembic `init` + first migration (creates 4 tables)
3. Add `app/core/security.py` + `app/dependencies.py`
4. Add `app/routes/auth.py` — login/refresh. Smoke-test with httpie
5. Replace `POST /api/audit` → `POST /api/audits` (async, 202). Keep old endpoint under feature flag during frontend update
6. Replace `_pending` download → `GET /api/audits/{job_id}/download`
7. Add `app/routes/admin.py` for ideal file management
8. Remove `_pending` dict and `/api/download/{token}`
9. Update `static/index.html` for JWT auth + polling

---

### v2.1 — DB-Backed Ideal Values (Configurable, Read-Only for Associates)

The database is the distribution mechanism. No git, no tokens, no subprocess. This was the right answer all along once we have a server.

**How it works:**
- Admin calls `POST /api/ideals/{check_id}` — guarded by `require_admin` (JWT role check → 403 for associates)
- Server stores file at `ideals/{tenant_id}/{check_id}.xlsx` (local FS or S3), writes a row to `IdealFile` table
- Associates get ideals at audit time from `IdealsLoader` which reads from server storage — no write path exists
- Read-only enforcement: JWT role at the API layer. No separate mechanism needed

**`IdealFile` table — add two columns:**
```python
class IdealFile(Base):
    ...
    content_hash: Mapped[str]  = mapped_column(String(64))   # SHA-256 hex of file bytes
    version:      Mapped[int]  = mapped_column(Integer, default=1)
    is_active:    Mapped[bool] = mapped_column(default=True)
    # On new upload: set old row is_active=False, insert new row with version+1
    # Append-only — never delete rows. Full version history is always queryable.
```

**SHA-256 in every report (SOX ITGC requirement):**
```python
# In audit_service.py
ideal_bytes = ideals_loader.load(check_id, tenant_id)
ideal_hash = hashlib.sha256(ideal_bytes).hexdigest()
excel_bytes = build_report(..., ideal_sha256=ideal_hash)

# In engine/writer.py _summary_sheet — append after row 14:
("Ideal file SHA-256", ideal_sha256),   # row 15 — Audit Summary sheet, cell B15
```

External auditors verify by fetching the `IdealFile.content_hash` from the DB for the given `AuditJob.ideal_file_id` and comparing. The chain: `AuditJob → IdealFile.content_hash → report B15`. Tamper-evident without git.

**`IdealsLoader` resolution order (in `app/services/ideals_loader.py`):**
1. Check `IdealFile` table for `(tenant_id, check_id, is_active=True)` → load from storage
2. Fall back to bundled `ideals/{check_id}.xlsx` in the repo (default for new tenants)

**Adding a new Oracle module:** 3 steps, zero code changes:
1. Create `ideals/{check_id}.xlsx` — bundled default
2. Add entry to `ideals/checks.json` (`check_id`, `name`, `file`, `default_sheet`)
3. Add any module-specific column renames to `engine/aliases.py`

After that, the new module appears in the UI dropdown automatically on next deploy.

**Keep Excel, not YAML.** Admins are Oracle Functional Consultants — they live in Excel. YAML requires a text editor, no autocomplete, and one indentation error causes a cryptic parse failure.

---

### v2.2 — Async Job Queue

```python
# celery_app.py
celery = Celery("auditforge", broker="redis://localhost:6379/0",
                backend="redis://localhost:6379/1")

# app/workers/audit_worker.py
@celery.task(bind=True, max_retries=2, default_retry_delay=5)
def run_audit_task(self, job_id: str) -> None:
    # 1. Load AuditJob row, set status="running"
    # 2. Download actual file from storage (actual_key)
    # 3. Load ideal bytes via ideals_loader (tenant-scoped, falls back to bundled)
    # 4. engine: read_actual → read_ideal → build_mapping → compare → build_report
    # 5. Upload report to storage at reports/{tenant_id}/{job_id}.xlsx
    # 6. AuditJob: status="done", report_key=..., finished_at=now()
    # On exception: status="failed", error_message=str(exc), retry if transient
```

---

### v3.0 — Multi-Tenant

- `IdealsLoader.load(check_id, tenant_id)` checks `ideals/{tenant_id}/{check_id}.xlsx` first, falls back to `ideals/{check_id}.xlsx`
- Every DB query filters `tenant_id = current_user.tenant_id` — enforced in `app/services/`, not in routes
- Uploaded files stored at `uploads/{tenant_id}/{job_id}/actual.xlsx` — deleted after report written
- Reports stored at `reports/{tenant_id}/{job_id}.xlsx` in S3/Blob
- Per-tenant ideal file versioning: `IdealFile` table is append-only; `status=active` flag marks canonical version

---

## Extensible Value Comparison Rules

For clients needing numeric range comparison (`ideal="1-5"`, `actual=3` → CIP):

```python
# app/services/rule_registry.py
class ComparisonRule(Protocol):
    def matches(self, actual: str, ideal: str) -> bool | None: ...

class NumericRangeRule:
    _RANGE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$")
    def matches(self, actual: str, ideal: str) -> bool | None:
        m = self._RANGE.match(ideal)
        if m is None: return None  # abstain
        try: return float(m.group(1)) <= float(actual) <= float(m.group(2))
        except ValueError: return None
```

Rules are post-processors: `engine.compare()` runs first (deterministic, unchanged), then `rule_registry.evaluate()` can reclassify gaps to CIP. Engine output is never mutated — the rule registry is a separate auditable layer in the service tier.

To add a rule: add one class to `rule_registry.py`, append to `_RULES`. To make rules tenant-configurable: `_RULES` becomes a per-tenant list loaded from Postgres.

---

## Oracle Modules

| check_id | Name | Sheet | Status |
|---|---|---|---|
| `inv_organization_parameters` | INV Organization Parameters | INV_ORGANIZATION_PARAMETER | ✓ Production |
| `receiving_parameters` | Receiving Parameters | RCV_OPTIONS | ✓ Production |
| `invoice_options` | Invoice Options | _(auto)_ | ✓ Production |
| `invoice_tolerances` | Invoice Tolerances | AP_TOLERANCE_TEMPLATE | ✓ Production |
| `common_pay_proc_options` | Common Pay Proc Options | AP_FINANCIAL_SYS_PARAM | ✓ Production |

**Next modules (backlog):** GL Journal Entry Controls, FA Asset Parameters, AR System Options

---

## Test Strategy

### Current
| File | Tests |
|---|---|
| `test_matcher.py` | 16 |
| `test_comparator.py` | 18 |
| `test_integration.py` | 13 |
| `test_reader.py`, `test_api.py`, `test_normalizer.py`, `test_oracle_audit_scenarios.py` | existing |

### To Add
- `test_oracle_audit_scenarios.py` — 5 new cases (LOV codes, unicode, duplicate BUs, fuzzy boundary, all-null column)
- `test_properties.py` — Hypothesis: normalize idempotency, compare row count invariant
- `test_benchmark.py` — pytest-benchmark: 100/300/500/1000 BU thresholds

### CI/CD (`.github/workflows/ci.yml`)
- Triggers: push to main/feat/fix, PR to main
- Stages: ruff lint → ruff format check → pyright → pytest+coverage (min 85%) → Hypothesis
- Benchmarks: main only, informational artifact

---

## Active Hooks (`.claude/settings.json`)

| Trigger | Hook | Timeout |
|---|---|---|
| Write/Edit any file | ruff format | 10s |
| Write/Edit any Python file | ruff check --fix | 10s |
| Write/Edit `engine/*.py` or `main.py` | pytest tests/ -x -q (last 6 lines) | 60s |
| Write/Edit `tests/test_*.py` | pytest that file -v (last 10 lines) | 60s |
| Write/Edit `requirements.txt` | pip install -r requirements.txt | 60s |
| Write/Edit `*.json` | python JSON validation | 5s |
| Bash `git commit` | pytest tests/ -x pre-commit guard | 60s |

---

## MCPs (`.mcp.json`)

Server-side docs loaded: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic, Python 3.12, python-jose (JWT), passlib (bcrypt), RQ, redis-py, asyncpg, httpx, pytest, slowapi, pandas, openpyxl + context7 + fetch.

---

## Known Limitations

1. **Integer LOV codes** — `normalize_value("1")` → `"y"` misclassifies Oracle LOV code 1 on `NegativeInvReceiptCode`. Tracked in TC-1 test above. Fix: per-config comparison mode in rule_registry.
2. **5 permanently unmatched fields** — LastUpdateDate, LastUpdateLogin, LastUpdatedBy, SourceOrganizationId, SourceSubinventory. By design.
3. **No multi-value ideal support** — `"Y or N"` compared literally. Fix at v2.1 via NumericRangeRule pattern.
4. **No async** — large files block the server. Fixed at v2.2 (RQ).
5. **`_pending` dict has no TTL** — memory leak in hosted mode. Pre-flight fix #3 above.

---

## Dependencies

```
# Current (v1.x)
fastapi, uvicorn[standard], python-multipart, openpyxl, xlrd, pandas,
thefuzz, python-Levenshtein, pywebview (dropped at v2.0)

# Phase 2 additions
python-jose[cryptography], passlib[bcrypt], sqlalchemy>=2.0, alembic,
pydantic-settings

# Phase 3 additions
asyncpg, rq, redis, boto3 (or azure-storage-blob), slowapi, hypothesis,
pytest-benchmark, pyright
```
