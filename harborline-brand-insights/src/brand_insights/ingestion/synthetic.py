"""Seeded synthetic data for all five raw tables, so the whole system runs without credentials.

The data is fictional. Segment behavior is deliberately different so the dashboard shows a
mix of outcomes (one under-invested, one over-invested, and segments with message gaps).
"""

import numpy as np
import pandas as pd

from ..config import SEGMENTS

AS_OF = pd.Timestamp("2026-09-30")
CATEGORIES = ["furniture", "decor", "textiles", "kitchen", "outdoor"]

# share of customers, age range, orders mean, order value mean, return rate, decor bias
PROFILES = {
    "Established Homeowners": (0.30, (35, 62), 4.0, 320.0, 0.05, 0.15),
    "First-Time Furnishers": (0.28, (22, 34), 2.0, 140.0, 0.14, 0.20),
    "Design Enthusiasts": (0.12, (24, 45), 5.0, 180.0, 0.10, 0.75),
    "Lapsed Customers": (0.15, (25, 60), 1.5, 110.0, 0.09, 0.20),
    "Nest & Co. Shoppers": (0.15, (25, 55), 3.0, 90.0, 0.12, 0.20),
}
# share of weekly ad budget, gross return on ad spend
AD_PROFILES = {
    "Established Homeowners": (0.17, 5.2),
    "First-Time Furnishers": (0.36, 2.4),
    "Design Enthusiasts": (0.15, 3.0),
    "Lapsed Customers": (0.12, 1.5),
    "Nest & Co. Shoppers": (0.20, 2.0),
    "Broad prospecting": (0.08, 2.2),
}

# (text, ) templates per segment; the topic words are what map a comment to a segment
COMMENT_TEMPLATES = {
    "First-Time Furnishers": [
        "Love the look for my first apartment but honestly so overpriced for a renter on a budget",
        "Too expensive for a starter set, I will keep shopping around on a budget",
        "Great starter pieces for my first apartment and worth the price",
        "As a renter the prices are hard to justify, overpriced for what you get",
        "Pretty sofa for a first apartment but the price is way too high",
    ],
    "Established Homeowners": [
        "Used this for our kitchen remodel and the quality is excellent and sturdy",
        "Our renovation looks gorgeous, reliable and durable pieces from a brand we trust",
        "Good quality for a homeowner, well made and worth it",
        "The table for our remodel is solid and perfect, great service too",
        "Nice homeowner upgrade, durable and honest pricing",
    ],
    "Design Enthusiasts": [
        "Beautiful aesthetic but it feels like a knockoff of designer pieces, not authentic",
        "Love the trend styling but the designer inspired look is a fake copy",
        "Gorgeous interior design vibes, stylish and trendy",
        "The aesthetic is great but I do not trust that it is original, feels like a copy",
        "Trending look, beautiful colors, a bit of a knockoff though",
    ],
    "Lapsed Customers": [
        "I used to shop here but switched after a sofa that felt cheaply made",
        "Stopped buying after a flimsy shelf broke, disappointed",
        "I switched to another store, used to shop here and it was fine",
    ],
    "Nest & Co. Shoppers": [
        "Nest & Co is cheap and decent value for the price",
        "Nest & Co has good prices and nice basics",
        "Nest & Co quality is okay, nothing special but affordable",
        "Did not know Nest & Co is the same company, great value",
    ],
    "Unmapped": [
        "Anyone know when the sale ends",
        "Delivery was fast and the box arrived on time",
        "Watching this for ideas, thanks for sharing",
    ],
}
COMMENT_COUNTS = {
    "First-Time Furnishers": 340, "Established Homeowners": 260, "Design Enthusiasts": 90,
    "Lapsed Customers": 22, "Nest & Co. Shoppers": 120, "Unmapped": 60,
}


def _customers_and_sales(rng: np.random.Generator, n: int):
    names = list(PROFILES)
    shares = np.array([PROFILES[s][0] for s in names])
    groups = rng.choice(names, size=n, p=shares / shares.sum())
    customers, online, store = [], [], []
    oid = tid = 0
    for i, group in enumerate(groups):
        _, (lo, hi), n_orders, value, ret_rate, decor_bias = PROFILES[group]
        cid = f"C{i:06d}"
        loyalty = rng.random() < 0.55
        customers.append({
            "customer_id": cid, "email_hash": f"h{rng.integers(10**12):012d}",
            "age": int(rng.integers(lo, hi + 1)),
            "join_date": (AS_OF - pd.Timedelta(days=int(rng.integers(30, 1800)))).date().isoformat(),
            "brand": "Nest & Co." if group == "Nest & Co. Shoppers" else "Harborline",
            "loyalty_member": loyalty,
        })
        count = 1 + rng.poisson(n_orders)
        for k in range(count):
            if group == "Lapsed Customers":
                days_back = int(rng.integers(600, 1200))
            elif k == 0:
                days_back = int(rng.integers(0, 300))
            else:
                days_back = int(rng.integers(0, 900))
            date = (AS_OF - pd.Timedelta(days=days_back)).date().isoformat()
            decor = rng.random() < decor_bias
            category = "decor" if decor else str(rng.choice([c for c in CATEGORIES if c != "decor"]))
            gross = float(max(15.0, rng.normal(value, value * 0.3)))
            returned = gross if rng.random() < ret_rate else 0.0
            if rng.random() < 0.36:  # online
                oid += 1
                guest = rng.random() < 0.08
                online.append({
                    "order_id": f"O{oid:07d}", "customer_id": None if guest else cid,
                    "order_date": date, "category": category, "gross_amount": round(gross, 2),
                    "return_amount": round(returned, 2),
                    "utm_campaign": str(rng.choice(["search", "social", "email", "video"])),
                })
            else:
                tid += 1
                scanned = loyalty and rng.random() < 0.7
                store.append({
                    "txn_id": f"T{tid:07d}", "store_id": f"S{int(rng.integers(1, 141)):03d}",
                    "txn_date": date, "loyalty_id": cid if scanned else None,
                    "category": category, "gross_amount": round(gross, 2),
                    "return_amount": round(returned, 2),
                })
    return pd.DataFrame(customers), pd.DataFrame(online), pd.DataFrame(store)


def _ads(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    weekly_budget = 80_000.0
    for week in range(26):
        date = (AS_OF - pd.Timedelta(weeks=25 - week)).date().isoformat()
        for segment, (share, roas) in AD_PROFILES.items():
            for platform in ("CM360", "DV360"):
                spend = weekly_budget * share * 0.5  # budget split evenly across the two platforms
                spend *= rng.normal(1.0, 0.08)
                impressions = int(spend / 9.0 * 1000)
                clicks = int(impressions * rng.normal(0.012, 0.001))
                value = spend * roas * rng.normal(1.0, 0.06)
                conversions = max(1, int(value / 210.0))
                rows.append({
                    "date": date, "platform": platform, "campaign": f"{segment} always-on",
                    "audience_segment": segment, "impressions": impressions, "clicks": clicks,
                    "spend": round(spend, 2), "conversions": conversions,
                    "conversion_value": round(value, 2),
                })
    return pd.DataFrame(rows)


def _comments(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    n = 0
    for segment, count in COMMENT_COUNTS.items():
        for _ in range(count):
            n += 1
            rows.append({
                "comment_id": f"Y{n:06d}", "video_id": f"V{int(rng.integers(1, 60)):03d}",
                "video_title": "Home decor and furniture ideas", "channel_id": "n/a",
                "published_at": (AS_OF - pd.Timedelta(days=int(rng.integers(0, 120)))).date().isoformat(),
                "text": str(rng.choice(COMMENT_TEMPLATES[segment])),
                "like_count": int(rng.integers(0, 40)), "search_term": "Harborline Home",
            })
    return pd.DataFrame(rows)


def generate(seed: int = 7, n_customers: int = 3000) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    customers, online, store = _customers_and_sales(rng, n_customers)
    assert set(AD_PROFILES) >= set(SEGMENTS)
    return {
        "raw_customers": customers, "raw_online_orders": online,
        "raw_store_transactions": store, "raw_ad_delivery": _ads(rng),
        "raw_youtube_comments": _comments(rng),
    }
