"""Load raw CSVs into DuckDB and create cleaned staging tables."""

from __future__ import annotations

from pathlib import Path

from analytics.duckdb_client import analytics_connection
from config import resolve_path, settings


RAW_TABLES = {
    "users": "users.csv",
    "sessions": "sessions.csv",
    "messages": "messages.csv",
    "group_chats": "group_chats.csv",
    "friend_requests": "friend_requests.csv",
    "notifications": "notifications.csv",
    "feature_usage": "feature_usage.csv",
    "user_reports": "user_reports.csv",
    "spam_flags": "spam_flags.csv",
    "app_crashes": "app_crashes.csv",
}


def raw_dir() -> Path:
    return resolve_path(settings.RAW_DATA_DIR)


def run_etl() -> None:
    with analytics_connection() as connection:
        for table_name, file_name in RAW_TABLES.items():
            file_path = raw_dir() / file_name
            connection.sql(f"DROP TABLE IF EXISTS raw_{table_name}")
            connection.sql(
                f"""
                CREATE TABLE raw_{table_name} AS
                SELECT * FROM read_csv_auto('{file_path.as_posix()}', HEADER=TRUE)
                """
            )

        connection.sql("DROP TABLE IF EXISTS stg_users")
        connection.sql(
            """
            CREATE TABLE stg_users AS
            SELECT
                user_id,
                CAST(signup_at AS TIMESTAMP) AS signup_at,
                country,
                city,
                platform,
                device_type,
                app_version,
                CAST(is_premium AS BOOLEAN) AS is_premium,
                acquisition_channel,
                persona,
                age_bucket
            FROM raw_users
            """
        )
        connection.sql("DROP TABLE IF EXISTS stg_sessions")
        connection.sql(
            """
            CREATE TABLE stg_sessions AS
            SELECT
                session_id,
                user_id,
                CAST(started_at AS TIMESTAMP) AS started_at,
                CAST(ended_at AS TIMESTAMP) AS ended_at,
                CAST(session_minutes AS DOUBLE) AS session_minutes,
                country,
                city,
                platform,
                app_version
            FROM raw_sessions
            """
        )
        connection.sql("DROP TABLE IF EXISTS stg_messages")
        connection.sql(
            """
            CREATE TABLE stg_messages AS
            SELECT
                event_id,
                message_id,
                sender_user_id,
                receiver_user_id,
                session_id,
                message_type,
                CAST(created_at AS TIMESTAMP) AS created_at,
                country,
                city,
                platform,
                CAST(is_spam AS BOOLEAN) AS is_spam,
                CASE WHEN delivered_at = '' THEN NULL ELSE CAST(delivered_at AS TIMESTAMP) END AS delivered_at,
                CASE WHEN opened_at = '' THEN NULL ELSE CAST(opened_at AS TIMESTAMP) END AS opened_at,
                CASE WHEN clicked_at = '' THEN NULL ELSE CAST(clicked_at AS TIMESTAMP) END AS clicked_at
            FROM raw_messages
            """
        )
        connection.sql("DROP TABLE IF EXISTS stg_notifications")
        connection.sql(
            """
            CREATE TABLE stg_notifications AS
            SELECT
                notification_id,
                user_id,
                notification_type,
                CAST(sent_at AS TIMESTAMP) AS sent_at,
                CASE WHEN opened_at = '' THEN NULL ELSE CAST(opened_at AS TIMESTAMP) END AS opened_at,
                country,
                platform,
                session_id
            FROM raw_notifications
            """
        )
        connection.sql("DROP TABLE IF EXISTS stg_feature_usage")
        connection.sql(
            """
            CREATE TABLE stg_feature_usage AS
            SELECT
                event_id,
                user_id,
                feature_name,
                CAST(used_at AS TIMESTAMP) AS used_at,
                country,
                platform,
                session_id,
                event_type
            FROM raw_feature_usage
            """
        )
        connection.sql("DROP TABLE IF EXISTS stg_friend_requests")
        connection.sql(
            """
            CREATE TABLE stg_friend_requests AS
            SELECT
                request_id,
                sender_user_id,
                receiver_user_id,
                CAST(created_at AS TIMESTAMP) AS created_at,
                CASE WHEN accepted_at = '' THEN NULL ELSE CAST(accepted_at AS TIMESTAMP) END AS accepted_at,
                country,
                platform,
                CAST(risk_score AS DOUBLE) AS risk_score
            FROM raw_friend_requests
            """
        )
        connection.sql("DROP TABLE IF EXISTS stg_user_reports")
        connection.sql(
            """
            CREATE TABLE stg_user_reports AS
            SELECT
                report_id,
                user_id,
                message_id,
                report_reason,
                CAST(reported_at AS TIMESTAMP) AS reported_at,
                country,
                platform,
                severity
            FROM raw_user_reports
            """
        )
        connection.sql("DROP TABLE IF EXISTS stg_spam_flags")
        connection.sql(
            """
            CREATE TABLE stg_spam_flags AS
            SELECT
                flag_id,
                message_id,
                user_id,
                CAST(flagged_at AS TIMESTAMP) AS flagged_at,
                CAST(risk_score AS DOUBLE) AS risk_score,
                country,
                platform,
                CAST(is_spam AS BOOLEAN) AS is_spam
            FROM raw_spam_flags
            """
        )
        connection.sql("DROP TABLE IF EXISTS stg_app_crashes")
        connection.sql(
            """
            CREATE TABLE stg_app_crashes AS
            SELECT
                crash_id,
                user_id,
                CAST(crashed_at AS TIMESTAMP) AS crashed_at,
                platform,
                country,
                city,
                app_version,
                error_type,
                severity
            FROM raw_app_crashes
            """
        )


if __name__ == "__main__":
    run_etl()
