from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.enums import NavigationMenu
from app.infrastructure.database.models.navigation_item import NavigationItem


class NavigationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_menu(self, menu: NavigationMenu) -> list[NavigationItem]:
        result = await self.session.scalars(
            select(NavigationItem)
            .where(NavigationItem.menu == menu)
            .order_by(
                NavigationItem.parent_id.is_not(None),
                NavigationItem.parent_id,
                NavigationItem.display_order,
                NavigationItem.id,
            )
        )
        return list(result.all())

    async def replace_menu(
        self,
        menu: NavigationMenu,
        items: list[NavigationItem],
    ) -> None:
        await self.session.execute(
            delete(NavigationItem).where(NavigationItem.menu == menu)
        )
        await self.session.flush()
        self.session.add_all(items)
        await self.session.flush()
