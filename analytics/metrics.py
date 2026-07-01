"""High-level analytics accessors built on top of DuckDB SQL queries."""

from __future__ import annotations

from typing import Any

from analytics.duckdb_client import analytics_connection
from analytics.queries import SQL_QUERIES


def fetch_dataframe(query_name: str):
    with analytics_connection(read_only=True) as connection:
        return connection.sql(SQL_QUERIES[query_name]).df()


def fetch_rows(query_name: str) -> list[dict[str, Any]]:
    return fetch_dataframe(query_name).to_dict(orient="records")


def fetch_scalar(sql: str, default: Any = 0) -> Any:
    with analytics_connection(read_only=True) as connection:
        rows = connection.sql(sql).fetchall()
    if not rows or rows[0][0] is None:
        return default
    return rows[0][0]


def dashboard_snapshot() -> dict[str, Any]:
    overview = fetch_rows("executive_overview")
    weekly = fetch_rows("weekly_growth_by_country")
    features = fetch_rows("feature_adoption")
    anomalies = fetch_rows("anomalies")
    return {
        "overview": overview[0] if overview else {},
        "weekly_growth_by_country": weekly,
        "feature_adoption": features,
        "anomalies": anomalies,
    }
