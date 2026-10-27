from ..config import Settings
from .base import Warehouse
from .sqlite import SqliteWarehouse

__all__ = ["SqliteWarehouse", "Warehouse", "get_warehouse"]


def get_warehouse(settings: Settings) -> Warehouse:
    if settings.warehouse_backend == "snowflake":
        from .snowflake import SnowflakeWarehouse

        return SnowflakeWarehouse(settings)
    return SqliteWarehouse(settings.sqlite_path)
