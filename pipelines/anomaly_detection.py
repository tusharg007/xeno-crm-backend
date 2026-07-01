"""Simple anomaly detection using rolling averages and percentage deltas."""

from __future__ import annotations

from analytics.duckdb_client import analytics_connection


def build_anomaly_table() -> None:
    with analytics_connection() as connection:
        connection.sql("DROP TABLE IF EXISTS anomaly_alerts")
        connection.sql(
            """
            CREATE TABLE anomaly_alerts AS
            WITH base AS (
                SELECT
                    metric_date,
                    dau,
                    messages_sent,
                    spam_reports,
                    crash_rate,
                    AVG(dau) OVER (ORDER BY metric_date ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS dau_mean,
                    AVG(messages_sent) OVER (ORDER BY metric_date ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS message_mean,
                    AVG(spam_reports) OVER (ORDER BY metric_date ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS spam_mean,
                    AVG(crash_rate) OVER (ORDER BY metric_date ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS crash_mean
                FROM daily_product_metrics
            ),
            rows AS (
                SELECT
                    'dau' AS metric_name,
                    metric_date AS anomaly_date,
                    dau AS current_value,
                    COALESCE(dau_mean, dau) AS rolling_mean,
                    CASE WHEN COALESCE(dau_mean, 0) = 0 THEN 0 ELSE (dau - dau_mean) * 100.0 / dau_mean END AS pct_change,
                    CASE WHEN COALESCE(dau_mean, 0) > 0 AND ABS((dau - dau_mean) * 100.0 / dau_mean) > 18 THEN 'high' ELSE 'normal' END AS severity,
                    CASE WHEN COALESCE(dau_mean, 0) > 0 AND ABS((dau - dau_mean) * 100.0 / dau_mean) > 18
                        THEN 'DAU moved sharply versus the trailing 7-day baseline.'
                        ELSE 'DAU is within normal bounds.'
                    END AS explanation
                FROM base
                UNION ALL
                SELECT
                    'messages_sent',
                    metric_date,
                    messages_sent,
                    COALESCE(message_mean, messages_sent),
                    CASE WHEN COALESCE(message_mean, 0) = 0 THEN 0 ELSE (messages_sent - message_mean) * 100.0 / message_mean END,
                    CASE WHEN COALESCE(message_mean, 0) > 0 AND ABS((messages_sent - message_mean) * 100.0 / message_mean) > 20 THEN 'high' ELSE 'normal' END,
                    CASE WHEN COALESCE(message_mean, 0) > 0 AND ABS((messages_sent - message_mean) * 100.0 / message_mean) > 20
                        THEN 'Messaging volume spiked or dipped relative to the trailing 7-day baseline.'
                        ELSE 'Messaging volume is within normal bounds.'
                    END
                FROM base
                UNION ALL
                SELECT
                    'spam_reports',
                    metric_date,
                    spam_reports,
                    COALESCE(spam_mean, spam_reports),
                    CASE WHEN COALESCE(spam_mean, 0) = 0 THEN 0 ELSE (spam_reports - spam_mean) * 100.0 / spam_mean END,
                    CASE WHEN COALESCE(spam_mean, 0) > 0 AND ABS((spam_reports - spam_mean) * 100.0 / spam_mean) > 30 THEN 'high' ELSE 'normal' END,
                    CASE WHEN COALESCE(spam_mean, 0) > 0 AND ABS((spam_reports - spam_mean) * 100.0 / spam_mean) > 30
                        THEN 'Spam or abuse reports increased materially.'
                        ELSE 'Spam reporting is stable.'
                    END
                FROM base
                UNION ALL
                SELECT
                    'crash_rate',
                    metric_date,
                    crash_rate,
                    COALESCE(crash_mean, crash_rate),
                    CASE WHEN COALESCE(crash_mean, 0) = 0 THEN 0 ELSE (crash_rate - crash_mean) * 100.0 / crash_mean END,
                    CASE WHEN COALESCE(crash_mean, 0) > 0 AND ABS((crash_rate - crash_mean) * 100.0 / crash_mean) > 25 THEN 'high' ELSE 'normal' END,
                    CASE WHEN COALESCE(crash_mean, 0) > 0 AND ABS((crash_rate - crash_mean) * 100.0 / crash_mean) > 25
                        THEN 'Crash rate jumped relative to the trailing 7-day baseline.'
                        ELSE 'Crash rate is within normal bounds.'
                    END
                FROM base
            )
            SELECT *
            FROM rows
            WHERE severity = 'high'
            ORDER BY anomaly_date DESC
            """
        )


if __name__ == "__main__":
    build_anomaly_table()
