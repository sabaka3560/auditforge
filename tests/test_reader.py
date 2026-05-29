"""Tests for engine.reader — read_actual() and read_ideal().

All fixtures create in-memory Excel/CSV files using openpyxl so no disk I/O is needed.
"""

import io
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import openpyxl
import pytest

from engine.reader import read_actual, read_ideal


# ── helpers ───────────────────────────────────────────────────────────────────


def make_xlsx(sheet_name: str, rows: list[list]) -> io.BytesIO:
    """Build an in-memory xlsx with one sheet and the given rows (first row = header)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def make_csv(content: str) -> io.BytesIO:
    return io.BytesIO(content.encode())


# ── read_actual ───────────────────────────────────────────────────────────────


class TestReadActual:
    def test_basic_xlsx(self):
        buf = make_xlsx(
            "INV_ORGANIZATION_PARAMETER",
            [
                ["Organization", "InventoryFlag", "MfgPlantFlag"],
                ["Mumbai Plant", "Y", "Y"],
                ["Delhi HQ", "Y", "N"],
            ],
        )
        df = read_actual(buf, sheet_name="INV_ORGANIZATION_PARAMETER")
        assert len(df) == 2
        assert df.columns[0] == "BU_NAME"
        assert list(df["BU_NAME"]) == ["Mumbai Plant", "Delhi HQ"]

    def test_column_a_renamed_to_bu_name(self):
        """Whatever column A is called in the export, it becomes BU_NAME."""
        buf = make_xlsx(
            "RCV_OPTIONS",
            [
                ["Organization Name", "AllowSubstitutions"],
                ["Singapore Regional", "Y"],
            ],
        )
        df = read_actual(buf, sheet_name="RCV_OPTIONS")
        assert "BU_NAME" in df.columns
        assert "Organization Name" not in df.columns

    def test_blank_bu_rows_dropped(self):
        buf = make_xlsx(
            "Sheet1",
            [
                ["BU", "Flag"],
                ["Mumbai Plant", "Y"],
                ["", "N"],
                [None, "Y"],
                ["Delhi HQ", "N"],
            ],
        )
        df = read_actual(buf, sheet_name="Sheet1")
        assert len(df) == 2
        assert list(df["BU_NAME"]) == ["Mumbai Plant", "Delhi HQ"]

    def test_nan_string_bu_dropped(self):
        """Rows where BU_NAME becomes the string 'nan' after str conversion are dropped."""
        buf = make_xlsx(
            "Sheet1",
            [["BU", "Flag"], ["Mumbai Plant", "Y"]],
        )
        df = read_actual(buf, sheet_name="Sheet1")
        assert "nan" not in list(df["BU_NAME"])

    def test_wrong_sheet_raises_value_error(self):
        buf = make_xlsx(
            "INV_ORGANIZATION_PARAMETER",
            [["BU", "Flag"], ["Mumbai Plant", "Y"]],
        )
        with pytest.raises(ValueError, match="Sheet 'WRONG_SHEET' not found"):
            read_actual(buf, sheet_name="WRONG_SHEET")

    def test_wrong_sheet_error_lists_available(self):
        buf = make_xlsx(
            "INV_ORGANIZATION_PARAMETER",
            [["BU", "Flag"], ["Mumbai Plant", "Y"]],
        )
        with pytest.raises(ValueError, match="INV_ORGANIZATION_PARAMETER"):
            read_actual(buf, sheet_name="MISSING")

    def test_csv_fallback(self):
        buf = make_csv("BU,InventoryFlag\nMumbai Plant,Y\nDelhi HQ,N\n")
        df = read_actual(buf, sheet_name="ignored")
        assert len(df) == 2
        assert df.columns[0] == "BU_NAME"

    def test_csv_bu_name_stripped(self):
        buf = make_csv("BU,Flag\n  Mumbai Plant  ,Y\n")
        df = read_actual(buf, sheet_name="anything")
        assert df.iloc[0]["BU_NAME"] == "Mumbai Plant"

    def test_empty_file_raises(self):
        buf = make_xlsx("Sheet1", [["BU", "Flag"]])
        with pytest.raises(ValueError, match="empty"):
            read_actual(buf, sheet_name="Sheet1")

    def test_rcv_options_sheet(self):
        buf = make_xlsx(
            "RCV_OPTIONS",
            [
                ["Organization", "AllowCascadeReceipt", "AllowSubstitutions"],
                ["Mumbai Plant", "Y", "N"],
                ["Delhi HQ", "Y", "Y"],
                ["Bangalore IT", "N", "N"],
            ],
        )
        df = read_actual(buf, sheet_name="RCV_OPTIONS")
        assert len(df) == 3
        assert "AllowCascadeReceipt" in df.columns

    def test_ap_tolerance_sheet(self):
        buf = make_xlsx(
            "AP_TOLERANCE_TEMPLATE",
            [
                ["BU Name", "MaxQuantityOrdered", "MaxQuantityReceived"],
                ["Mumbai Plant", "5.0", "5.0"],
                ["Delhi HQ", "10.0", "10.0"],
            ],
        )
        df = read_actual(buf, sheet_name="AP_TOLERANCE_TEMPLATE")
        assert len(df) == 2

    def test_financial_sys_param_sheet(self):
        buf = make_xlsx(
            "AP_FINANCIAL_SYS_PARAM",
            [
                ["BU Name", "PositivePayRequired", "AutoCalculateTaxFlag"],
                ["Mumbai Plant", "Y", "Y"],
            ],
        )
        df = read_actual(buf, sheet_name="AP_FINANCIAL_SYS_PARAM")
        assert len(df) == 1


# ── read_ideal ────────────────────────────────────────────────────────────────


class TestReadIdeal:
    def test_basic_xlsx(self):
        buf = make_xlsx(
            "Sheet1",
            [
                ["Config Name", "Ideal Value"],
                ["InventoryFlag", "Y"],
                ["AllowNegOnhandCcTxns", "N"],
            ],
        )
        df = read_ideal(buf)
        assert len(df) == 2
        assert list(df.columns) == ["config_name", "ideal_value", "options"]

    def test_csv_input(self):
        buf = make_csv("Name,Ideal Value\nInventoryFlag,Y\nMfgPlantFlag,Y\n")
        df = read_ideal(buf)
        assert len(df) == 2
        assert df.iloc[0]["config_name"] == "InventoryFlag"

    def test_options_column_detected(self):
        buf = make_xlsx(
            "Sheet1",
            [
                ["Config Name", "Ideal Value", "Options available"],
                ["InvoiceMatchOption", "PO", "PO, Receipt, Order"],
                ["PaymentTerms", "Net30", "Net30, Net60, Net90"],
            ],
        )
        df = read_ideal(buf)
        assert "options" in df.columns
        assert df.iloc[0]["options"] == "PO, Receipt, Order"

    def test_options_column_startswith(self):
        """'Options' alone or any prefix like 'Options available' all detected."""
        for header in ["Options", "Options available", "Options (Oracle)", "options"]:
            buf = make_xlsx(
                "Sheet1",
                [
                    ["Config Name", "Ideal Value", header],
                    ["SomeField", "Y", "A, B, C"],
                ],
            )
            df = read_ideal(buf)
            assert "options" in df.columns, f"header {header!r} not detected"

    def test_no_options_column_defaults_empty(self):
        buf = make_xlsx(
            "Sheet1",
            [["Config Name", "Ideal Value"], ["InventoryFlag", "Y"]],
        )
        df = read_ideal(buf)
        assert "options" in df.columns
        assert df.iloc[0]["options"] == ""

    def test_strips_whitespace(self):
        buf = make_csv("Name,Ideal Value\n  InventoryFlag  ,  Y  \n")
        df = read_ideal(buf)
        assert df.iloc[0]["config_name"] == "InventoryFlag"
        assert df.iloc[0]["ideal_value"] == "Y"

    def test_drops_empty_config_rows(self):
        buf = make_csv("Name,Ideal Value\nInventoryFlag,Y\n,\n\nMfgPlantFlag,Y\n")
        df = read_ideal(buf)
        assert len(df) == 2

    def test_nan_ideal_value_becomes_empty(self):
        buf = make_xlsx(
            "Sheet1",
            [["Config Name", "Ideal Value"], ["LastUpdateDate", None]],
        )
        df = read_ideal(buf)
        assert df.iloc[0]["ideal_value"] == ""

    def test_column_alias_parameter_name(self):
        buf = make_xlsx(
            "Sheet1",
            [["Parameter Name", "Expected Value"], ["InventoryFlag", "Y"]],
        )
        df = read_ideal(buf)
        assert df.iloc[0]["config_name"] == "InventoryFlag"
        assert df.iloc[0]["ideal_value"] == "Y"

    def test_too_few_columns_raises(self):
        buf = make_xlsx("Sheet1", [["Config Name"], ["InventoryFlag"]])
        with pytest.raises(ValueError, match="at least 2 columns"):
            read_ideal(buf)

    def test_ap_invoice_options_format(self):
        """Simulate realistic AP Invoice Options ideal file (CSV format)."""
        content = (
            "Configuration Name,Ideal Value,Options available\n"
            'Invoice Match Option,PO,"PO, Receipt"\n'
            'Hold Unmatched Invoices,N,"Y, N"\n'
            'Tax Calculation Level,Line,"Line, Header"\n'
        )
        buf = make_csv(content)
        df = read_ideal(buf)
        assert len(df) == 3
        assert df.iloc[0]["ideal_value"] == "PO"
        assert "PO" in df.iloc[0]["options"]

    def test_ap_tolerance_ideal_format(self):
        """Simulate realistic AP Tolerance ideal file."""
        buf = make_xlsx(
            "Sheet1",
            [
                ["Config Name", "Ideal Value"],
                ["MaxQuantityOrdered", "5.0"],
                ["MaxQuantityReceived", "5.0"],
                ["MaxAmountOrdered", "10.0"],
                ["TaxAmountRange", "Capture"],
            ],
        )
        df = read_ideal(buf)
        assert len(df) == 4
        assert (
            df[df["config_name"] == "MaxQuantityOrdered"].iloc[0]["ideal_value"]
            == "5.0"
        )
