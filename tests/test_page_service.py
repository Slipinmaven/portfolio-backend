import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.application.errors import ConflictError, ResourceNotFoundError
from app.application.pages.blocks import SkillsBlock
from app.application.pages.dto import PageCreateDTO, PageDraftDTO
from app.application.pages.service import (
    CURRENT_PAGE_SCHEMA_VERSION,
    PageService,
)
from app.infrastructure.database.models.enums import (
    MediaKind,
    PageRevisionState,
    PageStatus,
)
from app.infrastructure.database.models.page import Page
from app.infrastructure.database.models.page_revision import PageRevision
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.unit_of_work.pages import PagesUnitOfWork


class PageServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.uow = MagicMock(spec=PagesUnitOfWork)
        self.uow.pages = MagicMock()
        self.uow.revisions = MagicMock()
        self.uow.page_media = MagicMock()
        self.uow.audit_logs = MagicMock()
        self.uow.media = MagicMock()
        self.uow.projects = MagicMock()
        self.uow.posts = MagicMock()
        self.uow.pages.get_by_slug = AsyncMock(return_value=None)
        self.uow.pages.get_by_ids = AsyncMock(return_value=[])
        self.uow.pages.get_published_by_ids = AsyncMock(return_value=[])
        self.uow.pages.get_published_by_slug = AsyncMock(return_value=None)
        self.uow.pages.get_with_revisions_by_id = AsyncMock()
        self.uow.revisions.get_by_page_and_state = AsyncMock()
        self.uow.revisions.get_for_page = AsyncMock()
        self.uow.revisions.latest_revision_number = AsyncMock(return_value=0)
        self.uow.revisions.list_active_for_page = AsyncMock(return_value=[])
        self.uow.revisions.list_for_page = AsyncMock(return_value=[])
        self.uow.revisions.create = AsyncMock(
            side_effect=lambda revision: setattr(revision, "id", uuid4())
        )
        self.uow.revisions.delete_draft = AsyncMock()
        self.uow.page_media.replace_for_page = AsyncMock()
        self.uow.audit_logs.create = AsyncMock()
        self.uow.media.get_by_ids = AsyncMock(return_value=[])
        self.uow.projects.get_by_ids = AsyncMock(return_value=[])
        self.uow.projects.get_published_by_ids = AsyncMock(return_value=[])
        self.uow.projects.list_featured_published = AsyncMock(return_value=[])
        self.uow.projects.get_project_covers = AsyncMock(return_value={})
        self.uow.posts.get_by_ids = AsyncMock(return_value=[])
        self.uow.posts.get_published_by_ids = AsyncMock(return_value=[])
        self.uow.pages.create = AsyncMock(
            side_effect=lambda page: setattr(page, "id", uuid4())
        )
        self.uow.commit = AsyncMock()
        self.uow.rollback = AsyncMock()
        self.service = PageService(self.uow)
        self.actor_id = uuid4()

    async def test_public_page_uses_only_published_revision_and_targets(self) -> None:
        page = self.make_page(
            status=PageStatus.PUBLISHED,
            system_key="CONTACT",
        )
        linked_page_id = uuid4()
        post_id = uuid4()
        project_target_id = uuid4()
        selected_project_id = uuid4()
        image_id = uuid4()
        featured_project_id = uuid4()
        page.published_at = datetime.now(timezone.utc)
        published_sections = [
            {
                "id": str(uuid4()),
                "type": "HERO",
                "headline": "Live headline",
                "subline": None,
                "media_id": str(image_id),
                "button": {
                    "label": "Read more",
                    "link_target": {
                        "type": "PAGE",
                        "id": str(linked_page_id),
                    },
                },
            },
            {
                "id": str(uuid4()),
                "type": "HERO",
                "headline": "Project link",
                "subline": None,
                "media_id": None,
                "button": {
                    "label": "View project",
                    "link_target": {
                        "type": "PROJECT",
                        "id": str(project_target_id),
                    },
                },
            },
            {
                "id": str(uuid4()),
                "type": "HERO",
                "headline": "Post link",
                "subline": None,
                "media_id": None,
                "button": {
                    "label": "Read post",
                    "link_target": {"type": "POST", "id": str(post_id)},
                },
            },
            {
                "id": str(uuid4()),
                "type": "MARKDOWN",
                "body": f"![Live image](media:{image_id})",
            },
            {
                "id": str(uuid4()),
                "type": "PROJECT_GRID",
                "mode": "FEATURED",
                "project_ids": [],
                "limit": 2,
            },
            {
                "id": str(uuid4()),
                "type": "PROJECT_GRID",
                "mode": "MANUAL",
                "project_ids": [
                    str(selected_project_id),
                    str(uuid4()),
                ],
                "limit": 1,
            },
        ]
        published_revision = PageRevision(
            id=uuid4(),
            page_id=page.id,
            revision_number=2,
            state=PageRevisionState.PUBLISHED,
            title="Live page",
            summary="Public summary",
            sections=published_sections,
            schema_version=1,
            published_at=page.published_at,
        )
        draft_revision = PageRevision(
            id=uuid4(),
            page_id=page.id,
            revision_number=3,
            state=PageRevisionState.DRAFT,
            title="Private draft",
            summary=None,
            sections=[],
            schema_version=1,
        )
        page.revisions = [published_revision, draft_revision]
        linked_page = type(
            "LinkedPage",
            (),
            {"id": linked_page_id, "slug": "contact", "status": PageStatus.PUBLISHED},
        )()
        page_project = type(
            "PageProject",
            (),
            {
                "id": selected_project_id,
                "status": "PUBLISHED",
            },
        )()
        target_project = type(
            "TargetProject",
            (),
            {"id": project_target_id, "status": "PUBLISHED"},
        )()
        featured_project = type(
            "FeaturedProject",
            (),
            {"id": featured_project_id, "status": "PUBLISHED"},
        )()
        post = type(
            "PagePost",
            (),
            {"id": post_id, "status": "PUBLISHED"},
        )()
        image = Media(
            id=image_id,
            kind=MediaKind.IMAGE,
            storage_key="pages/live.png",
            original_filename="live.png",
            mime_type="image/png",
            size_bytes=12,
            checksum_sha256="a" * 64,
        )
        self.uow.pages.get_published_by_slug.return_value = page
        self.uow.pages.get_published_by_ids.return_value = [linked_page]
        self.uow.projects.get_published_by_ids.return_value = [
            page_project,
            target_project,
        ]
        self.uow.projects.list_featured_published.return_value = [featured_project]
        self.uow.posts.get_published_by_ids.return_value = [post]
        self.uow.media.get_by_ids.return_value = [image]

        result = await self.service.get_public_page_by_slug(page.slug)

        self.assertEqual(result.system_key, "CONTACT")
        self.assertEqual(result.title, "Live page")
        self.assertEqual(result.summary, "Public summary")
        self.assertEqual(result.sections[0].headline, "Live headline")
        self.assertEqual([item.id for item in result.images], [image_id])
        self.assertEqual(
            {item.id for item in result.projects},
            {selected_project_id, project_target_id, featured_project_id},
        )
        self.assertEqual([item.id for item in result.pages], [linked_page_id])
        self.assertEqual([item.id for item in result.posts], [post_id])
        self.uow.projects.list_featured_published.assert_awaited_once_with(limit=2)
        self.uow.projects.get_published_by_ids.assert_awaited_once()

    async def test_public_page_hides_unpublished_pages(self) -> None:
        with self.assertRaises(ResourceNotFoundError):
            await self.service.get_public_page_by_slug("private-page")

        self.uow.pages.get_published_by_slug.assert_awaited_once_with(
            "private-page"
        )
        self.uow.projects.get_published_by_ids.assert_not_awaited()

    @staticmethod
    def make_page(
        *,
        status: PageStatus = PageStatus.DRAFT,
        system_key: str | None = None,
    ) -> Page:
        now = datetime.now(timezone.utc)
        page = Page(
            id=uuid4(),
            slug="about-me" if system_key is None else system_key.lower(),
            system_key=system_key,
            status=status,
            published_at=now if status != PageStatus.DRAFT else None,
            archived_at=now if status == PageStatus.ARCHIVED else None,
            created_at=now,
            updated_at=now,
        )
        page.revisions = []
        return page

    async def test_create_page_starts_with_an_audited_draft_revision(self) -> None:
        page = self.make_page()
        self.uow.pages.create.side_effect = lambda created: (
            setattr(created, "id", page.id)
        )
        self.uow.pages.get_with_revisions_by_id.return_value = page

        result = await self.service.create_page(
            PageCreateDTO(slug="about-me", title="  About me  "),
            actor_id=self.actor_id,
        )

        self.assertEqual(result.id, page.id)
        self.uow.pages.create.assert_awaited_once()
        revision = self.uow.revisions.create.await_args.args[0]
        self.assertEqual(revision.page_id, page.id)
        self.assertEqual(revision.title, "About me")
        self.assertEqual(revision.state, PageRevisionState.DRAFT)
        self.assertEqual(revision.schema_version, CURRENT_PAGE_SCHEMA_VERSION)
        self.uow.audit_logs.create.assert_awaited_once()
        self.assertEqual(
            self.uow.audit_logs.create.await_args.args[0].action,
            "page.created",
        )
        self.uow.commit.assert_awaited_once()

    def test_parse_sections_accepts_skills_with_named_proficiency(self) -> None:
        sections = PageService._parse_sections(
            [
                {
                    "id": str(uuid4()),
                    "type": "SKILLS",
                    "heading": "Skills and strengths",
                    "description": None,
                    "skills": [
                        {
                            "id": str(uuid4()),
                            "name": "Python",
                            "proficiency": "ADVANCED",
                        }
                    ],
                }
            ]
        )

        self.assertIsInstance(sections[0], SkillsBlock)
        self.assertEqual(sections[0].skills[0].proficiency, "ADVANCED")

    def test_parse_sections_rejects_duplicate_skills(self) -> None:
        with self.assertRaisesRegex(ConflictError, "invalid block"):
            PageService._parse_sections(
                [
                    {
                        "id": str(uuid4()),
                        "type": "SKILLS",
                        "heading": "Skills and strengths",
                        "skills": [
                            {
                                "id": str(uuid4()),
                                "name": "Python",
                                "proficiency": "ADVANCED",
                            },
                            {
                                "id": str(uuid4()),
                                "name": "python",
                                "proficiency": "WORKING",
                            },
                        ],
                    }
                ]
            )

    def test_parse_sections_rejects_numeric_proficiency_percentages(self) -> None:
        with self.assertRaisesRegex(ConflictError, "invalid block"):
            PageService._parse_sections(
                [
                    {
                        "id": str(uuid4()),
                        "type": "SKILLS",
                        "heading": "Skills and strengths",
                        "skills": [
                            {
                                "id": str(uuid4()),
                                "name": "Python",
                                "proficiency": "75%",
                            }
                        ],
                    }
                ]
            )

    async def test_create_page_rejects_reserved_slugs(self) -> None:
        with self.assertRaisesRegex(ConflictError, "reserved"):
            await self.service.create_page(
                PageCreateDTO(slug="projects", title="Projects"),
                actor_id=self.actor_id,
            )

        self.uow.pages.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_saving_a_published_page_creates_a_private_draft_copy(self) -> None:
        page = self.make_page(status=PageStatus.PUBLISHED)
        live = PageRevision(
            id=uuid4(),
            page_id=page.id,
            revision_number=2,
            state=PageRevisionState.PUBLISHED,
            title="Live title",
            summary="Live summary",
            sections=[],
            schema_version=1,
        )
        self.uow.pages.get_with_revisions_by_id.return_value = page
        self.uow.revisions.get_by_page_and_state.side_effect = [None, live]
        self.uow.revisions.latest_revision_number.return_value = 2
        self.uow.revisions.list_active_for_page.return_value = [live]

        result = await self.service.save_draft(
            page.id,
            PageDraftDTO(
                slug=page.slug,
                title="New draft",
                summary=None,
                sections=[
                    {
                        "id": str(uuid4()),
                        "type": "MARKDOWN",
                        "body": "Draft only",
                    }
                ],
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(result.id, page.id)
        draft = self.uow.revisions.create.await_args.args[0]
        self.assertEqual(draft.revision_number, 3)
        self.assertEqual(draft.state, PageRevisionState.DRAFT)
        self.assertEqual(draft.title, "New draft")
        self.assertEqual(draft.schema_version, CURRENT_PAGE_SCHEMA_VERSION)
        self.assertEqual(live.state, PageRevisionState.PUBLISHED)
        self.uow.page_media.replace_for_page.assert_awaited_once_with(page.id, set())
        self.uow.commit.assert_awaited_once()

    async def test_published_page_slug_change_stays_locked(self) -> None:
        page = self.make_page(status=PageStatus.PUBLISHED)
        self.uow.pages.get_with_revisions_by_id.return_value = page

        with self.assertRaisesRegex(ConflictError, "redirects"):
            await self.service.save_draft(
                page.id,
                PageDraftDTO(
                    slug="renamed-page",
                    title="About me",
                    summary=None,
                    sections=[],
                ),
                actor_id=self.actor_id,
            )

        self.uow.revisions.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_publish_supersedes_live_revision_and_keeps_history(self) -> None:
        page = self.make_page(status=PageStatus.PUBLISHED)
        draft = PageRevision(
            id=uuid4(),
            page_id=page.id,
            revision_number=3,
            state=PageRevisionState.DRAFT,
            title="Updated",
            summary=None,
            sections=[],
            schema_version=1,
        )
        live = PageRevision(
            id=uuid4(),
            page_id=page.id,
            revision_number=2,
            state=PageRevisionState.PUBLISHED,
            title="Current",
            summary=None,
            sections=[],
            schema_version=1,
        )
        self.uow.pages.get_with_revisions_by_id.return_value = page
        self.uow.revisions.get_by_page_and_state.side_effect = [draft, live]
        self.uow.revisions.list_active_for_page.return_value = [draft]

        async def verify_previous_revision_is_flushed() -> None:
            self.assertEqual(live.state, PageRevisionState.SUPERSEDED)
            self.assertEqual(draft.state, PageRevisionState.DRAFT)

        self.uow.flush.side_effect = verify_previous_revision_is_flushed

        await self.service.publish_draft(
            page.id,
            actor_id=self.actor_id,
            change_note="Updated content",
        )

        self.uow.flush.assert_awaited_once()
        self.assertEqual(live.state, PageRevisionState.SUPERSEDED)
        self.assertIsNotNone(live.superseded_at)
        self.assertEqual(draft.state, PageRevisionState.PUBLISHED)
        self.assertEqual(draft.change_note, "Updated content")
        self.assertEqual(page.status, PageStatus.PUBLISHED)
        self.assertIsNotNone(page.published_at)
        self.uow.audit_logs.create.assert_awaited_once()
        self.uow.commit.assert_awaited_once()

    async def test_publish_rolls_back_if_superseding_revision_cannot_flush(self) -> None:
        page = self.make_page(status=PageStatus.PUBLISHED)
        draft = PageRevision(
            id=uuid4(),
            page_id=page.id,
            revision_number=3,
            state=PageRevisionState.DRAFT,
            title="Updated",
            sections=[],
            schema_version=1,
        )
        live = PageRevision(
            id=uuid4(),
            page_id=page.id,
            revision_number=2,
            state=PageRevisionState.PUBLISHED,
            title="Current",
            sections=[],
            schema_version=1,
        )
        self.uow.pages.get_with_revisions_by_id.return_value = page
        self.uow.revisions.get_by_page_and_state.side_effect = [draft, live]
        self.uow.flush.side_effect = IntegrityError(
            "UPDATE page_revisions",
            {},
            Exception("unique constraint"),
        )

        with self.assertRaisesRegex(ConflictError, "changed while it was being published"):
            await self.service.publish_draft(page.id, actor_id=self.actor_id)

        self.uow.rollback.assert_awaited_once()
        self.uow.commit.assert_not_awaited()

    async def test_rollback_is_blocked_while_a_draft_exists(self) -> None:
        page = self.make_page(status=PageStatus.PUBLISHED)
        draft = PageRevision(
            id=uuid4(),
            page_id=page.id,
            revision_number=2,
            state=PageRevisionState.DRAFT,
            title="Draft",
            sections=[],
            schema_version=1,
        )
        self.uow.pages.get_with_revisions_by_id.return_value = page
        self.uow.revisions.get_by_page_and_state.return_value = draft

        with self.assertRaisesRegex(ConflictError, "Publish or discard"):
            await self.service.rollback_to_revision(
                page.id,
                uuid4(),
                actor_id=self.actor_id,
            )

        self.uow.revisions.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_system_page_cannot_be_archived(self) -> None:
        page = self.make_page(
            status=PageStatus.PUBLISHED,
            system_key="ABOUT",
        )
        self.uow.pages.get_with_revisions_by_id.return_value = page

        with self.assertRaisesRegex(ConflictError, "System pages"):
            await self.service.archive_page(page.id, actor_id=self.actor_id)

        self.uow.commit.assert_not_awaited()
