"""Bootstrap helpers for the messaging analytics demo platform."""

from __future__ import annotations

import logging

from analytics.duckdb_client import analytics_connection
from pipelines.anomaly_detection import build_anomaly_table
from pipelines.build_metric_tables import build_metric_tables
from pipelines.etl_pipeline import run_etl
from pipelines.generate_synthetic_data import main as generate_synthetic_data


logger = logging.getLogger(__name__)

REQUIRED_TABLES = (
    "daily_product_metrics",
    "geo_daily_metrics",
    "feature_adoption_metrics",
    "retention_cohorts",
    "funnel_metrics",
    "message_engagement_metrics",
    "notification_engagement_metrics",
    "safety_metrics",
    "crash_metrics",
    "anomaly_alerts",
)


def analytics_tables_ready() -> bool:
    """Return True when all required analytics tables exist."""
    try:
        with analytics_connection(read_only=True) as connection:
            rows = connection.sql(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                """
            ).fetchall()
    except Exception:
        return False

    existing = {row[0] for row in rows}
    return all(table_name in existing for table_name in REQUIRED_TABLES)


def bootstrap_analytics_if_needed(row_count: int = 100000) -> None:
    """Build analytics demo artifacts when they do not already exist."""
    if analytics_tables_ready():
        logger.info("Analytics warehouse already prepared.")
        return

    logger.info("Analytics warehouse missing or incomplete. Bootstrapping synthetic demo data.")
    generate_synthetic_data(rows=row_count)
    run_etl()
    build_metric_tables()
    build_anomaly_table()
    logger.info("Analytics warehouse bootstrap complete.")
