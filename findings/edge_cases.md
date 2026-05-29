# Edge Case Analysis & Design Decisions

> Agent findings on feasibility, edge cases, and implementation recommendations.

## 1. Ideal File Column Auto-Detection

**Strategy (cascading, stop at first hit):**
1. Known-header alias scan (normalized): "name", "config", "parameter", "config name", "configuration" → name col; "ideal value", "ideal", "expected value", "expected", "standard", "value" → value col
2. Fallback: column 0 = name, column 1 = value
3. If >2 columns exist: use only the two detected columns, log a warning

## 2. Fuzzy Match Threshold

- **Default: 80** (not 85 — 85 misses short-name cases like WMSEnabled vs WMS Enabled)
- Use `token_sort_ratio` not `ratio` — config names are token bags
- Scores 70–79: flag as "Fuzzy (low confidence)" with yellow highlight in mapping sheet
- Below 70: mark Unmatched

## 3. Case-Sensitivity in Value Comparison

**Always normalize before comparison, preserve original in output.**

Boolean normalization map:
- Y / y / Yes / yes / true / 1 / enabled / on / active → `y`
- N / n / No / no / false / 0 / disabled / off / inactive → `n`
- Non-boolean values: just strip whitespace + lowercase

## 4. Null/Blank Actual Values

- Empty cell or whitespace → display as empty string `""`
- Compared against normalized ideal value → will produce a gap row (expected)
- Note in output as `""` not `"None"` (avoid confusion between Python None and string "None")

## 5. Capture Detection Patterns (case-insensitive substring)

```
"capture", "record the value", "extract", "document the actual",
"note the value", "for information only", "informational"
```

**Rule:** If any of these appear in the ideal value → extract-only, no comparison.

**Edge case:** Ideal value is literally the single word "Capture" — treated as capture instruction by default.

## 6. Multi-Value Ideal Fields (v1 scope)

- OR-list (`Y or N`, `Y/N`, `A, B, C`) → **not implemented in v1**
- Detection: if ideal value contains " or " or "/" → mark as "Manual Review Required" (not implemented yet, falls through to normal comparison)
- Numeric ranges (`1-5`, `>=1000`) → not implemented in v1
- Recommendation: v1 treats these as literal string comparisons; add tier 2 in v2

## 7. Required Libraries

**Standard library (no install):** `re`, `io`, `os`, `sys`, `pathlib`, `csv`, `argparse`

**pip install required:**
- `openpyxl>=3.1` — Excel read/write
- `pandas>=2.0` — DataFrame operations  
- `thefuzz[speedup]>=0.22` — fuzzy matching
- `python-Levenshtein>=0.25` — C-extension speedup for thefuzz
- `fastapi>=0.115` — HTTP server
- `uvicorn[standard]>=0.32` — ASGI server
- `python-multipart>=0.0.12` — multipart file upload parsing

## 8. UI Validation

**Before submission:**
- Both files must be present
- Actual file must be `.xlsx` or `.xls`
- Ideal file must be `.xlsx`, `.xls`, or `.csv`

**Server-side pre-flight:**
- Check sheet name exists in actual file, return 400 with sheet list if not
- Ideal file must have ≥2 columns
- Corrupt/invalid Excel → 422 with friendly message

## Architecture Decision: In-Memory Only

No temp files. All processing uses `io.BytesIO`. Upload bytes → engine → response bytes.
Reason: temp file cleanup bugs are the most common failure mode on Windows for file-upload tools.
