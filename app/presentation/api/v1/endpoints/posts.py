from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.application.posts.dto import (
    PostCreateDTO,
    PostListFilters,
    PostUpdateDTO,
)
from app.application.posts.markdown import render_markdown
from app.application.posts.service import PostService
from app.infrastructure.database.models.enums import (
    MediaKind,
    PostKind,
    PostMediaRole,
    ProjectStatus,
    ResourceStatus,
)
from app.infrastructure.database.models.post import Post
from app.infrastructure.database.models.resource import Resource
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_editor_or_admin
from app.presentation.dependencies.services import get_post_service
from app.presentation.schemas.posts import (
    MarkdownPreviewRequest,
    MarkdownPreviewResponse,
    PostAdminListResponse,
    PostAdminResponse,
    PostAttachmentResponse,
    PostCreateRequest,
    PostListRequest,
    PostUpdateRequest,
    PublicPostListResponse,
    PublicPostResponse,
    PostProjectResponse,
    PublicPostSummaryResponse,
)
from app.presentation.schemas.resources import ResourceLinkResponse

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post(
    "",
    response_model=PostAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_post(
    request: PostCreateRequest,
    editor: User = Depends(require_editor_or_admin),
    post_service: PostService = Depends(get_post_service),
) -> PostAdminResponse:
    post = await post_service.create_post(
        PostCreateDTO(
            kind=request.kind,
            title=request.title,
            slug=request.slug,
            summary=request.summary,
            body=request.body,
            category_ids=tuple(request.category_ids),
            attachment_media_ids=tuple(request.attachment_media_ids),
            project_ids=tuple(request.project_ids),
            resource_ids=tuple(request.resource_ids),
        ),
        actor_id=editor.id,
    )
    return _admin_response(post)


@router.get("/admin", response_model=PostAdminListResponse)
async def list_posts_for_management(
    query: PostListRequest = Depends(),
    _editor: User = Depends(require_editor_or_admin),
    post_service: PostService = Depends(get_post_service),
) -> PostAdminListResponse:
    posts, total = await post_service.list_posts(
        PostListFilters(
            offset=query.offset,
            limit=query.limit,
            kind=query.kind,
            status=query.status,
            category_id=query.category_id,
        )
    )
    return PostAdminListResponse(
        posts=[_admin_response(post) for post in posts],
        total=total,
        offset=query.offset,
        limit=query.limit,
    )


@router.post(
    "/admin/preview",
    response_model=MarkdownPreviewResponse,
)
async def preview_post_markdown(
    request: MarkdownPreviewRequest,
    _editor: User = Depends(require_editor_or_admin),
) -> MarkdownPreviewResponse:
    return MarkdownPreviewResponse(
        html=render_markdown(
            request.body,
            media_url_resolver=lambda media_id: (
                f"/api/v1/media/admin/{media_id}/content"
            ),
            media_video_url_resolver=lambda media_id: (
                f"/api/v1/media/admin/{media_id}/content"
            ),
            media_download_url_resolver=lambda media_id: (
                f"/api/v1/media/admin/{media_id}/content"
            ),
        )
    )


@router.get("/admin/{post_id}", response_model=PostAdminResponse)
async def get_post_for_management(
    post_id: UUID,
    _editor: User = Depends(require_editor_or_admin),
    post_service: PostService = Depends(get_post_service),
) -> PostAdminResponse:
    post = await post_service.get_post_for_management(post_id)
    return _admin_response(post)


@router.patch("/admin/{post_id}", response_model=PostAdminResponse)
async def update_post(
    post_id: UUID,
    request: PostUpdateRequest,
    editor: User = Depends(require_editor_or_admin),
    post_service: PostService = Depends(get_post_service),
) -> PostAdminResponse:
    post = await post_service.update_post(
        post_id,
        PostUpdateDTO(
            title=request.title,
            slug=request.slug,
            summary=request.summary,
            body=request.body,
            status=request.status,
            category_ids=(
                tuple(request.category_ids)
                if request.category_ids is not None
                else None
            ),
            attachment_media_ids=(
                tuple(request.attachment_media_ids)
                if request.attachment_media_ids is not None
                else None
            ),
            project_ids=(
                tuple(request.project_ids)
                if request.project_ids is not None
                else None
            ),
            resource_ids=(
                tuple(request.resource_ids)
                if request.resource_ids is not None
                else None
            ),
            fields_set=frozenset(request.model_fields_set),
        ),
        actor_id=editor.id,
    )
    return _admin_response(post)


@router.get("/{kind}", response_model=PublicPostListResponse)
async def list_published_posts(
    kind: PostKind,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    category_id: UUID | None = Query(default=None),
    post_service: PostService = Depends(get_post_service),
) -> PublicPostListResponse:
    posts, total = await post_service.list_posts(
        PostListFilters(
            offset=offset,
            limit=limit,
            kind=kind,
            published_only=True,
            category_id=category_id,
        )
    )
    return PublicPostListResponse(
        posts=[_public_summary_response(post) for post in posts],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{kind}/{slug}", response_model=PublicPostResponse)
async def get_published_post(
    kind: PostKind,
    slug: str,
    post_service: PostService = Depends(get_post_service),
) -> PublicPostResponse:
    post = await post_service.get_published_post(kind, slug)
    inline_media_urls = {
        association.media_id: f"/api/v1/media/{association.media_id}/content"
        for association in post.media_associations
        if association.role == PostMediaRole.INLINE
        and association.media.kind == MediaKind.IMAGE
    }
    return PublicPostResponse(
        **_public_summary_response(post).model_dump(),
        body_html=render_markdown(
            post.body,
            media_url_resolver=lambda media_id: inline_media_urls.get(media_id),
        ),
        attachments=_attachment_responses(post),
        related_projects=[
            PostProjectResponse(
                id=project.id,
                title=project.title,
                slug=project.slug,
                short_description=project.short_description,
            )
            for project in post.projects
            if project.status == ProjectStatus.PUBLISHED
        ],
        resources=[
            _resource_link_response(association.resource)
            for association in post.resource_associations
            if ResourceStatus(association.resource.status) == ResourceStatus.PUBLISHED
        ],
    )


def _admin_response(post: Post) -> PostAdminResponse:
    return PostAdminResponse(
        id=post.id,
        kind=post.kind,
        title=post.title,
        slug=post.slug,
        summary=post.summary,
        body=post.body,
        status=post.status,
        published_at=post.published_at,
        archived_at=post.archived_at,
        created_at=post.created_at,
        updated_at=post.updated_at,
        category_ids=[category.id for category in post.categories],
        project_ids=[project.id for project in post.projects],
        resource_ids=[
            association.resource_id for association in post.resource_associations
        ],
        attachments=_attachment_responses(post, admin=True),
    )


def _public_summary_response(post: Post) -> PublicPostSummaryResponse:
    return PublicPostSummaryResponse(
        id=post.id,
        kind=post.kind,
        title=post.title,
        slug=post.slug,
        summary=post.summary,
        published_at=post.published_at,
        categories=[
            category
            for category in post.categories
            if category.is_active
        ],
    )


def _attachment_responses(
    post: Post,
    *,
    admin: bool = False,
) -> list[PostAttachmentResponse]:
    return [
        PostAttachmentResponse(
            media_id=association.media_id,
            title=association.media.title,
            original_filename=association.media.original_filename,
            mime_type=association.media.mime_type,
            size_bytes=association.media.size_bytes,
            file_url=(
                f"/api/v1/media/admin/{association.media_id}/content"
                if admin
                else f"/api/v1/media/{association.media_id}/content"
            ),
        )
        for association in post.media_associations
        if association.role == PostMediaRole.ATTACHMENT
    ]


def _resource_link_response(resource: Resource) -> ResourceLinkResponse:
    return ResourceLinkResponse(
        id=resource.id,
        title=resource.title,
        url=resource.url,
        resource_type=resource.resource_type,
        creator=resource.creator,
        summary=resource.summary,
        commentary_html=render_markdown(resource.commentary or ""),
    )
