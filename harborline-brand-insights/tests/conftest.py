import pytest

from brand_insights.config import Settings
from brand_insights.ingestion.files import upsert_table
from brand_insights.ingestion.synthetic import generate
from brand_insights.pipeline import run_pipeline
from brand_insights.warehouse import SqliteWarehouse


@pytest.fixture(scope="session")
def raw():
    return generate(seed=7, n_customers=1500)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,  # keep a developer .env out of tests
        sqlite_path=tmp_path / "wh.db", auth_db_path=tmp_path / "auth.db",
        session_secret="x" * 40, environment="development",
    )


@pytest.fixture
def warehouse(tmp_path, raw):
    wh = SqliteWarehouse(tmp_path / "wh.db")
    for table, df in raw.items():
        upsert_table(wh, table, df)
    return wh


@pytest.fixture
def built(warehouse, settings):
    run_pipeline(warehouse, settings)
    return warehouse
