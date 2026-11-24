import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.application.errors import ConflictError, ResourceNotFoundError
from app.application.projects.dto import ProjectCreateDTO, ProjectUpdateDTO
from app.application.projects.service import ProjectService
from app.infrastructure.database.models.category import Category
from app.infrastructure.database.models.enums import (
    DevelopmentStatus,
    MediaKind,
    ProjectMediaRole,
    ProjectStatus,
)
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.tag import Tag
from app.infrastructure.database.unit_of_work.project import ProjectUnitOfWork


class ProjectServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.uow = MagicMock(spec=ProjectUnitOfWork)
        self.uow.projects = MagicMock()
        self.uow.categories = MagicMock()
        self.uow.tags = MagicMock()
        self.uow.media = MagicMock()
        self.uow.resources = MagicMock()
        self.uow.audit_logs = MagicMock()
        self.uow.projects.get_by_slug = AsyncMock(return_value=None)
        self.uow.projects.get_with_associations_by_id = AsyncMock()
        self.uow.categories.get_active_by_ids = AsyncMock(return_value=[])
        self.uow.tags.get_active_by_ids = AsyncMock(return_value=[])
        self.uow.media.get_by_ids = AsyncMock(return_value=[])
        self.uow.resources.get_by_ids = AsyncMock(return_value=[])
        self.uow.audit_logs.create = AsyncMock()
        self.uow.commit = AsyncMock()
        self.uow.rollback = AsyncMock()

        async def persist(project):
            project.id = uuid4()
            return project

        self.uow.projects.create = AsyncMock(side_effect=persist)
        self.service = ProjectService(self.uow)
        self.actor_id = uuid4()

    def create_data(self, **overrides) -> ProjectCreateDTO:
        values = {
            "title": " Example Project ",
            "slug": "example-project",
            "short_description": " A short description ",
            "development_status": DevelopmentStatus.IN_PROGRESS,
            "display_order": 3,
        }
        values.update(overrides)
        return ProjectCreateDTO(**values)

    async def test_create_project_persists_associations_and_audit_atomically(self) -> None:
        category_id = uuid4()
        tag_id = uuid4()
        category = Category(
            id=category_id,
            name="Backend",
            slug="backend",
            display_order=0,
            is_active=True,
        )
        tag = Tag(id=tag_id, name="Python", slug="python", is_active=True)
        self.uow.categories.get_active_by_ids.return_value = [category]
        self.uow.tags.get_active_by_ids.return_value = [tag]
        created_projects: dict[object, Project] = {}

        async def persist(project: Project) -> Project:
            project.id = uuid4()
            created_projects[project.id] = project
            return project

        async def reload_with_associations(project_id) -> Project | None:
            return created_projects.get(project_id)

        self.uow.projects.create.side_effect = persist
        self.uow.projects.get_with_associations_by_id.side_effect = (
            reload_with_associations
        )

        project = await self.service.create_project(
            self.create_data(
                category_ids=(category_id, category_id),
                tag_ids=(tag_id,),
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(project.title, "Example Project")
        self.assertEqual(project.slug, "example-project")
        self.assertEqual(project.short_description, "A short description")
        self.assertEqual(project.categories, [category])
        self.assertEqual(project.tags, [tag])
        self.uow.projects.get_with_associations_by_id.assert_awaited_once_with(
            project.id
        )
        self.uow.categories.get_active_by_ids.assert_awaited_once_with([category_id])
        self.uow.tags.get_active_by_ids.assert_awaited_once_with([tag_id])
        self.uow.projects.create.assert_awaited_once_with(project)
        self.uow.audit_logs.create.assert_awaited_once()
        audit = self.uow.audit_logs.create.await_args.args[0]
        self.assertEqual(audit.action, "project.created")
        self.assertEqual(audit.user_id, self.actor_id)
        self.assertEqual(audit.entity_id, project.id)
        self.assertEqual(audit.new_values["category_ids"], [str(category_id)])
        self.assertEqual(audit.new_values["tag_ids"], [str(tag_id)])
        self.uow.commit.assert_awaited_once()
        self.uow.rollback.assert_not_awaited()

    async def test_create_project_links_inline_images_from_overview(self) -> None:
        image_id = uuid4()
        image = Media(
            id=image_id,
            kind=MediaKind.IMAGE,
            storage_key="projects/overview.png",
            original_filename="overview.png",
            mime_type="image/png",
            size_bytes=100,
            checksum_sha256="a" * 64,
            alt_text="Overview diagram",
        )
        self.uow.media.get_by_ids.return_value = [image]
        created_projects: dict[object, Project] = {}

        async def persist(project: Project) -> Project:
            project.id = uuid4()
            created_projects[project.id] = project
            return project

        self.uow.projects.create.side_effect = persist
        async def reload_with_associations(project_id) -> Project | None:
            return created_projects.get(project_id)

        self.uow.projects.get_with_associations_by_id.side_effect = (
            reload_with_associations
        )

        project = await self.service.create_project(
            self.create_data(
                overview=(
                    f"![First use](media:{image_id})\\n\\n"
                    f"![Repeated use](media:{image_id})"
                )
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(len(project.media_associations), 1)
        association = project.media_associations[0]
        self.assertEqual(association.media_id, image_id)
        self.assertEqual(association.role, ProjectMediaRole.INLINE)
        self.assertEqual(association.display_order, 0)
        self.assertIs(association.media, image)
        self.uow.media.get_by_ids.assert_awaited_once_with([image_id])

    async def test_update_project_syncs_inline_image_associations(self) -> None:
        image_id = uuid4()
        image = Media(
            id=image_id,
            kind=MediaKind.IMAGE,
            storage_key="projects/overview.png",
            original_filename="overview.png",
            mime_type="image/png",
            size_bytes=100,
            checksum_sha256="b" * 64,
            alt_text="Overview diagram",
        )
        project = self.existing_project()
        self.uow.projects.get_with_associations_by_id.return_value = project
        self.uow.media.get_by_ids.return_value = [image]

        updated = await self.service.update_project(
            project.id,
            ProjectUpdateDTO(
                overview=f"![](media:{image_id})",
                fields_set=frozenset({"overview"}),
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(len(updated.media_associations), 1)
        self.assertEqual(updated.media_associations[0].role, ProjectMediaRole.INLINE)
        self.assertEqual(updated.media_associations[0].media_id, image_id)
        self.uow.commit.assert_awaited_once()

    async def test_update_project_syncs_inline_video_and_document_associations(self) -> None:
        video_id = uuid4()
        document_id = uuid4()
        video = Media(
            id=video_id,
            kind=MediaKind.VIDEO,
            storage_key="projects/walkthrough.mp4",
            original_filename="walkthrough.mp4",
            mime_type="video/mp4",
            size_bytes=100,
            checksum_sha256="e" * 64,
        )
        document = Media(
            id=document_id,
            kind=MediaKind.DOCUMENT,
            storage_key="projects/report.pdf",
            original_filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            checksum_sha256="f" * 64,
        )
        project = self.existing_project()
        self.uow.projects.get_with_associations_by_id.return_value = project
        self.uow.media.get_by_ids.return_value = [video, document]

        updated = await self.service.update_project(
            project.id,
            ProjectUpdateDTO(
                overview=(
                    f'![Product walkthrough](media:{video_id} "media-video")\n\n'
                    f"[Download the report](media:{document_id})"
                ),
                fields_set=frozenset({"overview"}),
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(
            [(item.media_id, item.role) for item in updated.media_associations],
            [
                (video_id, ProjectMediaRole.INLINE),
                (document_id, ProjectMediaRole.INLINE),
            ],
        )
        self.assertEqual(updated.media_associations[0].media.kind, MediaKind.VIDEO)
        self.assertEqual(updated.media_associations[1].media.kind, MediaKind.DOCUMENT)
        self.uow.commit.assert_awaited_once()

    async def test_update_project_rejects_inline_media_kind_mismatch(self) -> None:
        image_id = uuid4()
        image = Media(
            id=image_id,
            kind=MediaKind.IMAGE,
            storage_key="projects/diagram.png",
            original_filename="diagram.png",
            mime_type="image/png",
            size_bytes=100,
            checksum_sha256="1" * 64,
        )
        project = self.existing_project()
        self.uow.projects.get_with_associations_by_id.return_value = project
        self.uow.media.get_by_ids.return_value = [image]

        with self.assertRaisesRegex(ConflictError, "video references"):
            await self.service.update_project(
                project.id,
                ProjectUpdateDTO(
                    overview=f'![Walkthrough](media:{image_id} "media-video")',
                    fields_set=frozenset({"overview"}),
                ),
                actor_id=self.actor_id,
            )

        self.uow.commit.assert_not_awaited()

    async def test_published_project_rejects_inline_image_without_alt_text(self) -> None:
        image_id = uuid4()
        image = Media(
            id=image_id,
            kind=MediaKind.IMAGE,
            storage_key="projects/overview.png",
            original_filename="overview.png",
            mime_type="image/png",
            size_bytes=100,
            checksum_sha256="c" * 64,
        )
        category = Category(
            id=uuid4(),
            name="Analytics",
            slug="analytics",
            display_order=0,
            is_active=True,
        )
        self.uow.categories.get_active_by_ids.return_value = [category]
        self.uow.media.get_by_ids.return_value = [image]

        with self.assertRaises(ConflictError):
            await self.service.create_project(
                self.create_data(
                    overview=f"![](media:{image_id})",
                    status=ProjectStatus.PUBLISHED,
                    published_at=datetime.now(timezone.utc),
                    category_ids=(category.id,),
                ),
                actor_id=self.actor_id,
            )

        self.uow.projects.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_published_project_requires_labels_for_inline_video_and_document(self) -> None:
        category = Category(
            id=uuid4(),
            name="Analytics",
            slug="analytics",
            display_order=0,
            is_active=True,
        )
        self.uow.categories.get_active_by_ids.return_value = [category]
        for kind, filename, mime_type, overview in (
            (
                MediaKind.VIDEO,
                "walkthrough.mp4",
                "video/mp4",
                lambda media_id: f'![ ](media:{media_id} "media-video")',
            ),
            (
                MediaKind.DOCUMENT,
                "report.pdf",
                "application/pdf",
                lambda media_id: f"[ ](media:{media_id})",
            ),
        ):
            with self.subTest(kind=kind):
                media_id = uuid4()
                media = Media(
                    id=media_id,
                    kind=kind,
                    storage_key=f"projects/{filename}",
                    original_filename=filename,
                    mime_type=mime_type,
                    size_bytes=100,
                    checksum_sha256="2" * 64,
                )
                self.uow.media.get_by_ids.return_value = [media]

                with self.assertRaisesRegex(ConflictError, "descriptive text"):
                    await self.service.create_project(
                        self.create_data(
                            overview=overview(media_id),
                            status=ProjectStatus.PUBLISHED,
                            published_at=datetime.now(timezone.utc),
                            category_ids=(category.id,),
                        ),
                        actor_id=self.actor_id,
                    )

        self.uow.projects.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_publishing_checks_saved_inline_images_without_overview_update(self) -> None:
        image_id = uuid4()
        image = Media(
            id=image_id,
            kind=MediaKind.IMAGE,
            storage_key="projects/overview.png",
            original_filename="overview.png",
            mime_type="image/png",
            size_bytes=100,
            checksum_sha256="d" * 64,
        )
        category = Category(
            id=uuid4(),
            name="Analytics",
            slug="analytics",
            display_order=0,
            is_active=True,
        )
        project = self.existing_project()
        project.overview = f"![](media:{image_id})"
        project.categories = [category]
        self.uow.projects.get_with_associations_by_id.return_value = project
        self.uow.media.get_by_ids.return_value = [image]

        with self.assertRaises(ConflictError):
            await self.service.update_project(
                project.id,
                ProjectUpdateDTO(
                    status=ProjectStatus.PUBLISHED,
                    published_at=datetime.now(timezone.utc),
                    fields_set=frozenset({"status", "published_at"}),
                ),
                actor_id=self.actor_id,
            )

        self.assertEqual(project.status, ProjectStatus.DRAFT)

    async def test_create_project_rejects_existing_slug(self) -> None:
        self.uow.projects.get_by_slug.return_value = MagicMock()

        with self.assertRaises(ConflictError):
            await self.service.create_project(
                self.create_data(slug=" example-project "),
                actor_id=self.actor_id,
            )

        self.uow.projects.get_by_slug.assert_awaited_once_with("example-project")
        self.uow.projects.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_create_project_rejects_missing_or_inactive_category(self) -> None:
        category_id = uuid4()

        with self.assertRaises(ResourceNotFoundError):
            await self.service.create_project(
                self.create_data(category_ids=(category_id,)),
                actor_id=self.actor_id,
            )

        self.uow.projects.create.assert_not_awaited()
        self.uow.audit_logs.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_create_published_project_requires_a_category(self) -> None:
        with self.assertRaises(ConflictError):
            await self.service.create_project(
                self.create_data(
                    status=ProjectStatus.PUBLISHED,
                    published_at=datetime.now(timezone.utc),
                ),
                actor_id=self.actor_id,
            )

        self.uow.projects.create.assert_not_awaited()
        self.uow.audit_logs.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_create_project_rejects_missing_or_inactive_tag(self) -> None:
        tag_id = uuid4()

        with self.assertRaises(ResourceNotFoundError):
            await self.service.create_project(
                self.create_data(tag_ids=(tag_id,)),
                actor_id=self.actor_id,
            )

        self.uow.projects.create.assert_not_awaited()
        self.uow.audit_logs.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_create_project_rolls_back_after_database_integrity_error(self) -> None:
        self.uow.projects.create.side_effect = IntegrityError(
            "INSERT INTO projects", {}, Exception("duplicate slug")
        )
        self.uow.projects.get_by_slug.side_effect = [None, MagicMock()]

        with self.assertRaises(ConflictError):
            await self.service.create_project(
                self.create_data(),
                actor_id=self.actor_id,
            )

        self.uow.rollback.assert_awaited_once()
        self.uow.commit.assert_not_awaited()

    async def test_create_project_rolls_back_on_unexpected_error(self) -> None:
        self.uow.audit_logs.create.side_effect = RuntimeError("audit write failed")

        with self.assertRaisesRegex(RuntimeError, "audit write failed"):
            await self.service.create_project(
                self.create_data(),
                actor_id=self.actor_id,
            )

        self.uow.rollback.assert_awaited_once()
        self.uow.commit.assert_not_awaited()

    def existing_project(self) -> Project:
        return Project(
            id=uuid4(),
            title="Existing",
            slug="existing",
            short_description="Existing description",
            development_status=DevelopmentStatus.PLANNING,
            display_order=0,
            status=ProjectStatus.DRAFT,
            is_featured=False,
            categories=[],
            tags=[],
        )

    async def test_update_project_commits_fields_associations_and_audit(self) -> None:
        project = self.existing_project()
        category_id = uuid4()
        tag_id = uuid4()
        category = Category(
            id=category_id,
            name="Backend",
            slug="backend",
            display_order=0,
            is_active=True,
        )
        tag = Tag(id=tag_id, name="Python", slug="python", is_active=True)
        self.uow.projects.get_with_associations_by_id.return_value = project
        self.uow.categories.get_active_by_ids.return_value = [category]
        self.uow.tags.get_active_by_ids.return_value = [tag]

        updated = await self.service.update_project(
            project.id,
            ProjectUpdateDTO(
                title=" Updated ",
                category_ids=(category_id,),
                tag_ids=(tag_id,),
                fields_set=frozenset({"title", "category_ids", "tag_ids"}),
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(updated.title, "Updated")
        self.assertEqual(updated.categories, [category])
        self.assertEqual(updated.tags, [tag])
        self.uow.audit_logs.create.assert_awaited_once()
        audit = self.uow.audit_logs.create.await_args.args[0]
        self.assertEqual(audit.action, "project.updated")
        self.assertEqual(audit.old_values["title"], "Existing")
        self.assertEqual(audit.new_values["title"], "Updated")
        self.assertEqual(audit.new_values["category_ids"], [str(category_id)])
        self.uow.commit.assert_awaited_once()
        self.uow.rollback.assert_not_awaited()

    async def test_update_project_returns_reloaded_project(self) -> None:
        project = self.existing_project()
        updated_project = self.existing_project()
        updated_project.id = project.id
        updated_project.title = "Updated"
        updated_project.updated_at = datetime.now(timezone.utc)
        self.uow.projects.get_with_associations_by_id.side_effect = [
            project,
            updated_project,
        ]

        result = await self.service.update_project(
            project.id,
            ProjectUpdateDTO(
                title="Updated",
                fields_set=frozenset({"title"}),
            ),
            actor_id=self.actor_id,
        )

        self.assertIs(result, updated_project)
        self.uow.projects.get_with_associations_by_id.assert_has_awaits(
            [call(project.id), call(project.id)]
        )
        self.uow.commit.assert_awaited_once()

    async def test_update_project_rejects_publishing_without_timestamp(self) -> None:
        project = self.existing_project()
        self.uow.projects.get_with_associations_by_id.return_value = project

        with self.assertRaises(ConflictError):
            await self.service.update_project(
                project.id,
                ProjectUpdateDTO(
                    status=ProjectStatus.PUBLISHED,
                    fields_set=frozenset({"status"}),
                ),
                actor_id=self.actor_id,
            )

        self.assertEqual(project.status, ProjectStatus.DRAFT)
        self.uow.audit_logs.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_update_project_rejects_publishing_without_a_category(self) -> None:
        project = self.existing_project()
        self.uow.projects.get_with_associations_by_id.return_value = project

        with self.assertRaises(ConflictError):
            await self.service.update_project(
                project.id,
                ProjectUpdateDTO(
                    status=ProjectStatus.PUBLISHED,
                    published_at=datetime.now(timezone.utc),
                    fields_set=frozenset({"status", "published_at"}),
                ),
                actor_id=self.actor_id,
            )

        self.assertEqual(project.status, ProjectStatus.DRAFT)
        self.uow.audit_logs.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_update_project_preserves_inactive_associations(self) -> None:
        project = self.existing_project()
        inactive_category = Category(
            id=uuid4(),
            name="Inactive category",
            slug="inactive-category",
            display_order=0,
            is_active=False,
        )
        inactive_tag = Tag(
            id=uuid4(),
            name="Inactive tag",
            slug="inactive-tag",
            is_active=False,
        )
        project.categories = [inactive_category]
        project.tags = [inactive_tag]
        self.uow.projects.get_with_associations_by_id.return_value = project

        updated = await self.service.update_project(
            project.id,
            ProjectUpdateDTO(
                category_ids=(),
                tag_ids=(),
                fields_set=frozenset({"category_ids", "tag_ids"}),
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(updated.categories, [inactive_category])
        self.assertEqual(updated.tags, [inactive_tag])
        self.uow.categories.get_active_by_ids.assert_awaited_once_with([])
        self.uow.tags.get_active_by_ids.assert_awaited_once_with([])

    async def test_update_project_rejects_inactive_associations(self) -> None:
        project = self.existing_project()
        self.uow.projects.get_with_associations_by_id.return_value = project
        self.uow.categories.get_active_by_ids.return_value = []

        with self.assertRaises(ResourceNotFoundError):
            await self.service.update_project(
                project.id,
                ProjectUpdateDTO(
                    title="Should not apply",
                    category_ids=(uuid4(),),
                    fields_set=frozenset({"title", "category_ids"}),
                ),
                actor_id=self.actor_id,
            )

        self.assertEqual(project.title, "Existing")
        self.uow.audit_logs.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()
