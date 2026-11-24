from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_db_session
from app.infrastructure.database.unit_of_work.authentication import AuthenticationUnitOfWork
from app.infrastructure.database.unit_of_work.catalog import CatalogUnitOfWork
from app.infrastructure.database.unit_of_work.media import MediaUnitOfWork
from app.infrastructure.database.unit_of_work.project import ProjectUnitOfWork
from app.infrastructure.database.unit_of_work.posts import PostsUnitOfWork
from app.infrastructure.database.unit_of_work.pages import PagesUnitOfWork
from app.infrastructure.database.unit_of_work.site_settings import (
    SiteSettingsUnitOfWork,
)
from app.infrastructure.database.unit_of_work.resources import ResourcesUnitOfWork
from app.infrastructure.database.unit_of_work.navigation import NavigationUnitOfWork


def get_auth_unit_of_work(
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticationUnitOfWork:
    return AuthenticationUnitOfWork(session=session)


def get_project_unit_of_work(
    session: AsyncSession = Depends(get_db_session),
) -> ProjectUnitOfWork:
    return ProjectUnitOfWork(session=session)

def get_posts_unit_of_work(
    session: AsyncSession = Depends(get_db_session),
) -> PostsUnitOfWork:
    return PostsUnitOfWork(session=session)

def get_pages_unit_of_work(
    session: AsyncSession = Depends(get_db_session),
) -> PagesUnitOfWork:
    return PagesUnitOfWork(session=session)

def get_catalog_unit_of_work(
    session: AsyncSession = Depends(get_db_session),
) -> CatalogUnitOfWork:
    return CatalogUnitOfWork(session=session)


def get_media_unit_of_work(
    session: AsyncSession = Depends(get_db_session),
) -> MediaUnitOfWork:
    return MediaUnitOfWork(session=session)


def get_site_settings_unit_of_work(
    session: AsyncSession = Depends(get_db_session),
) -> SiteSettingsUnitOfWork:
    return SiteSettingsUnitOfWork(session=session)


def get_resources_unit_of_work(
    session: AsyncSession = Depends(get_db_session),
) -> ResourcesUnitOfWork:
    return ResourcesUnitOfWork(session=session)


def get_navigation_unit_of_work(
    session: AsyncSession = Depends(get_db_session),
) -> NavigationUnitOfWork:
    return NavigationUnitOfWork(session=session)
