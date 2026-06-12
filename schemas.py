import json
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class CustomerCreate(BaseModel):
    name: str
    email: str
    phone: str
    gender: str
    city: str
    age: int


class CustomerRead(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    gender: str
    city: str
    age: int
    created_at: datetime
    total_orders: int
    total_spend: float
    last_order_date: Optional[datetime]
    preferred_channel: Optional[str] = None
    preferred_day: Optional[str] = None
    next_best_category: Optional[str] = None
    rfm_persona: Optional[str] = None
    first_order_date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CustomerBulkCreate(BaseModel):
    customers: list[CustomerCreate]


class OrderCreate(BaseModel):
    customer_id: str
    amount: float
    category: str
    product_name: str
    order_date: datetime
    channel: str


class OrderRead(BaseModel):
    id: str
    customer_id: str
    amount: float
    category: str
    product_name: str
    order_date: datetime
    channel: str

    model_config = ConfigDict(from_attributes=True)


class OrderBulkCreate(BaseModel):
    orders: list[OrderCreate]


class SegmentCreate(BaseModel):
    name: str
    description: str
    filter_rules: dict[str, Any]


class SegmentRead(BaseModel):
    id: str
    name: str
    description: str
    filter_rules: dict[str, Any]
    customer_count: int
    created_at: datetime
    created_by: str

    @field_validator("filter_rules", mode="before")
    @classmethod
    def parse_filter_rules(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("filter_rules must be a JSON object")

    model_config = ConfigDict(from_attributes=True)


class JourneyCreate(BaseModel):
    name: str
    journey_type: str
    trigger_rules: dict[str, Any]
    message_template: str
    channel: str = "whatsapp"


class JourneyRead(BaseModel):
    id: str
    name: str
    journey_type: str
    status: str
    trigger_rules: dict[str, Any]
    message_template: str
    channel: str
    customers_enrolled: int
    campaigns_triggered: int
    created_at: datetime

    @field_validator("trigger_rules", mode="before")
    @classmethod
    def parse_trigger_rules(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("trigger_rules must be a JSON object")

    model_config = ConfigDict(from_attributes=True)


class CampaignCreate(BaseModel):
    name: str
    segment_id: str
    message_template: str
    channel: str


class CampaignRead(BaseModel):
    id: str
    name: str
    segment_id: str
    message_template: str
    channel: str
    status: str
    total_sent: int
    total_delivered: int
    total_read: int
    total_opened: int
    total_clicked: int
    total_failed: int
    total_attributed_orders: int
    total_attributed_revenue: float
    created_at: datetime
    launched_at: Optional[datetime]

    @computed_field
    @property
    def delivery_rate(self) -> float:
        return self.total_delivered / self.total_sent if self.total_sent > 0 else 0.0

    @computed_field
    @property
    def open_rate(self) -> float:
        return self.total_opened / self.total_delivered if self.total_delivered > 0 else 0.0

    @computed_field
    @property
    def read_rate(self) -> float:
        return self.total_read / self.total_delivered if self.total_delivered > 0 else 0.0

    @computed_field
    @property
    def click_rate(self) -> float:
        return self.total_clicked / self.total_opened if self.total_opened > 0 else 0.0

    @computed_field
    @property
    def attribution_rate(self) -> float:
        return (
            self.total_attributed_orders / self.total_sent
            if self.total_sent > 0
            else 0.0
        )

    model_config = ConfigDict(from_attributes=True)


class MessageRead(BaseModel):
    id: str
    campaign_id: str
    customer_id: str
    personalized_message: str
    status: str
    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]
    opened_at: Optional[datetime]
    clicked_at: Optional[datetime]
    failed_at: Optional[datetime]
    attributed_order: bool
    attributed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ReceiptPayload(BaseModel):
    message_id: str
    event: str
    timestamp: str


class OrderAttributionRequest(BaseModel):
    campaign_id: str
    order_amount: float


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    segment_preview: dict[str, Any] | None = None
    campaign_draft: dict[str, Any] | None = None
    awaiting_approval: bool = False
    pending_segment_id: str | None = None
    session_id: str = ""
