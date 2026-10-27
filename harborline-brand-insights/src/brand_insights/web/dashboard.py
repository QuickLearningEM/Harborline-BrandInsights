"""Turn mart tables into the plain-language data the dashboard templates display."""

import threading
import time

import pandas as pd

from ..analytics.sentiment import ATTRIBUTE_LABELS, ATTRIBUTES
from ..config import SEGMENTS
from ..warehouse import Warehouse

ORDER = {"Under-invested": 0, "Over-invested": 1, "Message mismatch": 2, "Aligned": 3}
CSS = {"Under-invested": "under", "Over-invested": "over", "Message mismatch": "mismatch",
       "Aligned": "aligned", "Not enough data": "nodata"}
CHART_MAX_WIDTH = 360
INDEX_BAR_WIDTH = 100


def _v(x):
    return None if x is None or pd.isna(x) else x


def pct(x, digits: int = 0) -> str:
    x = _v(x)
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


def _sentiment_class(score) -> str:
    score = _v(score)
    if score is None:
        return "nodata"
    return "pos" if score > 0.15 else "neg" if score < -0.15 else "neu"


def build_context(scorecard: pd.DataFrame, attributes: pd.DataFrame, status: pd.DataFrame) -> dict:
    sc = scorecard.set_index("segment").reindex(SEGMENTS).reset_index()
    max_share = max(float(sc["spend_share"].max()), float(sc["revenue_share"].max()), 0.01)
    rows = []
    for i, r in sc.iterrows():
        idx = _v(r["responsiveness_index"])
        score = _v(r["sentiment_score"])
        rows.append({
            "segment": r["segment"],
            "customers": f"{int(r['customers']):,}",
            "spend_share": pct(r["spend_share"]), "revenue_share": pct(r["revenue_share"]),
            "spend_w": round(float(r["spend_share"]) / max_share * CHART_MAX_WIDTH, 1),
            "revenue_w": round(float(r["revenue_share"]) / max_share * CHART_MAX_WIDTH, 1),
            "y": 12 + i * 52,
            "index": None if idx is None else round(float(idx)),
            "index_w": 0 if idx is None else round(min(float(idx), 200) / 200 * INDEX_BAR_WIDTH, 1),
            "roas": "n/a" if _v(r["net_roas"]) is None else f"{r['net_roas']:.2f}",
            "sentiment": f"Not enough data ({int(r['sentiment_n'])} comments)" if score is None
            else f"{score:+.2f}",
            "sentiment_class": _sentiment_class(score),
            "classification": r["classification"], "css": CSS.get(r["classification"], "nodata"),
            "recommendation": r["recommendation"],
            "evidence": (f"{pct(r['spend_share'])} of ad spend, {pct(r['revenue_share'])} of revenue, "
                         f"responsiveness {'n/a' if idx is None else round(float(idx))}"),
        })
    actions = sorted(rows, key=lambda x: (ORDER.get(x["classification"], 9), -(x["index"] or 0)))

    attr = attributes.set_index(["segment", "attribute"])
    matrix = []
    for seg in SEGMENTS:
        cells = []
        for a in ATTRIBUTES:
            score = _v(attr.loc[(seg, a), "score"]) if (seg, a) in attr.index else None
            cells.append({"text": "n/a" if score is None else f"{score:+.2f}",
                          "css": _sentiment_class(score)})
        matrix.append({"segment": seg, "cells": cells})

    s = status.iloc[0].to_dict()
    return {
        "rows": rows, "actions": actions, "matrix": matrix,
        "attribute_labels": [ATTRIBUTE_LABELS[a].capitalize() for a in ATTRIBUTES],
        "chart_height": 12 + 52 * len(rows),
        "status": {
            **s,
            "match_rate_store_txt": pct(s["match_rate_store"]),
            "match_rate_online_txt": pct(s["match_rate_online"]),
            "unattributed_txt": pct(s["unattributed_spend_share"], 1),
            "customers_txt": f"{int(s['customers_total']):,}",
            "comments_txt": f"{int(s['comments_total']):,}",
        },
    }


class DashboardService:
    """Reads the marts and caches the result briefly so page views do not hit the warehouse."""

    def __init__(self, warehouse: Warehouse, ttl_seconds: int = 300):
        self._wh, self._ttl = warehouse, ttl_seconds
        self._cache: tuple[float, dict] | None = None
        self._lock = threading.Lock()

    def get(self) -> dict | None:
        with self._lock:
            if self._cache and time.monotonic() - self._cache[0] < self._ttl:
                return self._cache[1]
            try:
                ctx = build_context(
                    self._wh.read_table("mart_segment_scorecard"),
                    self._wh.read_table("mart_sentiment_attributes"),
                    self._wh.read_table("mart_pipeline_status"),
                )
            except KeyError:
                return None
            self._cache = (time.monotonic(), ctx)
            return ctx
