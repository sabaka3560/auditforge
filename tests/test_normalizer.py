"""Exhaustive tests for engine.normalizer.

Covers every boolean synonym, every capture phrase, every exact-type descriptor,
float normalization edge cases, and header-stripping behaviour.
"""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytest

from engine.normalizer import (
    detect_ideal_columns,
    is_capture,
    normalize_value,
    strip_header,
)


class TestNormalizeValue:
    # ── boolean → y ────────────────────────────────────────────────────────
    @pytest.mark.parametrize(
        "v",
        [
            "Y",
            "y",
            "Yes",
            "yes",
            "YES",
            "true",
            "True",
            "TRUE",
            "enabled",
            "Enabled",
            "ENABLED",
            "on",
            "On",
            "ON",
            "active",
            "Active",
            "ACTIVE",
            "enable",
            "Enable",
            "ENABLE",
        ],
    )
    def test_y_variants(self, v):
        assert normalize_value(v) == "y", f"{v!r} should map to 'y'"

    # ── boolean → n ────────────────────────────────────────────────────────
    @pytest.mark.parametrize(
        "v",
        [
            "N",
            "n",
            "No",
            "no",
            "NO",
            "false",
            "False",
            "FALSE",
            "disabled",
            "Disabled",
            "DISABLED",
            "off",
            "Off",
            "OFF",
            "inactive",
            "Inactive",
            "INACTIVE",
            "disable",
            "Disable",
            "DISABLE",
        ],
    )
    def test_n_variants(self, v):
        assert normalize_value(v) == "n", f"{v!r} should map to 'n'"

    # ── null / missing ──────────────────────────────────────────────────────
    def test_none_returns_empty(self):
        assert normalize_value(None) == ""

    def test_nan_float_returns_empty(self):
        assert normalize_value(float("nan")) == ""
        assert normalize_value(math.nan) == ""

    def test_pandas_na_returns_empty(self):
        assert normalize_value(pd.NA) == ""

    def test_empty_string(self):
        assert normalize_value("") == ""

    # ── float normalization ─────────────────────────────────────────────────
    def test_whole_float_stripped(self):
        assert normalize_value("10.0") == "10"
        assert normalize_value("0.0") == "0"
        assert normalize_value("100.0") == "100"

    def test_float_object_normalized(self):
        assert normalize_value(10.0) == "10"
        assert normalize_value(0.0) == "0"

    def test_fractional_float_preserved(self):
        assert normalize_value("3.14") == "3.14"
        assert normalize_value("0.5") == "0.5"
        assert normalize_value("99.99") == "99.99"

    def test_integer_string_preserved(self):
        assert normalize_value("2") == "2"
        assert normalize_value("100") == "100"

    # ── whitespace stripping ────────────────────────────────────────────────
    def test_strips_leading_trailing_spaces(self):
        assert normalize_value("  Y  ") == "y"
        assert normalize_value("  N  ") == "n"
        assert normalize_value("  Standard  ") == "standard"

    # ── plain text lowercased ───────────────────────────────────────────────
    def test_text_lowercased(self):
        assert normalize_value("Standard") == "standard"
        assert normalize_value("FIFO") == "fifo"
        assert normalize_value("Receipt") == "receipt"

    # ── Oracle Fusion specific values ───────────────────────────────────────
    def test_oracle_rcv_values(self):
        # Oracle stores approval codes as text
        assert normalize_value("NONE") == "none"
        assert normalize_value("APPROVED") == "approved"

    def test_tolerance_percentage(self):
        assert normalize_value("5.0") == "5"
        assert normalize_value("2.5") == "2.5"


class TestIsCapture:
    # ── exact single-word type descriptors ────────────────────────────────
    @pytest.mark.parametrize(
        "v",
        [
            "Date",
            "date",
            "DATE",
            "Number",
            "number",
            "NUMBER",
            "Integer",
            "integer",
            "INTEGER",
            "Numeric",
            "numeric",
            "Text",
            "text",
            "TEXT",
            "String",
            "string",
            "STRING",
            "Timestamp",
            "timestamp",
            "TIMESTAMP",
        ],
    )
    def test_exact_type_descriptors(self, v):
        assert is_capture(v), f"{v!r} should be a capture"

    # ── standard capture phrases ────────────────────────────────────────────
    @pytest.mark.parametrize(
        "v",
        [
            "capture",
            "Capture",
            "CAPTURE",
            "Capture the value defined",
            "Capture the actual value",
            "Please capture",
            "record the value",
            "Record the Value",
            "extract",
            "Extract",
            "document the actual",
            "note the value",
            "for information only",
            "For Information Only",
            "informational",
            "Informational",
            "as per business need",
            "As Per Business Need",
            "separate annex",
            "Separate Annex",
        ],
    )
    def test_capture_phrases(self, v):
        assert is_capture(v), f"{v!r} should trigger capture"

    # ── non-capture values ──────────────────────────────────────────────────
    @pytest.mark.parametrize(
        "v", ["Y", "N", "Standard", "FIFO", "LIFO", "2", "100", "NONE"]
    )
    def test_non_capture_values(self, v):
        assert not is_capture(v), f"{v!r} should NOT be a capture"

    def test_capture_embedded_in_sentence(self):
        assert is_capture("Please capture this field for audit trail")
        assert is_capture("This is for information only — no action needed")

    def test_whitespace_only_not_capture(self):
        assert not is_capture("   ")

    def test_empty_string_not_capture(self):
        assert not is_capture("")


class TestStripHeader:
    def test_camelcase_lowercased(self):
        assert strip_header("AllowItemSubstitutions") == "allowitemsubstitutions"

    def test_spaces_removed(self):
        assert strip_header("Config Name") == "configname"
        assert strip_header("Ideal Value") == "idealvalue"

    def test_underscores_removed(self):
        assert strip_header("config_name") == "configname"
        assert strip_header("ideal_value") == "idealvalue"

    def test_hyphens_removed(self):
        assert strip_header("config-name") == "configname"

    def test_mixed_separators(self):
        assert strip_header("Config_Name Value") == "confignamevalue"
        assert strip_header("INV_ORGANIZATION_PARAMETER") == "invorganizationparameter"

    def test_already_lowercase_no_separators(self):
        assert strip_header("inventoryflag") == "inventoryflag"


class TestDetectIdealColumns:
    def test_detects_by_alias_name_and_idealvalue(self):
        df = pd.DataFrame({"Config Name": ["A", "B"], "Ideal Value": ["Y", "N"]})
        name_col, val_col = detect_ideal_columns(df)
        assert name_col == "Config Name"
        assert val_col == "Ideal Value"

    def test_detects_parameter_name_alias(self):
        df = pd.DataFrame({"Parameter Name": ["A"], "Expected Value": ["Y"]})
        name_col, val_col = detect_ideal_columns(df)
        assert name_col == "Parameter Name"
        assert val_col == "Expected Value"

    def test_falls_back_to_column_position(self):
        df = pd.DataFrame({"ColA": ["A"], "ColB": ["Y"]})
        name_col, val_col = detect_ideal_columns(df)
        assert name_col == "ColA"
        assert val_col == "ColB"

    def test_underscore_variant(self):
        df = pd.DataFrame({"config_name": ["A"], "ideal_value": ["Y"]})
        name_col, val_col = detect_ideal_columns(df)
        assert name_col == "config_name"
        assert val_col == "ideal_value"
