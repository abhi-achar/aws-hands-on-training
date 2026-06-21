"""Deterministic scoring logic (ported from app/services/scoring.py)."""

import pandas as pd

from .helpers import to_float, is_yes_or_one, first_existing


def calculate_priority_score(row: pd.Series) -> float:
    """
    Deterministic business scoring.
    Prevents the LLM from changing Priority 1/2/3 across runs for the same data.
    """
    score = 0.0

    score += 100.0 * to_float(
        first_existing(row, [
            "urgency_score", "Urgency_Score", "urgency", "Urgency",
            "priority_score", "Priority_Score", "score", "Score"
        ])
    )

    # Critical availability / OOS signals
    for col in row.index:
        col_l = col.lower()
        if "oos" in col_l and ("critical" in col_l or "flag" in col_l or "indicator" in col_l):
            if is_yes_or_one(row[col]):
                score += 10000.0

    instock = first_existing(row, ["Instock", "instock", "InStock", "in_stock", "inStock"])
    if instock is not None and not is_yes_or_one(instock):
        score += 8000.0

    days_cover = to_float(
        first_existing(row, [
            "days_of_cover", "Days_of_Cover", "Days of Cover", "daysCover",
            "DOC", "doc", "cover_days", "Days Cover"
        ]),
        default=9999.0,
    )
    if days_cover < 1:
        score += 7000.0
    elif days_cover < 3:
        score += 5000.0
    elif days_cover < 7:
        score += 2500.0
    elif days_cover < 14:
        score += 1000.0

    return score


def stable_sort_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add priority scores and sort deterministically."""
    df = df.copy()
    df["_priority_score"] = df.apply(calculate_priority_score, axis=1)
    df = df.sort_values("_priority_score", ascending=False, kind="mergesort").reset_index(drop=True)
    df["_deterministic_rank"] = range(1, len(df) + 1)
    return df
