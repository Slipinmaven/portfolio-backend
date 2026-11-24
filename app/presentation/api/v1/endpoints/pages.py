from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.application.pages.dto import (
    PageCreateDTO,
    PageDraftDTO,
    PageListFilters,
)
from app.application.pages.service import PageService
from app.application.posts.markdown import render_markdown
from app.infrastructure.database.models.enums import (
    PageRevisionState,
)
from app.infrastructure.database.models.page import Page
from app.infrastructure.database.models.page_revision import PageRevision
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_editor_or_admin
from app.presentation.dependencies.services import get_page_service
from app.presentation.schemas.pages import (
    PageCreateRequest,
    PageDetailResponse,
    PageDraftRequest,
    PageListRequest,
    PageListResponse,
    PageMarkdownPreviewRequest,
    PageMarkdownPreviewResponse,
    PagePublishRequest,
    PublicPageImageResponse,
    PublicPageLinkTargetResponse,
    PublicPageProjectCoverResponse,
    PublicPageProjectResponse,
    PublicPageResponse,
    PublicPostLinkTargetResponse,
    PageRevisionListResponse,
    PageRevisionResponse,
    PageSummaryResponse,
)

router = APIRouter(prefix="/pages", tags=["pages"])


@router.get(
    "/admin",
    response_model=PageListResponse,
    dependencies=[Depends(require_editor_or_admin)],
)
async def list_pages_for_management(
    query: PageListRequest = Depends(),
    page_service: PageService = Depends(get_page_service),
) -> PageListResponse:
    pages, total = await page_service.list_pages(
        PageListFilters(
            offset=query.offset,
            limit=query.limit,
            status=query.status,
        )
    )
    return PageListResponse(
        pages=[_summary_response(page) for page in pages],
        total=total,
        offset=query.offset,
        limit=query.limit,
    )


@router.post(
    "/admin",
    response_model=PageDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_page(
    request: PageCreateRequest,
    editor: User = Depends(require_editor_or_admin),
    page_service: PageService = Depends(get_page_service),
) -> PageDetailResponse:
    page = await page_service.create_page(
        PageCreateDTO(slug=request.slug, title=request.title),
        actor_id=editor.id,
    )
    return _detail_response(page)


@router.post(
    "/admin/preview",
    response_model=PageMarkdownPreviewResponse,
    dependencies=[Depends(require_editor_or_admin)],
)
async def preview_page_markdown(
    request: PageMarkdownPreviewRequest,
) -> PageMarkdownPreviewResponse:
    return PageMarkdownPreviewResponse(
        html=render_markdown(
            request.body,
            media_url_resolver=lambda media_id: (
                f"/api/v1/media/admin/{media_id}/content"
            ),
        )
    )


@router.get("/{slug}", response_model=PublicPageResponse)
async def get_public_page(
    slug: str,
    page_service: PageService = Depends(get_page_service),
) -> PublicPageResponse:
    page = await page_service.get_public_page_by_slug(slug)
    public_media_ids = {image.id for image in page.images}
    rendered_markdown = {
        str(block.id): render_markdown(
            block.body,
            media_url_resolver=lambda media_id: (
                f"/api/v1/media/{media_id}/content"
                if media_id in public_media_ids
                else None
            ),
        )
        for block in page.sections
        if block.type == "MARKDOWN"
    }
    return PublicPageResponse(
        slug=page.slug,
        system_key=page.system_key,
        title=page.title,
        summary=page.summary,
        published_at=page.published_at,
        sections=page.sections,
        images=[
            PublicPageImageResponse(
                id=image.id,
                title=image.title,
                alt_text=image.alt_text,
                width=image.width,
                height=image.height,
            )
            for image in page.images
        ],
        projects=[
            PublicPageProjectResponse(
                **PublicPageProjectResponse.model_validate(project).model_dump(
                    exclude={"cover_media"}
                ),
                cover_media=(
                    PublicPageProjectCoverResponse(
                        media_id=cover.media.id,
                        title=cover.media.title,
                        alt_text=cover.media.alt_text,
                        file_url=f"/api/v1/media/{cover.media.id}/content",
                    )
                    if (cover := page.project_covers.get(project.id))
                    else None
                ),
            )
            for project in page.projects
        ],
        pages=[
            PublicPageLinkTargetResponse(
                id=target.id,
                slug=target.slug,
                status=target.status,
            )
            for target in page.pages
        ],
        posts=[
            PublicPostLinkTargetResponse(
                id=target.id,
                kind=target.kind,
                slug=target.slug,
                status=target.status,
            )
            for target in page.posts
        ],
        rendered_markdown=rendered_markdown,
    )


@router.get(
    "/admin/{page_id}",
    response_model=PageDetailResponse,
    dependencies=[Depends(require_editor_or_admin)],
)
async def get_page_for_management(
    page_id: UUID,
    page_service: PageService = Depends(get_page_service),
) -> PageDetailResponse:
    return _detail_response(
        await page_service.get_page_for_management(page_id)
    )


@router.put(
    "/admin/{page_id}/draft",
    response_model=PageDetailResponse,
)
async def save_page_draft(
    page_id: UUID,
    request: PageDraftRequest,
    editor: User = Depends(require_editor_or_admin),
    page_service: PageService = Depends(get_page_service),
) -> PageDetailResponse:
    page = await page_service.save_draft(
        page_id,
        PageDraftDTO(
            slug=request.slug,
            title=request.title,
            summary=request.summary,
            sections=[
                block.model_dump(mode="json")
                for block in request.sections
            ],
        ),
        actor_id=editor.id,
    )
    return _detail_response(page)


@router.post(
    "/admin/{page_id}/publish",
    response_model=PageDetailResponse,
)
async def publish_page_draft(
    page_id: UUID,
    request: PagePublishRequest,
    editor: User = Depends(require_editor_or_admin),
    page_service: PageService = Depends(get_page_service),
) -> PageDetailResponse:
    page = await page_service.publish_draft(
        page_id,
        actor_id=editor.id,
        change_note=request.change_note,
    )
    return _detail_response(page)


@router.post(
    "/admin/{page_id}/discard",
    response_model=PageDetailResponse,
)
async def discard_page_draft(
    page_id: UUID,
    editor: User = Depends(require_editor_or_admin),
    page_service: PageService = Depends(get_page_service),
) -> PageDetailResponse:
    return _detail_response(
        await page_service.discard_draft(page_id, actor_id=editor.id)
    )


@router.get(
    "/admin/{page_id}/revisions",
    response_model=PageRevisionListResponse,
    dependencies=[Depends(require_editor_or_admin)],
)
async def list_page_revisions(
    page_id: UUID,
    page_service: PageService = Depends(get_page_service),
) -> PageRevisionListResponse:
    revisions = await page_service.get_revision_history(page_id)
    return PageRevisionListResponse(
        page_id=page_id,
        revisions=[
            PageRevisionResponse.model_validate(revision)
            for revision in revisions
        ],
    )


@router.post(
    "/admin/{page_id}/revisions/{revision_id}/rollback",
    response_model=PageDetailResponse,
)
async def rollback_page_revision(
    page_id: UUID,
    revision_id: UUID,
    editor: User = Depends(require_editor_or_admin),
    page_service: PageService = Depends(get_page_service),
) -> PageDetailResponse:
    page = await page_service.rollback_to_revision(
        page_id,
        revision_id,
        actor_id=editor.id,
    )
    return _detail_response(page)


@router.post(
    "/admin/{page_id}/archive",
    response_model=PageDetailResponse,
)
async def archive_page(
    page_id: UUID,
    editor: User = Depends(require_editor_or_admin),
    page_service: PageService = Depends(get_page_service),
) -> PageDetailResponse:
    return _detail_response(
        await page_service.archive_page(page_id, actor_id=editor.id)
    )


@router.post(
    "/admin/{page_id}/republish",
    response_model=PageDetailResponse,
)
async def republish_page(
    page_id: UUID,
    editor: User = Depends(require_editor_or_admin),
    page_service: PageService = Depends(get_page_service),
) -> PageDetailResponse:
    return _detail_response(
        await page_service.republish_page(page_id, actor_id=editor.id)
    )


def _revision_state_value(revision: PageRevision) -> str:
    state = revision.state
    return state.value if isinstance(state, PageRevisionState) else state


def _summary_response(page: Page) -> PageSummaryResponse:
    revisions = {
        _revision_state_value(revision): revision for revision in page.revisions
    }
    draft = revisions.get(PageRevisionState.DRAFT.value)
    published = revisions.get(PageRevisionState.PUBLISHED.value)
    current = draft or published
    return PageSummaryResponse(
        id=page.id,
        slug=page.slug,
        system_key=page.system_key,
        status=page.status,
        title=current.title if current is not None else "Untitled page",
        published_at=page.published_at,
        archived_at=page.archived_at,
        created_at=page.created_at,
        updated_at=page.updated_at,
        draft_revision_number=draft.revision_number if draft else None,
    )


def _detail_response(page: Page) -> PageDetailResponse:
    revisions = {
        _revision_state_value(revision): revision for revision in page.revisions
    }
    draft = revisions.get(PageRevisionState.DRAFT.value)
    published = revisions.get(PageRevisionState.PUBLISHED.value)
    return PageDetailResponse(
        **_summary_response(page).model_dump(),
        draft_revision=(
            PageRevisionResponse.model_validate(draft)
            if draft is not None
            else None
        ),
        published_revision=(
            PageRevisionResponse.model_validate(published)
            if published is not None
            else None
        ),
    )
