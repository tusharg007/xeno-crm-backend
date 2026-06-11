"""
Receipt callback handler — POST /receipt

The channel service fires this endpoint as each message progresses through
its delivery lifecycle: queued → sent → delivered → opened → clicked (or failed).
Callbacks may arrive out of order or be duplicated — both cases are handled.

Design decisions:
  Idempotency — STATUS_ORDER index comparison ensures we only advance state
    forward, never backward. A duplicate 'delivered' callback after 'opened'
    is silently ignored. This mirrors production receipt handling with providers
    like Twilio (which can send duplicate webhooks on retry).

  Aggregate counters — updated via SQL COUNT subqueries on every callback,
    not Python-side counting. Safe under concurrent callbacks for the same
    campaign. In production: use SELECT FOR UPDATE or a Redis counter.

  Auto-complete — campaign.status changes to 'completed' automatically once
    all messages reach a terminal state. No separate job or cron needed.

  At scale: add idempotency keys to prevent double-processing, a dead-letter
    queue for callbacks that fail to reach this endpoint, and a Redis stream
    for real-time dashboard updates instead of polling.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Campaign, Message
from schemas import ReceiptPayload


router = APIRouter()

# Defines valid lifecycle progression for a single message.
# Index position enforces forward-only state transitions:
#   index(new_event) must be > index(current_status), or event must be "failed".
# This handles: duplicate callbacks, out-of-order delivery, provider retries.
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

    # Update campaign aggregate counters using SQL COUNT subqueries.
    # Reason: if we used Python-side counting (campaign.total_delivered += 1),
    # concurrent callbacks for the same campaign could cause race conditions
    # where two requests read the same value and both increment it, losing one.
    # SQL COUNT runs atomically inside the database transaction.
    campaign_id = message.campaign_id

    campaign.total_delivered = db.query(func.count(Message.id)).filter(
        Message.campaign_id == campaign_id,
        Message.status.in_(["delivered", "opened", "clicked"])
    ).scalar() or 0

    campaign.total_opened = db.query(func.count(Message.id)).filter(
        Message.campaign_id == campaign_id,
        Message.status.in_(["opened", "clicked"])
    ).scalar() or 0

    campaign.total_clicked = db.query(func.count(Message.id)).filter(
        Message.campaign_id == campaign_id,
        Message.status == "clicked"
    ).scalar() or 0

    campaign.total_failed = db.query(func.count(Message.id)).filter(
        Message.campaign_id == campaign_id,
        Message.status == "failed"
    ).scalar() or 0

    terminal_count = campaign.total_delivered + campaign.total_failed
    if campaign.total_sent > 0 and terminal_count >= campaign.total_sent:
        campaign.status = "completed"

    db.commit()
    return {
        "ok": True,
        "message_id": payload.message_id,
        "new_status": payload.event,
    }
