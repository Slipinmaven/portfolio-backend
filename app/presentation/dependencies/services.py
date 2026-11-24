from fastapi import Depends

from app.application.auth.service import AuthService
from app.application.categories.service import CategoryService
from app.application.media.service import MediaService
from app.application.projects.service import ProjectService
from app.application.projects.media_service import ProjectMediaService
from app.application.posts.service import PostService
from app.application.pages.service import PageService
from app.application.tags.service import TagService
from app.application.users.service import UserService
from app.application.site_settings.service import SiteSettingsService
from app.application.resources.service import ResourceService
from app.application.navigation.service import NavigationService
from app.core.config import settings
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
from app.presentation.dependencies.database import (
    get_auth_unit_of_work,
    get_catalog_unit_of_work,
    get_media_unit_of_work,
    get_project_unit_of_work,
    get_posts_unit_of_work,
    get_pages_unit_of_work,
    get_site_settings_unit_of_work,
    get_resources_unit_of_work,
    get_navigation_unit_of_work,
)


def get_auth_service(
    unit_of_work: AuthenticationUnitOfWork = Depends(get_auth_unit_of_work),
) -> AuthService:
    return AuthService(unit_of_work=unit_of_work)


def get_user_service(
    unit_of_work: AuthenticationUnitOfWork = Depends(get_auth_unit_of_work),
) -> UserService:
    return UserService(unit_of_work=unit_of_work)


def get_project_service(
    unit_of_work: ProjectUnitOfWork = Depends(get_project_unit_of_work),
) -> ProjectService:
    return ProjectService(unit_of_work=unit_of_work)


def get_project_media_service(
    unit_of_work: ProjectUnitOfWork = Depends(get_project_unit_of_work),
) -> ProjectMediaService:
    return ProjectMediaService(unit_of_work=unit_of_work)

def get_post_service(
    unit_of_work: PostsUnitOfWork = Depends(get_posts_unit_of_work),
) -> PostService:
    return PostService(unit_of_work=unit_of_work)

def get_page_service(
    unit_of_work: PagesUnitOfWork = Depends(get_pages_unit_of_work),
) -> PageService:
    return PageService(unit_of_work=unit_of_work)

def get_media_service(
    unit_of_work: MediaUnitOfWork = Depends(get_media_unit_of_work),
) -> MediaService:
    return MediaService(unit_of_work=unit_of_work, configuration=settings)


def get_category_service(
    unit_of_work: CatalogUnitOfWork = Depends(get_catalog_unit_of_work),
) -> CategoryService:
    return CategoryService(unit_of_work=unit_of_work)


def get_tag_service(
    unit_of_work: CatalogUnitOfWork = Depends(get_catalog_unit_of_work),
) -> TagService:
    return TagService(unit_of_work=unit_of_work)


def get_site_settings_service(
    unit_of_work: SiteSettingsUnitOfWork = Depends(
        get_site_settings_unit_of_work
    ),
) -> SiteSettingsService:
    return SiteSettingsService(unit_of_work=unit_of_work)


def get_resource_service(
    unit_of_work: ResourcesUnitOfWork = Depends(get_resources_unit_of_work),
) -> ResourceService:
    return ResourceService(unit_of_work=unit_of_work)


def get_navigation_service(
    unit_of_work: NavigationUnitOfWork = Depends(get_navigation_unit_of_work),
) -> NavigationService:
    return NavigationService(unit_of_work=unit_of_work)
