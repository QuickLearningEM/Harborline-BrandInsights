"""Build one curated customer record from CRM, online, and in-store data.

Customers are matched on customer ID (online orders) and loyalty ID (store transactions).
Transactions that cannot be matched are counted and reported, never silently dropped
from the data-quality figures. Email hashes are not carried past this step.
"""

import pandas as pd


def _transactions(online: pd.DataFrame, store: pd.DataFrame) -> pd.DataFrame:
    o = online.rename(columns={"order_id": "txn_id", "order_date": "txn_date"})
    o = o.assign(channel="online")[
        ["txn_id", "customer_id", "txn_date", "category", "gross_amount", "return_amount", "channel"]
    ]
    s = store.rename(columns={"loyalty_id": "customer_id"}).assign(channel="store")[
        ["txn_id", "customer_id", "txn_date", "category", "gross_amount", "return_amount", "channel"]
    ]
    tx = pd.concat([o, s], ignore_index=True)
    tx["txn_date"] = pd.to_datetime(tx["txn_date"])
    return tx


def build_customer_table(
    customers: pd.DataFrame,
    online: pd.DataFrame,
    store: pd.DataFrame,
    window_days: int = 365,
) -> tuple[pd.DataFrame, dict, pd.Timestamp]:
    """Return (curated customers, match statistics, as_of date)."""
    tx = _transactions(online, store)
    as_of = tx["txn_date"].max()
    known = set(customers["customer_id"])
    tx["matched"] = tx["customer_id"].isin(known)

    def rate(frame: pd.DataFrame) -> float:
        total = frame["gross_amount"].sum()
        return float(frame.loc[frame["matched"], "gross_amount"].sum() / total) if total else 0.0

    stats = {
        "match_rate_overall": rate(tx),
        "match_rate_store": rate(tx[tx["channel"] == "store"]),
        "match_rate_online": rate(tx[tx["channel"] == "online"]),
        "unmatched_transactions": int((~tx["matched"]).sum()),
        "total_transactions": len(tx),
    }

    m = tx[tx["matched"]].copy()
    m["in_window"] = m["txn_date"] >= as_of - pd.Timedelta(days=window_days)
    m["gross_w"] = m["gross_amount"].where(m["in_window"], 0.0)
    m["return_w"] = m["return_amount"].where(m["in_window"], 0.0)
    m["decor_amt"] = m["gross_amount"].where(m["category"] == "decor", 0.0)
    m["online_amt"] = m["gross_amount"].where(m["channel"] == "online", 0.0)

    agg = m.groupby("customer_id").agg(
        orders=("txn_id", "count"), gross_revenue=("gross_amount", "sum"),
        return_amount=("return_amount", "sum"), gross_window=("gross_w", "sum"),
        return_window=("return_w", "sum"), last_purchase_date=("txn_date", "max"),
        decor_amt=("decor_amt", "sum"), online_amt=("online_amt", "sum"),
    ).reset_index()

    out = customers.drop(columns=["email_hash"]).merge(agg, on="customer_id", how="left")
    for col in ("orders", "gross_revenue", "return_amount", "gross_window", "return_window"):
        out[col] = out[col].fillna(0)
    out["net_revenue"] = out["gross_revenue"] - out["return_amount"]
    out["net_revenue_window"] = out["gross_window"] - out["return_window"]
    total = out["gross_revenue"].replace(0, pd.NA)
    out["decor_share"] = (out["decor_amt"] / total).fillna(0.0).astype(float)
    out["online_share"] = (out["online_amt"] / total).fillna(0.0).astype(float)
    join = pd.to_datetime(out["join_date"])
    last = out["last_purchase_date"].fillna(join)
    out["days_since_last"] = (as_of - last).dt.days
    out["last_purchase_date"] = out["last_purchase_date"].dt.strftime("%Y-%m-%d")
    out = out.drop(columns=["decor_amt", "online_amt"])
    return out, stats, as_of
