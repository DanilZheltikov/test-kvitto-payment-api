from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

Money = Annotated[
    int,
    Field(strict=True, ge=0, description="Amount in kopecks")
]
InstallmentMonths = Literal[3, 6, 12]


class PaymentMethod(StrEnum):
    CARD = "card"
    SBP = "sbp"
    INSTALLMENT = "installment"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
