import os
import time
from datetime import datetime
from uuid import uuid4

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


CRM_BACKEND_URL = os.getenv("CRM_BACKEND_URL", "http://localhost:8000")
BACKEND_TIMEOUT_SECONDS = int(os.getenv("BACKEND_TIMEOUT_SECONDS", "65"))

st.set_page_config(
    page_title="Xeno - StyleHub",
    layout="wide",
    page_icon=":blue_heart:",
)

st.markdown(
    """
<style>
.block-container { padding-top: 1.5rem !important; }
[data-testid="stSidebar"] { border-right: 1px solid rgba(0,0,0,0.08); }
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
[data-testid="stMetric"] {
    background: rgba(91,99,254,0.04);
    border: 1px solid rgba(91,99,254,0.12);
    border-radius: 10px;
    padding: 1rem;
}
[data-testid="stMetricValue"] { font-size: 1.75rem !important; }
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
.stButton > button[kind="primary"] {
    background: #5B63FE !important;
    border: none !important;
    color: white !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
}
</style>
""",
    unsafe_allow_html=True,
)


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


def _request_backend(method: str, path: str, timeout: int = BACKEND_TIMEOUT_SECONDS, **kwargs):
    last_error = None
    for attempt in range(2):
        try:
            response = requests.request(
                method,
                f"{CRM_BACKEND_URL}{path}",
                timeout=timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(2)
    raise last_error


def _get_json(path: str, fallback):
    try:
        return _request_backend("GET", path).json()
    except Exception:
        return fallback


def _post_json(path: str, payload: dict | list | None = None, timeout: int = 90):
    return _request_backend("POST", path, json=payload, timeout=timeout)


def _resolve_segment_id(campaign_draft: dict | None) -> str | None:
    if campaign_draft and campaign_draft.get("segment_id"):
        return campaign_draft["segment_id"]
    if st.session_state.get("pending_segment_id"):
        return st.session_state.pending_segment_id

    segments = _get_json("/segments", [])
    if not isinstance(segments, list) or not segments:
        return None

    segment_name = (campaign_draft or {}).get("segment_name")
    if segment_name:
        for segment in segments:
            if segment.get("name") == segment_name:
                return segment.get("id")

    return segments[0].get("id")


def _render_suggestions() -> None:
    st.markdown(
        """
    <div style="text-align:center;padding:2rem 1rem 1.5rem;">
        <div style="font-size:32px;margin-bottom:8px;">&#128153;</div>
        <div style="font-size:18px;font-weight:600;margin-bottom:6px;">Hi, I'm Xeno</div>
        <div style="font-size:14px;color:#888;margin-bottom:1.5rem;max-width:320px;margin-left:auto;margin-right:auto;">
            Your AI campaign manager for StyleHub.
            Describe who you want to reach; I'll handle the rest.
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    prompt_pairs = [
        (
            "Women inactive 45+ days",
            "Find women who bought ethnic wear but haven't ordered in 45 days",
        ),
        ("High-value at-risk", "Show me high-value customers at risk of churning"),
        (
            "Win back one-time buyers",
            "Find one-time buyers we could convert to loyal customers",
        ),
        ("Campaign performance", "Show me all campaign performance"),
    ]
    cols = st.columns(2)
    for index, (label, full_prompt) in enumerate(prompt_pairs):
        if cols[index % 2].button(label, key=f"starter_{index}", use_container_width=True):
            st.session_state.pending_input = full_prompt
            st.rerun()


def _sync_agent_state(data: dict) -> None:
    st.session_state.segment_preview = data.get("segment_preview")
    st.session_state.campaign_draft = data.get("campaign_draft")
    st.session_state.awaiting_approval = data.get("awaiting_approval", False)
    segment_id = (
        data.get("pending_segment_id")
        or (data.get("campaign_draft") or {}).get("segment_id")
        or st.session_state.get("pending_segment_id")
    )
    if segment_id and st.session_state.campaign_draft is not None:
        st.session_state.campaign_draft["segment_id"] = segment_id
    st.session_state.pending_segment_id = segment_id
    st.session_state.session_id = data.get("session_id") or st.session_state.session_id


def _sidebar_legacy() -> None:
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


def _agent_tab_legacy() -> None:
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
                            segment_id = _resolve_segment_id(campaign_draft)
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
        campaigns_resp = _request_backend("GET", "/campaigns").json()
        campaigns = campaigns_resp.get("data", [])
        overview = _request_backend("GET", "/customers/stats/overview").json()
    except Exception as exc:
        st.error(
            "Cannot reach backend yet. Render free services can take about a minute "
            f"to wake up; refresh once the backend is warm. Details: {exc}"
        )
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


def _sidebar() -> None:
    st.markdown(
        """
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
        <div style="width:32px;height:32px;background:#5B63FE;border-radius:8px;
                    display:flex;align-items:center;justify-content:center;">
            <span style="color:white;font-size:16px;font-weight:700;">S</span>
        </div>
        <div>
            <div style="font-weight:600;font-size:15px;line-height:1.2;">StyleHub</div>
            <div style="font-size:11px;color:#888;line-height:1.2;">CRM &middot; Powered by Xeno</div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.divider()

    overview = _get_json("/customers/stats/overview", {})
    segments = _get_json("/segments", [])
    campaigns_resp = _get_json("/campaigns", {"data": []})
    campaigns = campaigns_resp.get("data", [])
    segment_count = len(segments) if isinstance(segments, list) else len(segments.get("data", []))
    avg_open = (
        sum(c.get("open_rate", 0) for c in campaigns) / len(campaigns) * 100
        if campaigns
        else 0
    )

    col1, col2 = st.columns(2)
    col1.metric("Customers", f"{overview.get('total_customers', 0):,}")
    col2.metric("Segments", segment_count)
    col1.metric("Campaigns", len(campaigns))
    col2.metric("Avg open", f"{avg_open:.1f}%")

    st.divider()
    if overview.get("total_customers", 0) > 0:
        st.markdown("**Customer health**")
        total = max(overview.get("total_customers", 1), 1)

        def rfm_bar(label: str, count: int, color: str) -> None:
            pct = count / total * 100
            st.markdown(
                f"""
            <div style="margin-bottom:8px;">
                <div style="display:flex;justify-content:space-between;
                            font-size:12px;margin-bottom:3px;">
                    <span>{label}</span>
                    <span style="color:#888;">{count} &middot; {pct:.0f}%</span>
                </div>
                <div style="background:#f0f0f0;border-radius:4px;height:6px;">
                    <div style="width:{min(pct, 100):.1f}%;background:{color};
                                border-radius:4px;height:6px;"></div>
                </div>
            </div>""",
                unsafe_allow_html=True,
            )

        rfm_bar("Loyal", overview.get("loyal_count", 0), "#5B63FE")
        rfm_bar("At-risk", overview.get("at_risk_count", 0), "#F59E0B")
        rfm_bar("Lapsed", overview.get("lapsed_count", 0), "#EF4444")

    st.divider()
    with st.expander("Demo guide", expanded=False):
        steps = [
            ("1", "Find women who bought ethnic wear but haven't ordered in 45 days"),
            ("2", "Draft a monsoon sale message with 20% off"),
            ("3", "Launch it on WhatsApp"),
            ("4", "Switch to Analytics and watch live updates"),
        ]
        for num, text in steps:
            st.markdown(
                f"""
            <div style="display:flex;gap:8px;align-items:flex-start;
                        margin-bottom:8px;font-size:13px;">
                <span style="background:#5B63FE;color:white;border-radius:50%;
                             width:18px;height:18px;display:flex;align-items:center;
                             justify-content:center;font-size:10px;flex-shrink:0;
                             margin-top:1px;">{num}</span>
                <code style="background:#f5f5f5;padding:4px 8px;border-radius:6px;
                             font-size:12px;line-height:1.4;">{text}</code>
            </div>""",
                unsafe_allow_html=True,
            )

    st.divider()
    if st.button("Reset demo", use_container_width=True):
        try:
            response = _post_json("/demo/reset")
            if response.ok:
                st.session_state.messages = []
                st.session_state.segment_preview = None
                st.session_state.campaign_draft = None
                st.session_state.awaiting_approval = False
                st.success("Demo reset.")
                st.rerun()
            else:
                st.error("Reset failed.")
        except Exception:
            st.error("Cannot reach backend.")


def _agent_tab() -> None:
    col_chat, col_preview = st.columns([6, 4])

    with col_chat:
        st.subheader("Campaign Agent")

        if not st.session_state.get("messages"):
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
        st.markdown(
            """
        <div style="background:rgba(91,99,254,0.03);
                    border:1px solid rgba(91,99,254,0.12);
                    border-radius:12px;padding:1rem 1.25rem;min-height:220px;">
        """,
            unsafe_allow_html=True,
        )
        st.markdown("**Campaign preview**")

        seg_prev = st.session_state.get("segment_preview")
        camp_draft = st.session_state.get("campaign_draft")
        awaiting = st.session_state.get("awaiting_approval", False)

        if seg_prev:
            count = seg_prev.get("count", 0)
            summary = seg_prev.get("filter_summary", "")
            st.markdown(
                f"""
            <div style="margin:0.75rem 0;">
                <span style="font-size:2rem;font-weight:700;color:#5B63FE;">{count:,}</span>
                <span style="font-size:14px;color:#888;margin-left:8px;">customers matched</span>
            </div>
            <div style="font-size:13px;color:#555;margin-bottom:1rem;
                        line-height:1.5;">{summary}</div>
            """,
                unsafe_allow_html=True,
            )

            for customer in seg_prev.get("sample", [])[:3]:
                days = customer.get("last_order_days_ago")
                days_str = f"{days}d ago" if days is not None else "never"
                spend = customer.get("total_spend", 0)
                st.markdown(
                    f"""
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:6px 0;border-bottom:1px solid rgba(0,0,0,0.06);
                            font-size:13px;">
                    <div>
                        <div style="font-weight:500;">{customer.get("name", "")}</div>
                        <div style="color:#888;font-size:11px;">
                            {customer.get("city", "")} &middot; Last order: {days_str}
                        </div>
                    </div>
                    <div style="color:#5B63FE;font-weight:500;">Rs {spend:,.0f}</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                """
            <div style="color:#bbb;font-size:13px;margin-top:1rem;line-height:1.6;">
                Your matched audience will appear here once
                the agent finds customers matching your description.
            </div>
            """,
                unsafe_allow_html=True,
            )

        if camp_draft:
            st.divider()
            variants = camp_draft.get("variants", [])
            if variants:
                selected_msg = st.radio(
                    "Message variants:",
                    variants,
                    key="msg_variant",
                    label_visibility="collapsed",
                )
                channel = st.selectbox("Channel", ["WhatsApp", "SMS", "Email"])
                if awaiting:
                    if st.button("Launch campaign", type="primary", use_container_width=True):
                        segment_id = _resolve_segment_id(camp_draft)
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
                        "Launch campaign",
                        disabled=True,
                        help="Agent will ask for confirmation first",
                        use_container_width=True,
                    )

        st.markdown("</div>", unsafe_allow_html=True)


_init_session_state()
with st.sidebar:
    _sidebar()

tab1, tab2 = st.tabs(["🤖 AI Campaign Agent", "📊 Analytics"])
with tab1:
    _agent_tab()
with tab2:
    _analytics_tab()
