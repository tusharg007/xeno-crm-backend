"""
LangGraph tool definitions for the Xeno campaign agent.

Five tools, each decorated with @tool so LangGraph can bind them to the model.
All tools receive a SQLAlchemy db Session via closure (get_tools factory) so
they share the same database session as the HTTP request that spawned the agent.

Tool call sequence for a typical campaign:
  1. query_customers_by_filters  — find the audience
  2. create_segment              — save the audience (returns segment_id)
  3. draft_campaign_message      — LLM generates 3 message variants
  4. [AWAITING_APPROVAL gate]    — human confirms in the UI
  5. launch_campaign             — create + launch via channel service
  6. get_campaign_analytics      — check performance (any time)
"""

import json
import logging
from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from agent.groq_utils import build_groq_model, retry_sync_groq_call
from config import settings
from models import Campaign, Customer, Order, Segment
from routers.campaigns import launch_campaign_record, schedule_campaign_batches
from routers.segments import execute_segment_filter


logger = logging.getLogger(__name__)

CATEGORY_ALIASES = {
    "ethnic": "Ethnic Wear",
    "ethnic wear": "Ethnic Wear",
    "footwear": "Footwear",
    "shoes": "Footwear",
    "shoe": "Footwear",
    "sandals": "Footwear",
    "skincare": "Skincare",
    "skin care": "Skincare",
    "accessories": "Accessories",
    "accessory": "Accessories",
    "activewear": "Activewear",
    "active wear": "Activewear",
}


def _filter_summary(filter_rules: dict[str, Any]) -> str:
    descriptions = []
    if "recency_days" in filter_rules:
        descriptions.append(f"inactive for more than {filter_rules['recency_days']} days")
    if "max_recency_days" in filter_rules:
        descriptions.append(f"active within {filter_rules['max_recency_days']} days")
    if "min_spend" in filter_rules:
        descriptions.append(f"spent at least Rs {filter_rules['min_spend']}")
    if "max_spend" in filter_rules:
        descriptions.append(f"spent at most Rs {filter_rules['max_spend']}")
    if "gender" in filter_rules:
        descriptions.append(f"gender {filter_rules['gender']}")
    if "city" in filter_rules:
        descriptions.append(f"from {filter_rules['city']}")
    if "category" in filter_rules:
        descriptions.append(f"ordered {filter_rules['category']}")
    if "min_orders" in filter_rules:
        descriptions.append(f"placed at least {filter_rules['min_orders']} orders")
    if "max_orders" in filter_rules:
        descriptions.append(f"placed at most {filter_rules['max_orders']} orders")
    return "Matched customers who are " + ", ".join(descriptions) + "." if descriptions else "Matched all customers."


def _parse_variants(raw: str) -> list[str]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        raise ValueError("Campaign copy response must be a JSON array.")
    return [str(item) for item in parsed[:3]]


def _to_int(value: int | str | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _to_float(value: float | int | str | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _normalize_category(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = CATEGORY_ALIASES.get(value.strip().lower())
    return normalized or value


def _normalize_gender(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"m", "male", "men", "man"}:
        return "M"
    if lowered in {"f", "female", "women", "woman"}:
        return "F"
    return value


def _schedule_channel_send(send_payloads: list[dict]) -> None:
    try:
        schedule_campaign_batches(send_payloads)
    except Exception as exc:
        logger.warning("Unable to schedule channel send: %s", exc)


def _campaign_rates(campaign: Campaign) -> dict[str, float]:
    delivery_rate = campaign.total_delivered / campaign.total_sent if campaign.total_sent else 0.0
    open_rate = campaign.total_opened / campaign.total_delivered if campaign.total_delivered else 0.0
    click_rate = campaign.total_clicked / campaign.total_opened if campaign.total_opened else 0.0
    return {
        "delivery_rate": round(delivery_rate, 3),
        "open_rate": round(open_rate, 3),
        "click_rate": round(click_rate, 3),
    }


def get_tools(db: Session) -> list:
    @tool
    def query_customers_by_filters(
        recency_days: int | str | None = None,
        max_recency_days: int | str | None = None,
        min_spend: float | str | None = None,
        max_spend: float | str | None = None,
        gender: str | None = None,
        city: str | None = None,
        category: str | None = None,
        min_orders: int | str | None = None,
        max_orders: int | str | None = None,
    ) -> dict:
        """Find customers matching demographic and behavioural filters.

        Always call this FIRST when a marketer asks to target, find, or reach
        any group of customers. Returns count + 5 sample customers so the marketer
        can verify the audience looks right before saving it as a segment.

        Filter key guide:
          recency_days=60      → customers inactive for 60+ days (lapsed)
          max_recency_days=30  → customers who bought within 30 days (recent)
          gender="F"           → female customers only
          category="Ethnic Wear" → has ordered this category at least once
          min_spend=5000       → lifetime spend above ₹5,000

        Combine filters freely: recency_days=45 + gender="F" + category="Ethnic Wear"
        finds women who bought ethnic wear but haven't returned in 45 days.
        Returns filter_rules dict — pass it directly to create_segment.
        """
        recency_days = _to_int(recency_days)
        max_recency_days = _to_int(max_recency_days)
        min_spend = _to_float(min_spend)
        max_spend = _to_float(max_spend)
        min_orders = _to_int(min_orders)
        max_orders = _to_int(max_orders)
        gender = _normalize_gender(gender)
        category = _normalize_category(category)

        filter_rules = {
            key: value
            for key, value in {
                "recency_days": recency_days,
                "max_recency_days": max_recency_days,
                "min_spend": min_spend,
                "max_spend": max_spend,
                "gender": gender,
                "city": city,
                "category": category,
                "min_orders": min_orders,
                "max_orders": max_orders,
            }.items()
            if value is not None
        }
        customer_ids = execute_segment_filter(filter_rules, db)
        if not customer_ids:
            return {
                "count": 0,
                "sample": [],
                "filter_rules": filter_rules,
                "filter_summary": "No customers matched. Try relaxing the filters, for example increase recency_days or remove one constraint.",
            }

        now = datetime.utcnow()
        sample_customers = db.scalars(
            select(Customer).where(Customer.id.in_(customer_ids)).limit(5)
        ).all()
        sample = [
            {
                "name": customer.name,
                "city": customer.city,
                "last_order_days_ago": (now - customer.last_order_date).days
                if customer.last_order_date
                else None,
                "total_spend": round(customer.total_spend, 0),
            }
            for customer in sample_customers
        ]
        return {
            "count": len(customer_ids),
            "sample": sample,
            "filter_rules": filter_rules,
            "filter_summary": _filter_summary(filter_rules),
        }

    @tool
    def get_category_insights(
        gender: str | None = None,
        category: str | None = None,
    ) -> dict:
        """Return SQL-backed category buying insights.

        Use this for questions like "what categories are men buying?" or
        "what are women buying?" Never answer those analytical questions from
        general knowledge: use this tool and report only the returned
        categories/counts. For "find customers who bought [category]" questions,
        use query_customers_by_filters instead because that is an audience query.
        """
        gender = _normalize_gender(gender)
        category = _normalize_category(category)

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
        if category:
            query = query.filter(Order.category == category)

        rows = (
            query.group_by(Order.category)
            .order_by(func.count(Order.id).desc())
            .all()
        )

        categories = [
            {
                "category": row.category,
                "order_count": int(row.order_count or 0),
                "customer_count": int(row.customer_count or 0),
                "total_spend": float(row.total_spend or 0),
            }
            for row in rows
        ]

        if category:
            customer_ids = execute_segment_filter(
                {
                    key: value
                    for key, value in {"gender": gender, "category": category}.items()
                    if value is not None
                },
                db,
            )
        else:
            customer_ids = []

        scope = "all customers"
        if gender == "M":
            scope = "male customers"
        elif gender == "F":
            scope = "female customers"

        return {
            "scope": scope,
            "gender": gender,
            "category_filter": category,
            "categories": categories,
            "matching_customer_count": len(customer_ids) if category else None,
            "allowed_categories": sorted(set(CATEGORY_ALIASES.values())),
        }

    @tool
    def create_segment(name: str, description: str, filter_rules: dict) -> dict:
        """Save the matched audience as a named segment in the database.

        Call this AFTER query_customers_by_filters has confirmed the audience
        is correct. Sets created_by='ai' to distinguish AI-generated segments
        from manually built ones (visible in the Analytics dashboard).

        IMPORTANT: The returned segment_id must be passed to launch_campaign.
        Do not lose it between turns — it is stored in pending_segment_id in state.
        """
        customer_ids = execute_segment_filter(filter_rules, db)
        segment = Segment(
            name=name,
            description=description,
            filter_rules=json.dumps(filter_rules),
            customer_count=len(customer_ids),
            created_by="ai",
        )
        db.add(segment)
        db.commit()
        db.refresh(segment)
        return {
            "segment_id": segment.id,
            "name": segment.name,
            "customer_count": segment.customer_count,
        }

    @tool
    def draft_campaign_message(
        segment_description: str,
        offer: str,
        tone: str = "friendly",
    ) -> dict:
        """Generate 3 personalized message variants using GPT-4o-mini.

        Calls the LLM with a StyleHub-specific system prompt and returns
        exactly 3 WhatsApp/SMS message variants under 160 characters each.
        Always includes {name} as a personalization token — the campaign
        launcher replaces this with each customer's actual name at send time.

        tone options: "friendly" (default), "urgent", "exclusive"
        Returns {"variants": [...], "recommended": variants[0]}
        """
        if not settings.GROQ_API_KEY:
            variants = [
                f"Hey {{name}}, {offer} is live at StyleHub. Pick your favorites today.",
                f"Hi {{name}}, StyleHub has {offer} for you. Shop the latest looks now.",
                f"{{name}}, refresh your wardrobe with {offer} at StyleHub.",
            ]
            return {"variants": variants, "recommended": variants[0]}

        llm = build_groq_model(temperature=0.7)
        system = f"""You are a CRM copywriter for StyleHub, an Indian fashion retail brand.
Write punchy messages for WhatsApp and SMS under 160 characters each.
Always include {{name}} as a personalization token.
Tone: {tone}. No hashtags. No emojis. Sound human, not promotional."""
        user = f"""Audience: {segment_description}
Offer: {offer}
Return ONLY a valid JSON array of exactly 3 message strings. No explanation, no markdown.
Example: ["Hey {{name}}, ...", "Hi {{name}}, ...", "{{name}}, ..."]"""
        try:
            response = retry_sync_groq_call(
                lambda: llm.invoke(
                    [{"role": "system", "content": system}, {"role": "user", "content": user}]
                ),
                label="Groq campaign copy generation",
            )
            variants = _parse_variants(str(response.content))
        except Exception as exc:
            logger.warning("Groq campaign copy generation failed: %s", exc)
            variants = [
                f"Hey {{name}}, {offer} is live at StyleHub. Pick your favorites today.",
                f"Hi {{name}}, StyleHub has {offer} for you. Shop the latest looks now.",
                f"{{name}}, refresh your wardrobe with {offer} at StyleHub.",
            ]
        return {"variants": variants[:3], "recommended": variants[0]}

    @tool
    def launch_campaign(
        segment_id: str,
        message_template: str,
        campaign_name: str,
        channel: str = "whatsapp",
    ) -> dict:
        """Launch a campaign to a saved segment via the channel service.

        Creates a Campaign row, personalizes the message for each customer
        (substituting {name}, {city}, {last_category}), creates a Message row
        per recipient, then batch-POSTs to the channel service /send-batch
        endpoint in chunks of 50.

        ONLY call this after the marketer has explicitly approved. The system
        prompt forbids calling this without AWAITING_APPROVAL confirmation.
        segment_id must be the exact UUID returned by create_segment.
        """
        segment = db.get(Segment, segment_id)
        if segment is None:
            return {"error": "Segment not found", "segment_id": segment_id}

        campaign = Campaign(
            name=campaign_name,
            segment_id=segment_id,
            message_template=message_template,
            channel=channel,
            status="draft",
        )
        db.add(campaign)
        db.flush()
        result, send_payloads = launch_campaign_record(campaign, db)
        _schedule_channel_send(send_payloads)
        return {
            "campaign_id": result["campaign_id"],
            "name": campaign_name,
            "total_queued": result["total_queued"],
            "channel": channel,
            "status": result["status"],
        }

    @tool
    def get_campaign_analytics(campaign_id: str | None = None) -> dict:
        """Fetch campaign performance statistics from the database.

        If campaign_id given: returns detailed stats for that specific campaign
        including delivery_rate, open_rate, click_rate as floats (0.0-1.0).
        If campaign_id is None: returns overview of the last 5 campaigns.

        Call this when the marketer asks about performance, results, stats,
        how a campaign did, open rates, click rates, or anything analytical.
        """
        if campaign_id:
            campaign = db.get(Campaign, campaign_id)
            if campaign is None:
                return {"campaigns": [], "summary": "No campaign found for that id."}
            rates = _campaign_rates(campaign)
            return {
                "campaigns": [
                    {
                        "campaign_id": campaign.id,
                        "name": campaign.name,
                        "sent": campaign.total_sent,
                        "delivered": campaign.total_delivered,
                        "opened": campaign.total_opened,
                        "clicked": campaign.total_clicked,
                        "failed": campaign.total_failed,
                        "status": campaign.status,
                        **rates,
                    }
                ],
                "summary": f"{campaign.name} is {campaign.status} with {rates['delivery_rate']:.1%} delivery and {rates['click_rate']:.1%} click rate.",
            }

        campaigns = db.scalars(
            select(Campaign).order_by(desc(Campaign.created_at)).limit(5)
        ).all()
        rows = []
        for campaign in campaigns:
            rows.append(
                {
                    "campaign_id": campaign.id,
                    "name": campaign.name,
                    "sent": campaign.total_sent,
                    "status": campaign.status,
                    **_campaign_rates(campaign),
                }
            )
        return {
            "campaigns": rows,
            "summary": f"Showing the latest {len(rows)} campaigns." if rows else "No campaigns have been launched yet.",
        }

    return [
        query_customers_by_filters,
        get_category_insights,
        create_segment,
        draft_campaign_message,
        launch_campaign,
        get_campaign_analytics,
    ]
