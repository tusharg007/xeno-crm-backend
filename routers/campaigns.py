import asyncio
import json
import logging
import threading
from datetime import datetime
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Campaign, Customer, Message, Order, Segment
from routers.segments import execute_segment_filter
from schemas import CampaignCreate, CampaignRead, MessageRead


router = APIRouter()
logger = logging.getLogger(__name__)


def _campaign_or_404(campaign_id: str, db: Session) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _latest_order_category(customer_id: str, db: Session) -> str:
    return (
        db.scalar(
            select(Order.category)
            .where(Order.customer_id == customer_id)
            .order_by(desc(Order.order_date))
            .limit(1)
        )
        or ""
    )


def _personalize_message(template: str, customer: Customer, db: Session) -> str:
    return (
        template.replace("{name}", customer.name)
        .replace("{city}", customer.city)
        .replace("{last_category}", _latest_order_category(customer.id, db))
    )


def _chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


async def _send_batch(client: httpx.AsyncClient, payload: list[dict]) -> None:
    try:
        await client.post(f"{settings.CHANNEL_SERVICE_URL}/send-batch", json=payload)
    except Exception as exc:
        logger.warning("Channel service batch send failed: %s", exc)


async def _send_campaign_batches(payloads: list[dict]) -> None:
    if not payloads:
        return
    async with httpx.AsyncClient(timeout=15.0) as client:
        await asyncio.gather(
            *[_send_batch(client, chunk) for chunk in _chunks(payloads, 50)]
        )


def schedule_campaign_batches(payloads: list[dict]) -> None:
    if not payloads:
        return
    worker = threading.Thread(
        target=lambda: asyncio.run(_send_campaign_batches(payloads)),
        daemon=True,
    )
    worker.start()


def launch_campaign_record(campaign: Campaign, db: Session) -> tuple[dict[str, object], list[dict]]:
    segment = db.get(Segment, campaign.segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")

    campaign.status = "running"
    campaign.launched_at = datetime.utcnow()
    filter_rules = json.loads(segment.filter_rules)
    customer_ids = execute_segment_filter(filter_rules, db)
    customers = db.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()

    messages: list[Message] = []
    send_payloads: list[dict] = []
    for customer in customers:
        personalized_message = _personalize_message(
            campaign.message_template,
            customer,
            db,
        )
        message = Message(
            id=str(uuid4()),
            campaign_id=campaign.id,
            customer_id=customer.id,
            personalized_message=personalized_message,
            status="queued",
        )
        messages.append(message)
        send_payloads.append(
            {
                "message_id": message.id,
                "campaign_id": campaign.id,
                "customer_id": customer.id,
                "phone": customer.phone,
                "message": personalized_message,
                "channel": campaign.channel,
            }
        )

    if messages:
        db.bulk_save_objects(messages)
    campaign.total_sent = len(customer_ids)
    db.commit()

    return (
        {
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "total_queued": len(customer_ids),
            "status": "running",
        },
        send_payloads,
    )


@router.post("/", response_model=CampaignRead)
async def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
) -> Campaign:
    if db.get(Segment, payload.segment_id) is None:
        raise HTTPException(status_code=404, detail="Segment not found")

    campaign = Campaign(
        name=payload.name,
        segment_id=payload.segment_id,
        message_template=payload.message_template,
        channel=payload.channel,
        status="draft",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    campaign = _campaign_or_404(campaign_id, db)
    result, send_payloads = launch_campaign_record(campaign, db)
    schedule_campaign_batches(send_payloads)
    return result


@router.get("/")
async def list_campaigns(db: Session = Depends(get_db)) -> dict[str, object]:
    total = db.scalar(select(func.count()).select_from(Campaign)) or 0
    campaigns = db.scalars(select(Campaign).order_by(desc(Campaign.created_at))).all()
    return {
        "data": [CampaignRead.model_validate(campaign) for campaign in campaigns],
        "total": total,
    }


@router.get("/summary")
async def campaign_summary(db: Session = Depends(get_db)) -> dict[str, object]:
    """Overview of all campaigns with key performance and attribution metrics."""
    campaigns = db.scalars(select(Campaign)).all()
    total_campaigns = len(campaigns)
    total_sent = sum(campaign.total_sent or 0 for campaign in campaigns)
    total_delivered = sum(campaign.total_delivered or 0 for campaign in campaigns)
    total_opened = sum(campaign.total_opened or 0 for campaign in campaigns)
    total_attributed = sum(campaign.total_attributed_orders or 0 for campaign in campaigns)
    total_revenue = round(
        sum(campaign.total_attributed_revenue or 0.0 for campaign in campaigns),
        2,
    )

    best = None
    for campaign in campaigns:
        open_rate = _rate(campaign.total_opened or 0, campaign.total_delivered or 0)
        if best is None or open_rate > best["open_rate"]:
            best = {"name": campaign.name, "open_rate": open_rate}

    return {
        "total_campaigns": total_campaigns,
        "total_messages_sent": total_sent,
        "overall_delivery_rate": _rate(total_delivered, total_sent),
        "overall_open_rate": _rate(total_opened, total_delivered),
        "overall_attribution_rate": _rate(total_attributed, total_sent),
        "total_attributed_revenue": total_revenue,
        "best_campaign": best or {"name": "N/A", "open_rate": 0.0},
    }


@router.get("/{campaign_id}", response_model=CampaignRead)
async def get_campaign(campaign_id: str, db: Session = Depends(get_db)) -> Campaign:
    return _campaign_or_404(campaign_id, db)


@router.get("/{campaign_id}/performance")
async def campaign_performance(
    campaign_id: str,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return complete communication performance insights for a campaign."""
    campaign = _campaign_or_404(campaign_id, db)
    segment = db.get(Segment, campaign.segment_id)

    sent = campaign.total_sent or 0
    delivered = campaign.total_delivered or 0
    read = campaign.total_read or 0
    opened = campaign.total_opened or 0
    clicked = campaign.total_clicked or 0
    failed = campaign.total_failed or 0
    attributed = campaign.total_attributed_orders or 0
    revenue = round(float(campaign.total_attributed_revenue or 0.0), 2)

    city_rows = db.execute(
        select(
            Customer.city,
            func.count(Message.id).label("sent"),
            func.sum(
                case((Message.status.in_(["opened", "clicked"]), 1), else_=0)
            ).label("opened"),
            func.sum(case((Message.status == "clicked", 1), else_=0)).label("clicked"),
        )
        .join(Customer, Customer.id == Message.customer_id)
        .where(Message.campaign_id == campaign_id)
        .group_by(Customer.city)
        .order_by(desc("sent"))
        .limit(5)
    ).all()
    by_city = [
        {
            "city": row.city,
            "sent": int(row.sent or 0),
            "opened": int(row.opened or 0),
            "clicked": int(row.clicked or 0),
            "open_rate": _rate(row.opened or 0, row.sent or 0),
        }
        for row in city_rows
    ]

    performers = db.execute(
        select(Customer.name, Customer.city, Message.status, Message.attributed_order)
        .join(Customer, Customer.id == Message.customer_id)
        .where(
            Message.campaign_id == campaign_id,
            (Message.status == "clicked") | (Message.attributed_order == True),  # noqa: E712
        )
        .order_by(desc(Message.attributed_order), desc(Message.clicked_at))
        .limit(5)
    ).all()
    top_performers = [
        {
            "name": row.name,
            "city": row.city,
            "status": row.status,
            "attributed": bool(row.attributed_order),
        }
        for row in performers
    ]

    launch_time = campaign.launched_at or campaign.created_at
    delivered_messages = db.scalars(
        select(Message.delivered_at)
        .where(Message.campaign_id == campaign_id, Message.delivered_at.is_not(None))
    ).all()
    hourly_counts: dict[int, int] = {}
    for delivered_at in delivered_messages:
        hour = max(0, int((delivered_at - launch_time).total_seconds() // 3600))
        hourly_counts[hour] = hourly_counts.get(hour, 0) + 1

    return {
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "segment_name": segment.name if segment else "Unknown segment",
        "channel": campaign.channel,
        "status": campaign.status,
        "launched_at": campaign.launched_at.isoformat() if campaign.launched_at else None,
        "funnel": {
            "sent": sent,
            "delivered": delivered,
            "read": read,
            "opened": opened,
            "clicked": clicked,
            "failed": failed,
            "attributed_orders": attributed,
        },
        "rates": {
            "delivery_rate": _rate(delivered, sent),
            "read_rate": _rate(read, delivered),
            "open_rate": _rate(opened, delivered),
            "click_rate": _rate(clicked, opened),
            "click_to_open_rate": _rate(clicked, opened),
            "attribution_rate": _rate(attributed, sent),
            "failure_rate": _rate(failed, sent),
        },
        "revenue": {
            "total_attributed_revenue": revenue,
            "avg_order_value": round(revenue / attributed, 2) if attributed else 0.0,
            "revenue_per_message_sent": round(revenue / sent, 2) if sent else 0.0,
        },
        "audience_breakdown": {
            "by_city": by_city,
            "top_performers": top_performers,
        },
        "timeline": {
            "hourly_deliveries": [
                {"hour": hour, "count": hourly_counts[hour]}
                for hour in sorted(hourly_counts)
            ]
        },
    }


@router.get("/{campaign_id}/messages")
async def list_campaign_messages(
    campaign_id: str,
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _campaign_or_404(campaign_id, db)
    filters = [Message.campaign_id == campaign_id]
    if status is not None:
        filters.append(Message.status == status)

    total = db.scalar(select(func.count()).select_from(Message).where(*filters)) or 0
    messages = db.scalars(
        select(Message)
        .where(*filters)
        .order_by(desc(Message.sent_at), Message.id)
        .offset(skip)
        .limit(limit)
    ).all()
    return {
        "data": [MessageRead.model_validate(message) for message in messages],
        "total": total,
    }
