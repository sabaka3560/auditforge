"""Header matching — resolves each ideal config name to an actual column.

Matching runs as a 4-stage waterfall; each stage is tried in order and the
first hit wins. Fuzzy matching is the last resort.

Public API:
    build_mapping(ideal_df, actual_headers, fuzzy_threshold) -> list[MappingResult]
"""

from typing import Optional

import pandas as pd
from thefuzz import fuzz

from .aliases import MANUAL_ALIASES
from .normalizer import strip_header
from .types import MappingResult

_FUZZY_LOW_CONFIDENCE = 90  # scores below this get a "verify" remark


def build_mapping(
    ideal_df: pd.DataFrame,
    actual_headers: list[str],
    fuzzy_threshold: int = 80,
) -> list[MappingResult]:
    """Return one MappingResult per row in ideal_df."""
    norm_to_actual = {strip_header(h): h for h in actual_headers}
    return [
        _match_one(
            row["config_name"],
            row["ideal_value"],
            row.get("options", ""),
            actual_headers,
            norm_to_actual,
            fuzzy_threshold,
        )
        for _, row in ideal_df.iterrows()
    ]


def _match_one(
    ideal: str,
    ideal_val: str,
    options: str,
    actuals: list[str],
    norm_to_actual: dict[str, str],
    threshold: int,
) -> MappingResult:
    # Stage 1 — exact
    if ideal in actuals:
        return MappingResult(
            ideal, ideal_val, ideal, "Exact", 1.0, "Matched", "", options
        )

    # Stage 2 — normalized (ignore spaces / underscores / hyphens / case)
    norm = strip_header(ideal)
    if norm in norm_to_actual:
        return MappingResult(
            ideal,
            ideal_val,
            norm_to_actual[norm],
            "Normalized",
            1.0,
            "Matched",
            "",
            options,
        )

    # Stage 3 — manual alias (known Oracle Fusion column renames)
    alias = MANUAL_ALIASES.get(ideal)
    if alias:
        if alias in actuals:
            return MappingResult(
                ideal, ideal_val, alias, "Manual Alias", 1.0, "Matched", "", options
            )
        norm_alias = strip_header(alias)
        if norm_alias in norm_to_actual:
            return MappingResult(
                ideal,
                ideal_val,
                norm_to_actual[norm_alias],
                "Manual Alias",
                1.0,
                "Matched",
                "",
                options,
            )

    # Stage 4 — fuzzy token sort ratio
    best_score, best_header = _best_fuzzy(ideal, actuals)
    if best_score >= threshold:
        remark = (
            "Low confidence — verify mapping"
            if best_score < _FUZZY_LOW_CONFIDENCE
            else ""
        )
        return MappingResult(
            ideal,
            ideal_val,
            best_header,
            "Fuzzy",
            best_score / 100.0,
            "Matched",
            remark,
            options,
        )

    hint = f"Best candidate: {best_header} (score {best_score})" if best_header else ""
    return MappingResult(
        ideal,
        ideal_val,
        None,
        "Unmatched",
        best_score / 100.0,
        "Unmatched",
        hint,
        options,
    )


def _best_fuzzy(ideal: str, actuals: list[str]) -> tuple[int, Optional[str]]:
    best_score = 0
    best_header = None
    for actual in actuals:
        score = fuzz.token_sort_ratio(ideal.lower(), actual.lower())
        if score > best_score:
            best_score, best_header = score, actual
    return best_score, best_header
