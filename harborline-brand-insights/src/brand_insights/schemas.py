"""Expected shape of every raw table landed in the warehouse.

Salesforce and Shopify arrive through the managed ELT connector (already mapped to these
columns); Xstore and the CM360/DV360 reports arrive as files; YouTube is pulled by this
codebase. Every path validates against the same schemas before anything is processed.

Type codes: str, int, float, bool, date. A trailing "?" means the column may be empty.
"""

import pandas as pd

RAW_SCHEMAS: dict[str, dict[str, str]] = {
    "raw_customers": {
        "customer_id": "str", "email_hash": "str", "age": "int", "join_date": "date",
        "brand": "str", "loyalty_member": "bool",
    },
    "raw_online_orders": {
        "order_id": "str", "customer_id": "str?", "order_date": "date", "category": "str",
        "gross_amount": "float", "return_amount": "float", "utm_campaign": "str?",
    },
    "raw_store_transactions": {
        "txn_id": "str", "store_id": "str", "txn_date": "date", "loyalty_id": "str?",
        "category": "str", "gross_amount": "float", "return_amount": "float",
    },
    "raw_ad_delivery": {
        "date": "date", "platform": "str", "campaign": "str", "audience_segment": "str",
        "impressions": "int", "clicks": "int", "spend": "float", "conversions": "int",
        "conversion_value": "float",
    },
    "raw_youtube_comments": {
        "comment_id": "str", "video_id": "str", "video_title": "str", "channel_id": "str",
        "published_at": "date", "text": "str", "like_count": "int", "search_term": "str",
    },
}

PRIMARY_KEYS: dict[str, list[str]] = {
    "raw_customers": ["customer_id"],
    "raw_online_orders": ["order_id"],
    "raw_store_transactions": ["txn_id"],
    "raw_ad_delivery": ["date", "platform", "campaign", "audience_segment"],
    "raw_youtube_comments": ["comment_id"],
}


class SchemaError(ValueError):
    pass


def validate(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Return a cleaned copy of df, or raise SchemaError describing what is wrong."""
    spec = RAW_SCHEMAS[table]
    missing = [c for c in spec if c not in df.columns]
    if missing:
        raise SchemaError(f"{table}: missing columns {missing}")
    out = df[list(spec)].copy()
    for col, code in spec.items():
        optional = code.endswith("?")
        kind = code.rstrip("?")
        if not optional and out[col].isna().any():
            raise SchemaError(f"{table}.{col}: contains empty values")
        try:
            if kind == "date":
                out[col] = pd.to_datetime(out[col]).dt.strftime("%Y-%m-%d")
            elif kind == "int":
                out[col] = pd.to_numeric(out[col]).astype("int64")
            elif kind == "float":
                out[col] = pd.to_numeric(out[col]).astype("float64")
            elif kind == "bool":
                out[col] = out[col].map(lambda v: str(v).lower() in {"1", "true", "t", "yes"})
            else:
                out[col] = out[col].where(out[col].isna(), out[col].astype(str))
        except (ValueError, TypeError) as exc:
            raise SchemaError(f"{table}.{col}: cannot convert to {kind}") from exc
    dupes = int(out.duplicated(PRIMARY_KEYS[table]).sum())
    if dupes:
        out = out.drop_duplicates(PRIMARY_KEYS[table], keep="last")
    return out.reset_index(drop=True)
