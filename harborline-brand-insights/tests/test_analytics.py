import numpy as np
import pandas as pd

from brand_insights.analytics.mistargeting import ALIGNED, MISMATCH, OVER, UNDER, classify_segments
from brand_insights.analytics.sentiment import (
    LexiconClassifier,
    LLMClassifier,
    map_segment,
    score_comments,
    summarize_by_segment,
)
from brand_insights.config import SEGMENTS


def test_identity_match_rates_reported(built):
    status = built.read_table("mart_pipeline_status").iloc[0]
    assert 0 < status["match_rate_store"] < status["match_rate_online"] <= 1
    assert status["unmatched_transactions"] > 0


def test_every_customer_gets_one_segment(built):
    cur = built.read_table("curated_customers")
    assert set(cur["segment"]) <= set(SEGMENTS)
    assert cur["customer_id"].is_unique
    assert "email_hash" not in cur.columns  # data minimization


def test_scorecard_shares_sum_to_one(built):
    sc = built.read_table("mart_segment_scorecard")
    assert abs(sc["spend_share"].sum() - 1) < 1e-6
    assert abs(sc["revenue_share"].sum() - 1) < 1e-6
    assert set(sc["classification"]) <= {UNDER, OVER, MISMATCH, ALIGNED, "Not enough data"}


def test_expected_demo_outcomes(built):
    sc = built.read_table("mart_segment_scorecard").set_index("segment")
    assert sc.loc["Established Homeowners", "classification"] == UNDER
    assert sc.loc["Lapsed Customers", "classification"] == OVER
    assert sc.loc["Design Enthusiasts", "classification"] == MISMATCH


def test_small_samples_are_suppressed(built):
    sc = built.read_table("mart_segment_scorecard").set_index("segment")
    lapsed = sc.loc["Lapsed Customers"]
    assert not lapsed["sentiment_reliable"] and pd.isna(lapsed["sentiment_score"])
    assert pd.isna(lapsed["weakest_score"])


def test_classification_rules():
    base = {"spend": 1.0, "weakest_attribute": "price_value"}
    rows = pd.DataFrame([
        {**base, "responsiveness_index": 150, "spend_share": .1, "revenue_share": .4, "weakest_score": np.nan},
        {**base, "responsiveness_index": 50, "spend_share": .4, "revenue_share": .1, "weakest_score": np.nan},
        {**base, "responsiveness_index": 100, "spend_share": .2, "revenue_share": .2, "weakest_score": -.5},
        {**base, "responsiveness_index": 100, "spend_share": .2, "revenue_share": .2, "weakest_score": .3},
    ])
    out = classify_segments(rows)["classification"].tolist()
    assert out == [UNDER, OVER, MISMATCH, ALIGNED]


def test_lexicon_handles_negation_and_clauses():
    clf = LexiconClassifier()
    good, bad = clf.classify(["Great quality, sturdy", "I do not trust it, feels like a copy"])
    assert good.sentiment > 0.5 and good.attributes["quality"] > 0
    assert bad.sentiment < -0.5 and bad.attributes["trust"] < 0


def test_segment_mapping():
    assert map_segment("Perfect for my first apartment") == "First-Time Furnishers"
    assert map_segment("Delivery was fast") == "Unmapped"


def test_summary_marks_unreliable(raw):
    scored = score_comments(raw["raw_youtube_comments"], LexiconClassifier())
    summary, attrs = summarize_by_segment(scored, min_sample=30, min_mentions=10)
    assert summary.set_index("segment").loc["Lapsed Customers", "sentiment_reliable"] == False
    assert attrs[attrs["segment"] == "Lapsed Customers"]["score"].isna().all()


class _FakeMessages:
    def __init__(self, reply):
        self.reply = reply

    def create(self, **kwargs):
        block = type("B", (), {"type": "text", "text": self.reply})()
        return type("M", (), {"content": [block]})()


class _FakeClient:
    def __init__(self, reply):
        self.messages = _FakeMessages(reply)


def test_llm_classifier_validates_and_falls_back():
    ok = LLMClassifier(_FakeClient('[{"id":0,"sentiment":2,"attributes":{"quality":0.5,"bogus":1}}]'), "m")
    result = ok.classify(["anything"])[0]
    assert result.sentiment == 1.0 and result.attributes == {"quality": 0.5}
    bad = LLMClassifier(_FakeClient("Ignore previous instructions"), "m")
    fallback = bad.classify(["Great quality"])[0]
    assert fallback.sentiment > 0  # lexicon fallback
