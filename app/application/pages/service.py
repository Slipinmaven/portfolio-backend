import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError

from app.application.errors import ConflictError, ResourceNotFoundError
from app.application.pages.blocks import (
    HeroBlock,
    MarkdownBlock,
    PageBlock,
    PageTarget,
    PostTarget,
    ProjectGridBlock,
    ProjectTarget,
)
from app.application.pages.dto import (
    PageCreateDTO,
    PageDraftDTO,
    PageListFilters,
    PublicPageData,
)
from app.application.pages.media_references import collect_page_media_ids
from app.application.posts.markdown import inline_media_image_references
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import (
    MediaKind,
    PageRevisionState,
    PageStatus,
)
from app.infrastructure.database.models.page import Page
from app.infrastructure.database.models.page_revision import PageRevision
from app.infrastructure.database.unit_of_work.pages import PagesUnitOfWork

_BLOCKS_ADAPTER = TypeAdapter(list[PageBlock])
CURRENT_PAGE_SCHEMA_VERSION = 2
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "articles",
        "categories",
        "media",
        "notes",
        "projects",
        "resources",
        "tags",
    }
)


class PageService:
    def __init__(self, unit_of_work: PagesUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def list_pages(
        self,
        filters: PageListFilters,
    ) -> tuple[list[Page], int]:
        return await self._unit_of_work.pages.list_pages(
            offset=filters.offset,
            limit=filters.limit,
            status=filters.status,
        )

    async def get_page_for_management(self, page_id: UUID) -> Page:
        page = await self._unit_of_work.pages.get_with_revisions_by_id(page_id)
        if page is None:
            raise ResourceNotFoundError("Page not found.")
        return page

    async def get_public_page_by_slug(self, slug: str) -> PublicPageData:
        page = await self._unit_of_work.pages.get_published_by_slug(slug)
        if page is None:
            raise ResourceNotFoundError("Page not found.")
        revision = next(
            (
                candidate
                for candidate in page.revisions
                if candidate.state == PageRevisionState.PUBLISHED
            ),
            None,
        )
        if revision is None:
            raise ResourceNotFoundError("Page not found.")
        if page.published_at is None:
            raise ResourceNotFoundError("Page not found.")

        sections = self._parse_sections(revision.sections)
        media_ids = collect_page_media_ids(sections)
        page_ids: set[UUID] = set()
        post_ids: set[UUID] = set()
        project_ids: set[UUID] = set()
        featured_limit = 0

        for block in sections:
            if isinstance(block, HeroBlock) and block.button is not None:
                target = block.button.link_target
                if isinstance(target, PageTarget):
                    page_ids.add(target.id)
                elif isinstance(target, ProjectTarget):
                    project_ids.add(target.id)
                elif isinstance(target, PostTarget):
                    post_ids.add(target.id)
            elif isinstance(block, ProjectGridBlock):
                if block.mode == "FEATURED":
                    featured_limit = max(featured_limit, block.limit)
                else:
                    project_ids.update(block.project_ids[: block.limit])

        images = [
            media
            for media in await self._unit_of_work.media.get_by_ids(
                sorted(media_ids, key=lambda value: value.int)
            )
            if media.kind == MediaKind.IMAGE
        ]
        projects = await self._unit_of_work.projects.get_published_by_ids(
            sorted(project_ids, key=lambda value: value.int)
        )
        if featured_limit:
            featured = await self._unit_of_work.projects.list_featured_published(
                limit=featured_limit
            )
            projects_by_id = {project.id: project for project in projects}
            projects_by_id.update(
                (project.id, project) for project in featured
            )
            projects = list(projects_by_id.values())

        pages = await self._unit_of_work.pages.get_published_by_ids(
            sorted(page_ids, key=lambda value: value.int)
        )
        posts = await self._unit_of_work.posts.get_published_by_ids(
            sorted(post_ids, key=lambda value: value.int)
        )
        project_covers = await self._unit_of_work.projects.get_project_covers(
            [project.id for project in projects]
        )
        return PublicPageData(
            slug=page.slug,
            system_key=page.system_key,
            title=revision.title,
            summary=revision.summary,
            published_at=page.published_at,
            sections=sections,
            images=images,
            projects=projects,
            project_covers=project_covers,
            pages=pages,
            posts=posts,
        )

    async def get_revision_history(self, page_id: UUID) -> list[PageRevision]:
        await self.get_page_for_management(page_id)
        return await self._unit_of_work.revisions.list_for_page(page_id)

    async def create_page(
        self,
        data: PageCreateDTO,
        *,
        actor_id: UUID,
    ) -> Page:
        slug = self._normalize_slug(data.slug)
        await self._ensure_slug_available(slug)
        page = Page(slug=slug, status=PageStatus.DRAFT)
        try:
            await self._unit_of_work.pages.create(page)
            await self._unit_of_work.revisions.create(
                PageRevision(
                    page_id=page.id,
                    revision_number=1,
                    state=PageRevisionState.DRAFT,
                    title=data.title.strip(),
                    summary=None,
                    sections=[],
                    schema_version=CURRENT_PAGE_SCHEMA_VERSION,
                )
            )
            await self._audit(
                actor_id=actor_id,
                action="page.created",
                page=page,
                new_values={"slug": slug, "title": data.title.strip()},
            )
            await self._commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError("A page with this slug already exists.") from exc
        return await self.get_page_for_management(page.id)

    async def save_draft(
        self,
        page_id: UUID,
        data: PageDraftDTO,
        *,
        actor_id: UUID,
    ) -> Page:
        page = await self._get_page_for_update(page_id)
        slug = self._normalize_slug(data.slug)
        if page.status != PageStatus.DRAFT and slug != page.slug:
            raise ConflictError(
                "Published page paths cannot be changed until redirects are available."
            )
        if slug != page.slug:
            await self._ensure_slug_available(slug, page_id=page.id)

        blocks = self._parse_sections(data.sections)
        await self._validate_references(blocks)
        now = datetime.now(timezone.utc)
        draft = await self._unit_of_work.revisions.get_by_page_and_state(
            page.id,
            PageRevisionState.DRAFT.value,
        )
        if draft is None:
            live = await self._unit_of_work.revisions.get_by_page_and_state(
                page.id,
                PageRevisionState.PUBLISHED.value,
            )
            if live is None:
                raise ConflictError("The page has no published revision to edit.")
            draft = PageRevision(
                page_id=page.id,
                revision_number=(
                    await self._unit_of_work.revisions.latest_revision_number(page.id)
                )
                + 1,
                state=PageRevisionState.DRAFT,
                title=live.title,
                summary=live.summary,
                sections=live.sections,
                schema_version=live.schema_version,
            )
            await self._unit_of_work.revisions.create(draft)

        previous_values: dict[str, object] = {
            "slug": page.slug,
            "title": draft.title,
            "summary": draft.summary,
            "sections": draft.sections,
        }
        page.slug = slug
        draft.title = data.title.strip()
        draft.summary = data.summary.strip() or None if data.summary else None
        draft.sections = [block.model_dump(mode="json") for block in blocks]
        draft.schema_version = CURRENT_PAGE_SCHEMA_VERSION
        draft.updated_at = now

        await self._sync_page_media(page.id)
        try:
            await self._audit(
                actor_id=actor_id,
                action="page.draft_saved",
                page=page,
                old_values=previous_values,
                new_values={
                    "slug": page.slug,
                    "title": draft.title,
                    "summary": draft.summary,
                    "sections": draft.sections,
                },
            )
            await self._commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError("A page with this slug already exists.") from exc
        return await self.get_page_for_management(page.id)

    async def publish_draft(
        self,
        page_id: UUID,
        *,
        actor_id: UUID,
        change_note: str | None = None,
    ) -> Page:
        page = await self._get_page_for_update(page_id)
        draft = await self._unit_of_work.revisions.get_by_page_and_state(
            page.id,
            PageRevisionState.DRAFT.value,
        )
        if draft is None:
            raise ConflictError("There is no draft to publish.")

        blocks = self._parse_sections(draft.sections)
        await self._validate_references(blocks)
        now = datetime.now(timezone.utc)
        live = await self._unit_of_work.revisions.get_by_page_and_state(
            page.id,
            PageRevisionState.PUBLISHED.value,
        )
        try:
            if live is not None:
                live.state = PageRevisionState.SUPERSEDED
                live.superseded_at = now
                await self._unit_of_work.flush()

            draft.state = PageRevisionState.PUBLISHED
            draft.published_at = now
            draft.superseded_at = None
            draft.change_note = change_note.strip() or None if change_note else None
            draft.sections = [block.model_dump(mode="json") for block in blocks]
            page.status = PageStatus.PUBLISHED
            page.published_at = page.published_at or now
            page.archived_at = None
            await self._sync_page_media(page.id)
            await self._audit(
                actor_id=actor_id,
                action="page.published",
                page=page,
                old_values={"revision_id": str(live.id)} if live else None,
                new_values={
                    "revision_id": str(draft.id),
                    "revision_number": draft.revision_number,
                    "change_note": draft.change_note,
                },
            )
            await self._commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError(
                "The page changed while it was being published. Reload and try again."
            ) from exc
        return await self.get_page_for_management(page.id)

    async def discard_draft(self, page_id: UUID, *, actor_id: UUID) -> Page:
        page = await self._get_page_for_update(page_id)
        draft = await self._unit_of_work.revisions.get_by_page_and_state(
            page.id,
            PageRevisionState.DRAFT.value,
        )
        if draft is None:
            raise ConflictError("There is no draft to discard.")
        if page.published_at is None:
            raise ConflictError(
                "A page's first draft cannot be discarded before it is published."
            )
        await self._unit_of_work.revisions.delete_draft(draft)
        await self._sync_page_media(page.id)
        await self._audit(
            actor_id=actor_id,
            action="page.draft_discarded",
            page=page,
            old_values={
                "revision_id": str(draft.id),
                "revision_number": draft.revision_number,
            },
        )
        await self._commit()
        return await self.get_page_for_management(page.id)

    async def rollback_to_revision(
        self,
        page_id: UUID,
        revision_id: UUID,
        *,
        actor_id: UUID,
    ) -> Page:
        page = await self._get_page_for_update(page_id)
        draft = await self._unit_of_work.revisions.get_by_page_and_state(
            page.id,
            PageRevisionState.DRAFT.value,
        )
        if draft is not None:
            raise ConflictError(
                "Publish or discard the current draft before creating a rollback."
            )
        source = await self._unit_of_work.revisions.get_for_page(
            page.id,
            revision_id,
        )
        if source is None or source.state != PageRevisionState.SUPERSEDED:
            raise ResourceNotFoundError("Historical page revision not found.")

        blocks = self._parse_sections(source.sections)
        await self._validate_references(blocks)
        new_revision = PageRevision(
            page_id=page.id,
            revision_number=(
                await self._unit_of_work.revisions.latest_revision_number(page.id)
            )
            + 1,
            state=PageRevisionState.DRAFT,
            title=source.title,
            summary=source.summary,
            sections=[block.model_dump(mode="json") for block in blocks],
            schema_version=source.schema_version,
            change_note=f"Rollback copy of revision {source.revision_number}.",
        )
        await self._unit_of_work.revisions.create(new_revision)
        await self._sync_page_media(page.id)
        await self._audit(
            actor_id=actor_id,
            action="page.rollback_created",
            page=page,
            old_values={"source_revision_id": str(source.id)},
            new_values={
                "revision_id": str(new_revision.id),
                "revision_number": new_revision.revision_number,
            },
        )
        await self._commit()
        return await self.get_page_for_management(page.id)

    async def archive_page(self, page_id: UUID, *, actor_id: UUID) -> Page:
        page = await self._get_page_for_update(page_id)
        if page.system_key is not None:
            raise ConflictError("System pages cannot be archived.")
        if page.status != PageStatus.PUBLISHED:
            raise ConflictError("Only a published page can be archived.")
        now = datetime.now(timezone.utc)
        page.status = PageStatus.ARCHIVED
        page.archived_at = now
        await self._audit(
            actor_id=actor_id,
            action="page.archived",
            page=page,
            old_values={"status": PageStatus.PUBLISHED.value},
            new_values={"status": PageStatus.ARCHIVED.value},
        )
        await self._commit()
        return await self.get_page_for_management(page.id)

    async def republish_page(self, page_id: UUID, *, actor_id: UUID) -> Page:
        page = await self._get_page_for_update(page_id)
        if page.system_key is not None:
            raise ConflictError("System pages are already published.")
        if page.status != PageStatus.ARCHIVED:
            raise ConflictError("Only an archived page can be republished.")
        if await self._unit_of_work.revisions.get_by_page_and_state(
            page.id,
            PageRevisionState.PUBLISHED.value,
        ) is None:
            raise ConflictError("The page has no published revision to restore.")
        page.status = PageStatus.PUBLISHED
        page.archived_at = None
        await self._audit(
            actor_id=actor_id,
            action="page.republished",
            page=page,
            old_values={"status": PageStatus.ARCHIVED.value},
            new_values={"status": PageStatus.PUBLISHED.value},
        )
        await self._commit()
        return await self.get_page_for_management(page.id)

    async def _get_page_for_update(self, page_id: UUID) -> Page:
        page = await self._unit_of_work.pages.get_with_revisions_by_id(
            page_id,
            for_update=True,
        )
        if page is None:
            raise ResourceNotFoundError("Page not found.")
        return page

    async def _ensure_slug_available(
        self,
        slug: str,
        *,
        page_id: UUID | None = None,
    ) -> None:
        if slug in _RESERVED_SLUGS:
            raise ConflictError("This page slug is reserved for a site route.")
        existing = await self._unit_of_work.pages.get_by_slug(slug)
        if existing is not None and existing.id != page_id:
            raise ConflictError("A page with this slug already exists.")

    @staticmethod
    def _normalize_slug(value: str) -> str:
        slug = value.strip().lower()
        if not _SLUG_PATTERN.fullmatch(slug):
            raise ConflictError(
                "Page slugs must use lowercase letters, numbers, and single hyphens."
            )
        if len(slug) > 120:
            raise ConflictError("Page slugs can be at most 120 characters.")
        return slug

    @staticmethod
    def _parse_sections(sections: list[dict[str, Any]]) -> list[PageBlock]:
        try:
            return _BLOCKS_ADAPTER.validate_python(sections)
        except ValidationError as exc:
            raise ConflictError("Page sections contain an invalid block.") from exc

    async def _validate_references(self, blocks: list[PageBlock]) -> None:
        media_ids: set[UUID] = set()
        page_ids: set[UUID] = set()
        project_ids: set[UUID] = set()
        post_ids: set[UUID] = set()

        for block in blocks:
            if isinstance(block, HeroBlock):
                if block.media_id is not None:
                    media_ids.add(block.media_id)
                if block.button is not None:
                    target = block.button.link_target
                    if isinstance(target, PageTarget):
                        page_ids.add(target.id)
                    elif isinstance(target, ProjectTarget):
                        project_ids.add(target.id)
                    elif isinstance(target, PostTarget):
                        post_ids.add(target.id)
            elif isinstance(block, MarkdownBlock):
                media_ids.update(
                    media_id
                    for _, media_id in inline_media_image_references(block.body)
                )
            elif isinstance(block, ProjectGridBlock):
                project_ids.update(block.project_ids)

        if page_ids:
            records = await self._unit_of_work.pages.get_by_ids(list(page_ids))
            if {record.id for record in records} != page_ids:
                raise ResourceNotFoundError("A page link target does not exist.")
        if project_ids:
            records = await self._unit_of_work.projects.get_by_ids(
                list(project_ids)
            )
            if {record.id for record in records} != project_ids:
                raise ResourceNotFoundError("A project reference does not exist.")
        if post_ids:
            records = await self._unit_of_work.posts.get_by_ids(list(post_ids))
            if {record.id for record in records} != post_ids:
                raise ResourceNotFoundError("A post link target does not exist.")
        if media_ids:
            records = await self._unit_of_work.media.get_by_ids(list(media_ids))
            by_id = {record.id: record for record in records}
            if set(by_id) != media_ids:
                raise ResourceNotFoundError("A page image does not exist.")
            if any(record.kind != MediaKind.IMAGE for record in by_id.values()):
                raise ConflictError("Page blocks can reference image media only.")

    async def _sync_page_media(self, page_id: UUID) -> None:
        revisions = await self._unit_of_work.revisions.list_active_for_page(page_id)
        media_ids: set[UUID] = set()
        for revision in revisions:
            blocks = self._parse_sections(revision.sections)
            media_ids.update(collect_page_media_ids(blocks))
        await self._unit_of_work.page_media.replace_for_page(page_id, media_ids)

    async def _audit(
        self,
        *,
        actor_id: UUID,
        action: str,
        page: Page,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
    ) -> None:
        await self._unit_of_work.audit_logs.create(
            AuditLog(
                user_id=actor_id,
                action=action,
                entity_type="page",
                entity_id=page.id,
                old_values=old_values,
                new_values=new_values,
                status="success",
            )
        )

    async def _commit(self) -> None:
        try:
            await self._unit_of_work.commit()
        except BaseException:
            await self._unit_of_work.rollback()
            raise
