from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.schemas.types import (
    InstallmentMonths,
    Money,
    PaymentMethod,
    PaymentStatus
)


class PaymentCreate(BaseModel):
    tariff_id: int = Field(strict=True, gt=0)
    email: EmailStr
    method: PaymentMethod
    installment_months: InstallmentMonths | None = None
    promo_code: str | None = None

    @field_validator("promo_code")
    @classmethod
    def normalize_promo_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.upper() if value is not None else None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: PaymentStatus
    tariff_id: int
    amount: Money
    discount: Money
    method: PaymentMethod
    installment_months: InstallmentMonths | None
    schedule: list[Money] | None
    email: EmailStr
    created_at: datetime
