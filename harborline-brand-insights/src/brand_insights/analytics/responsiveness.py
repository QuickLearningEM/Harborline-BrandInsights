"""Segment responsiveness: how well each segment converts for the money spent on it.

Return on ad spend is calculated net of returns (REQ-009), using each segment's own
return rate from its trailing-window purchases.
"""

import numpy as np
import pandas as pd

from ..config import SEGMENTS

AD_SUMS = ["spend", "impressions", "clicks", "conversions", "conversion_value"]


def segment_responsiveness(ads: pd.DataFrame, curated: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    total_spend = float(ads["spend"].sum())
    attributed = ads[ads["audience_segment"].isin(SEGMENTS)]
    unattributed_share = 1 - float(attributed["spend"].sum()) / total_spend if total_spend else 0.0

    g = attributed.groupby("audience_segment")[AD_SUMS].sum().reindex(SEGMENTS).fillna(0)
    cur = curated.groupby("segment")[
        ["gross_window", "return_window", "gross_revenue", "return_amount", "net_revenue_window"]
    ].sum().reindex(SEGMENTS).fillna(0)
    customers = curated.groupby("segment")["customer_id"].count().reindex(SEGMENTS).fillna(0)

    window_rate = cur["return_window"] / cur["gross_window"].replace(0, np.nan)
    lifetime_rate = cur["return_amount"] / cur["gross_revenue"].replace(0, np.nan)
    return_rate = window_rate.fillna(lifetime_rate).fillna(0.0)

    out = g.copy()
    out["customers"] = customers.astype(int)
    out["return_rate"] = return_rate
    out["net_value"] = out["conversion_value"] * (1 - out["return_rate"])
    out["cvr"] = out["conversions"] / out["clicks"].replace(0, np.nan)
    out["cpa"] = out["spend"] / out["conversions"].replace(0, np.nan)
    out["net_roas"] = out["net_value"] / out["spend"].replace(0, np.nan)
    blended = out["net_value"].sum() / out["spend"].sum() if out["spend"].sum() else np.nan
    out["responsiveness_index"] = out["net_roas"] / blended * 100
    out["spend_share"] = out["spend"] / out["spend"].sum() if out["spend"].sum() else 0.0
    revenue = cur["net_revenue_window"]
    out["net_revenue_window"] = revenue
    out["revenue_share"] = revenue / revenue.sum() if revenue.sum() else 0.0
    out = out.rename_axis("segment").reset_index()
    return out, {"blended_net_roas": float(blended), "unattributed_spend_share": unattributed_share}
