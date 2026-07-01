"""Funnel helpers for activation and engagement conversion analysis."""

from __future__ import annotations

from analytics.metrics import fetch_rows


def funnel_rows():
    return fetch_rows("funnel_summary")
