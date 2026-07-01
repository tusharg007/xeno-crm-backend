"""Build product analytics metric tables from staged DuckDB data."""

from __future__ import annotations

from analytics.duckdb_client import analytics_connection


def build_metric_tables() -> None:
    with analytics_connection() as connection:
        connection.sql("DROP TABLE IF EXISTS daily_product_metrics")
        connection.sql(
            """
            CREATE TABLE daily_product_metrics AS
            WITH session_daily AS (
                SELECT
                    DATE(started_at) AS metric_date,
                    COUNT(DISTINCT user_id) AS dau
                FROM stg_sessions
                GROUP BY 1
            ),
            message_daily AS (
                SELECT
                    DATE(created_at) AS metric_date,
                    COUNT(*) AS messages_sent,
                    SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END) AS delivered_messages
                FROM stg_messages
                GROUP BY 1
            ),
            notification_daily AS (
                SELECT
                    DATE(sent_at) AS metric_date,
                    COUNT(*) AS notifications_sent,
                    SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) AS notifications_opened
                FROM stg_notifications
                GROUP BY 1
            ),
            report_daily AS (
                SELECT DATE(reported_at) AS metric_date, COUNT(*) AS spam_reports
                FROM stg_user_reports
                GROUP BY 1
            ),
            crash_daily AS (
                SELECT
                    DATE(crashed_at) AS metric_date,
                    COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM stg_users), 0) AS crash_rate
                FROM stg_app_crashes
                GROUP BY 1
            )
            SELECT
                s.metric_date,
                s.dau,
                COALESCE(m.messages_sent, 0) AS messages_sent,
                COALESCE(m.delivered_messages, 0) * 100.0 / NULLIF(COALESCE(m.messages_sent, 0), 0) AS message_delivery_rate,
                COALESCE(n.notifications_opened, 0) * 100.0 / NULLIF(COALESCE(n.notifications_sent, 0), 0) AS notification_open_rate,
                COALESCE(r.spam_reports, 0) AS spam_reports,
                COALESCE(c.crash_rate, 0) AS crash_rate
            FROM session_daily s
            LEFT JOIN message_daily m USING(metric_date)
            LEFT JOIN notification_daily n USING(metric_date)
            LEFT JOIN report_daily r USING(metric_date)
            LEFT JOIN crash_daily c USING(metric_date)
            ORDER BY metric_date
            """
        )

        connection.sql("DROP TABLE IF EXISTS geo_daily_metrics")
        connection.sql(
            """
            CREATE TABLE geo_daily_metrics AS
            SELECT
                DATE(created_at) AS metric_date,
                country,
                COUNT(*) AS messages_sent,
                COUNT(DISTINCT sender_user_id) AS active_users
            FROM stg_messages
            GROUP BY 1, 2
            """
        )

        connection.sql("DROP TABLE IF EXISTS feature_adoption_metrics")
        connection.sql(
            """
            CREATE TABLE feature_adoption_metrics AS
            WITH base AS (
                SELECT
                    feature_name,
                    COUNT(*) AS events,
                    COUNT(DISTINCT user_id) AS unique_users
                FROM stg_feature_usage
                GROUP BY 1
            ),
            totals AS (
                SELECT COUNT(DISTINCT user_id) AS total_users FROM stg_users
            )
            SELECT
                b.feature_name,
                b.unique_users,
                b.unique_users * 100.0 / NULLIF(t.total_users, 0) AS adoption_rate,
                b.events * 1.0 / NULLIF(b.unique_users, 0) AS avg_events_per_user
            FROM base b
            CROSS JOIN totals t
            ORDER BY adoption_rate DESC
            """
        )

        connection.sql("DROP TABLE IF EXISTS retention_cohorts")
        connection.sql(
            """
            CREATE TABLE retention_cohorts AS
            WITH user_first_session AS (
                SELECT
                    user_id,
                    DATE(MIN(started_at)) AS first_session_date
                FROM stg_sessions
                GROUP BY 1
            ),
            user_return_days AS (
                SELECT
                    s.user_id,
                    u.first_session_date,
                    MIN(DATEDIFF('day', u.first_session_date, DATE(s.started_at))) FILTER (WHERE DATE(s.started_at) > u.first_session_date) AS first_return_day,
                    MAX(CASE WHEN DATEDIFF('day', u.first_session_date, DATE(s.started_at)) <= 7 AND DATE(s.started_at) > u.first_session_date THEN 1 ELSE 0 END) AS returned_d7,
                    MAX(CASE WHEN DATEDIFF('day', u.first_session_date, DATE(s.started_at)) <= 30 AND DATE(s.started_at) > u.first_session_date THEN 1 ELSE 0 END) AS returned_d30
                FROM stg_sessions s
                JOIN user_first_session u USING(user_id)
                GROUP BY 1, 2
            )
            SELECT
                DATE_TRUNC('week', first_session_date) AS cohort_week,
                COUNT(*) AS cohort_size,
                AVG(CASE WHEN first_return_day = 1 THEN 1 ELSE 0 END) * 100.0 AS d1_retention,
                AVG(returned_d7) * 100.0 AS d7_retention,
                AVG(returned_d30) * 100.0 AS d30_retention
            FROM user_return_days
            GROUP BY 1
            ORDER BY cohort_week DESC
            """
        )

        connection.sql("DROP TABLE IF EXISTS funnel_metrics")
        connection.sql(
            """
            CREATE TABLE funnel_metrics AS
            WITH base AS (
                SELECT COUNT(*) AS signed_up FROM stg_users
            ),
            sessions AS (
                SELECT COUNT(DISTINCT user_id) AS activated FROM stg_sessions
            ),
            messages AS (
                SELECT COUNT(DISTINCT sender_user_id) AS sent_message FROM stg_messages
            ),
            social AS (
                SELECT COUNT(DISTINCT sender_user_id) AS social_connection FROM stg_friend_requests WHERE accepted_at IS NOT NULL
            )
            SELECT * FROM (
                VALUES
                    (1, 'Signed up', (SELECT signed_up FROM base)),
                    (2, 'Started a session', (SELECT activated FROM sessions)),
                    (3, 'Sent a message', (SELECT sent_message FROM messages)),
                    (4, 'Built a connection', (SELECT social_connection FROM social))
            ) t(step_order, step_name, users)
            """
        )
        connection.sql(
            """
            CREATE OR REPLACE TABLE funnel_metrics AS
            SELECT
                step_order,
                step_name,
                users,
                users * 100.0 / NULLIF(LAG(users) OVER (ORDER BY step_order), 0) AS conversion_from_previous,
                users * 100.0 / NULLIF(FIRST_VALUE(users) OVER (ORDER BY step_order), 0) AS conversion_from_start
            FROM funnel_metrics
            ORDER BY step_order
            """
        )

        connection.sql("DROP TABLE IF EXISTS message_engagement_metrics")
        connection.sql(
            """
            CREATE TABLE message_engagement_metrics AS
            SELECT
                DATE(created_at) AS metric_date,
                COUNT(*) AS messages_sent,
                SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END) AS delivered_messages,
                SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) AS opened_messages,
                SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) AS clicked_messages,
                SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) AS delivery_rate,
                SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS open_rate,
                SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS click_to_open_rate
            FROM stg_messages
            GROUP BY 1
            ORDER BY metric_date
            """
        )

        connection.sql("DROP TABLE IF EXISTS notification_engagement_metrics")
        connection.sql(
            """
            CREATE TABLE notification_engagement_metrics AS
            SELECT
                DATE(sent_at) AS metric_date,
                COUNT(*) AS notifications_sent,
                SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) AS notifications_opened,
                SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) AS notification_open_rate
            FROM stg_notifications
            GROUP BY 1
            ORDER BY metric_date
            """
        )

        connection.sql("DROP TABLE IF EXISTS safety_metrics")
        connection.sql(
            """
            CREATE TABLE safety_metrics AS
            WITH spam AS (
                SELECT DATE(flagged_at) AS metric_date, COUNT(*) AS spam_flags, AVG(risk_score) AS avg_risk_score
                FROM stg_spam_flags
                GROUP BY 1
            ),
            reports AS (
                SELECT
                    DATE(reported_at) AS metric_date,
                    COUNT(*) AS user_reports,
                    SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) AS severe_reports
                FROM stg_user_reports
                GROUP BY 1
            ),
            requests AS (
                SELECT
                    DATE(created_at) AS metric_date,
                    SUM(CASE WHEN risk_score > 0.8 THEN 1 ELSE 0 END) AS suspicious_friend_requests
                FROM stg_friend_requests
                GROUP BY 1
            )
            SELECT
                COALESCE(spam.metric_date, reports.metric_date, requests.metric_date) AS metric_date,
                COALESCE(spam.spam_flags, 0) AS spam_flags,
                COALESCE(reports.user_reports, 0) AS user_reports,
                COALESCE(reports.severe_reports, 0) AS severe_reports,
                COALESCE(requests.suspicious_friend_requests, 0) AS suspicious_friend_requests,
                COALESCE(spam.avg_risk_score, 0) * 100.0 AS platform_wide_risk_score
            FROM spam
            FULL OUTER JOIN reports USING(metric_date)
            FULL OUTER JOIN requests USING(metric_date)
            ORDER BY metric_date
            """
        )

        connection.sql("DROP TABLE IF EXISTS crash_metrics")
        connection.sql(
            """
            CREATE TABLE crash_metrics AS
            WITH platform_users AS (
                SELECT platform, COUNT(DISTINCT user_id) AS platform_users
                FROM stg_users
                GROUP BY 1
            )
            SELECT
                DATE(c.crashed_at) AS metric_date,
                c.platform,
                COUNT(*) AS crashes,
                COUNT(*) * 100.0 / NULLIF(MAX(p.platform_users), 0) AS crash_rate
            FROM stg_app_crashes c
            JOIN platform_users p USING(platform)
            GROUP BY 1, 2
            ORDER BY metric_date, platform
            """
        )


if __name__ == "__main__":
    build_metric_tables()
