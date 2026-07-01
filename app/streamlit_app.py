"""Streamlit dashboard for the global messaging analytics platform."""

from __future__ import annotations

import asyncio

import pandas as pd
import plotly.express as px
import streamlit as st

from ai.copilot import answer_analytics_question
from analytics.metrics import dashboard_snapshot, fetch_rows
from analytics.reports import generate_weekly_report_markdown


st.set_page_config(page_title="Messaging Product Analytics", layout="wide")


def _safe_df(query_name: str) -> pd.DataFrame:
    return pd.DataFrame(fetch_rows(query_name))


def _run_copilot_sync(prompt: str) -> dict:
    try:
        return asyncio.run(answer_analytics_question(prompt))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(answer_analytics_question(prompt))
        finally:
            loop.close()


def executive_page():
    st.subheader("Executive Overview")
    snapshot = dashboard_snapshot()
    overview = snapshot.get("overview", {})
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("DAU", int(overview.get("dau", 0)))
    col2.metric("Messages sent", int(overview.get("messages_sent", 0)))
    col3.metric("Delivery rate", f"{float(overview.get('message_delivery_rate', 0)):.1f}%")
    col4.metric("Crash rate", f"{float(overview.get('crash_rate', 0)):.2f}%")

    left, right = st.columns([2, 1])
    with left:
        weekly = pd.DataFrame(snapshot.get("weekly_growth_by_country", []))
        if not weekly.empty:
            st.plotly_chart(
                px.bar(weekly, x="country", y="messages_sent", title="Weekly message growth by country"),
                use_container_width=True,
            )
    with right:
        anomalies = snapshot.get("anomalies", [])
        st.markdown("**Anomaly watchlist**")
        if anomalies:
            for row in anomalies[:6]:
                st.warning(f"{row['metric_name']} on {row['anomaly_date']}: {row['explanation']}")
        else:
            st.success("No major anomalies in the current synthetic window.")


def product_engagement_page():
    st.subheader("Product Engagement")
    messages_df = _safe_df("message_engagement")
    notifications_df = _safe_df("notification_engagement")
    if not messages_df.empty:
        st.plotly_chart(
            px.line(messages_df, x="metric_date", y=["delivery_rate", "open_rate", "click_to_open_rate"], title="Message engagement rates"),
            use_container_width=True,
        )
    if not notifications_df.empty:
        st.plotly_chart(
            px.line(notifications_df, x="metric_date", y="notification_open_rate", title="Notification open rate"),
            use_container_width=True,
        )


def retention_page():
    st.subheader("Retention & Funnel")
    cohorts = _safe_df("retention_cohorts")
    funnel = _safe_df("funnel_summary")
    left, right = st.columns(2)
    with left:
        if not cohorts.empty:
            st.dataframe(cohorts, use_container_width=True, hide_index=True)
    with right:
        if not funnel.empty:
            st.plotly_chart(
                px.funnel(funnel, x="users", y="step_name", title="Activation funnel"),
                use_container_width=True,
            )


def feature_page():
    st.subheader("Feature Adoption")
    features = _safe_df("feature_adoption")
    if not features.empty:
        st.plotly_chart(
            px.bar(features, x="feature_name", y="adoption_rate", title="Feature adoption rate"),
            use_container_width=True,
        )
        st.dataframe(features, use_container_width=True, hide_index=True)


def safety_page():
    st.subheader("Platform Safety")
    safety = _safe_df("safety_summary")
    crashes = _safe_df("crash_summary")
    anomalies = _safe_df("anomalies")
    if not safety.empty:
        st.plotly_chart(
            px.line(safety, x="metric_date", y=["spam_flags", "user_reports", "suspicious_friend_requests"], title="Safety events over time"),
            use_container_width=True,
        )
    if not crashes.empty:
        st.plotly_chart(
            px.bar(crashes, x="metric_date", y="crashes", color="platform", title="Crash volume by platform"),
            use_container_width=True,
        )
    if not anomalies.empty:
        st.dataframe(anomalies, use_container_width=True, hide_index=True)


def copilot_page():
    st.subheader("AI Insights Copilot")
    st.caption("Ask product, growth, retention, or safety questions against the synthetic analytics dataset.")
    prompt = st.text_input(
        "Ask a question",
        placeholder="Why did DAU drop this week?",
        key="copilot_prompt",
    )
    if prompt:
        try:
            payload = _run_copilot_sync(prompt)
            st.markdown(payload.get("answer", "No answer returned."))
            sources = payload.get("sources") or []
            if sources:
                st.caption("Sources: " + ", ".join(sources))
        except Exception as exc:
            st.error(f"Could not generate an analytics answer: {exc}")

    with st.expander("Example questions"):
        st.markdown(
            "- Why did DAU drop this week?\n"
            "- Which country has highest message growth?\n"
            "- Which feature has the lowest adoption?\n"
            "- Are spam reports increasing in any region?\n"
            "- Which platform has the highest crash rate?\n"
            "- Generate a weekly product performance report."
        )
    with st.expander("Current weekly report"):
        st.markdown(generate_weekly_report_markdown())


def main():
    st.title("Global Messaging Product Analytics & AI Insights")
    st.write(
        "A simulated large-scale analytics platform for a global messaging and social app. "
        "This demo focuses on product engagement, retention, feature adoption, safety, and AI-assisted analytics."
    )

    page = st.sidebar.radio(
        "Navigate",
        [
            "Executive Overview",
            "Product Engagement",
            "Retention & Funnel",
            "Feature Adoption",
            "Platform Safety",
            "AI Insights Copilot",
        ],
    )
    if page == "Executive Overview":
        executive_page()
    elif page == "Product Engagement":
        product_engagement_page()
    elif page == "Retention & Funnel":
        retention_page()
    elif page == "Feature Adoption":
        feature_page()
    elif page == "Platform Safety":
        safety_page()
    else:
        copilot_page()


if __name__ == "__main__":
    main()
