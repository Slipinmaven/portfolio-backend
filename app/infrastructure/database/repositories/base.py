from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.base import Base

EntityT = TypeVar("EntityT", bound=Base)
KeyT = TypeVar("KeyT")


class BaseRepository(Generic[EntityT, KeyT]):
    def __init__(self, session: AsyncSession, model: type[EntityT]) -> None:
        self.session = session
        self.model = model

    async def get_by_id(self, entity_id: KeyT) -> EntityT | None:
        return await self.session.get(self.model, entity_id)

    async def get_all(self) -> list[EntityT]:
        result = await self.session.scalars(select(self.model))
        return list(result.all())

    async def create(self, entity: EntityT) -> EntityT:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity: EntityT) -> None:
        await self.session.delete(entity)
        await self.session.flush()
