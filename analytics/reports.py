"""Markdown report generation for weekly product summaries."""

from __future__ import annotations

from datetime import datetime

from analytics.metrics import dashboard_snapshot, fetch_rows


def generate_weekly_report_markdown() -> str:
    snapshot = dashboard_snapshot()
    overview = snapshot.get("overview", {})
    anomalies = snapshot.get("anomalies", [])[:5]
    growth_rows = snapshot.get("weekly_growth_by_country", [])[:5]
    features = snapshot.get("feature_adoption", [])[:5]
    safety_rows = fetch_rows("safety_summary")[:7]

    anomaly_lines = "\n".join(
        f"- **{row['metric_name']}** on {row['anomaly_date']}: {row['explanation']}"
        for row in anomalies
    ) or "- No major anomalies detected this week."
    growth_lines = "\n".join(
        f"- {row['country']}: {int(row['messages_sent'])} messages"
        for row in growth_rows
    ) or "- No geo growth data yet."
    feature_lines = "\n".join(
        f"- {row['feature_name']}: {row['adoption_rate']:.1f}% adoption"
        for row in features
    ) or "- No feature adoption data yet."
    safety_lines = "\n".join(
        f"- {row['metric_date']}: {int(row['spam_flags'])} spam flags, {int(row['user_reports'])} user reports"
        for row in safety_rows[:3]
    ) or "- No safety metrics yet."

    return f"""# Weekly Product Performance Report

Generated on {datetime.utcnow():%Y-%m-%d %H:%M UTC}

## Executive summary
- DAU: {int(overview.get('dau', 0))}
- Messages sent: {int(overview.get('messages_sent', 0))}
- Message delivery rate: {float(overview.get('message_delivery_rate', 0)):.1f}%
- Notification open rate: {float(overview.get('notification_open_rate', 0)):.1f}%
- Spam reports: {int(overview.get('spam_reports', 0))}
- Crash rate: {float(overview.get('crash_rate', 0)):.2f}%

## Top growth markets
{growth_lines}

## Feature adoption highlights
{feature_lines}

## Safety and trust signals
{safety_lines}

## Anomaly watchlist
{anomaly_lines}
"""
