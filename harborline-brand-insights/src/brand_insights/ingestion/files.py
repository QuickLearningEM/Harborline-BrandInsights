"""Load file-based sources (Xstore nightly file, CM360/DV360 report exports).

Files are dropped in the landing directory by the scheduled exports, named
<table>*.csv (for example raw_ad_delivery_2026-10-14.csv). Loads are idempotent: rows
are merged by primary key, so re-loading a file never double counts.
"""

import logging
from pathlib import Path

import pandas as pd

from ..schemas import PRIMARY_KEYS, RAW_SCHEMAS, validate
from ..warehouse import Warehouse

log = logging.getLogger(__name__)

FILE_TABLES = ("raw_store_transactions", "raw_ad_delivery")


def upsert_table(warehouse: Warehouse, table: str, new_rows: pd.DataFrame) -> int:
    """Merge validated rows into a raw table by primary key. Returns the resulting row count."""
    clean = validate(new_rows, table)
    if warehouse.table_exists(table):
        existing = validate(warehouse.read_table(table), table)
        clean = pd.concat([existing, clean], ignore_index=True)
        clean = clean.drop_duplicates(PRIMARY_KEYS[table], keep="last")
    warehouse.write_table(table, clean.reset_index(drop=True))
    return len(clean)


def load_landing_files(landing_dir: Path, warehouse: Warehouse) -> dict[str, int]:
    """Load every landing file for the file-based tables. Returns row counts by table."""
    counts: dict[str, int] = {}
    for table in FILE_TABLES:
        files = sorted(landing_dir.glob(f"{table}*.csv"))
        if not files:
            log.warning("No landing files found for %s in %s", table, landing_dir)
            continue
        frames = [pd.read_csv(f, dtype=str, keep_default_na=True) for f in files]
        counts[table] = upsert_table(warehouse, table, pd.concat(frames, ignore_index=True))
        log.info("Loaded %d files into %s (%d rows)", len(files), table, counts[table])
    return counts


def expected_columns(table: str) -> list[str]:
    """Columns a report export must contain; used in docs and export templates."""
    return list(RAW_SCHEMAS[table])
