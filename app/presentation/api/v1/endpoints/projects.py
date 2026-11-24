from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.application.projects.dto import (
    ProjectCreateDTO,
    ProjectListFilters,
    ProjectUpdateDTO,
)
from app.application.projects.service import ProjectService
from app.application.posts.markdown import render_markdown
from app.infrastructure.database.models.enums import (
    MediaKind,
    ProjectMediaRole,
    ProjectStatus,
    ResourceStatus,
)
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.resource import Resource
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_editor_or_admin
from app.presentation.dependencies.services import get_project_service
from app.presentation.schemas.projects import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectAdminListRequest,
    ProjectListRequest,
    ProjectListResponse,
    PublicProjectDetailResponse,
    PublicProjectListResponse,
    PublicProjectTagResponse,
    PublicProjectSummaryResponse,
    ProjectSummaryResponse,
    ProjectUpdateRequest,
)
from app.presentation.schemas.resources import ResourceLinkResponse
from app.presentation.schemas.project_media import (
    project_cover_media_response,
    project_media_response,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    request: ProjectCreateRequest,
    editor: User = Depends(require_editor_or_admin),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectCreateResponse:
    project = await project_service.create_project(
        ProjectCreateDTO(
            title=request.title,
            slug=request.slug,
            short_description=request.short_description,
            development_status=request.development_status,
            display_order=request.display_order,
            github_url=request.github_url,
            demo_url=request.demo_url,
            overview=request.overview,
            status=request.status,
            published_at=request.published_at,
            archived_at=request.archived_at,
            is_featured=request.is_featured,
            category_ids=tuple(request.category_ids),
            tag_ids=tuple(request.tag_ids),
            resource_ids=tuple(request.resource_ids),
        ),
        actor_id=editor.id,
    )
    return ProjectCreateResponse(
        **ProjectSummaryResponse.model_validate(project).model_dump(),
        category_ids=[category.id for category in project.categories],
        tag_ids=[tag.id for tag in project.tags],
        resource_ids=[
            association.resource_id for association in project.resource_associations
        ],
    )


@router.get("", response_model=PublicProjectListResponse)
async def list_projects(
    query: ProjectListRequest = Depends(),
    project_service: ProjectService = Depends(get_project_service),
) -> PublicProjectListResponse:
    return await _list_public_projects(
        query=query,
        project_service=project_service,
    )


@router.get("/admin", response_model=ProjectListResponse)
async def list_projects_for_management(
    query: ProjectAdminListRequest = Depends(),
    _editor: User = Depends(require_editor_or_admin),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectListResponse:
    return await _list_projects(
        query=query,
        project_service=project_service,
        status_filter=query.status,
        active_catalog_only=False,
    )


@router.get(
    "/admin/{project_id}",
    response_model=ProjectDetailResponse,
)
async def get_project_for_management(
    project_id: UUID,
    _editor: User = Depends(require_editor_or_admin),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectDetailResponse:
    project = await project_service.get_project_for_management(project_id)
    return ProjectDetailResponse(
        **ProjectSummaryResponse.model_validate(project).model_dump(),
        category_ids=[category.id for category in project.categories],
        tag_ids=[tag.id for tag in project.tags],
        resource_ids=[
            association.resource_id for association in project.resource_associations
        ],
        media=[
            project_media_response(association)
            for association in project.media_associations
        ],
    )


@router.patch(
    "/admin/{project_id}",
    response_model=ProjectDetailResponse,
)
async def update_project(
    project_id: UUID,
    request: ProjectUpdateRequest,
    editor: User = Depends(require_editor_or_admin),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectDetailResponse:
    project = await project_service.update_project(
        project_id,
        ProjectUpdateDTO(
            title=request.title,
            slug=request.slug,
            short_description=request.short_description,
            development_status=request.development_status,
            display_order=request.display_order,
            github_url=request.github_url,
            demo_url=request.demo_url,
            overview=request.overview,
            status=request.status,
            published_at=request.published_at,
            archived_at=request.archived_at,
            is_featured=request.is_featured,
            category_ids=(
                tuple(request.category_ids)
                if request.category_ids is not None
                else None
            ),
            tag_ids=tuple(request.tag_ids) if request.tag_ids is not None else None,
            resource_ids=(
                tuple(request.resource_ids)
                if request.resource_ids is not None
                else None
            ),
            fields_set=frozenset(request.model_fields_set),
        ),
        actor_id=editor.id,
    )
    return ProjectDetailResponse(
        **ProjectSummaryResponse.model_validate(project).model_dump(),
        category_ids=[category.id for category in project.categories],
        tag_ids=[tag.id for tag in project.tags],
        resource_ids=[
            association.resource_id for association in project.resource_associations
        ],
        media=[
            project_media_response(association)
            for association in project.media_associations
        ],
    )


@router.get("/{slug}", response_model=PublicProjectDetailResponse)
async def get_published_project(
    slug: str,
    project_service: ProjectService = Depends(get_project_service),
) -> PublicProjectDetailResponse:
    project = await project_service.get_published_project(slug)
    inline_media_urls = {
        association.media_id: f"/api/v1/media/{association.media_id}/content"
        for association in project.media_associations
        if association.role == ProjectMediaRole.INLINE
        and association.media.kind == MediaKind.IMAGE
    }
    inline_video_urls = {
        association.media_id: f"/api/v1/media/{association.media_id}/content"
        for association in project.media_associations
        if association.role == ProjectMediaRole.INLINE
        and association.media.kind == MediaKind.VIDEO
    }
    inline_download_urls = {
        association.media_id: f"/api/v1/media/{association.media_id}/content"
        for association in project.media_associations
        if association.role == ProjectMediaRole.INLINE
        and association.media.kind == MediaKind.DOCUMENT
    }
    return PublicProjectDetailResponse(
        **ProjectSummaryResponse.model_validate(project).model_dump(),
        category_ids=[
            category.id for category in project.categories if category.is_active
        ],
        tag_ids=[tag.id for tag in project.tags if tag.is_active],
        resource_ids=[
            association.resource_id
            for association in project.resource_associations
            if ResourceStatus(association.resource.status)
            == ResourceStatus.PUBLISHED
        ],
        tags=[
            PublicProjectTagResponse.model_validate(tag)
            for tag in project.tags
            if tag.is_active
        ],
        media=[
            project_media_response(association)
            for association in project.media_associations
        ],
        resources=[
            _resource_link_response(association.resource)
            for association in project.resource_associations
            if ResourceStatus(association.resource.status) == ResourceStatus.PUBLISHED
        ],
        overview_html=render_markdown(
            project.overview or "",
            media_url_resolver=lambda media_id: inline_media_urls.get(media_id),
            media_video_url_resolver=lambda media_id: inline_video_urls.get(media_id),
            media_download_url_resolver=lambda media_id: inline_download_urls.get(
                media_id
            ),
        ),
    )


async def _list_projects(
    *,
    query: ProjectListRequest,
    project_service: ProjectService,
    status_filter: ProjectStatus | None,
    active_catalog_only: bool,
) -> ProjectListResponse:
    projects, total = await _list_project_data(
        query=query,
        project_service=project_service,
        status_filter=status_filter,
        active_catalog_only=active_catalog_only,
    )
    return ProjectListResponse(
        projects=[ProjectSummaryResponse.model_validate(project) for project in projects],
        total=total,
        offset=query.offset,
        limit=query.limit,
    )


async def _list_public_projects(
    *,
    query: ProjectListRequest,
    project_service: ProjectService,
) -> PublicProjectListResponse:
    projects, total = await _list_project_data(
        query=query,
        project_service=project_service,
        status_filter=ProjectStatus.PUBLISHED,
        active_catalog_only=True,
    )
    covers = (
        await project_service.get_project_covers([project.id for project in projects])
        if projects
        else {}
    )
    return PublicProjectListResponse(
        projects=[
            PublicProjectSummaryResponse(
                **ProjectSummaryResponse.model_validate(project).model_dump(),
                cover_media=(
                    project_cover_media_response(covers[project.id])
                    if project.id in covers
                    else None
                ),
            )
            for project in projects
        ],
        total=total,
        offset=query.offset,
        limit=query.limit,
    )


async def _list_project_data(
    *,
    query: ProjectListRequest,
    project_service: ProjectService,
    status_filter: ProjectStatus | None,
    active_catalog_only: bool,
) -> tuple[list[Project], int]:
    filters = ProjectListFilters(
        offset=query.offset,
        limit=query.limit,
        status=status_filter,
        development_status=query.development_status,
        is_featured=query.is_featured,
        category_id=query.category_id,
        tag_id=query.tag_id,
        active_catalog_only=active_catalog_only,
    )
    return await project_service.list_projects(filters)


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
