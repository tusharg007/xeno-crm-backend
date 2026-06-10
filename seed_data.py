import random
import re
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import uuid4

from faker import Faker
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from database import SessionLocal, create_tables
from models import Campaign, Customer, Message, Order, Segment


fake = Faker("en_IN")
Faker.seed(42)
random.seed(42)

PRODUCTS = {
    "Ethnic Wear": [
        "Cotton Anarkali",
        "Block Print Kurta Set",
        "Embroidered Saree",
        "Silk Palazzo Set",
        "Mirror Work Lehenga",
        "Chanderi Suit Set",
    ],
    "Footwear": [
        "Kolhapuri Flats",
        "Block Heel Sandals",
        "Canvas Sneakers",
        "Leather Loafers",
        "Wedge Boots",
    ],
    "Skincare": [
        "Kumkumadi Face Oil",
        "Neem Clay Mask",
        "Rose Water Toner",
        "Vitamin C Serum",
        "Ubtan Face Wash",
    ],
    "Accessories": [
        "Oxidised Earrings",
        "Beaded Bracelet Set",
        "Embroidered Clutch",
        "Silk Scrunchie Pack",
        "Jute Tote Bag",
    ],
    "Activewear": [
        "Dry-fit Yoga Pants",
        "Sports Crop Top",
        "Running Shorts Set",
        "Gym Backpack",
        "Resistance Band Kit",
    ],
}

CATEGORY_WEIGHTS = {
    "Ethnic Wear": 35,
    "Footwear": 20,
    "Skincare": 20,
    "Accessories": 15,
    "Activewear": 10,
}

AMOUNT_RANGES = {
    "Ethnic Wear": (800, 5000),
    "Footwear": (600, 3500),
    "Skincare": (300, 2000),
    "Accessories": (200, 1500),
    "Activewear": (500, 4000),
}

CITY_COUNTS = {
    "Mumbai": 40,
    "Delhi": 40,
    "Bangalore": 30,
    "Pune": 20,
    "Hyderabad": 20,
    "Chennai": 20,
    "Kolkata": 10,
    "Ahmedabad": 7,
    "Jaipur": 7,
    "Surat": 6,
}


def _clean_name_part(value: str) -> str:
    cleaned = re.sub(r"[^a-z]", "", value.lower())
    return cleaned or "stylehub"


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [_clean_name_part(part) for part in full_name.split() if part.strip()]
    if not parts:
        return "stylehub", "customer"
    if len(parts) == 1:
        return parts[0], "customer"
    return parts[0], parts[-1]


def _unique_email(full_name: str, used_emails: set[str], index: int) -> str:
    first, last = _split_name(full_name)
    email = f"{first}{last}{index}@gmail.com"
    if email not in used_emails:
        used_emails.add(email)
        return email

    suffix = 1
    while True:
        fallback_email = f"{first}{last}{index}{suffix}@gmail.com"
        if fallback_email not in used_emails:
            used_emails.add(fallback_email)
            return fallback_email
        suffix += 1


def _phone_number() -> str:
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


def _customer_inputs() -> list[tuple[str, str]]:
    cities = [city for city, count in CITY_COUNTS.items() for _ in range(count)]
    genders = ["F"] * 120 + ["M"] * 80
    random.shuffle(cities)
    random.shuffle(genders)
    return list(zip(cities, genders))


def _create_customers() -> list[Customer]:
    used_emails: set[str] = set()
    customers: list[Customer] = []

    for index, (city, gender) in enumerate(_customer_inputs()):
        name = fake.name()
        customers.append(
            Customer(
                id=str(uuid4()),
                name=name,
                email=_unique_email(name, used_emails, index),
                phone=_phone_number(),
                gender=gender,
                city=city,
                age=int(random.triangular(20, 55, 30)),
                created_at=datetime.utcnow() - timedelta(days=random.randint(120, 720)),
            )
        )

    return customers


def _choose_category() -> str:
    categories = list(CATEGORY_WEIGHTS.keys())
    weights = list(CATEGORY_WEIGHTS.values())
    return random.choices(categories, weights=weights, k=1)[0]


def _order_datetime(reference: datetime, min_days: int, max_days: int) -> datetime:
    days_ago = random.randint(min_days, max_days)
    order_day = reference - timedelta(days=days_ago)
    if order_day.weekday() < 5:
        hour = random.randint(18, 22)
    else:
        hour = random.randint(0, 23)
    return order_day.replace(
        hour=hour,
        minute=random.randint(0, 59),
        second=random.randint(0, 59),
        microsecond=0,
    )


def _order_count_plan() -> list[int]:
    loyal = [random.randint(10, 14) for _ in range(40)]
    at_risk = [random.randint(4, 7) for _ in range(60)]
    lapsed = [random.randint(2, 4) for _ in range(60)]
    one_time = [random.randint(1, 2) for _ in range(40)]
    return loyal + at_risk + lapsed + one_time


def _segment_windows(index: int) -> tuple[int, int, int]:
    if index < 40:
        return 2, 20, 540
    if index < 100:
        return 46, 90, 365
    if index < 160:
        return 92, 180, 365
    return 182, 400, 400


def _create_order(customer_id: str, order_date: datetime) -> Order:
    category = _choose_category()
    low, high = AMOUNT_RANGES[category]
    return Order(
        id=str(uuid4()),
        customer_id=customer_id,
        amount=round(random.uniform(low, high), 2),
        category=category,
        product_name=random.choice(PRODUCTS[category]),
        order_date=order_date,
        channel=random.choices(["online", "offline"], weights=[70, 30], k=1)[0],
    )


def _create_orders(customers: list[Customer]) -> list[Order]:
    reference = datetime.utcnow()
    counts = _order_count_plan()
    orders: list[Order] = []

    for index, customer in enumerate(customers):
        recent_min, recent_max, span_max = _segment_windows(index)
        customer_orders: list[Order] = [
            _create_order(customer.id, _order_datetime(reference, recent_min, recent_max))
        ]

        for _ in range(counts[index] - 1):
            historical_min = min(recent_max + 1, span_max)
            customer_orders.append(
                _create_order(
                    customer.id,
                    _order_datetime(reference, historical_min, span_max),
                )
            )

        orders.extend(customer_orders)

    return orders


def _segment_order_counts(orders: list[Order], customers: list[Customer]) -> dict[str, int]:
    customer_positions = {customer.id: index for index, customer in enumerate(customers)}
    counts = {"loyal": 0, "at_risk": 0, "lapsed": 0, "one_time": 0}

    for order in orders:
        index = customer_positions[order.customer_id]
        if index < 40:
            counts["loyal"] += 1
        elif index < 100:
            counts["at_risk"] += 1
        elif index < 160:
            counts["lapsed"] += 1
        else:
            counts["one_time"] += 1

    return counts


def _update_customer_aggregates(customers: list[Customer], orders: list[Order]) -> None:
    orders_by_customer: dict[str, list[Order]] = defaultdict(list)
    for order in orders:
        orders_by_customer[order.customer_id].append(order)

    for customer in customers:
        customer_orders = orders_by_customer[customer.id]
        customer.total_orders = len(customer_orders)
        customer.total_spend = round(sum(order.amount for order in customer_orders), 2)
        customer.last_order_date = max(order.order_date for order in customer_orders)


def run_seed(db: Session = None) -> int:
    owns_session = db is None
    if db is None:
        db = SessionLocal()

    try:
        db.execute(delete(Message))
        db.execute(delete(Campaign))
        db.execute(delete(Segment))

        customer_count = db.scalar(select(func.count()).select_from(Customer)) or 0
        if customer_count == 0:
            print("Creating 200 customers...")
            customers = _create_customers()
            print("Creating orders for 4 RFM segments...")
            orders = _create_orders(customers)
            segment_counts = _segment_order_counts(orders, customers)
            print(f"Loyal (40 customers): ~{segment_counts['loyal']} orders")
            print(f"At-risk (60 customers): ~{segment_counts['at_risk']} orders")
            print(f"Lapsed (60 customers): ~{segment_counts['lapsed']} orders")
            print(f"One-time (40 customers): ~{segment_counts['one_time']} orders")
            print("Updating customer aggregates...")
            _update_customer_aggregates(customers, orders)
            db.bulk_save_objects(customers)
            db.bulk_save_objects(orders)
            db.flush()
            order_count = len(orders)
        else:
            order_count = db.scalar(select(func.count()).select_from(Order)) or 0

        db.commit()
        print(f"Done. 200 customers, {order_count} orders seeded.")
        return order_count
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    create_tables()
    run_seed()
