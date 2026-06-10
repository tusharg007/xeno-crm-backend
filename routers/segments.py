import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from database import get_db
from models import Customer, Order, Segment
from schemas import CustomerRead, SegmentCreate, SegmentRead


router = APIRouter()


def execute_segment_filter(filter_rules: dict, db: Session) -> list[str]:
    """Returns list of customer_ids matching ALL provided filter rules."""
    query = select(Customer.id)
    joined_orders = False

    if "category" in filter_rules:
        query = query.join(Order, Order.customer_id == Customer.id)
        joined_orders = True
        query = query.where(Order.category == filter_rules["category"])

    if "recency_days" in filter_rules:
        cutoff = datetime.utcnow() - timedelta(days=int(filter_rules["recency_days"]))
        query = query.where(Customer.last_order_date < cutoff)

    if "max_recency_days" in filter_rules:
        cutoff = datetime.utcnow() - timedelta(
            days=int(filter_rules["max_recency_days"])
        )
        query = query.where(Customer.last_order_date >= cutoff)

    if "min_spend" in filter_rules:
        query = query.where(Customer.total_spend >= float(filter_rules["min_spend"]))

    if "max_spend" in filter_rules:
        query = query.where(Customer.total_spend <= float(filter_rules["max_spend"]))

    if "gender" in filter_rules:
        query = query.where(Customer.gender == filter_rules["gender"])

    if "city" in filter_rules:
        query = query.where(Customer.city == filter_rules["city"])

    if "min_orders" in filter_rules:
        query = query.where(Customer.total_orders >= int(filter_rules["min_orders"]))

    if "max_orders" in filter_rules:
        query = query.where(Customer.total_orders <= int(filter_rules["max_orders"]))

    if joined_orders:
        query = query.distinct()

    return list(db.scalars(query).all())


def _segment_or_404(segment_id: str, db: Session) -> Segment:
    segment = db.get(Segment, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    return segment


def _load_filter_rules(segment: Segment) -> dict:
    parsed = json.loads(segment.filter_rules)
    return parsed if isinstance(parsed, dict) else {}


@router.post("/", response_model=SegmentRead)
async def create_segment(
    payload: SegmentCreate,
    db: Session = Depends(get_db),
) -> Segment:
    customer_ids = execute_segment_filter(payload.filter_rules, db)
    segment = Segment(
        name=payload.name,
        description=payload.description,
        filter_rules=json.dumps(payload.filter_rules),
        customer_count=len(customer_ids),
        created_by="human",
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


@router.get("/")
async def list_segments(db: Session = Depends(get_db)) -> list[SegmentRead]:
    segments = db.scalars(select(Segment).order_by(desc(Segment.created_at))).all()
    return [SegmentRead.model_validate(segment) for segment in segments]


@router.get("/{segment_id}", response_model=SegmentRead)
async def get_segment(segment_id: str, db: Session = Depends(get_db)) -> Segment:
    return _segment_or_404(segment_id, db)


@router.get("/{segment_id}/customers")
async def get_segment_customers(
    segment_id: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    segment = _segment_or_404(segment_id, db)
    customer_ids = execute_segment_filter(_load_filter_rules(segment), db)
    customers = []
    if customer_ids:
        customers = db.scalars(
            select(Customer)
            .where(Customer.id.in_(customer_ids))
            .order_by(desc(Customer.created_at))
            .offset(skip)
            .limit(limit)
        ).all()

    return {
        "data": [CustomerRead.model_validate(customer) for customer in customers],
        "total": len(customer_ids),
        "skip": skip,
        "limit": limit,
    }


@router.delete("/{segment_id}")
async def delete_segment(segment_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    segment = _segment_or_404(segment_id, db)
    db.delete(segment)
    db.commit()
    return {"deleted": True}
