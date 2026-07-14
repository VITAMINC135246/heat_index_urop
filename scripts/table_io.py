"""Shared spreadsheet helpers for project tables.

The project writes human-reviewed tables as .xlsx files so Excel and Numbers
open them without XLSX delimiter, encoding, or type-guessing surprises.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def read_table(path: Path, **kwargs: Any) -> pd.DataFrame:
    """Read a project table from .xlsx."""
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"Expected an .xlsx table path, got: {path}")
    return pd.read_excel(path, **kwargs)


def write_table(path: Path, df: pd.DataFrame, columns: list[str] | None = None) -> None:
    """Write a DataFrame to .xlsx with a stable column order."""
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"Expected an .xlsx table path, got: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        work = df.copy()
        for column in columns:
            if column not in work.columns:
                work[column] = ""
        work = work[columns]
    else:
        work = df
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        work.to_excel(writer, index=False, sheet_name="Sheet1")
        worksheet = writer.sheets["Sheet1"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions


def write_rows(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    """Write row dictionaries to .xlsx."""
    if columns is None:
        columns = sorted({key for row in rows for key in row})
    write_table(path, pd.DataFrame(rows), columns)
