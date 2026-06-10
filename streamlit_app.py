import os
import time
from datetime import datetime
from uuid import uuid4

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


CRM_BACKEND_URL = os.getenv("CRM_BACKEND_URL", "http://localhost:8000")

st.set_page_config(title="Xeno - StyleHub", layout="wide", page_icon="💙")


def _init_session_state() -> None:
    defaults = {
        "messages": [],
        "session_id": str(uuid4()),
        "segment_preview": None,
        "campaign_draft": None,
        "awaiting_approval": False,
        "pending_segment_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _get_json(path: str, fallback):
    try:
        response = requests.get(f"{CRM_BACKEND_URL}{path}", timeout=8)
        response.raise_for_status()
        return response.json()
    except Exception:
        return fallback


def _post_json(path: str, payload: dict | list | None = None, timeout: int = 15):
    return requests.post(f"{CRM_BACKEND_URL}{path}", json=payload, timeout=timeout)


def _render_suggestions() -> None:
    prompts = [
        "Find women who bought ethnic wear but haven't ordered in 45 days",
        "Show me high-value customers at risk of churning",
        "Find one-time buyers we could convert to loyal customers",
        "Show me all campaign performance",
    ]
    for row_start in range(0, len(prompts), 2):
        cols = st.columns(2)
        for col, prompt in zip(cols, prompts[row_start : row_start + 2]):
            if col.button(prompt, use_container_width=True):
                st.session_state.pending_input = prompt
                st.rerun()


def _sync_agent_state(data: dict) -> None:
    st.session_state.segment_preview = data.get("segment_preview")
    st.session_state.campaign_draft = data.get("campaign_draft")
    st.session_state.awaiting_approval = data.get("awaiting_approval", False)
    st.session_state.pending_segment_id = data.get("pending_segment_id") or st.session_state.get(
        "pending_segment_id"
    )
    st.session_state.session_id = data.get("session_id") or st.session_state.session_id


def _sidebar() -> None:
    st.markdown("## 💙 StyleHub")
    st.caption("Powered by Xeno CRM")
    st.divider()

    overview = _get_json("/customers/stats/overview", {})
    segments = _get_json("/segments", [])
    campaigns_resp = _get_json("/campaigns", {"data": []})
    campaigns = campaigns_resp.get("data", [])

    st.metric("Customers", overview.get("total_customers", 0))
    st.metric("Segments", len(segments) if isinstance(segments, list) else 0)
    st.metric("Campaigns", len(campaigns))

    st.divider()
    with st.expander("Demo Guide", expanded=False):
        steps = [
            "Find women who bought ethnic wear but haven't ordered in 45 days",
            "Draft a monsoon sale message with 20% off",
            "Launch it on WhatsApp",
            "Switch to Analytics tab and watch live updates",
        ]
        for index, step in enumerate(steps, start=1):
            st.markdown(f"{index}.")
            st.code(step)

    st.divider()
    if st.button("🔄 Reset Demo"):
        try:
            response = _post_json("/demo/reset")
            if response.ok:
                st.session_state.messages = []
                st.session_state.segment_preview = None
                st.session_state.campaign_draft = None
                st.session_state.awaiting_approval = False
                st.success("Demo reset.")
            else:
                st.error("Demo reset failed.")
        except Exception as exc:
            st.error(f"Demo reset failed: {exc}")


def _agent_tab() -> None:
    col_chat, col_preview = st.columns([6, 4])

    with col_chat:
        st.subheader("Campaign Agent")

        if not st.session_state.messages:
            _render_suggestions()

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        user_input = st.chat_input("Message Xeno...")
        if not user_input:
            user_input = st.session_state.pop("pending_input", "")

        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("Xeno is thinking..."):
                    try:
                        response = _post_json(
                            "/agent/chat",
                            {
                                "message": user_input,
                                "conversation_history": st.session_state.messages[-10:],
                                "session_id": st.session_state.session_id,
                            },
                            timeout=30,
                        )
                        response.raise_for_status()
                        data = response.json()
                        reply = data.get("response", "")
                        st.markdown(reply)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": reply}
                        )
                        _sync_agent_state(data)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Xeno could not respond: {exc}")

    with col_preview:
        with st.container(border=True):
            st.subheader("Campaign Preview")

            segment_preview = st.session_state.segment_preview
            campaign_draft = st.session_state.campaign_draft
            awaiting_approval = st.session_state.awaiting_approval

            if segment_preview:
                st.metric("Matched customers", segment_preview.get("count", 0))
                if segment_preview.get("filter_summary"):
                    st.caption(segment_preview["filter_summary"])
                if segment_preview.get("sample"):
                    st.dataframe(
                        pd.DataFrame(segment_preview["sample"]),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.caption(
                    "Your audience will appear here once the agent finds matching customers."
                )

            if campaign_draft:
                st.divider()
                variants = campaign_draft.get("variants", [])
                if variants:
                    selected_msg = st.radio(
                        "Message variants:",
                        variants,
                        label_visibility="collapsed",
                    )
                    channel = st.selectbox("Channel", ["WhatsApp", "SMS", "Email"])

                    if awaiting_approval:
                        if st.button(
                            "🚀 Launch Campaign",
                            type="primary",
                            use_container_width=True,
                        ):
                            segment_id = campaign_draft.get(
                                "segment_id"
                            ) or st.session_state.get("pending_segment_id")
                            if segment_id:
                                create_response = _post_json(
                                    "/campaigns/",
                                    {
                                        "name": f"Campaign {datetime.now().strftime('%b %d %H:%M')}",
                                        "segment_id": segment_id,
                                        "message_template": selected_msg,
                                        "channel": channel.lower(),
                                    },
                                )
                                if create_response.ok:
                                    campaign_id = create_response.json()["id"]
                                    launch_response = _post_json(
                                        f"/campaigns/{campaign_id}/launch"
                                    )
                                    if launch_response.ok:
                                        data = launch_response.json()
                                        st.success(
                                            f"Launched to {data['total_queued']} customers. Watch Analytics!"
                                        )
                                        st.session_state.campaign_draft = None
                                        st.session_state.awaiting_approval = False
                                    else:
                                        st.error("Campaign launch failed.")
                                else:
                                    st.error("Campaign creation failed.")
                            else:
                                st.error("No saved segment is ready to launch.")
                    else:
                        st.button(
                            "🚀 Launch Campaign",
                            disabled=True,
                            help="Agent will ask for confirmation first",
                            use_container_width=True,
                        )


def _analytics_tab() -> None:
    try:
        campaigns_resp = requests.get(f"{CRM_BACKEND_URL}/campaigns", timeout=8).json()
        campaigns = campaigns_resp.get("data", [])
        overview = requests.get(
            f"{CRM_BACKEND_URL}/customers/stats/overview",
            timeout=8,
        ).json()
    except Exception as exc:
        st.error(f"Cannot reach backend: {exc}")
        st.stop()

    avg_delivery = (
        sum(c.get("delivery_rate", 0) for c in campaigns) / len(campaigns)
        if campaigns
        else 0
    )
    avg_open = (
        sum(c.get("open_rate", 0) for c in campaigns) / len(campaigns)
        if campaigns
        else 0
    )

    cols = st.columns(4)
    cols[0].metric("Total Customers", overview.get("total_customers", 0))
    cols[1].metric("Campaigns", len(campaigns))
    cols[2].metric("Avg Delivery", f"{round(avg_delivery * 100, 1)}%")
    cols[3].metric("Avg Open", f"{round(avg_open * 100, 1)}%")

    st.divider()
    st.subheader("Campaigns")

    if campaigns:
        df = pd.DataFrame(
            [
                {
                    "Name": campaign["name"],
                    "Channel": campaign["channel"].title(),
                    "Sent": campaign["total_sent"],
                    "Delivered %": f"{round(campaign.get('delivery_rate', 0) * 100, 1)}%",
                    "Opened %": f"{round(campaign.get('open_rate', 0) * 100, 1)}%",
                    "Clicked %": f"{round(campaign.get('click_rate', 0) * 100, 1)}%",
                    "Status": campaign["status"].title(),
                }
                for campaign in campaigns
            ]
        )

        selected = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )

        if selected.selection.rows:
            index = selected.selection.rows[0]
            campaign = campaigns[index]
            st.divider()
            st.subheader(f"Campaign: {campaign['name']}")

            col_funnel, col_donut = st.columns([6, 4])

            with col_funnel:
                fig = go.Figure(
                    go.Funnel(
                        y=["Sent", "Delivered", "Opened", "Clicked"],
                        x=[
                            campaign["total_sent"],
                            campaign["total_delivered"],
                            campaign["total_opened"],
                            campaign["total_clicked"],
                        ],
                        textinfo="value+percent initial",
                        marker_color=["#5B63FE", "#7B82FE", "#9DA3FE", "#BFC2FE"],
                    )
                )
                fig.update_layout(margin=dict(l=0, r=0, t=20, b=0), height=280)
                st.plotly_chart(fig, use_container_width=True)

            with col_donut:
                labels = ["Delivered only", "Opened", "Clicked", "Failed", "In transit"]
                values = [
                    max(0, campaign["total_delivered"] - campaign["total_opened"]),
                    max(0, campaign["total_opened"] - campaign["total_clicked"]),
                    campaign["total_clicked"],
                    campaign["total_failed"],
                    max(
                        0,
                        campaign["total_sent"]
                        - campaign["total_delivered"]
                        - campaign["total_failed"],
                    ),
                ]
                donut = go.Figure(
                    go.Pie(
                        labels=labels,
                        values=values,
                        hole=0.5,
                        marker_colors=[
                            "#5B63FE",
                            "#7B82FE",
                            "#BFC2FE",
                            "#FF6B6B",
                            "#E0E0E0",
                        ],
                    )
                )
                donut.update_layout(margin=dict(l=0, r=0, t=20, b=0), height=280)
                st.plotly_chart(donut, use_container_width=True)
    else:
        st.info("No campaigns yet. Use the AI Agent tab to create and launch one.")

    running = any(c["status"] == "running" for c in campaigns)
    if running:
        st.markdown("🔴 **Live** - refreshing every 4 seconds as deliveries arrive")
        time.sleep(4)
        st.rerun()


_init_session_state()
with st.sidebar:
    _sidebar()

tab1, tab2 = st.tabs(["🤖 AI Campaign Agent", "📊 Analytics"])
with tab1:
    _agent_tab()
with tab2:
    _analytics_tab()
