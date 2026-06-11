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
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph

from agent.tools import get_tools
from config import settings
from database import SessionLocal


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


async def agent_node(state: AgentState) -> dict:
    if not settings.GROQ_API_KEY:
        return _fallback_response(state)

    db = SessionLocal()
    try:
        model = ChatGroq(
            model=settings.LLM_MODEL,
            temperature=0.3,
            groq_api_key=settings.GROQ_API_KEY,
        )
        tools = get_tools(db)
        model_with_tools = model.bind_tools(tools)
        messages = state["messages"]
        try:
            response = await model_with_tools.ainvoke([SystemMessage(SYSTEM_PROMPT)] + messages)
        except Exception as exc:
            logger.exception("Groq agent call failed: %s", exc)
            response = AIMessage(
                content=(
                    "I could not reach Groq right now. The CRM tools are available, "
                    "but the AI campaign manager needs network access to respond."
                )
            )
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
