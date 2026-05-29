# AuditForge — CLAUDE.md

Standalone deterministic configuration audit tool. No AI, no database, no session state.
Upload two Excel files → get a 5-sheet comparison report.

---

## Commands

```bash
pip install -r requirements.txt   # first time setup
python main.py                    # start server → http://127.0.0.1:7373
python -m pytest tests/ -v        # run all tests
python -m ruff format engine/ tests/ main.py
python -m ruff check  engine/ tests/ main.py
```

---

## Structure

```
engine/
  types.py       — MappingResult, AuditRow dataclasses (shared types)
  aliases.py     — MANUAL_ALIASES dict (Oracle Fusion column renames)
  normalizer.py  — strip_header, normalize_value, is_capture, detect_ideal_columns
  reader.py      — read_actual(), read_ideal() — file ingestion only
  matcher.py     — build_mapping() — 4-stage waterfall header matching
  comparator.py  — compare() — deterministic BU × config classification
  styles.py      — openpyxl PatternFill/Font constants
  writer.py      — build_report() — 5-sheet Excel builder
  __init__.py    — public API re-exports

main.py          — FastAPI app + uvicorn entry point
static/index.html — minimal upload form (vanilla HTML)
tests/           — pytest unit + integration tests
```

Import from `engine`, never from `engine.submodule` in `main.py`.

---

## Matching Pipeline (4 stages, first hit wins)

1. **Exact** — `ideal_name in actual_headers`
2. **Normalized** — strip spaces/underscores/hyphens, lowercase, compare
3. **Manual Alias** — lookup in `engine/aliases.py`
4. **Fuzzy** — `token_sort_ratio(ideal, actual) >= threshold` (default 80)

If all 4 stages fail → **Unmatched**. Unmatched configs appear in the mapping sheet but produce no audit rows.

---

## Value Comparison Rules

- Both actual and ideal pass through `normalize_value()` before comparison
- Boolean synonyms: Y/y/yes/true/1/enabled/on → `y`; N/n/no/false/0/disabled/off → `n`
- Ideal value containing "capture" (case-insensitive) → extract only, no comparison
- Null actual against a comparison ideal → **Control gap**

---

## Andrej Karpathy Rules for This Codebase

These apply to every change made with Claude Code or otherwise.

**1. Read before write.** Never edit a file without reading it first. Always read the diff before committing.

**2. Stay close to the data.** Run the tool against real Excel files after every non-trivial change. Unit tests on toy data don't catch real-world bugs.

**3. One file, one purpose.** Each module in `engine/` does exactly one thing. `reader.py` reads files. `matcher.py` matches headers. Nothing else. If you find yourself writing parsing logic in `comparator.py`, you're in the wrong file.

**4. Explicit over implicit.** No magic, no metaprogramming, no dynamic dispatch. If a function surprises you on a second read, simplify it.

**5. Functions should be boring.** A function that fits on a screen, takes typed inputs, returns a typed output, and has no side effects is a good function.

**6. Delete code as a feature.** The best refactor removes lines. If you added something "just in case", remove it.

**7. Test with production-like data.** Tests in `test_integration.py` use real Oracle Fusion BU names and realistic config values. Don't replace them with `foo/bar` placeholders.

**8. Commit after each green test.** Small commits are reviewable. Large commits are not.

**9. Type hints are not optional.** Every public function must be typed. `Any` is a code smell.

**10. Comments explain WHY, not WHAT.** The code already says what it does. Comments explain why a surprising decision was made. If it's obvious, don't comment it.

**11. No global mutable state.** All state flows through function parameters. Nothing is shared between requests.

**12. The diff is the product.** Every PR should be reviewable in under 5 minutes. If it isn't, it's too big.

---

## Known Unmatched Fields (by design)

These 5 Oracle Fusion fields exist in the ideal file but have no matching column in the standard INV export. They appear as `Unmatched` in the mapping sheet and produce no audit rows.

- `LastUpdateDate` — audit metadata, not in standard INV org parameter export
- `LastUpdateLogin` — same
- `LastUpdatedBy` — same
- `SourceOrganizationId` — best fuzzy score ~0.72, below threshold
- `SourceSubinventory` — best fuzzy score ~0.70, below threshold

---

## Adding a New Manual Alias

When a client's Oracle Fusion export uses a different column name for a known config:

1. Open `engine/aliases.py`
2. Add `"IdealName": "ActualColumnName"` to `MANUAL_ALIASES`
3. Add a test in `tests/test_matcher.py` covering the new alias
4. Run `python -m pytest tests/test_matcher.py -v`
