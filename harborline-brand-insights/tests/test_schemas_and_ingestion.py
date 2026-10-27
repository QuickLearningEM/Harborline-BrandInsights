import pytest

from brand_insights.ingestion.files import load_landing_files, upsert_table
from brand_insights.schemas import SchemaError, validate
from brand_insights.warehouse import SqliteWarehouse
from brand_insights.warehouse.base import check_table_name


def test_validate_rejects_missing_columns(raw):
    with pytest.raises(SchemaError, match="missing columns"):
        validate(raw["raw_customers"].drop(columns=["age"]), "raw_customers")


def test_validate_rejects_empty_required_values(raw):
    bad = raw["raw_customers"].copy()
    bad.loc[0, "customer_id"] = None
    with pytest.raises(SchemaError, match="empty values"):
        validate(bad, "raw_customers")


def test_upsert_is_idempotent(tmp_path, raw):
    wh = SqliteWarehouse(tmp_path / "w.db")
    first = upsert_table(wh, "raw_customers", raw["raw_customers"])
    second = upsert_table(wh, "raw_customers", raw["raw_customers"])
    assert first == second == len(raw["raw_customers"])


def test_landing_files_load(tmp_path, raw):
    landing = tmp_path / "landing"
    landing.mkdir()
    raw["raw_ad_delivery"].to_csv(landing / "raw_ad_delivery_2026-09-30.csv", index=False)
    wh = SqliteWarehouse(tmp_path / "w.db")
    counts = load_landing_files(landing, wh)
    assert counts == {"raw_ad_delivery": len(raw["raw_ad_delivery"])}


def test_table_names_are_validated():
    with pytest.raises(ValueError):
        check_table_name("raw_customers; DROP TABLE x")
