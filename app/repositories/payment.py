from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.repositories.base import BaseRepository
from app.schemas.types import PaymentStatus


class PaymentRepository(BaseRepository[Payment, UUID]):
    async def get_by_idempotency_key(
        self,
        session: AsyncSession,
        key: str,
    ) -> Payment | None:
        statement = select(self.model).where(self.model.idempotency_key == key)
        return await session.scalar(statement)

    async def get_for_update(
        self,
        session: AsyncSession,
        payment_id: UUID,
    ) -> Payment | None:
        """Lock and reload the payment within the caller's transaction."""
        statement = (
            select(self.model)
            .where(self.model.id == payment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await session.scalar(statement)

    async def list(
        self,
        session: AsyncSession,
        *,
        email: str | None = None,
        status: PaymentStatus | None = None,
    ) -> list[Payment]:
        statement = select(self.model)
        if email is not None:
            statement = statement.where(self.model.email == email)
        if status is not None:
            statement = statement.where(self.model.status == status)
        statement = statement.order_by(
            self.model.created_at.desc(), self.model.id.desc()
        )
        result = await session.scalars(statement)
        return list(result.all())


payment_repository = PaymentRepository(Payment)
