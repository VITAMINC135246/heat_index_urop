"""Numeric table-value conversions shared by spatial and review components."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def as_int(value: Any) -> int:
    number = as_float(value)
    if number is None:
        raise ValueError(f"Expected numeric value, got {value!r}")
    return int(round(number))
