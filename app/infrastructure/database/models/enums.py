from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"

class ProjectStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

class PostKind(str, Enum):
    ARTICLE = "ARTICLE"
    NOTE = "NOTE"

class PostStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

class PageStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

class PageRevisionState(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"

class DevelopmentStatus(str, Enum):
    PLANNING = "PLANNING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"
    CANCELLED = "CANCELLED"

class MediaKind(str, Enum):
    IMAGE = "IMAGE"
    DOCUMENT = "DOCUMENT"
    VIDEO = "VIDEO"

class ProjectMediaRole(str, Enum):
    COVER = "COVER"
    GALLERY = "GALLERY"
    INLINE = "INLINE"
    ATTACHMENT = "ATTACHMENT"

class PostMediaRole(str, Enum):
    INLINE = "INLINE"
    ATTACHMENT = "ATTACHMENT"

class SiteLinkPlatform(str, Enum):
    GITHUB = "GITHUB"
    LINKEDIN = "LINKEDIN"
    X = "X"
    YOUTUBE = "YOUTUBE"
    TIKTOK = "TIKTOK"
    INSTAGRAM = "INSTAGRAM"
    BLUESKY = "BLUESKY"
    MASTODON = "MASTODON"
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"
    OTHER = "OTHER"

class ResourceType(str, Enum):
    ARTICLE = "ARTICLE"
    BOOK = "BOOK"
    COURSE = "COURSE"
    DOCS = "DOCS"
    TOOL = "TOOL"
    VIDEO = "VIDEO"
    OTHER = "OTHER"

class ResourceStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

class NavigationMenu(str, Enum):
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    MOBILE = "MOBILE"

class NavigationLinkType(str, Enum):
    NONE = "NONE"
    PAGE = "PAGE"
    ROUTE = "ROUTE"
    PROJECT = "PROJECT"
    POST = "POST"
    CATEGORY = "CATEGORY"
    EXTERNAL = "EXTERNAL"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    TEXT = "TEXT"
