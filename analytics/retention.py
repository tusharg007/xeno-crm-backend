"""Retention helpers for the Streamlit dashboard and AI copilot."""

from __future__ import annotations

from analytics.metrics import fetch_rows


def cohort_retention_rows():
    return fetch_rows("retention_cohorts")


def retention_explainer() -> str:
    return (
        "D1 retention means the share of users who come back one day after signup. "
        "D7 retention tracks whether a cohort returns within a week. "
        "D30 retention tracks longer-term habit formation."
    )
