import random
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
            func.min(Order.order_date),
        ).where(Order.customer_id == customer_id)
    ).one()
    customer = db.get(Customer, customer_id)
    if customer is None:
        return
    customer.total_orders = aggregates[0]
    customer.total_spend = round(float(aggregates[1] or 0.0), 2)
    customer.last_order_date = aggregates[2]
    customer.first_order_date = aggregates[3]

    orders = db.scalars(
        select(Order).where(Order.customer_id == customer_id).order_by(Order.order_date)
    ).all()
    if not orders:
        return

    if customer.gender == "F":
        customer.preferred_channel = random.choices(
            ["whatsapp", "email", "sms"],
            weights=[60, 25, 15],
            k=1,
        )[0]
    else:
        customer.preferred_channel = random.choices(
            ["whatsapp", "sms", "email"],
            weights=[45, 30, 25],
            k=1,
        )[0]
    weekend_orders = sum(1 for order in orders if order.order_date.weekday() >= 5)
    customer.preferred_day = "Weekends" if weekend_orders / len(orders) > 0.6 else "Weekdays"

    top_category = _top_category(customer_id, db)
    next_best_lookup = {
        "Ethnic Wear": "Accessories",
        "Footwear": "Activewear",
        "Skincare": "Accessories",
        "Accessories": "Ethnic Wear",
        "Activewear": "Footwear",
    }
    customer.next_best_category = next_best_lookup.get(top_category)

    recency_days = (datetime.utcnow() - customer.last_order_date).days
    if customer.total_orders <= 1:
        customer.rfm_persona = "New" if recency_days <= 90 else "Solo Buyer"
    elif recency_days <= 30 and customer.total_spend > 15000:
        customer.rfm_persona = "Champion"
    elif recency_days <= 60:
        customer.rfm_persona = "Loyal"
    elif recency_days <= 120:
        customer.rfm_persona = "At Risk"
    else:
        customer.rfm_persona = "Lapsed"


def _top_category(customer_id: str, db: Session) -> str:
    row = db.execute(
        select(Order.category, func.count(Order.id).label("count"))
        .where(Order.customer_id == customer_id)
        .group_by(Order.category)
        .order_by(desc("count"))
        .limit(1)
    ).first()
    return row[0] if row else "N/A"


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
    search: str | None = None,
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

    if search is not None and search.strip():
        term = f"%{search.strip()}%"
        filters.append((Customer.name.ilike(term)) | (Customer.city.ilike(term)))
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


@router.get("/{customer_id}/profile")
async def get_customer_profile(
    customer_id: str,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return a rich CDP-style customer profile with RFM and behaviour signals."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    now = datetime.utcnow()
    last_order = db.scalars(
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(desc(Order.order_date))
        .limit(1)
    ).first()
    top_category = _top_category(customer_id, db)
    campaigns_received = (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.customer_id == customer_id)
        )
        or 0
    )
    campaigns_opened = (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.customer_id == customer_id,
                Message.status.in_(["opened", "clicked"]),
            )
        )
        or 0
    )

    recency_days = (
        (now - customer.last_order_date).days if customer.last_order_date else 0
    )
    first_order_months_ago = (
        max(0, int((now - customer.first_order_date).days // 30))
        if customer.first_order_date
        else 0
    )
    avg_transactional_value = (
        round(customer.total_spend / customer.total_orders, 2)
        if customer.total_orders
        else 0.0
    )

    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "gender": customer.gender,
        "city": customer.city,
        "age": customer.age,
        "rfm_persona": customer.rfm_persona or "N/A",
        "recency_days": recency_days,
        "frequency": customer.total_orders,
        "first_order_months_ago": first_order_months_ago,
        "avg_transactional_value": avg_transactional_value,
        "last_bought_product": last_order.product_name if last_order else "N/A",
        "next_best_category": customer.next_best_category or "N/A",
        "preferred_channel": customer.preferred_channel or "N/A",
        "preferred_day": customer.preferred_day or "N/A",
        "top_category": top_category,
        "total_spend": round(customer.total_spend, 2),
        "campaigns_received": campaigns_received,
        "campaigns_opened": campaigns_opened,
    }


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(customer_id: str, db: Session = Depends(get_db)) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer
