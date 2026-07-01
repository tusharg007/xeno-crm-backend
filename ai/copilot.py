"""Analytics copilot that mixes deterministic routing, retrieval, and optional Groq help."""

from __future__ import annotations

import logging
from textwrap import shorten

from agent.groq_utils import GROQ_UNAVAILABLE_MESSAGE, build_groq_model, retry_async_groq_call
from ai.rag import retrieve_docs
from ai.tools import detect_anomaly, generate_weekly_report, summarize_dashboard_insights
from analytics.funnel import funnel_rows
from analytics.metrics import fetch_rows
from analytics.retention import retention_explainer
from config import settings


logger = logging.getLogger(__name__)


def _rows_to_bullets(rows: list[dict], keys: list[str]) -> str:
    lines = []
    for row in rows[:5]:
        parts = [f"{key}={row.get(key)}" for key in keys]
        lines.append(f"- {', '.join(parts)}")
    return "\n".join(lines) or "- No data available."


def _deterministic_analytics_answer(question: str) -> str | None:
    lowered = question.lower()
    if "weekly report" in lowered:
        return generate_weekly_report()["markdown"]
    if "d7 retention" in lowered:
        rows = fetch_rows("retention_cohorts")[:3]
        return (
            retention_explainer()
            + "\n\nRecent cohorts:\n"
            + _rows_to_bullets(rows, ["cohort_week", "cohort_size", "d7_retention"])
        )
    if "difference between dau and engaged dau" in lowered:
        docs = retrieve_docs("engaged DAU DAU")
        snippet = docs[0].content if docs else "DAU counts everyone with a session. Engaged DAU counts users who also completed a meaningful action."
        return shorten(snippet, width=500, placeholder="...")
    if "why did dau drop" in lowered or "anomaly" in lowered:
        anomalies = detect_anomaly("dau")
        if anomalies:
            row = anomalies[0]
            return (
                f"DAU anomaly on {row['anomaly_date']}: current value {row['current_value']}, "
                f"baseline {row['rolling_mean']:.1f}, change {row['pct_change']:.1f}%. "
                f"{row['explanation']}"
            )
        return "I do not see a recent DAU anomaly in the current synthetic dataset."
    if "highest message growth" in lowered or "message growth" in lowered:
        rows = fetch_rows("weekly_growth_by_country")
        if rows:
            top = rows[0]
            return f"{top['country']} currently has the highest message volume with {int(top['messages_sent'])} messages in the last 7 days."
        return "I do not have weekly geo growth data yet."
    if "low adoption" in lowered or "feature adoption" in lowered:
        rows = sorted(fetch_rows("feature_adoption"), key=lambda row: row["adoption_rate"])
        if rows:
            low = rows[0]
            return f"{low['feature_name']} has the lowest adoption right now at {low['adoption_rate']:.1f}%."
        return "I do not have feature adoption data yet."
    if "spam reports" in lowered or "safety" in lowered:
        rows = detect_anomaly("spam_reports")
        if rows:
            row = rows[0]
            return f"Spam reports are elevated on {row['anomaly_date']}. {row['explanation']}"
        latest = fetch_rows("safety_summary")[:3]
        return "Recent safety metrics:\n" + _rows_to_bullets(latest, ["metric_date", "spam_flags", "user_reports"])
    if "crash rate" in lowered or "highest crash" in lowered:
        rows = fetch_rows("crash_summary")
        if rows:
            top = sorted(rows, key=lambda row: row["crashes"], reverse=True)[0]
            return f"{top['platform']} currently shows the highest crash volume with {int(top['crashes'])} crashes and a {top['crash_rate']:.2f}% crash rate."
        return "I do not have crash metrics yet."
    if "funnel" in lowered:
        rows = funnel_rows()
        return "Current funnel:\n" + _rows_to_bullets(rows, ["step_name", "users", "conversion_from_start"])
    return None


async def answer_analytics_question(question: str) -> dict:
    deterministic = _deterministic_analytics_answer(question)
    context_chunks = retrieve_docs(question)
    context = "\n\n".join(
        f"[{chunk.source}]\n{shorten(chunk.content, width=900, placeholder='...')}"
        for chunk in context_chunks
    )
    if deterministic:
        return {"answer": deterministic, "sources": [chunk.source for chunk in context_chunks]}

    if not settings.GROQ_API_KEY:
        return {
            "answer": (
                "I could not find a deterministic answer for that question and Groq is not configured. "
                "Try asking about DAU, D7 retention, feature adoption, message growth, spam reports, crash rate, or a weekly report."
            ),
            "sources": [chunk.source for chunk in context_chunks],
        }

    prompt = (
        "You are an analytics copilot for a synthetic messaging platform.\n"
        "Use only the provided context. If the answer is not supported, say so clearly.\n\n"
        f"Question:\n{question}\n\n"
        f"Context:\n{context or 'No supporting documentation retrieved.'}"
    )
    try:
        model = build_groq_model(temperature=0.1)
        response = await retry_async_groq_call(lambda: model.ainvoke(prompt), label="analytics copilot")
        return {"answer": response.content, "sources": [chunk.source for chunk in context_chunks]}
    except Exception as exc:
        logger.exception("Analytics copilot fallback triggered: %s", exc)
        return {
            "answer": (
                "I could not complete the Groq-backed explanation right now. "
                "Please try a more specific analytics question such as weekly report, DAU drop, feature adoption, spam reports, or crash rate."
            ),
            "sources": [chunk.source for chunk in context_chunks],
        }
