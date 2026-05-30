"""Tests for engine.comparator — value comparison, capture, and boolean normalization.

Uses realistic Oracle Fusion INV data: BU names are actual Indian/global plant names,
config values reflect real export patterns (Y/N, mixed case, nulls, integer codes).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from engine.comparator import compare
from engine.matcher import build_mapping


# ── fixtures ──────────────────────────────────────────────────────────────────

BUS = [
    "Mumbai Plant",
    "Delhi HQ",
    "Bangalore IT",
    "Singapore Regional",
    "UAE Free Zone",
]


def make_actual(configs: dict[str, list]) -> pd.DataFrame:
    """Build a BU × config DataFrame. configs maps column name → list of values (one per BU)."""
    data = {"BU_NAME": BUS, **configs}
    return pd.DataFrame(data)


def make_ideal(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["config_name", "ideal_value"])


def run(
    actual_df: pd.DataFrame, ideal_rows: list[tuple[str, str]], threshold: int = 80
):
    ideal_df = make_ideal(ideal_rows)
    mapping = build_mapping(ideal_df, list(actual_df.columns), threshold)
    return compare(actual_df, mapping)


# ── controls in place ─────────────────────────────────────────────────────────


class TestControlsInPlace:
    def test_exact_match_all_bus(self):
        df = make_actual({"InventoryFlag": ["Y", "Y", "Y", "Y", "Y"]})
        cip, gaps, extra = run(df, [("InventoryFlag", "Y")])
        assert len(cip) == 5
        assert len(gaps) == 0

    def test_boolean_normalization_lower_y(self):
        """Actual = 'y', ideal = 'Y' → should match (case insensitive)."""
        df = make_actual({"EamEnabledFlag": ["y", "Y", "yes", "Yes", "YES"]})
        cip, gaps, _ = run(df, [("EamEnabledFlag", "Y")])
        assert len(cip) == 5

    def test_boolean_normalization_true_maps_to_y(self):
        df = make_actual({"MfgPlantFlag": ["true", "True", "enabled", "on", "Y"]})
        cip, gaps, _ = run(df, [("MfgPlantFlag", "Y")])
        assert len(cip) == 5

    def test_n_variants_match_n_ideal(self):
        df = make_actual(
            {"AllowNegOnhandCcTxns": ["N", "n", "no", "false", "disabled"]}
        )
        cip, gaps, _ = run(df, [("AllowNegOnhandCcTxns", "N")])
        assert len(cip) == 5


# ── control gaps ──────────────────────────────────────────────────────────────


class TestControlGaps:
    def test_wrong_value_is_gap(self):
        """InventoryFlag ideal = Y, but Mumbai Plant has N → gap."""
        df = make_actual({"InventoryFlag": ["N", "Y", "Y", "Y", "Y"]})
        cip, gaps, _ = run(df, [("InventoryFlag", "Y")])
        assert len(gaps) == 1
        assert gaps[0].bu_name == "Mumbai Plant"

    def test_null_actual_is_gap(self):
        """Null (NaN) actual value against a comparison ideal → gap."""
        df = make_actual({"CopyLotAttributeFlag": [None, "Y", None, "Y", None]})
        cip, gaps, _ = run(df, [("CopyLotAttributeFlag", "Y")])
        assert len(cip) == 2  # Delhi HQ, Singapore Regional
        assert len(gaps) == 3  # Mumbai Plant, Bangalore IT, UAE Free Zone

    def test_integer_code_mismatch(self):
        """NegativeInvReceiptCode ideal = 'n' (maps to n), actual = 1 or 2 (integers)."""
        # NegativeInvReceiptCode in actual file stores integers 1/2, not Y/N
        df = make_actual({"NegativeInvReceiptCode": [1, 2, 1, 1, 2]})
        cip, gaps, _ = run(df, [("NegativeInvReceiptCode", "N")])
        # 1 normalizes to "1" which doesn't match "n" — all gaps
        assert len(gaps) == 5

    def test_mixed_pass_fail(self):
        """5 BUs, 2 pass, 3 fail."""
        df = make_actual({"FifoOrigRcptDateFlag": ["Y", "Y", "N", None, "N"]})
        cip, gaps, _ = run(df, [("FifoOrigRcptDateFlag", "Y")])
        assert len(cip) == 2
        assert len(gaps) == 3


# ── capture / additional data ─────────────────────────────────────────────────


class TestCapture:
    def test_capture_phrase_skips_comparison(self):
        df = make_actual(
            {"BusinessUnitName": ["Mumbai BU", "Delhi BU", "Blr BU", "SG BU", "UAE BU"]}
        )
        cip, gaps, extra = run(df, [("BusinessUnitId", "Capture the value defined")])
        assert len(extra) == 5
        assert len(cip) == 0
        assert len(gaps) == 0

    def test_capture_preserves_actual_value(self):
        df = make_actual({"OrganizationCode": [2, 50, 51, 200, 300]})
        _, _, extra = run(df, [("OrganizationCode", "Capture the value defined")])
        captured_values = [r.actual_value for r in extra]
        assert "2" in captured_values
        assert "200" in captured_values

    def test_capture_with_null_actual(self):
        """Null actual for a capture field → captured as empty string."""
        df = make_actual({"SourceType": [None, None, "1", None, None]})
        _, _, extra = run(df, [("SourceType", "Capture the value defined")])
        assert len(extra) == 5
        assert extra[0].actual_value == ""  # null → ""
        assert extra[2].actual_value == "1"  # Bangalore IT has a value

    def test_various_capture_phrases(self):
        phrases = [
            "capture",
            "Capture the actual value",
            "record the value",
            "extract",
            "for information only",
        ]
        for phrase in phrases:
            df = make_actual({"SomeField": ["X", "X", "X", "X", "X"]})
            _, _, extra = run(df, [("SomeField", phrase)])
            assert len(extra) == 5, f"phrase '{phrase}' should trigger capture"


# ── multi-config × multi-BU ───────────────────────────────────────────────────


class TestMatrix:
    def test_full_matrix_row_count(self):
        """5 BUs × 3 configs = 15 total rows across all buckets."""
        df = make_actual(
            {
                "InventoryFlag": ["Y", "Y", "N", "Y", "Y"],
                "AllowNegOnhandCcTxns": ["N", "N", "N", "Y", "N"],
                "BusinessUnitName": [
                    "Mumbai BU",
                    "Delhi BU",
                    "Blr BU",
                    "SG BU",
                    "UAE BU",
                ],
            }
        )
        cip, gaps, extra = run(
            df,
            [
                ("InventoryFlag", "Y"),
                ("AllowNegOnhandCcTxns", "N"),
                ("BusinessUnitId", "Capture the value defined"),
            ],
        )
        total = len(cip) + len(gaps) + len(extra)
        assert total == 15

    def test_comment_text_is_exact(self):
        # Single-row DataFrame — explicit to avoid BUS length mismatch
        df = pd.DataFrame(
            {
                "BU_NAME": ["Mumbai Plant"],
                "InventoryFlag": ["Y"],
                "MfgPlantFlag": ["N"],
                "BusinessUnitName": ["Mumbai BU"],
            }
        )
        cip, gaps, extra = run(
            df,
            [
                ("InventoryFlag", "Y"),
                ("MfgPlantFlag", "Y"),
                ("BusinessUnitId", "Capture the value defined"),
            ],
        )
        assert cip[0].comment == "Controls in place"
        assert gaps[0].comment == "Controls gaps"
        assert extra[0].comment == "Actual config captured"

    def test_unmatched_config_produces_no_rows(self):
        """Unmatched ideal configs are excluded from comparison — no rows produced."""
        df = make_actual({"InventoryFlag": ["Y", "Y", "Y", "Y", "Y"]})
        cip, gaps, extra = run(df, [("LastUpdateDate", "Capture")])
        assert len(cip) + len(gaps) + len(extra) == 0
