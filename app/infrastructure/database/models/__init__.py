"""Import ORM models here so Alembic can discover their tables."""

from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.login_attempt import LoginAttempt
from app.infrastructure.database.models.session import Session
from app.infrastructure.database.models.trusted_device import TrustedDevice
from app.infrastructure.database.models.user import User
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.category import Category
from app.infrastructure.database.models.project_category import ProjectCategory
from app.infrastructure.database.models.tag import Tag
from app.infrastructure.database.models.project_tag import ProjectTag
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.media_upload_job import MediaUploadJob
from app.infrastructure.database.models.media_link import MediaLink
from app.infrastructure.database.models.project_media import ProjectMedia
from app.infrastructure.database.models.post import Post
from app.infrastructure.database.models.post_category import PostCategory
from app.infrastructure.database.models.post_media import PostMedia
from app.infrastructure.database.models.post_project import post_projects
from app.infrastructure.database.models.page import Page
from app.infrastructure.database.models.page_revision import PageRevision
from app.infrastructure.database.models.page_media import PageMedia
from app.infrastructure.database.models.site_settings import SiteSettings
from app.infrastructure.database.models.site_link import SiteLink
from app.infrastructure.database.models.resource import Resource
from app.infrastructure.database.models.post_resource import PostResource
from app.infrastructure.database.models.project_resource import ProjectResource
from app.infrastructure.database.models.navigation_item import NavigationItem

__all__ = [
    "AuditLog",
    "LoginAttempt",
    "Session",
    "TrustedDevice",
    "User",
    "Project",
    "Category",
    "ProjectCategory",
    "Tag",
    "ProjectTag",
    "Media",
    "MediaUploadJob",
    "MediaLink",
    "ProjectMedia",
    "Post",
    "PostCategory",
    "PostMedia",
    "post_projects",
    "Page",
    "PageRevision",
    "PageMedia",
    "SiteSettings",
    "SiteLink",
    "Resource",
    "PostResource",
    "ProjectResource",
    "NavigationItem",
]
