from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidInstallmentMonths,
    InvalidPromoCode,
    InvalidTransition,
    PaymentNotFound,
    TariffNotFound,
)
from app.core.constants import (
    ALLOWED_TRANSITIONS,
    DEFAULT_DISCOUNT_PERCENT,
    NAME_IDEMPOTENCY_KEY_CONSTRAINT,
    PROMO_DISCOUNTS_PERCENT,
    UNIQUE_VIOLATION_CODE
)
from app.models.payment import Payment
from app.repositories.payment import payment_repository
from app.repositories.tariff import tariff_repository
from app.schemas.payment import PaymentCreate
from app.schemas.types import PaymentMethod, PaymentStatus
from app.services.money import apply_discount, build_schedule


class PaymentService:
    def _validate_create(self, data: PaymentCreate) -> None:
        if (
            data.promo_code is not None
            and data.promo_code.upper() not in PROMO_DISCOUNTS_PERCENT
        ):
            raise InvalidPromoCode(data.promo_code)

        months = data.installment_months
        if data.method == PaymentMethod.INSTALLMENT:
            if months is None:
                raise InvalidInstallmentMonths(
                    months,
                    "Installment months are required for installment payments"
                )
        elif months is not None:
            raise InvalidInstallmentMonths(
                months,
                "Installment months are only allowed for installment payments"
            )

    @staticmethod
    def is_idempotency_conflict(exc: IntegrityError) -> bool:
        driver_error = exc.driver_exception

        return (
            getattr(driver_error, "sqlstate", None) == UNIQUE_VIOLATION_CODE
            and getattr(driver_error, "constraint_name", None)
            == NAME_IDEMPOTENCY_KEY_CONSTRAINT
        )

    async def create(
        self,
        session: AsyncSession,
        data: PaymentCreate,
        idempotency_key: str | None = None,
    ) -> tuple[Payment, bool]:
        """
        Return (payment, created); own the transaction on a fresh session.
        """
        self._validate_create(data)
        try:
            async with session.begin():
                if idempotency_key is not None:
                    existing = await payment_repository.get_by_idempotency_key(
                        session,
                        idempotency_key
                    )
                    if existing is not None:
                        return existing, False

                tariff = await tariff_repository.get_by_id(
                    session,
                    data.tariff_id
                )
                if tariff is None:
                    raise TariffNotFound(data.tariff_id)

                discount_percent = (
                    PROMO_DISCOUNTS_PERCENT[data.promo_code.upper()]
                    if data.promo_code is not None
                    else DEFAULT_DISCOUNT_PERCENT
                )
                amount, discount = apply_discount(
                    tariff.price,
                    discount_percent
                )
                schedule = None
                if data.installment_months is not None:
                    schedule = build_schedule(amount, data.installment_months)

                payment = Payment(
                    tariff_id=tariff.id,
                    email=str(data.email),
                    method=data.method,
                    status=PaymentStatus.PENDING,
                    amount=amount,
                    discount=discount,
                    installment_months=data.installment_months,
                    schedule=schedule,
                    idempotency_key=idempotency_key,
                )
                await payment_repository.add(session, payment)
            return payment, True

        except IntegrityError as error:
            if not self.is_idempotency_conflict(error):
                raise
            async with session.begin():
                existing = await payment_repository.get_by_idempotency_key(
                    session,
                    idempotency_key
                )
                if existing is None:
                    raise
                return existing, False

    async def get_by_id(
        self,
        session: AsyncSession,
        payment_id: UUID,
    ) -> Payment:
        payment = await payment_repository.get_by_id(session, payment_id)
        if payment is None:
            raise PaymentNotFound
        return payment

    async def change_status(
        self,
        session: AsyncSession,
        payment_id: UUID,
        status: PaymentStatus,
    ) -> None:
        async with session.begin():
            payment = await payment_repository.get_for_update(
                session,
                payment_id
            )
            if payment is None:
                raise PaymentNotFound
            if status not in ALLOWED_TRANSITIONS[payment.status]:
                raise InvalidTransition
            payment.status = status

    async def list(
        self,
        session: AsyncSession,
        *,
        email: str | None = None,
        status: PaymentStatus | None = None,
    ) -> list[Payment]:
        return await payment_repository.list(
            session,
            email=email,
            status=status
        )


payment_service = PaymentService()
