import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from database import get_db
from models import Campaign, Journey, Message, Segment
from routers.campaigns import launch_campaign_record, schedule_campaign_batches
from routers.segments import execute_segment_filter
from schemas import JourneyCreate, JourneyRead


router = APIRouter()


JOURNEY_TEMPLATES = [
    {
        "type": "win_back",
        "name": "Win-Back Lapsed Customers",
        "description": "Automatically reach customers who haven't bought in 60+ days",
        "trigger_rules": {"recency_days": 60},
        "default_message": "Hey {name}, we miss you at StyleHub! Come back for 20% off your next order.",
        "icon": "Refresh",
    },
    {
        "type": "high_value_at_risk",
        "name": "Save High-Value Customers",
        "description": "Reach top spenders who are becoming inactive (30-60 days)",
        "trigger_rules": {"recency_days": 30, "max_recency_days": 60, "min_spend": 5000},
        "default_message": "Hi {name}, as one of our valued StyleHub customers, here's an exclusive 15% off just for you.",
        "icon": "Star",
    },
    {
        "type": "first_purchase_followup",
        "name": "First Purchase Follow-up",
        "description": "Engage new customers within 7 days of their first order",
        "trigger_rules": {"max_recency_days": 7, "max_orders": 1},
        "default_message": "Hi {name}! Thank you for your first purchase. Here's what's trending next.",
        "icon": "Party",
    },
    {
        "type": "repeat_buyer_reward",
        "name": "Reward Repeat Buyers",
        "description": "Thank customers who have made 5+ orders",
        "trigger_rules": {"min_orders": 5, "max_recency_days": 45},
        "default_message": "You're a StyleHub Champion {name}! Enjoy free shipping on your next order.",
        "icon": "Trophy",
    },
    {
        "type": "lapsed",
        "name": "Re-engage Lapsed Buyers",
        "description": "Customers inactive for 90-180 days",
        "trigger_rules": {"recency_days": 90},
        "default_message": "{name}, it's been a while! New arrivals are waiting for you at StyleHub.",
        "icon": "Sleep",
    },
    {
        "type": "category_cross_sell",
        "name": "Category Cross-Sell",
        "description": "Suggest next best category to single-category buyers",
        "trigger_rules": {"max_orders": 3},
        "default_message": "Hi {name}, loving your {last_category} picks! Have you explored our {next_best_category} collection?",
        "icon": "Bag",
    },
]


def _journey_or_404(journey_id: str, db: Session) -> Journey:
    journey = db.get(Journey, journey_id)
    if journey is None:
        raise HTTPException(status_code=404, detail="Journey not found")
    return journey


def _active_campaign_customer_ids(db: Session) -> set[str]:
    return set(
        db.scalars(
            select(Message.customer_id)
            .join(Campaign, Campaign.id == Message.campaign_id)
            .where(Campaign.status == "running")
        ).all()
    )


@router.get("/templates")
async def journey_templates() -> list[dict[str, object]]:
    return JOURNEY_TEMPLATES


@router.get("/")
async def list_journeys(db: Session = Depends(get_db)) -> list[JourneyRead]:
    journeys = db.scalars(select(Journey).order_by(desc(Journey.created_at))).all()
    return [JourneyRead.model_validate(journey) for journey in journeys]


@router.post("/", response_model=JourneyRead)
async def create_journey(
    payload: JourneyCreate,
    db: Session = Depends(get_db),
) -> Journey:
    journey = Journey(
        name=payload.name,
        journey_type=payload.journey_type,
        trigger_rules=json.dumps(payload.trigger_rules),
        message_template=payload.message_template,
        channel=payload.channel,
        status="active",
    )
    db.add(journey)
    db.commit()
    db.refresh(journey)
    return journey


@router.post("/{journey_id}/pause", response_model=JourneyRead)
async def toggle_journey_status(
    journey_id: str,
    db: Session = Depends(get_db),
) -> Journey:
    journey = _journey_or_404(journey_id, db)
    journey.status = "paused" if journey.status == "active" else "active"
    db.commit()
    db.refresh(journey)
    return journey


@router.post("/{journey_id}/trigger")
async def trigger_journey(
    journey_id: str,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    journey = _journey_or_404(journey_id, db)
    if journey.status != "active":
        return {"queued": 0, "status": journey.status, "reason": "journey is paused"}

    trigger_rules = json.loads(journey.trigger_rules)
    customer_ids = execute_segment_filter(trigger_rules, db)
    active_customer_ids = _active_campaign_customer_ids(db)
    eligible_customer_ids = [
        customer_id
        for customer_id in customer_ids
        if customer_id not in active_customer_ids
    ]

    journey.customers_enrolled = len(eligible_customer_ids)
    if not eligible_customer_ids:
        db.commit()
        return {
            "queued": 0,
            "matched": len(customer_ids),
            "excluded_active_campaign": len(active_customer_ids.intersection(customer_ids)),
            "reason": "no eligible customers",
        }

    filter_rules = {"customer_ids": eligible_customer_ids}
    segment = Segment(
        name=f"{journey.name} - {datetime.utcnow().strftime('%b %d %H:%M')}",
        description=f"Auto-generated audience for journey {journey.name}",
        filter_rules=json.dumps(filter_rules),
        customer_count=len(eligible_customer_ids),
        created_by="journey",
    )
    db.add(segment)
    db.flush()

    campaign = Campaign(
        name=f"{journey.name} Journey {datetime.utcnow().strftime('%b %d %H:%M')}",
        segment_id=segment.id,
        message_template=journey.message_template,
        channel=journey.channel,
        status="draft",
    )
    db.add(campaign)
    db.flush()
    result, send_payloads = launch_campaign_record(campaign, db)
    journey.campaigns_triggered += 1
    journey.customers_enrolled = len(eligible_customer_ids)
    db.commit()
    schedule_campaign_batches(send_payloads)

    return {
        "journey_id": journey.id,
        "campaign_id": result["campaign_id"],
        "queued": result["total_queued"],
        "matched": len(customer_ids),
        "excluded_active_campaign": len(active_customer_ids.intersection(customer_ids)),
        "status": result["status"],
    }
