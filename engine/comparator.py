"""Deterministic comparison — classifies each BU × config pair into one of three buckets.

Controls in place  — actual value matches ideal (after normalization)
Control gaps       — actual value does not match ideal
Additional data    — ideal value is a capture instruction; actual is just extracted

Public API:
    compare(actual_df, mapping) -> (controls_in_place, control_gaps, additional_data)
"""

import pandas as pd

from .normalizer import check_range, is_capture, is_range, normalize_value
from .types import AuditRow, MappingResult


def compare(
    actual_df: pd.DataFrame,
    mapping: list[MappingResult],
) -> tuple[list[AuditRow], list[AuditRow], list[AuditRow]]:
    controls_in_place: list[AuditRow] = []
    control_gaps: list[AuditRow] = []
    additional_data: list[AuditRow] = []

    matched = [
        m for m in mapping if m.matched_header and m.matched_header in actual_df.columns
    ]

    for m in matched:
        for _, row in actual_df.iterrows():
            bu = str(row["BU_NAME"]).strip()
            if not bu or bu == "nan":
                continue

            raw = row.get(m.matched_header)
            display = (
                ""
                if (raw is None or (isinstance(raw, float) and pd.isna(raw)))
                else str(raw).strip()
            )

            if is_capture(m.ideal_value):
                additional_data.append(
                    AuditRow(
                        bu,
                        m.ideal_name,
                        display,
                        m.ideal_value,
                        "Actual config captured",
                    )
                )
            elif is_range(m.ideal_value):
                # Range comparison: ideal like "<=5", ">=1", "1-5", ">0"
                if check_range(raw, m.ideal_value):
                    controls_in_place.append(
                        AuditRow(
                            bu,
                            m.ideal_name,
                            display,
                            m.ideal_value,
                            "Controls in place",
                        )
                    )
                else:
                    control_gaps.append(
                        AuditRow(
                            bu,
                            m.ideal_name,
                            display,
                            m.ideal_value,
                            "Controls gaps",
                            m.options,
                        )
                    )
            elif normalize_value(raw) == normalize_value(m.ideal_value):
                controls_in_place.append(
                    AuditRow(
                        bu, m.ideal_name, display, m.ideal_value, "Controls in place"
                    )
                )
            else:
                control_gaps.append(
                    AuditRow(
                        bu,
                        m.ideal_name,
                        display,
                        m.ideal_value,
                        "Controls gaps",
                        m.options,
                    )
                )

    return controls_in_place, control_gaps, additional_data
