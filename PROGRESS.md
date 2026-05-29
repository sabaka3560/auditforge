# AuditForge — Progress Tracker

## Status: Active Development

---

## Completed

### v0.1 — Core Engine (2026-05-27)
- [x] `read_actual()` — reads Oracle Fusion INV export, normalizes BU column
- [x] `read_ideal()` — reads ideal value file (Excel or CSV), auto-detects columns
- [x] `build_mapping()` — 4-stage waterfall: exact → normalized → manual alias → fuzzy
- [x] `compare()` — deterministic BU × config classification
- [x] `build_report()` — 5-sheet styled Excel output
- [x] FastAPI server on port 7373, in-memory only (no temp files)
- [x] Minimal dark HTML form
- [x] Smoke test: 300 BUs × 33 ideal configs → matches sample output exactly
  - Controls in place: 441
  - Control gaps: 4,059
  - Additional data: 3,900

### v0.2 — Modular Refactor + Tests (2026-05-27)
- [x] Split engine into 8 focused modules (`types`, `aliases`, `normalizer`, `reader`, `matcher`, `comparator`, `styles`, `writer`)
- [x] Public API via `engine/__init__.py` — `main.py` imports from package, not submodules
- [x] `engine/aliases.py` — 7 known Oracle Fusion column renames isolated to one file
- [x] `engine/normalizer.py` — all value/header normalization in one place
- [x] `engine/styles.py` — Excel style constants centralized
- [x] Test suite: `test_matcher.py` (16 tests), `test_comparator.py` (18 tests), `test_integration.py` (13 tests)
- [x] Tests use realistic Oracle Fusion BU names and config patterns
- [x] CLAUDE.md with Karpathy rules, architecture notes, contribution guide
- [x] Architecture visualizer: `architecture.html`
- [x] Claude Code hooks (ruff format + lint on Python file edits)
- [x] `.mcp.json` with Python documentation MCP

---

## In Progress

_(nothing currently)_

---

## Backlog

### v0.3 — Hardening
- [ ] Multi-value ideal fields: `Y or N`, `A/B/C` — OR-list comparison
- [ ] Numeric range ideal fields: `1-5`, `>=1` — detect and flag as "Manual Review Required"
- [ ] Configurable capture phrase list (editable from UI or config file)
- [ ] "Match Review" step before report generation — show proposed mapping, allow overrides
- [ ] Sheet name selector in UI (show available sheets after file upload)
- [ ] File size limit enforcement (currently uncapped)

### v0.4 — Multiple Module Support
- [ ] Support non-INV Oracle Fusion modules (AP, AR, GL, FA)
- [ ] Per-module alias tables and sheet name defaults
- [ ] Module selector in UI

### v0.5 — Distribution
- [ ] PyInstaller `.exe` — `build_exe.bat`
- [ ] Auto-open browser tab on launch
- [ ] Version number in UI header

---

## Test Coverage

| File | Tests | Last Run |
|---|---|---|
| `test_matcher.py` | 16 | 2026-05-27 ✓ |
| `test_comparator.py` | 18 | 2026-05-27 ✓ |
| `test_integration.py` | 13 | 2026-05-27 ✓ |

---

## Known Limitations

1. **5 unmatched fields** — LastUpdateDate, LastUpdateLogin, LastUpdatedBy, SourceOrganizationId, SourceSubinventory have no matching column in standard Oracle Fusion INV export. They appear as Unmatched in the mapping sheet by design.
2. **Integer lookup codes not normalized** — NegativeInvReceiptCode stores integers (1/2), not Y/N. Comparing against a Y/N ideal will produce gaps even for "correct" values.
3. **No multi-value support** — Ideal values like `Y or N` are compared literally, not as acceptable ranges.
