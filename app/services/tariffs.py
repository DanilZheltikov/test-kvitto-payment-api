from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_TARIFFS
from app.models.tariff import Tariff
from app.repositories.tariff import tariff_repository


class TariffService:
    async def list(self, session: AsyncSession) -> list[Tariff]:
        return await tariff_repository.list(session)

    async def seed(self, session: AsyncSession) -> None:
        async with session.begin():
            for title, price in DEFAULT_TARIFFS:
                await tariff_repository.add_if_missing(session, title, price)


tariff_service = TariffService()
