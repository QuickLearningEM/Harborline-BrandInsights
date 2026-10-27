"""Table-level warehouse interface.

Only whole-table reads and writes are exposed, and table names are validated, so no
caller can build SQL from untrusted text.
"""

import re
from abc import ABC, abstractmethod

import pandas as pd

_TABLE_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


def check_table_name(name: str) -> str:
    if not _TABLE_RE.match(name):
        raise ValueError(f"Invalid table name: {name!r}")
    return name


class Warehouse(ABC):
    @abstractmethod
    def write_table(self, name: str, df: pd.DataFrame) -> None:
        """Create or fully replace a table."""

    @abstractmethod
    def read_table(self, name: str) -> pd.DataFrame:
        """Read a whole table. Raises KeyError if it does not exist."""

    @abstractmethod
    def table_exists(self, name: str) -> bool: ...

    def close(self) -> None:  # pragma: no cover - default no-op
        return None
