from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import Campaign, Message
from schemas import ReceiptPayload


router = APIRouter()
STATUS_ORDER = ["queued", "sent", "delivered", "opened", "clicked", "failed"]


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.utcnow()


def _status_index(status: str) -> int:
    if status in STATUS_ORDER:
        return STATUS_ORDER.index(status)
    return -1


def _count_messages(campaign_id: str, statuses: tuple[str, ...], db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.campaign_id == campaign_id, Message.status.in_(statuses))
        )
        or 0
    )


@router.post("/receipt")
async def receive_receipt(
    payload: ReceiptPayload,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    message = db.get(Message, payload.message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if payload.event not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail="Unsupported receipt event")

    should_process = payload.event == "failed" or _status_index(payload.event) > _status_index(
        message.status
    )
    if not should_process:
        return {"ok": True, "skipped": True, "reason": "no forward progress"}

    message.status = payload.event
    timestamp = _parse_timestamp(payload.timestamp)
    timestamp_field = f"{payload.event}_at"
    if hasattr(message, timestamp_field):
        setattr(message, timestamp_field, timestamp)
    db.flush()

    campaign = db.get(Campaign, message.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.total_delivered = _count_messages(
        campaign.id,
        ("delivered", "opened", "clicked"),
        db,
    )
    campaign.total_opened = _count_messages(campaign.id, ("opened", "clicked"), db)
    campaign.total_clicked = _count_messages(campaign.id, ("clicked",), db)
    campaign.total_failed = _count_messages(campaign.id, ("failed",), db)

    terminal = campaign.total_delivered + campaign.total_failed
    if campaign.total_sent > 0 and terminal >= campaign.total_sent:
        campaign.status = "completed"

    db.commit()
    return {
        "ok": True,
        "message_id": payload.message_id,
        "new_status": payload.event,
    }
