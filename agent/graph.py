"""
LangGraph campaign agent for Xeno Mini CRM.

Architecture:
  StateGraph with two nodes — agent (ReAct reasoning loop) and tools
  (executes tool calls). The graph cycles agent → tools → agent until
  the model produces a response with no tool calls, then exits to END.

HITL approval pattern:
  Rather than a separate approval node or complex branching, the agent
  embeds a signal token "AWAITING_APPROVAL:[segment_id]" in its text
  response when it wants human confirmation before launching. The agent_node
  parses this signal, sets awaiting_approval=True in state, and stores the
  segment_id as pending_segment_id. The frontend surfaces an approval card.
  launch_campaign is never called until the marketer explicitly confirms.

Session memory:
  _sessions dict (module-level) maps session_id → AgentState, persisting
  context between HTTP requests. In production this would be Redis or
  DynamoDB; for this scope an in-memory dict is sufficient.
"""

import json
import logging
import operator
import re
from datetime import datetime
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from sqlalchemy import desc, func, select

from agent.groq_utils import GROQ_UNAVAILABLE_MESSAGE, build_groq_model, retry_async_groq_call
from agent.tools import CATEGORY_ALIASES, get_tools
from config import settings
from database import SessionLocal
from models import Campaign, Customer, Journey, Message, Order, Segment
from routers.segments import execute_segment_filter


logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    segment_preview: Optional[dict]
    campaign_draft: Optional[dict]
    awaiting_approval: bool
    pending_segment_id: Optional[str]
    final_response: str
    session_id: str


SYSTEM_PROMPT = """You are Xeno, an AI campaign manager for StyleHub, an Indian fashion brand.
You help marketers reach the right customers with the right message.

YOUR EXACT WORKFLOW — follow this sequence every time:

Step 1 — Find the audience
When asked to find, target, or reach any customers:
  Call query_customers_by_filters with the relevant parameters.
  Present the count and sample: "I found [N] customers matching that profile.
  Here's a sample: [list 3 names with city and days since last order].
  Want me to save this audience and draft a message?"

Step 2 — Save the segment
When the marketer confirms yes:
  Call create_segment to save the audience.
  Remember the returned segment_id — you will need it for launch.

Step 3 — Draft the message
  Call draft_campaign_message with a clear segment_description and the offer.
  Present all 3 variants. Ask which the marketer prefers or if they want changes.

Step 4 — Present for approval
  Show a clear campaign summary with: audience name, count, selected message, channel.
  End your response with EXACTLY this line (no extra text after it):
  AWAITING_APPROVAL:[the segment_id from step 2]
  Do NOT call launch_campaign yet.

Step 5 — Launch on approval
  When the marketer says yes / launch / go / send / approved / do it:
  Call launch_campaign using the pending_segment_id from step 2.
  Confirm with: "Launched [campaign name] to [N] customers on [channel]. Check Analytics."

Step 6 — Analytics
  When asked about stats or performance: call get_campaign_analytics.
  Present numbers clearly with context.
  When asked about revenue, ROI, orders generated, or attribution:
  use get_campaign_analytics and highlight the attributed_orders and
  attributed_revenue fields.

ACCURACY RULES:
For category, product, gender buying-pattern, or "what are men/women buying"
analytics questions:
  Call get_category_insights first.
  Use only categories, counts, and spend returned by tools.
  Never guess from retail common sense.
  Never invent categories such as "Western wear" unless the tool returned them.
  If a tool returns zero results, say zero and list the valid categories from the tool.

For "find customers/men/women who bought [category]" audience questions:
  Call query_customers_by_filters with gender/category filters.
  Return the exact customer count and sample from that tool.
  Ask whether to save the audience and draft a message.

When answering audience counts:
  Use the exact count from the tool result.
  Do not remove or add sample customers based on assumptions.
  Do not mention extra people who are not present in the tool output.

TONE RULES:
Be specific — say "I found 187 customers" not "I found some customers".
Format all responses in clean markdown. Be concise."""


# In-memory session store: maps session_id (str) -> persisted AgentState dict.
# Persists context (pending_segment_id, awaiting_approval, message history)
# between sequential HTTP requests from the same frontend session.
# Module-level so it survives across requests within the same process.
# At production scale: replace with Redis HSET with TTL.
_sessions: dict[str, dict] = {}


def _fallback_response(state: AgentState) -> dict:
    return {
        "messages": [AIMessage(content="Groq is not configured yet. Add GROQ_API_KEY to .env to use the AI campaign manager.")],
        "final_response": "Groq is not configured yet. Add `GROQ_API_KEY` to `.env` to use the AI campaign manager.",
        "awaiting_approval": False,
    }


def _normalize_gender(text: str) -> str | None:
    lowered = text.lower()
    if any(word in lowered for word in [" men", "men ", "male", " man "]):
        return "M"
    if any(word in lowered for word in [" women", "women ", "female", " woman "]):
        return "F"
    return None


def _normalize_category_from_text(text: str) -> str | None:
    lowered = text.lower()
    for alias, category in CATEGORY_ALIASES.items():
        if alias in lowered:
            return category
    return None


def _sample_customers(customer_ids: list[str], db) -> list[dict]:
    if not customer_ids:
        return []
    now = datetime.utcnow()
    customers = db.scalars(
        select(Customer).where(Customer.id.in_(customer_ids)).limit(5)
    ).all()
    return [
        {
            "name": customer.name,
            "city": customer.city,
            "last_order_days_ago": (now - customer.last_order_date).days
            if customer.last_order_date
            else None,
            "total_spend": round(customer.total_spend, 0),
        }
        for customer in customers
    ]


def _format_customer_sample(sample: list[dict]) -> str:
    lines = []
    for customer in sample[:3]:
        days = customer.get("last_order_days_ago")
        days_text = f"{days} days since last order" if days is not None else "no orders yet"
        lines.append(f"* {customer['name']} ({customer['city']}, {days_text})")
    return "\n".join(lines)


def _segment_preview_response(filter_rules: dict, db) -> dict:
    customer_ids = execute_segment_filter(filter_rules, db)
    sample = _sample_customers(customer_ids, db)
    preview = {
        "count": len(customer_ids),
        "sample": sample,
        "filter_rules": filter_rules,
        "filter_summary": f"Matched customers using filters: {filter_rules}.",
    }
    if not customer_ids:
        response = "I found 0 customers matching that profile. Try relaxing the filters."
    else:
        response = (
            f"I found {len(customer_ids)} customers matching that profile.\n"
            "Here's a sample:\n"
            f"{_format_customer_sample(sample)}\n\n"
            "Want me to save this audience and draft a message?"
        )
    return {
        "response": response,
        "segment_preview": preview,
        "campaign_draft": None,
        "awaiting_approval": False,
        "pending_segment_id": None,
    }


def _category_insights_response(gender: str | None, db) -> dict:
    query = (
        db.query(
            Order.category.label("category"),
            func.count(Order.id).label("order_count"),
            func.count(func.distinct(Customer.id)).label("customer_count"),
            func.round(func.sum(Order.amount), 2).label("total_spend"),
        )
        .join(Customer, Customer.id == Order.customer_id)
    )
    if gender:
        query = query.filter(Customer.gender == gender)
    rows = query.group_by(Order.category).order_by(func.count(Order.id).desc()).all()
    audience = "Men" if gender == "M" else "Women" if gender == "F" else "Customers"
    if not rows:
        response = f"{audience} have no orders yet."
    else:
        lines = [
            f"- {row.category}: {int(row.customer_count)} customers, "
            f"{int(row.order_count)} orders, Rs {float(row.total_spend or 0):,.0f} spend"
            for row in rows
        ]
        response = f"{audience} are buying from these categories:\n" + "\n".join(lines)
    return {
        "response": response,
        "segment_preview": None,
        "campaign_draft": None,
        "awaiting_approval": False,
        "pending_segment_id": None,
    }


def _rate(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator or 0) / float(denominator or 1)) * 100, 1)


def _active_campaign_customer_ids(db) -> set[str]:
    return set(
        db.scalars(
            select(Message.customer_id)
            .join(Campaign, Campaign.id == Message.campaign_id)
            .where(Campaign.status == "running")
        ).all()
    )


def _journey_readiness_lines(db) -> list[str]:
    active_customer_ids = _active_campaign_customer_ids(db)
    journeys = db.scalars(
        select(Journey)
        .where(Journey.status == "active")
        .order_by(desc(Journey.created_at))
        .limit(5)
    ).all()
    lines = []
    for journey in journeys:
        try:
            trigger_rules = json.loads(journey.trigger_rules)
            customer_ids = set(execute_segment_filter(trigger_rules, db))
        except Exception:
            customer_ids = set()
        excluded = len(customer_ids.intersection(active_customer_ids))
        eligible = max(len(customer_ids) - excluded, 0)
        lines.append(
            f"* {journey.name}: {len(customer_ids)} matched now, "
            f"{eligible} eligible to queue, {journey.campaigns_triggered or 0} campaigns triggered"
        )
    return lines


def _campaign_performance_response(db) -> dict:
    campaigns = db.scalars(
        select(Campaign).order_by(desc(Campaign.created_at)).limit(5)
    ).all()
    total_campaigns = db.scalar(select(func.count()).select_from(Campaign)) or 0
    if not campaigns:
        journey_lines = _journey_readiness_lines(db)
        if journey_lines:
            response = (
                "There are no launched campaigns yet, so delivery, open, click, "
                "and revenue metrics are not available.\n\n"
                f"Journey readiness report ({len(journey_lines)} active shown):\n"
                + "\n".join(journey_lines)
                + "\n\n"
                "Click Run now on a journey with eligible customers to create the first campaign. "
                "After it queues messages, Analytics will show the campaign performance report."
            )
        else:
            response = "There is no campaign performance to show yet because no campaigns have been launched."
    else:
        total_sent = sum(campaign.total_sent or 0 for campaign in campaigns)
        total_delivered = sum(campaign.total_delivered or 0 for campaign in campaigns)
        total_opened = sum(campaign.total_opened or 0 for campaign in campaigns)
        total_clicked = sum(campaign.total_clicked or 0 for campaign in campaigns)
        total_failed = sum(campaign.total_failed or 0 for campaign in campaigns)
        total_orders = sum(campaign.total_attributed_orders or 0 for campaign in campaigns)
        total_revenue = sum(campaign.total_attributed_revenue or 0.0 for campaign in campaigns)
        lines = [
            f"* {campaign.name}: {campaign.status}, {campaign.total_sent or 0} targeted, "
            f"{_rate(campaign.total_delivered, campaign.total_sent)}% delivered, "
            f"{_rate(campaign.total_opened, campaign.total_delivered)}% opened, "
            f"{campaign.total_attributed_orders or 0} returned orders, "
            f"Rs {campaign.total_attributed_revenue or 0.0:,.0f} revenue"
            for campaign in campaigns
        ]
        response = (
            f"I found {int(total_campaigns)} campaigns.\n\n"
            f"Latest {len(campaigns)} campaign performance:\n"
            + "\n".join(lines)
            + "\n\n"
            f"Overall for these campaigns: {total_sent} targeted, "
            f"{_rate(total_delivered, total_sent)}% delivered, "
            f"{_rate(total_opened, total_delivered)}% opened, "
            f"{_rate(total_clicked, total_opened)}% click-to-open, "
            f"{total_failed} failed, {total_orders} returned orders, "
            f"Rs {total_revenue:,.0f} attributed revenue."
        )
    return {
        "response": response,
        "segment_preview": None,
        "campaign_draft": None,
        "awaiting_approval": False,
        "pending_segment_id": None,
    }


def _draft_for_saved_segment(session: dict, db) -> dict | None:
    preview = session.get("segment_preview") or {}
    filter_rules = preview.get("filter_rules")
    if not filter_rules:
        return None

    name = "AI Audience"
    if "category" in filter_rules:
        name = f"{filter_rules['category']} Audience"
    elif filter_rules.get("max_orders") == 2:
        name = "One-time Buyers"
    elif "recency_days" in filter_rules:
        name = "At-risk Audience"

    segment = Segment(
        name=name,
        description=preview.get("filter_summary", "AI-generated audience"),
        filter_rules=json.dumps(filter_rules),
        customer_count=preview.get("count", 0),
        created_by="ai",
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)

    variants = [
        "Hey {name}, we saved a special StyleHub offer for you. Come back and explore today.",
        "Hi {name}, your next StyleHub pick is waiting. Enjoy 20% off on your favourites.",
        "{name}, refresh your wardrobe with a limited StyleHub offer today.",
    ]
    draft = {
        "segment_id": segment.id,
        "segment_name": segment.name,
        "customer_count": segment.customer_count,
        "variants": variants,
        "recommended": variants[0],
    }
    return {
        "response": (
            f"I've saved this audience as \"{segment.name}\" "
            f"with {segment.customer_count} customers. Here are three message variants:\n"
            f"* {variants[0]}\n* {variants[1]}\n* {variants[2]}\n\n"
            "Choose a variant and launch when ready."
        ),
        "segment_preview": preview,
        "campaign_draft": draft,
        "awaiting_approval": True,
        "pending_segment_id": segment.id,
    }


def _deterministic_response(message: str, session: dict, db) -> dict | None:
    lowered = message.lower()
    tokens = set(re.findall(r"[a-z]+", lowered))
    wants_save = bool(tokens & {"yes", "save", "draft", "approve", "approved"})
    if wants_save:
        saved = _draft_for_saved_segment(session, db)
        if saved:
            return saved

    if (
        "campaign performance" in lowered
        or "campaign stats" in lowered
        or "campaign analytics" in lowered
        or ("campaign" in lowered and any(word in lowered for word in ["performance", "stats", "analytics", "revenue", "delivery", "open"]))
    ):
        return _campaign_performance_response(db)

    gender = _normalize_gender(f" {lowered} ")
    category = _normalize_category_from_text(lowered)

    if ("what" in lowered or "which" in lowered) and (
        "buying" in lowered or "buy from" in lowered or "categories" in lowered
    ):
        return _category_insights_response(gender, db)

    filter_rules = {}
    if "one-time" in lowered or "one time" in lowered:
        filter_rules["max_orders"] = 2
        filter_rules["recency_days"] = 180
    if "least loyal" in lowered or "lapsed" in lowered:
        filter_rules["recency_days"] = 90
    if "at risk" in lowered or "at-risk" in lowered:
        filter_rules["recency_days"] = 60
        filter_rules["max_spend"] = 10000
    if gender:
        filter_rules["gender"] = gender
    if category:
        filter_rules["category"] = category
    recency_match = re.search(r"(\d+)\+?\s*days", lowered)
    if recency_match:
        filter_rules["recency_days"] = int(recency_match.group(1))

    is_audience_query = any(
        phrase in lowered
        for phrase in ["find", "show me", "audience", "customers", "buyers", "bought"]
    )
    if filter_rules and is_audience_query:
        return _segment_preview_response(filter_rules, db)

    return None


async def agent_node(state: AgentState) -> dict:
    if not settings.GROQ_API_KEY:
        return _fallback_response(state)

    db = SessionLocal()
    try:
        model = build_groq_model(temperature=0.3)
        tools = get_tools(db)
        model_with_tools = model.bind_tools(tools)
        messages = state["messages"]
        try:
            response = await retry_async_groq_call(
                lambda: model_with_tools.ainvoke([SystemMessage(SYSTEM_PROMPT)] + messages),
                label="Groq agent call",
            )
        except Exception as exc:
            logger.exception("Groq agent call failed: %s", exc)
            response = AIMessage(content=GROQ_UNAVAILABLE_MESSAGE)
    finally:
        db.close()

    new_state: dict = {"messages": [response]}
    content = response.content if isinstance(response.content, str) else ""

    # Signal parsing: the agent embeds AWAITING_APPROVAL:[uuid] in its response
    # to trigger the human-in-the-loop gate. We parse it here, strip it from
    # the visible response, and store the segment_id for the launch step.
    # This avoids a separate graph node and keeps the state machine simple.
    if "AWAITING_APPROVAL:" in content:
        match = re.search(r"AWAITING_APPROVAL:([a-f0-9-]+)", content)
        if match:
            new_state["awaiting_approval"] = True
            new_state["pending_segment_id"] = match.group(1)
            new_state["final_response"] = re.sub(
                r"\nAWAITING_APPROVAL:[^\n]+",
                "",
                content,
            ).strip()
        else:
            new_state["final_response"] = content
    else:
        new_state["final_response"] = content
        if not getattr(response, "tool_calls", None):
            new_state["awaiting_approval"] = False

    return new_state


async def tools_node(state: AgentState) -> dict:
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    db = SessionLocal()
    try:
        tools_by_name = {tool.name: tool for tool in get_tools(db)}
        tool_messages = []
        new_state: dict = {}
        for call in tool_calls:
            name = call["name"]
            args = call.get("args") or {}
            tool_result = tools_by_name[name].invoke(args)
            if name == "query_customers_by_filters":
                new_state["segment_preview"] = tool_result
            elif name == "create_segment":
                draft = dict(state.get("campaign_draft") or {})
                draft["segment_id"] = tool_result.get("segment_id")
                draft["segment_name"] = tool_result.get("name")
                draft["customer_count"] = tool_result.get("customer_count")
                new_state["campaign_draft"] = draft
                new_state["pending_segment_id"] = tool_result.get("segment_id")
            elif name == "draft_campaign_message":
                draft = dict(state.get("campaign_draft") or {})
                draft.update(tool_result)
                if state.get("pending_segment_id"):
                    draft["segment_id"] = state.get("pending_segment_id")
                new_state["campaign_draft"] = draft
            tool_messages.append(
                ToolMessage(
                    content=json.dumps(tool_result, default=str),
                    name=name,
                    tool_call_id=call["id"],
                )
            )
        new_state["messages"] = tool_messages
        return new_state
    finally:
        db.close()


def should_continue(state: AgentState):
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")
graph = workflow.compile()


async def run_agent(
    message: str,
    conversation_history: list,
    session_id: str,
    db,
) -> dict:
    session = _sessions.get(
        session_id,
        {
            "messages": [],
            "segment_preview": None,
            "campaign_draft": None,
            "awaiting_approval": False,
            "pending_segment_id": None,
            "final_response": "",
            "session_id": session_id,
        },
    )
    if conversation_history and not session["messages"]:
        for item in conversation_history[-20:]:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role in {"assistant", "ai"}:
                session["messages"].append(AIMessage(content=content))
            else:
                session["messages"].append(HumanMessage(content=content))

    session["messages"] = session["messages"][-20:] + [HumanMessage(content=message)]
    deterministic = _deterministic_response(message, session, db)
    if deterministic is not None:
        session.update(
            {
                "messages": session["messages"]
                + [AIMessage(content=deterministic["response"])],
                "segment_preview": deterministic.get("segment_preview"),
                "campaign_draft": deterministic.get("campaign_draft"),
                "awaiting_approval": deterministic.get("awaiting_approval", False),
                "pending_segment_id": deterministic.get("pending_segment_id"),
                "final_response": deterministic["response"],
                "session_id": session_id,
            }
        )
        _sessions[session_id] = session
        return {
            "response": deterministic["response"],
            "segment_preview": deterministic.get("segment_preview"),
            "campaign_draft": deterministic.get("campaign_draft"),
            "awaiting_approval": deterministic.get("awaiting_approval", False),
            "pending_segment_id": deterministic.get("pending_segment_id"),
            "session_id": session_id,
        }

    result = await graph.ainvoke(session)
    _sessions[session_id] = result
    return {
        "response": result.get("final_response", ""),
        "segment_preview": result.get("segment_preview"),
        "campaign_draft": result.get("campaign_draft"),
        "awaiting_approval": result.get("awaiting_approval", False),
        "pending_segment_id": result.get("pending_segment_id"),
        "session_id": session_id,
    }
