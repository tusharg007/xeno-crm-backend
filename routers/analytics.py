"""Analytics API routes for the messaging insights platform."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ai.copilot import answer_analytics_question
from ai.tools import run_sql_query, summarize_dashboard_insights
from analytics.metrics import fetch_rows
from analytics.reports import generate_weekly_report_markdown


router = APIRouter()


@router.get("/overview")
async def analytics_overview():
    return summarize_dashboard_insights()


@router.get("/product-engagement")
async def product_engagement():
    return {
        "messages": fetch_rows("message_engagement"),
        "notifications": fetch_rows("notification_engagement"),
    }


@router.get("/retention-funnel")
async def retention_funnel():
    return {
        "cohorts": fetch_rows("retention_cohorts"),
        "funnel": fetch_rows("funnel_summary"),
    }


@router.get("/feature-adoption")
async def feature_adoption():
    return {"features": fetch_rows("feature_adoption")}


@router.get("/platform-safety")
async def platform_safety():
    return {
        "safety": fetch_rows("safety_summary"),
        "crashes": fetch_rows("crash_summary"),
        "anomalies": fetch_rows("anomalies"),
    }


@router.get("/weekly-report")
async def weekly_report():
    return {"report_markdown": generate_weekly_report_markdown()}


@router.get("/sql")
async def read_only_sql(sql: str = Query(..., description="Read-only SELECT query")):
    try:
        return {"rows": run_sql_query(sql)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/copilot")
async def analytics_copilot(question: str = Query(..., min_length=3)):
    return await answer_analytics_question(question)
