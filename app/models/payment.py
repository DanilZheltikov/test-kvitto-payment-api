from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.schemas.types import PaymentMethod, PaymentStatus


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    tariff_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tariffs.id", ondelete="RESTRICT"),
        nullable=False
    )
    email: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(
            PaymentMethod,
            name="payment_method",
            values_callable=lambda members: [
                member.value for member in members
            ],
        ),
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            name="payment_status",
            values_callable=lambda members: [
                member.value for member in members
            ],
        ),
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default=text("'pending'"),
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0")
    )
    installment_months: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )
    schedule: Mapped[list[int] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_payments_idempotency_key"
        ),
        CheckConstraint(
            "amount >= 0",
            name="ck_payments_amount_nonnegative"
        ),
        CheckConstraint(
            "discount >= 0",
            name="ck_payments_discount_nonnegative"
        ),
        CheckConstraint(
            "(method = 'installment' "
            "AND installment_months IS NOT NULL "
            "AND installment_months IN (3, 6, 12) "
            "AND schedule IS NOT NULL "
            "AND jsonb_typeof(schedule) = 'array') "
            "OR (method IN ('card', 'sbp') "
            "AND installment_months IS NULL AND schedule IS NULL)",
            name="ck_payments_installment_fields",
        ),
    )
