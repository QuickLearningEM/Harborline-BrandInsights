"""SQLite backend for local development, demos, and tests."""

import sqlite3
from pathlib import Path

import pandas as pd

from .base import Warehouse, check_table_name


class SqliteWarehouse(Warehouse):
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def write_table(self, name: str, df: pd.DataFrame) -> None:
        check_table_name(name)
        with self._connect() as conn:
            df.to_sql(name, conn, if_exists="replace", index=False)

    def read_table(self, name: str) -> pd.DataFrame:
        check_table_name(name)
        if not self.table_exists(name):
            raise KeyError(name)
        with self._connect() as conn:
            return pd.read_sql_query(f'SELECT * FROM "{name}"', conn)

    def table_exists(self, name: str) -> bool:
        check_table_name(name)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
            ).fetchone()
        return row is not None
