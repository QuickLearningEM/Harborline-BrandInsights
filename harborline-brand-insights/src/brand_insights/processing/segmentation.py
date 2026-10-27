"""Assign each customer one primary segment using transparent, reviewable rules.

Rules are applied in order; the first match wins. They are intentionally simple so Brand
Strategy can read, challenge, and change them. Clustering can later refine the
Design Enthusiasts and First-Time Furnishers boundaries.
"""

import numpy as np
import pandas as pd


def assign_segments(curated: pd.DataFrame, as_of: pd.Timestamp, lapsed_days: int = 540) -> pd.DataFrame:
    conditions = [
        curated["brand"] == "Nest & Co.",
        curated["days_since_last"] > lapsed_days,
        (curated["decor_share"] >= 0.5) & (curated["orders"] >= 3),
        curated["age"] >= 35,
    ]
    choices = [
        "Nest & Co. Shoppers",
        "Lapsed Customers",
        "Design Enthusiasts",
        "Established Homeowners",
    ]
    out = curated.copy()
    out["segment"] = np.select(conditions, choices, default="First-Time Furnishers")
    out["segment_version"] = as_of.strftime("%Y-%m")
    return out
