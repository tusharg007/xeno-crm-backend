"""Shared DuckDB helpers for synthetic messaging analytics."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

from config import resolve_path, settings


def analytics_db_path() -> Path:
    path = resolve_path(settings.ANALYTICS_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def analytics_connection(read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(str(analytics_db_path()), read_only=read_only)
    try:
        yield connection
    finally:
        connection.close()
