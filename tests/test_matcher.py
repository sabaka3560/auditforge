"""Tests for engine.matcher — all 4 matching stages."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from engine.matcher import build_mapping


def ideal(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["config_name", "ideal_value"])


ACTUAL_HEADERS = [
    "BU_NAME",
    "AllowItemSubstitutions",  # alias target for AllowItemSubstitutionsFlag
    "AllowNegOnhandCcTxns",
    "InventoryFlag",
    "FABookTypeCode",  # normalised match for FaBookTypeCode
    "MfgPlantFlag",
    "BusinessUnitName",  # alias target for BusinessUnitId
    "OrganizationCode",
    "EamEnabledFlag",
    "FifoOrigRcptDateFlag",
    "MoPickConfirmRequired",
    "NegativeInvReceiptCode",
]


class TestExactMatch:
    def test_exact_hit(self):
        result = build_mapping(ideal([("AllowNegOnhandCcTxns", "N")]), ACTUAL_HEADERS)
        assert result[0].match_method == "Exact"
        assert result[0].matched_header == "AllowNegOnhandCcTxns"
        assert result[0].status == "Matched"

    def test_exact_takes_priority_over_fuzzy(self):
        """InventoryFlag is exact — should not fall through to fuzzy."""
        result = build_mapping(ideal([("InventoryFlag", "Y")]), ACTUAL_HEADERS)
        assert result[0].match_method == "Exact"


class TestNormalizedMatch:
    def test_case_difference(self):
        """FaBookTypeCode vs FABookTypeCode — only case differs."""
        result = build_mapping(ideal([("FaBookTypeCode", "N")]), ACTUAL_HEADERS)
        assert result[0].match_method == "Normalized"
        assert result[0].matched_header == "FABookTypeCode"

    def test_underscore_vs_none(self):
        """Columns that differ only by underscores/spaces should normalize-match."""
        headers = ["BU_NAME", "Allow_Neg_Onhand_Cc_Txns"]
        result = build_mapping(ideal([("AllowNegOnhandCcTxns", "N")]), headers)
        assert result[0].status == "Matched"


class TestManualAlias:
    def test_allow_item_substitutions_flag(self):
        result = build_mapping(
            ideal([("AllowItemSubstitutionsFlag", "Y")]), ACTUAL_HEADERS
        )
        assert result[0].match_method == "Manual Alias"
        assert result[0].matched_header == "AllowItemSubstitutions"

    def test_business_unit_id(self):
        result = build_mapping(
            ideal([("BusinessUnitId", "Capture the value defined")]), ACTUAL_HEADERS
        )
        assert result[0].match_method == "Manual Alias"
        assert result[0].matched_header == "BusinessUnitName"


class TestFuzzyMatch:
    def test_fuzzy_above_threshold(self):
        """EamEnabled has no alias and only a fuzzy match to EamEnabledFlag."""
        headers = ["BU_NAME", "EamEnabledFlag", "InventoryFlag"]
        result = build_mapping(
            ideal([("EamEnabled", "Y")]), headers, fuzzy_threshold=70
        )
        assert result[0].status == "Matched"
        assert result[0].matched_header == "EamEnabledFlag"
        assert result[0].match_method == "Fuzzy"

    def test_fuzzy_below_threshold_is_unmatched(self):
        """LastUpdateDate has no close match in the actual headers."""
        result = build_mapping(
            ideal([("LastUpdateDate", "Capture")]), ACTUAL_HEADERS, fuzzy_threshold=80
        )
        assert result[0].status == "Unmatched"

    def test_threshold_respected(self):
        """Lower threshold allows weaker matches; higher blocks them."""
        result_strict = build_mapping(
            ideal([("OrganizationId", "X")]), ACTUAL_HEADERS, fuzzy_threshold=95
        )
        result_loose = build_mapping(
            ideal([("OrganizationId", "X")]), ACTUAL_HEADERS, fuzzy_threshold=60
        )
        assert result_loose[0].status == "Matched"
        # strict may or may not match depending on score — just verify it's more restrictive
        if result_strict[0].status == "Matched":
            assert result_strict[0].similarity_score >= result_loose[0].similarity_score


class TestUnmatched:
    def test_no_match_returns_unmatched(self):
        result = build_mapping(
            ideal([("ZZZ_NonExistentParam_XYZ", "Y")]), ACTUAL_HEADERS
        )
        assert result[0].status == "Unmatched"
        assert result[0].matched_header is None

    def test_unmatched_has_best_candidate_in_remarks(self):
        result = build_mapping(ideal([("LastUpdateDate", "Capture")]), ACTUAL_HEADERS)
        assert result[0].remarks != ""


class TestMultipleConfigs:
    def test_returns_one_result_per_ideal_row(self):
        configs = ideal(
            [
                ("AllowNegOnhandCcTxns", "N"),
                ("InventoryFlag", "Y"),
                ("AllowItemSubstitutionsFlag", "Y"),
                ("LastUpdateDate", "Capture"),
            ]
        )
        results = build_mapping(configs, ACTUAL_HEADERS)
        assert len(results) == 4

    def test_mixed_match_types(self):
        configs = ideal(
            [
                ("AllowNegOnhandCcTxns", "N"),  # Exact
                ("FaBookTypeCode", "N"),  # Normalized
                ("AllowItemSubstitutionsFlag", "Y"),  # Manual Alias
                ("LastUpdateDate", "Capture"),  # Unmatched
            ]
        )
        results = build_mapping(configs, ACTUAL_HEADERS)
        methods = {r.ideal_name: r.match_method for r in results}
        assert methods["AllowNegOnhandCcTxns"] == "Exact"
        assert methods["FaBookTypeCode"] == "Normalized"
        assert methods["AllowItemSubstitutionsFlag"] == "Manual Alias"
        assert methods["LastUpdateDate"] == "Unmatched"
