from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.types import PaymentStatus


class BankWebhook(BaseModel):
    payment_id: UUID
    status: PaymentStatus


class WebhookResponse(BaseModel):
    result: Literal["ok"] = "ok"


class InvalidTransitionResponse(BaseModel):
    error: Literal["invalid_transition"] = "invalid_transition"
