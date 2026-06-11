from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from database import get_db
from models import Campaign, Customer, Message, Order
from schemas import CustomerBulkCreate, CustomerRead, OrderAttributionRequest, OrderBulkCreate


router = APIRouter()


def _recalculate_customer_aggregates(customer_id: str, db: Session) -> None:
    aggregates = db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.amount), 0.0),
            func.max(Order.order_date),
        ).where(Order.customer_id == customer_id)
    ).one()
    customer = db.get(Customer, customer_id)
    if customer is None:
        return
    customer.total_orders = aggregates[0]
    customer.total_spend = round(float(aggregates[1] or 0.0), 2)
    customer.last_order_date = aggregates[2]


@router.post("/bulk")
async def bulk_create_customers(
    payload: CustomerBulkCreate,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    rows = [customer.model_dump() for customer in payload.customers]
    if not rows:
        return {"inserted": 0, "skipped": 0}

    before_count = db.scalar(select(func.count()).select_from(Customer)) or 0
    statement = sqlite_insert(Customer).values(rows).prefix_with("OR IGNORE")
    db.execute(statement)
    db.commit()
    after_count = db.scalar(select(func.count()).select_from(Customer)) or 0
    inserted = after_count - before_count
    return {"inserted": inserted, "skipped": len(rows) - inserted}


@router.post("/bulk-orders")
async def bulk_create_orders(
    payload: OrderBulkCreate,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    orders = [Order(**order.model_dump()) for order in payload.orders]
    if not orders:
        return {"inserted": 0}

    affected_customer_ids = {order.customer_id for order in orders}
    db.bulk_save_objects(orders)
    db.flush()
    for customer_id in affected_customer_ids:
        _recalculate_customer_aggregates(customer_id, db)
    db.commit()
    return {"inserted": len(orders)}


@router.get("/")
async def list_customers(
    skip: int = 0,
    limit: int = 50,
    city: str | None = None,
    gender: str | None = None,
    min_spend: float | None = None,
    max_spend: float | None = None,
    inactive_days: int | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    query = select(Customer)
    count_query = select(func.count()).select_from(Customer)
    filters = []

    if city is not None:
        filters.append(Customer.city == city)
    if gender is not None:
        filters.append(Customer.gender == gender)
    if min_spend is not None:
        filters.append(Customer.total_spend >= min_spend)
    if max_spend is not None:
        filters.append(Customer.total_spend <= max_spend)
    if inactive_days is not None:
        cutoff = datetime.utcnow() - timedelta(days=inactive_days)
        filters.append(Customer.last_order_date < cutoff)

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = db.scalar(count_query) or 0
    customers = db.scalars(
        query.order_by(desc(Customer.created_at)).offset(skip).limit(limit)
    ).all()
    return {
        "data": [CustomerRead.model_validate(customer) for customer in customers],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/stats/overview")
async def customer_stats_overview(db: Session = Depends(get_db)) -> dict[str, object]:
    now = datetime.utcnow()
    loyal_cutoff = now - timedelta(days=30)
    at_risk_cutoff = now - timedelta(days=90)

    total_customers = db.scalar(select(func.count()).select_from(Customer)) or 0
    loyal_count = (
        db.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.last_order_date >= loyal_cutoff)
        )
        or 0
    )
    at_risk_count = (
        db.scalar(
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.last_order_date < loyal_cutoff,
                Customer.last_order_date >= at_risk_cutoff,
            )
        )
        or 0
    )
    lapsed_count = (
        db.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.last_order_date < at_risk_cutoff)
        )
        or 0
    )
    order_count = db.scalar(select(func.count()).select_from(Order)) or 0
    avg_order_value = db.scalar(select(func.avg(Order.amount))) if order_count else 0.0
    top_category_row = db.execute(
        select(Order.category, func.count(Order.id).label("order_count"))
        .group_by(Order.category)
        .order_by(desc("order_count"))
        .limit(1)
    ).first()

    return {
        "total_customers": total_customers,
        "loyal_count": loyal_count,
        "at_risk_count": at_risk_count,
        "lapsed_count": lapsed_count,
        "avg_order_value": round(float(avg_order_value), 2),
        "top_category": top_category_row[0] if top_category_row else "N/A",
    }


@router.post("/{customer_id}/order-attributed")
async def attribute_customer_order(
    customer_id: str,
    payload: OrderAttributionRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Attribute an order to a campaign communication within a 7-day window."""
    now = datetime.utcnow()
    cutoff = now - timedelta(days=7)
    eligible_statuses = ("delivered", "read", "opened", "clicked")

    message = db.scalars(
        select(Message)
        .where(
            Message.customer_id == customer_id,
            Message.campaign_id == payload.campaign_id,
            Message.status.in_(eligible_statuses),
            Message.attributed_order == False,  # noqa: E712
        )
        .order_by(desc(Message.delivered_at), desc(Message.sent_at))
        .limit(1)
    ).first()

    if (
        message is None
        or message.delivered_at is None
        or message.delivered_at < cutoff
    ):
        return {"attributed": False, "reason": "no eligible message"}

    campaign = db.get(Campaign, payload.campaign_id)
    if campaign is None:
        return {"attributed": False, "reason": "campaign not found"}

    message.attributed_order = True
    message.attributed_at = now
    campaign.total_attributed_orders = (campaign.total_attributed_orders or 0) + 1
    campaign.total_attributed_revenue = round(
        float(campaign.total_attributed_revenue or 0.0) + payload.order_amount,
        2,
    )
    db.commit()

    return {
        "attributed": True,
        "campaign_id": payload.campaign_id,
        "customer_id": customer_id,
        "order_amount": payload.order_amount,
    }


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(customer_id: str, db: Session = Depends(get_db)) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer
