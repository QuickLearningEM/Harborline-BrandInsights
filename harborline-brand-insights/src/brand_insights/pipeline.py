"""End-to-end pipeline: raw tables -> curated tables -> marts read by the dashboard."""

import logging
from datetime import UTC, datetime

import pandas as pd

from .analytics.mistargeting import classify_segments
from .analytics.responsiveness import segment_responsiveness
from .analytics.sentiment import (
    Classifier,
    get_classifier,
    score_comments,
    summarize_by_segment,
    weakest_attributes,
)
from .config import Settings
from .processing.identity import build_customer_table
from .processing.segmentation import assign_segments
from .schemas import RAW_SCHEMAS, validate
from .warehouse import Warehouse

log = logging.getLogger(__name__)

MARTS = ("mart_segment_scorecard", "mart_sentiment_attributes", "mart_pipeline_status")


def _load_raw(warehouse: Warehouse) -> dict[str, pd.DataFrame]:
    raw = {}
    for table in RAW_SCHEMAS:
        if not warehouse.table_exists(table):
            raise RuntimeError(f"Raw table {table} is missing. Ingest data before running the pipeline.")
        raw[table] = validate(warehouse.read_table(table), table)
    return raw


def run_pipeline(
    warehouse: Warehouse, settings: Settings, classifier: Classifier | None = None
) -> dict:
    raw = _load_raw(warehouse)

    curated, match_stats, as_of = build_customer_table(
        raw["raw_customers"], raw["raw_online_orders"], raw["raw_store_transactions"],
        window_days=settings.revenue_window_days,
    )
    curated = assign_segments(curated, as_of, settings.lapsed_days)
    warehouse.write_table("curated_customers", curated)

    scored = score_comments(raw["raw_youtube_comments"], classifier or get_classifier(settings))
    warehouse.write_table("curated_comment_scores", scored)
    sentiment, attributes = summarize_by_segment(
        scored, settings.min_sentiment_sample, settings.min_attribute_mentions
    )

    resp, ad_stats = segment_responsiveness(raw["raw_ad_delivery"], curated)
    scorecard = (
        resp.merge(sentiment, on="segment").merge(weakest_attributes(attributes), on="segment")
    )
    scorecard = classify_segments(
        scorecard, settings.under_invested_index, settings.over_invested_index,
        settings.mismatch_threshold,
    )
    warehouse.write_table("mart_segment_scorecard", scorecard)
    warehouse.write_table("mart_sentiment_attributes", attributes)

    status = pd.DataFrame([{
        "run_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "customers_total": len(curated),
        "transactions_total": match_stats["total_transactions"],
        "unmatched_transactions": match_stats["unmatched_transactions"],
        "match_rate_overall": round(match_stats["match_rate_overall"], 4),
        "match_rate_store": round(match_stats["match_rate_store"], 4),
        "match_rate_online": round(match_stats["match_rate_online"], 4),
        "unattributed_spend_share": round(ad_stats["unattributed_spend_share"], 4),
        "blended_net_roas": round(ad_stats["blended_net_roas"], 3),
        "comments_total": len(scored),
        "comments_unmapped": int((scored["segment"] == "Unmapped").sum()),
        "latest_sales_date": as_of.strftime("%Y-%m-%d"),
        "latest_ad_date": str(raw["raw_ad_delivery"]["date"].max()),
        "latest_comment_date": str(raw["raw_youtube_comments"]["published_at"].max()),
    }])
    warehouse.write_table("mart_pipeline_status", status)
    log.info("Pipeline finished: %d customers, %d comments", len(curated), len(scored))
    return status.iloc[0].to_dict()
