from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.types import (
    InstallmentMonths,
    Money,
    PaymentMethod,
    PaymentStatus
)


class PaymentCreate(BaseModel):
    tariff_id: str = Field(min_length=1)
    email: EmailStr
    method: PaymentMethod
    installment_months: InstallmentMonths | None = None
    promo_code: str | None = None

    @field_validator("promo_code")
    @classmethod
    def validate_promo_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.upper() != "KVITTO10":
            raise ValueError("Unknown promo code")
        return value.upper()

    @field_validator("installment_months", mode="before")
    @classmethod
    def validate_months_type(cls, value: object) -> object:
        if value is not None and type(value) is not int:
            raise ValueError("Installment months must be an integer")
        return value

    @model_validator(mode="after")
    def validate_installment(self) -> Self:
        if (
            self.method == PaymentMethod.INSTALLMENT
            and self.installment_months is None
        ):
            raise ValueError(
                "Installment months are required for installment payments"
            )
        if (
            self.method != PaymentMethod.INSTALLMENT
            and self.installment_months is not None
        ):
            raise ValueError(
                "Installment months are only allowed for installment payments"
            )
        return self


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: PaymentStatus
    tariff_id: str
    amount: Money
    discount: Money
    method: PaymentMethod
    installment_months: InstallmentMonths | None
    schedule: list[Money] | None
    email: EmailStr
    created_at: datetime
