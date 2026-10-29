"""
The webhook notifications and their deliveries. Nothing here is specific to one event: see events.py for those.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WebhookEvent(Enum):
    CONVERSATION_COMPLETED = "conversation.completed"


class WebhookNotification(BaseModel):
    """
    What the platform decrypts from the body. The same envelope for every event; what is specific is in `data`.
    """
    event: WebhookEvent
    version: int = Field(description="The version of the shape of `data` for this event.")
    delivery_id: str = Field(description="The same in every attempt of one notification: dedupe on it.")
    sent_at: datetime = Field(description="When this attempt was sent.")
    external_id: str
    data: dict[str, Any]


class DeliveryStatus(Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class WebhookDelivery(BaseModel):
    """
    One notification and the outcome of its attempts, as stored. Neither the body nor the data are kept: each attempt
    builds them again from `event_ref`, so a retry carries the current data.
    """
    id: str
    event: WebhookEvent
    external_id: str
    event_ref: dict[str, Any]
    """
    What identifies the event, e.g. the session id; its data is built from it at send time. JSON values only.
    Unique with the event and external_id, so the same thing is notified once even if it is emitted twice.
    """
    status: DeliveryStatus
    attempts: int = 0
    next_attempt_at: datetime
    lease_until: datetime
    """
    An attempt in progress holds the delivery until then, so no other attempt sends it at the same time. On-prem runs
    one backend process today, but the lease also makes an attempt interrupted by a restart be retried once the lease
    is over, and keeps it right if several instances run the retries.
    """
    url: Optional[str] = None
    """
    Where the last attempt was sent.
    """
    last_attempt_at: Optional[datetime] = None
    last_status_code: Optional[int] = None
    last_error: Optional[str] = None
    created_at: datetime
