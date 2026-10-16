from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tariff import Tariff
from app.repositories.base import BaseRepository


class TariffRepository(BaseRepository[Tariff, int]):
    async def list(self, session: AsyncSession) -> list[Tariff]:
        statement = select(self.model).order_by(self.model.id)
        result = await session.scalars(statement)
        return list(result.all())


tariff_repository = TariffRepository(Tariff)
