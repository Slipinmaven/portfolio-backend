from fastapi import APIRouter

from app.presentation.api.v1.endpoints import (
    auth,
    categories,
    health,
    media,
    navigation,
    pages,
    project_media,
    posts,
    projects,
    resources,
    site_settings,
    tags,
    users,
)

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["auth"])
router.include_router(users.router)
router.include_router(projects.router)
router.include_router(posts.router)
router.include_router(resources.router)
router.include_router(navigation.router)
router.include_router(pages.router)
router.include_router(site_settings.router)
router.include_router(media.router)
router.include_router(project_media.router)
router.include_router(categories.router)
router.include_router(tags.router)
