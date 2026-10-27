"""Snowflake backend. Requires the optional `snowflake` extra.

Use key-pair authentication and a least-privilege role: the pipeline role needs write
access to the schema, while the web app role should only be able to SELECT from the
mart_* tables (see sql/snowflake_setup.sql).
"""

import pandas as pd

from ..config import Settings
from .base import Warehouse, check_table_name


class SnowflakeWarehouse(Warehouse):
    def __init__(self, settings: Settings):
        try:
            import snowflake.connector
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the snowflake extra: pip install '.[snowflake]'") from exc

        params: dict = {
            "account": settings.snowflake_account,
            "user": settings.snowflake_user,
            "role": settings.snowflake_role or None,
            "warehouse": settings.snowflake_warehouse or None,
            "database": settings.snowflake_database,
            "schema": settings.snowflake_schema,
        }
        if settings.snowflake_private_key_path:
            params["private_key_file"] = str(settings.snowflake_private_key_path)
        else:
            params["password"] = settings.snowflake_password
        self._conn = snowflake.connector.connect(**{k: v for k, v in params.items() if v})

    def write_table(self, name: str, df: pd.DataFrame) -> None:  # pragma: no cover
        from snowflake.connector.pandas_tools import write_pandas

        check_table_name(name)
        write_pandas(
            self._conn, df, name.upper(), auto_create_table=True, overwrite=True,
            use_logical_type=True,
        )

    def read_table(self, name: str) -> pd.DataFrame:  # pragma: no cover
        check_table_name(name)
        if not self.table_exists(name):
            raise KeyError(name)
        cur = self._conn.cursor()
        try:
            cur.execute(f'SELECT * FROM "{name.upper()}"')
            df = cur.fetch_pandas_all()
        finally:
            cur.close()
        df.columns = [c.lower() for c in df.columns]
        return df

    def table_exists(self, name: str) -> bool:  # pragma: no cover
        check_table_name(name)
        cur = self._conn.cursor()
        try:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = CURRENT_SCHEMA() AND table_name = %s",
                (name.upper(),),
            )
            return cur.fetchone()[0] > 0
        finally:
            cur.close()

    def close(self) -> None:  # pragma: no cover
        self._conn.close()
