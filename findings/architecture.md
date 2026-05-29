# AuditForge — Architecture Document

> Software architect agent findings on tech stack, data flow, and deployment options.

## Stack Decision

| Layer | Choice | Reason |
|---|---|---|
| Backend | FastAPI + uvicorn | Native async, `UploadFile` abstracts multipart, auto `/docs` |
| Frontend | Vanilla HTML/JS | No build step, PyInstaller-friendly, ~200 lines covers full UX |
| Excel read | pandas + openpyxl | DataFrame ops for BU × config matrix; openpyxl for cell-level styling |
| Fuzzy match | thefuzz (token_sort_ratio) | token_sort_ratio beats ratio for ERP param naming conventions |
| Storage | None — in-memory only | BytesIO: no temp file leaks, no cleanup bugs, stateless per-request |

## Project Structure

```
AuditForge/
├── main.py               # Entry point — FastAPI app + uvicorn runner
├── requirements.txt      # Pinned deps
├── build_exe.bat         # PyInstaller one-click build
│
├── engine/               # Pure domain logic — no HTTP, no I/O except BytesIO
│   ├── __init__.py
│   ├── reader.py         # read_actual() + read_ideal() → DataFrames
│   ├── matcher.py        # build_mapping() — 4-stage waterfall, MappingResult list
│   ├── comparator.py     # compare() → (controls_in_place, control_gaps, additional_data)
│   └── writer.py         # build_report() → Excel bytes
│
├── static/
│   └── index.html        # Single-page UI — drag-drop upload + Fetch API download
│
└── findings/             # Agent analysis documents
    ├── actual_file_analysis.md
    ├── output_analysis.md
    ├── edge_cases.md
    └── architecture.md   (this file)
```

## Data Flow

```
Browser (upload 2 files)
    │
    ▼
POST /api/audit  [FastAPI]
    │
    ├── read_actual(BytesIO)  →  DataFrame[300 BUs × 126 cols]
    ├── read_ideal(BytesIO)   →  DataFrame[33 rows × 2 cols]
    │
    ├── build_mapping(ideal_df, actual_headers, threshold=80)
    │       ├── Stage 1: Exact match
    │       ├── Stage 2: Normalized (strip spaces/underscores/hyphens)
    │       ├── Stage 3: Manual alias (6 known renames)
    │       └── Stage 4: Fuzzy token_sort_ratio ≥ threshold
    │       → list[MappingResult]
    │
    ├── compare(actual_df, mapping)
    │       For each BU × each matched config:
    │       ├── is_capture(ideal_value) → additional_data list
    │       └── normalize_value(actual) == normalize_value(ideal)
    │           → controls_in_place or control_gaps
    │
    ├── build_report(cip, gaps, extra, mapping, ...)
    │       5 sheets: in-place | gaps | additional | mapping log | summary
    │       openpyxl: green/red/blue fills, styled headers, auto-fit columns
    │       → Excel bytes (BytesIO)
    │
    └── StreamingResponse(excel_bytes)  →  Browser auto-download
```

No temp files. No database. No session. Each request is fully self-contained.

## Running the Tool

```bash
# First time setup
pip install -r requirements.txt

# Start server
python main.py
# → Opens http://127.0.0.1:8080 in browser automatically
```

## Packaging as .exe

```
build_exe.bat
→ dist/AuditForge.exe  (~35-45 MB)
```

Double-click opens a terminal + browser tab. Distribute to auditors with no Python installation required.

## Key Design Decisions

**Why not Flask?**  
FastAPI's `UploadFile` + `StreamingResponse` + Pydantic validation is cleaner. Flask would need manual `request.files` + `send_file` + custom error handling. FastAPI gives all of this plus auto `/docs` for free.

**Why openpyxl for output, not pandas `to_excel`?**  
`pandas.to_excel` gives no cell-level styling control. Audit outputs require colour-coded gap rows (red), match rows (green), and styled headers — all requiring openpyxl's `PatternFill` and `Font` APIs directly.

**Why a 4-stage waterfall, not just fuzzy?**  
Fuzzy-only on short ERP param names produces false positives. The waterfall ensures exact/normalized matches are never "improved" by fuzziness — fuzzy only runs when the first 3 stages fail.

**Why `token_sort_ratio` and not `ratio`?**  
`AllowItemSubstitutionsFlag` vs `AllowItemSubstitutions` — `ratio` scores ~88, `token_sort_ratio` scores ~95. For ERP naming conventions where params are token bags, `token_sort_ratio` is the correct scorer.
