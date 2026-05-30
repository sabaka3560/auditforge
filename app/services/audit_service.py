"""Audit orchestration service — the only place that calls engine/.

Public API:
    run_audit(...) -> bytes
"""

from __future__ import annotations

import io

from engine import build_mapping, build_report, compare, read_actual, read_ideal


async def run_audit(
    actual_bytes: bytes,
    ideal_bytes: bytes,
    check_id: str,
    actual_filename: str,
    ideal_name: str,
    sheet_name: str,
    fuzzy_threshold: int,
) -> bytes:
    """Run the full audit pipeline and return excel_bytes.

    Raises:
        ValueError: for bad input (propagated from engine).
        RuntimeError: wraps any unexpected engine exception.
    """
    effective_sheet = sheet_name or "INV_ORGANIZATION_PARAMETER"

    try:
        actual_df = read_actual(io.BytesIO(actual_bytes), sheet_name=effective_sheet)
        ideal_df = read_ideal(io.BytesIO(ideal_bytes))
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to parse input files: {exc}") from exc

    try:
        mapping = build_mapping(
            ideal_df,
            list(actual_df.columns),
            fuzzy_threshold=fuzzy_threshold,
        )
        cip, gaps, extra = compare(actual_df, mapping)
        excel_bytes = build_report(
            cip,
            gaps,
            extra,
            mapping,
            actual_filename=actual_filename,
            ideal_filename=ideal_name,
            total_bu_rows=len(actual_df),
            fuzzy_threshold=fuzzy_threshold,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Audit pipeline error: {exc}") from exc

    return excel_bytes
