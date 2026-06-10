import json
import logging
from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from langchain_groq import ChatGroq
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from config import settings
from models import Campaign, Customer, Segment
from routers.campaigns import launch_campaign_record, schedule_campaign_batches
from routers.segments import execute_segment_filter


logger = logging.getLogger(__name__)


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
        recency_days: int | None = None,
        max_recency_days: int | None = None,
        min_spend: float | None = None,
        max_spend: float | None = None,
        gender: str | None = None,
        city: str | None = None,
        category: str | None = None,
        min_orders: int | None = None,
        max_orders: int | None = None,
    ) -> dict:
        """Find customers matching filters. Always call this first when a marketer wants to target an audience. recency_days: customers inactive for more than N days. max_recency_days: customers active within N days. min_spend/max_spend: lifetime spend in rupees. gender: M or F. city: exact city name. category: ordered this category at least once."""
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
    def create_segment(name: str, description: str, filter_rules: dict) -> dict:
        """Save the matched audience as a named segment in the database. Call this after query_customers_by_filters has confirmed the audience looks correct. Returns the segment_id which you must remember for the launch step."""
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
        """Generate 3 personalized message variants using AI. segment_description: plain English description of who the audience is. offer: what you are promoting, e.g. '20% off ethnic wear'. tone: friendly, urgent, or exclusive."""
        if not settings.GROQ_API_KEY:
            variants = [
                f"Hey {{name}}, {offer} is live at StyleHub. Pick your favorites today.",
                f"Hi {{name}}, StyleHub has {offer} for you. Shop the latest looks now.",
                f"{{name}}, refresh your wardrobe with {offer} at StyleHub.",
            ]
            return {"variants": variants, "recommended": variants[0]}

        llm = ChatGroq(
            model=settings.LLM_MODEL,
            temperature=0.7,
            groq_api_key=settings.GROQ_API_KEY,
        )
        system = f"""You are a CRM copywriter for StyleHub, an Indian fashion retail brand.
Write punchy messages for WhatsApp and SMS under 160 characters each.
Always include {{name}} as a personalization token.
Tone: {tone}. No hashtags. No emojis. Sound human, not promotional."""
        user = f"""Audience: {segment_description}
Offer: {offer}
Return ONLY a valid JSON array of exactly 3 message strings. No explanation, no markdown.
Example: ["Hey {{name}}, ...", "Hi {{name}}, ...", "{{name}}, ..."]"""
        try:
            response = llm.invoke(
                [{"role": "system", "content": system}, {"role": "user", "content": user}]
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
        """Launch a campaign to a saved segment. ONLY call this after the marketer has explicitly approved. segment_id must be the id returned by create_segment. channel options: whatsapp, sms, email."""
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
        """Get campaign performance stats. If campaign_id given: detailed stats for that campaign. If campaign_id is None: overview of the last 5 campaigns."""
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
        create_segment,
        draft_campaign_message,
        launch_campaign,
        get_campaign_analytics,
    ]
