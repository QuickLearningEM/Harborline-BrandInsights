"""Classify each segment as under-invested, over-invested, message mismatch, or aligned."""

import pandas as pd

from .sentiment import ATTRIBUTE_LABELS

UNDER, OVER, MISMATCH, ALIGNED, NO_DATA = (
    "Under-invested", "Over-invested", "Message mismatch", "Aligned", "Not enough data",
)


def _classify(row: pd.Series, under: float, over: float, threshold: float) -> str:
    idx = row["responsiveness_index"]
    if pd.isna(idx) or row["spend"] <= 0:
        return NO_DATA
    if idx > under and row["spend_share"] < row["revenue_share"]:
        return UNDER
    if idx < over and row["spend_share"] > row["revenue_share"]:
        return OVER
    if pd.notna(row.get("weakest_score")) and row["weakest_score"] <= threshold:
        return MISMATCH
    return ALIGNED


def _recommend(row: pd.Series) -> str:
    c = row["classification"]
    if c == UNDER:
        return "Increase spend. This segment responds strongly and gets less budget than its share of revenue."
    if c == OVER:
        return "Reduce spend or change targeting. Budget is higher than this segment returns."
    if c == MISMATCH:
        label = ATTRIBUTE_LABELS.get(row.get("weakest_attribute"), "the brand")
        return f"Revise creative and messaging. Public sentiment is negative on {label}."
    if c == ALIGNED:
        return "Keep the current approach."
    return "Collect more data before changing spend."


def classify_segments(
    scorecard: pd.DataFrame, under: float = 120.0, over: float = 80.0, threshold: float = -0.15
) -> pd.DataFrame:
    out = scorecard.copy()
    out["classification"] = out.apply(_classify, axis=1, args=(under, over, threshold))
    out["recommendation"] = out.apply(_recommend, axis=1)
    return out
