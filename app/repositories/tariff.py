from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tariff import Tariff
from app.repositories.base import BaseRepository


class TariffRepository(BaseRepository[Tariff, int]):
    async def add_if_missing(
        self,
        session: AsyncSession,
        title: str,
        price: int,
    ) -> None:
        statement = (
            insert(self.model)
            .values(title=title, price=price)
            .on_conflict_do_nothing(index_elements=[self.model.title])
        )
        await session.execute(statement)

    async def list(self, session: AsyncSession) -> list[Tariff]:
        statement = select(self.model).order_by(self.model.id)
        result = await session.scalars(statement)
        return list(result.all())


tariff_repository = TariffRepository(Tariff)
