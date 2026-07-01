"""Central SQL queries used by APIs, Streamlit, and the AI copilot."""

from __future__ import annotations

from textwrap import dedent


SQL_QUERIES = {
    "executive_overview": dedent(
        """
        WITH base AS (
            SELECT
                (SELECT MAX(metric_date) FROM daily_product_metrics) AS latest_day
        )
        SELECT
            m.metric_date,
            m.dau,
            m.messages_sent,
            m.message_delivery_rate,
            m.notification_open_rate,
            m.spam_reports,
            m.crash_rate
        FROM daily_product_metrics m
        CROSS JOIN base
        WHERE m.metric_date = base.latest_day
        """
    ),
    "weekly_growth_by_country": dedent(
        """
        SELECT
            country,
            SUM(messages_sent) AS messages_sent,
            SUM(active_users) AS active_users
        FROM geo_daily_metrics
        WHERE metric_date >= CURRENT_DATE - INTERVAL 7 DAY
        GROUP BY country
        ORDER BY messages_sent DESC
        LIMIT 10
        """
    ),
    "feature_adoption": dedent(
        """
        SELECT
            feature_name,
            unique_users,
            adoption_rate,
            avg_events_per_user
        FROM feature_adoption_metrics
        ORDER BY adoption_rate DESC
        """
    ),
    "retention_cohorts": dedent(
        """
        SELECT
            cohort_week,
            cohort_size,
            d1_retention,
            d7_retention,
            d30_retention
        FROM retention_cohorts
        ORDER BY cohort_week DESC
        LIMIT 12
        """
    ),
    "funnel_summary": dedent(
        """
        SELECT
            step_name,
            users,
            conversion_from_previous,
            conversion_from_start
        FROM funnel_metrics
        ORDER BY step_order
        """
    ),
    "message_engagement": dedent(
        """
        SELECT
            metric_date,
            messages_sent,
            delivered_messages,
            opened_messages,
            clicked_messages,
            delivery_rate,
            open_rate,
            click_to_open_rate
        FROM message_engagement_metrics
        ORDER BY metric_date DESC
        LIMIT 30
        """
    ),
    "notification_engagement": dedent(
        """
        SELECT
            metric_date,
            notifications_sent,
            notifications_opened,
            notification_open_rate
        FROM notification_engagement_metrics
        ORDER BY metric_date DESC
        LIMIT 30
        """
    ),
    "safety_summary": dedent(
        """
        SELECT
            metric_date,
            spam_flags,
            user_reports,
            severe_reports,
            suspicious_friend_requests,
            platform_wide_risk_score
        FROM safety_metrics
        ORDER BY metric_date DESC
        LIMIT 30
        """
    ),
    "crash_summary": dedent(
        """
        SELECT
            metric_date,
            platform,
            crashes,
            crash_rate
        FROM crash_metrics
        ORDER BY metric_date DESC, crashes DESC
        LIMIT 60
        """
    ),
    "anomalies": dedent(
        """
        SELECT
            metric_name,
            anomaly_date,
            current_value,
            rolling_mean,
            pct_change,
            severity,
            explanation
        FROM anomaly_alerts
        ORDER BY anomaly_date DESC, ABS(pct_change) DESC
        LIMIT 25
        """
    ),
}
