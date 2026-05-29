"""Value normalization, capture detection, and ideal-column auto-detection.

All comparison logic runs through normalize_value() so that Y / y / Yes / true
are treated as equivalent. Capture detection is a substring check — anything
containing a known capture phrase skips comparison and is extracted as-is.
"""

import re
import pandas as pd

# Single-word type descriptors in an ideal value mean "capture this field, don't compare".
_CAPTURE_EXACT: set[str] = {
    "date",
    "number",
    "integer",
    "numeric",
    "text",
    "string",
    "timestamp",
}

# Both actual and ideal values are mapped through this before comparison.
_BOOL_MAP: dict[str, str] = {
    "y": "y",
    "yes": "y",
    "true": "y",
    "1": "y",
    "enabled": "y",
    "on": "y",
    "active": "y",
    "enable": "y",
    "n": "n",
    "no": "n",
    "false": "n",
    "0": "n",
    "disabled": "n",
    "off": "n",
    "inactive": "n",
    "disable": "n",
}

_CAPTURE_PHRASES = [
    "capture",
    "record the value",
    "extract",
    "document the actual",
    "note the value",
    "for information only",
    "informational",
    "as per business need",
    "separate annex",
]

# Column-name aliases used to auto-detect which column in the ideal file
# is the config name and which is the ideal value.
_NAME_ALIASES = [
    "name",
    "config",
    "parameter",
    "config name",
    "config_name",
    "parameter name",
    "field",
    "configuration name",
    "configuration",
]
_VALUE_ALIASES = [
    "ideal value",
    "ideal",
    "expected value",
    "expected",
    "standard",
    "value",
    "target",
    "benchmark",
    "ideal_value",
    "expected_value",
]


def strip_header(s: str) -> str:
    """Collapse spaces/underscores/hyphens and lowercase. Used for header matching."""
    return re.sub(r"[\s_\-]+", "", str(s)).lower()


def normalize_value(v) -> str:
    """Strip whitespace, lowercase, apply boolean synonym map, and normalize floats."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(v).strip().lower()
    # Float-normalize first so "1.0" and "1" reach the bool map as the same token.
    try:
        f = float(s)
        s = str(int(f)) if f == int(f) else str(f)
    except (ValueError, OverflowError):
        pass
    mapped = _BOOL_MAP.get(s)
    if mapped is not None:
        return mapped
    return s


def is_capture(ideal_value: str) -> bool:
    """True when the ideal value is a capture instruction — extract only, no comparison."""
    v = ideal_value.strip().lower()
    return v in _CAPTURE_EXACT or any(phrase in v for phrase in _CAPTURE_PHRASES)


def detect_ideal_columns(df: pd.DataFrame) -> tuple[str, str]:
    """Return (name_col, value_col) by matching column headers against known aliases.

    Falls back to column position (0 = name, 1 = value) when no alias matches.
    """
    headers = list(df.columns)
    norm_map = {strip_header(h): h for h in headers}

    name_col = next(
        (
            norm_map[strip_header(a)]
            for a in _NAME_ALIASES
            if strip_header(a) in norm_map
        ),
        headers[0],
    )
    value_col = next(
        (
            norm_map[strip_header(a)]
            for a in _VALUE_ALIASES
            if strip_header(a) in norm_map
        ),
        next(h for h in headers if h != name_col),
    )
    return name_col, value_col
