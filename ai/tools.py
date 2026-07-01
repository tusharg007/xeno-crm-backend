"""Read-only tools used by the analytics copilot."""

from __future__ import annotations

from textwrap import shorten

from analytics.anomalies import anomaly_rows
from analytics.duckdb_client import analytics_connection
from analytics.metrics import dashboard_snapshot, fetch_rows
from analytics.reports import generate_weekly_report_markdown
from ai.rag import retrieve_docs


def run_sql_query(sql: str) -> list[dict]:
    lowered = sql.lower().strip()
    if not lowered.startswith("select"):
        raise ValueError("Only SELECT statements are allowed.")
    with analytics_connection(read_only=True) as connection:
        return connection.sql(sql).df().to_dict(orient="records")


def retrieve_metric_definition(query: str) -> list[dict]:
    return [
        {"source": chunk.source, "content": shorten(chunk.content, width=320, placeholder="...")}
        for chunk in retrieve_docs(query)
    ]


def detect_anomaly(metric_name: str | None = None) -> list[dict]:
    rows = anomaly_rows()
    if metric_name:
        return [row for row in rows if row["metric_name"] == metric_name]
    return rows


def generate_weekly_report() -> dict:
    return {"markdown": generate_weekly_report_markdown()}


def summarize_dashboard_insights() -> dict:
    snapshot = dashboard_snapshot()
    overview = snapshot.get("overview", {})
    anomalies = snapshot.get("anomalies", [])[:5]
    return {
        "overview": overview,
        "top_anomalies": anomalies,
        "weekly_growth_by_country": snapshot.get("weekly_growth_by_country", [])[:5],
        "feature_adoption": snapshot.get("feature_adoption", [])[:5],
    }


def campaign_performance_summary() -> list[dict]:
    return fetch_rows("message_engagement")[:7]
