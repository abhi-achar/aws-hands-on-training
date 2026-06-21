"""Utility helpers (ported from app/utils/helpers.py)."""

import pandas as pd


def to_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def is_yes_or_one(value) -> bool:
    """Return True if value looks like a truthy indicator."""
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value >= 1
    s = str(value).strip().lower()
    return s in ("yes", "y", "1", "true", "t")


def first_existing(row: pd.Series, candidates: list):
    """Return the value of the first column name that exists in the row."""
    for col in candidates:
        if col in row.index and pd.notna(row[col]):
            return row[col]
    return None
