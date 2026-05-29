"""File ingestion — reads the client file and ideal value file into DataFrames.

Public API:
    read_actual(file_obj, sheet_name) -> pd.DataFrame
    read_ideal(file_obj) -> pd.DataFrame
"""

from typing import BinaryIO

import pandas as pd

from .normalizer import detect_ideal_columns


def _open_excel(file_obj: BinaryIO) -> pd.ExcelFile:
    """Open an Excel file using openpyxl (.xlsx) or xlrd (.xls), whichever works."""
    try:
        return pd.ExcelFile(file_obj, engine="openpyxl")
    except Exception:
        file_obj.seek(0)
        return pd.ExcelFile(file_obj, engine="xlrd")


def read_actual(
    file_obj: BinaryIO, sheet_name: str = "INV_ORGANIZATION_PARAMETER"
) -> pd.DataFrame:
    """Read the client-uploaded Oracle Fusion export (Excel or CSV).

    Column A is always the BU identifier, renamed to BU_NAME for uniform access.
    Blank or NaN BU rows are dropped. CSV files ignore sheet_name.
    """
    try:
        xl = _open_excel(file_obj)
        if sheet_name not in xl.sheet_names:
            raise ValueError(
                f"Sheet '{sheet_name}' not found. Available: {', '.join(xl.sheet_names)}"
            )
        df = xl.parse(sheet_name, header=0)
    except ValueError:
        raise
    except Exception:
        file_obj.seek(0)
        df = pd.read_csv(file_obj)

    if df.empty:
        raise ValueError("File is empty.")

    # Normalize column A to a known name regardless of what the export called it
    df = df.rename(columns={df.columns[0]: "BU_NAME"})
    df["BU_NAME"] = df["BU_NAME"].astype(str).str.strip()
    df = df[df["BU_NAME"].notna() & ~df["BU_NAME"].isin(["", "nan"])]
    return df.reset_index(drop=True)


def read_ideal(file_obj: BinaryIO) -> pd.DataFrame:
    """Read the ideal value file — Excel or CSV, any column names.

    Auto-detects which column is the config name and which is the ideal value.
    If an 'Options' column exists it is preserved as a third column.
    Returns a DataFrame with columns: config_name, ideal_value, options.
    """
    try:
        df = pd.read_excel(file_obj, header=0, engine="openpyxl")
    except Exception:
        file_obj.seek(0)
        df = pd.read_csv(file_obj)

    if df.shape[1] < 2:
        raise ValueError("Ideal value file must have at least 2 columns.")

    name_col, value_col = detect_ideal_columns(df)
    options_col = next(
        (h for h in df.columns if str(h).strip().lower().startswith("options")),
        None,
    )

    cols = [name_col, value_col] + ([options_col] if options_col else [])
    out = df[cols].copy()
    out.columns = ["config_name", "ideal_value"] + (["options"] if options_col else [])
    out["config_name"] = out["config_name"].astype(str).str.strip()
    out["ideal_value"] = out["ideal_value"].fillna("").astype(str).str.strip()
    if "options" in out.columns:
        out["options"] = (
            out["options"].fillna("").astype(str).str.strip().replace("nan", "")
        )
    else:
        out["options"] = ""
    out = out[~out["config_name"].isin(["", "nan"])]
    return out.reset_index(drop=True)
