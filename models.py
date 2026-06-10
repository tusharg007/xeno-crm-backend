from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    phone: Mapped[str]
    gender: Mapped[str]
    city: Mapped[str]
    age: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    total_orders: Mapped[int] = mapped_column(default=0)
    total_spend: Mapped[float] = mapped_column(default=0.0)
    last_order_date: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    orders: Mapped[List["Order"]] = relationship(back_populates="customer")
    messages: Mapped[List["Message"]] = relationship(back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    amount: Mapped[float]
    category: Mapped[str]
    product_name: Mapped[str]
    order_date: Mapped[datetime]
    channel: Mapped[str]
    customer: Mapped["Customer"] = relationship(back_populates="orders")


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str]
    description: Mapped[str]
    filter_rules: Mapped[str]
    customer_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(default="human")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str]
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"))
    message_template: Mapped[str]
    channel: Mapped[str]
    status: Mapped[str] = mapped_column(default="draft")
    total_sent: Mapped[int] = mapped_column(default=0)
    total_delivered: Mapped[int] = mapped_column(default=0)
    total_opened: Mapped[int] = mapped_column(default=0)
    total_clicked: Mapped[int] = mapped_column(default=0)
    total_failed: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    launched_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    segment: Mapped["Segment"] = relationship()
    messages: Mapped[List["Message"]] = relationship(back_populates="campaign")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    personalized_message: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued")
    sent_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    clicked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    campaign: Mapped["Campaign"] = relationship(back_populates="messages")
    customer: Mapped["Customer"] = relationship(back_populates="messages")
