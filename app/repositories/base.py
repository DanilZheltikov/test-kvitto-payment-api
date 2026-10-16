from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base


ModelType = TypeVar("ModelType", bound=Base)
IdType = TypeVar("IdType", int, UUID)


class BaseRepository(Generic[ModelType, IdType]):
    def __init__(self, model: type[ModelType]) -> None:
        self.model = model

    async def get_by_id(
        self,
        session: AsyncSession,
        entity_id: IdType,
    ) -> ModelType | None:
        return await session.get(self.model, entity_id)

    async def add(
        self,
        session: AsyncSession,
        obj: ModelType,
    ) -> ModelType:
        session.add(obj)
        await session.flush()
        return obj
