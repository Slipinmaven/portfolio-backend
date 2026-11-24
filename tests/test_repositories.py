import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.category import Category
from app.infrastructure.database.models.enums import (
    DevelopmentStatus,
    MediaKind,
    ProjectMediaRole,
    ProjectStatus,
)
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.media_link import MediaLink
from app.infrastructure.database.models.page import Page
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.project_media import ProjectMedia
from app.infrastructure.database.models.session import Session
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.base import BaseRepository
from app.infrastructure.database.repositories.category import CategoryRepository
from app.infrastructure.database.repositories.login_attempt import (
    LoginAttemptRepository,
)
from app.infrastructure.database.repositories.media import MediaRepository
from app.infrastructure.database.repositories.media_link import MediaLinkRepository
from app.infrastructure.database.repositories.page import PageRepository
from app.infrastructure.database.repositories.project import ProjectRepository
from app.infrastructure.database.repositories.project_media import (
    ProjectMediaRepository,
)
from app.infrastructure.database.repositories.session import SessionRepository
from app.infrastructure.database.repositories.trusted_device import (
    TrustedDeviceRepository,
)
from app.infrastructure.database.repositories.user import UserRepository


class RepositoryTests(unittest.TestCase):
    def test_page_repository_refreshes_revisions_for_existing_page(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            session.scalar.return_value = MagicMock(spec=Page)
            repository = PageRepository(session)

            await repository.get_with_revisions_by_id(uuid4())

            statement = session.scalar.await_args.args[0]
            self.assertTrue(
                statement.get_execution_options().get("populate_existing")
            )

        asyncio.run(run())

    def test_media_repository_gets_by_storage_key_and_checksum(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            media = MagicMock(spec=Media)
            session.scalar.return_value = media
            result = MagicMock()
            result.all.return_value = [media]
            session.scalars.return_value = result
            repository = MediaRepository(session)

            found = await repository.get_by_storage_key("media/abc.webp")
            matching = await repository.get_by_checksum("a" * 64)

            key_query = session.scalar.await_args.args[0]
            self.assertIn(
                "media.storage_key = ",
                str(key_query.compile(dialect=postgresql.dialect())),
            )
            checksum_query = session.scalars.await_args.args[0]
            self.assertIn(
                "media.checksum_sha256 = ",
                str(checksum_query.compile(dialect=postgresql.dialect())),
            )
            self.assertEqual(found, media)
            self.assertEqual(matching, [media])

        asyncio.run(run())

    def test_media_repository_lists_by_kind_with_total(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            result = MagicMock()
            result.all.return_value = []
            session.scalars.return_value = result
            session.scalar.return_value = 2
            repository = MediaRepository(session)

            media, total = await repository.list_media(
                offset=1,
                limit=5,
                kind=MediaKind.IMAGE,
                unused_only=True,
            )

            query = session.scalars.await_args.args[0]
            compiled = str(query.compile(dialect=postgresql.dialect()))
            count_query = session.scalar.await_args.args[0]
            count_compiled = str(count_query.compile(dialect=postgresql.dialect()))
            self.assertEqual(media, [])
            self.assertEqual(total, 2)
            self.assertIn("media.kind =", compiled)
            self.assertIn("NOT ((EXISTS", compiled)
            self.assertIn("project_media.media_id = media.id", compiled)
            self.assertIn("post_media.media_id = media.id", compiled)
            self.assertIn(
                "site_settings.profile_image_media_id = media.id",
                compiled,
            )
            self.assertIn("NOT ((EXISTS", count_compiled)
            self.assertIn("post_media.media_id = media.id", count_compiled)
            self.assertIn(
                "ORDER BY media.size_bytes DESC, media.created_at DESC",
                compiled,
            )
            self.assertIn("LIMIT", compiled)
            self.assertIn("OFFSET", compiled)

        asyncio.run(run())

    def test_media_repository_reports_storage_usage_and_largest_files(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            aggregate_result = MagicMock()
            aggregate_result.all.return_value = [
                (MediaKind.IMAGE, 2, 100),
                (MediaKind.VIDEO, 1, 500),
            ]
            video_keys_result = MagicMock()
            video_keys_result.all.return_value = ["2026/11/video.mp4"]
            largest_result = MagicMock()
            largest_result.all.return_value = []
            session.execute.return_value = aggregate_result
            session.scalars.side_effect = [video_keys_result, largest_result]
            repository = MediaRepository(session)

            usage = await repository.get_storage_usage_by_kind()
            video_keys = await repository.list_video_storage_keys()
            largest = await repository.list_largest_media(limit=5)

            usage_query = session.execute.await_args.args[0]
            video_query = session.scalars.await_args_list[0].args[0]
            largest_query = session.scalars.await_args_list[1].args[0]
            self.assertIn("GROUP BY media.kind", str(usage_query.compile(
                dialect=postgresql.dialect()
            )))
            self.assertIn("media.kind =", str(video_query.compile(
                dialect=postgresql.dialect()
            )))
            self.assertIn("ORDER BY media.size_bytes DESC", str(largest_query.compile(
                dialect=postgresql.dialect()
            )))
            self.assertEqual(usage, [(MediaKind.IMAGE, 2, 100), (MediaKind.VIDEO, 1, 500)])
            self.assertEqual(video_keys, ["2026/11/video.mp4"])
            self.assertEqual(largest, [])

        asyncio.run(run())

    def test_media_link_repository_queries_media_links_in_display_order(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            media_id = uuid4()
            link = MagicMock(spec=MediaLink)
            session.scalar.return_value = link
            result = MagicMock()
            result.all.return_value = [link]
            session.scalars.return_value = result
            repository = MediaLinkRepository(session)

            found = await repository.get_by_media_and_url(
                media_id,
                "https://example.com/source",
            )
            links = await repository.list_by_media_id(media_id)

            lookup_query = session.scalar.await_args.args[0]
            lookup_compiled = str(lookup_query.compile(dialect=postgresql.dialect()))
            list_query = session.scalars.await_args.args[0]
            list_compiled = str(list_query.compile(dialect=postgresql.dialect()))
            self.assertEqual(found, link)
            self.assertEqual(links, [link])
            self.assertIn("media_links.media_id =", lookup_compiled)
            self.assertIn("media_links.url =", lookup_compiled)
            self.assertIn("ORDER BY media_links.display_order", list_compiled)

        asyncio.run(run())

    def test_project_media_repository_queries_cover_and_project_items(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            project_id = uuid4()
            association = MagicMock(spec=ProjectMedia)
            session.scalar.return_value = association
            result = MagicMock()
            result.all.return_value = [association]
            session.scalars.return_value = result
            repository = ProjectMediaRepository(session)

            cover = await repository.get_cover_for_project(project_id)
            associations = await repository.list_by_project(
                project_id,
                role=ProjectMediaRole.GALLERY,
            )

            cover_query = session.scalar.await_args.args[0]
            cover_compiled = str(cover_query.compile(dialect=postgresql.dialect()))
            list_query = session.scalars.await_args.args[0]
            list_compiled = str(list_query.compile(dialect=postgresql.dialect()))
            self.assertEqual(cover, association)
            self.assertEqual(associations, [association])
            self.assertIn("project_media.project_id =", cover_compiled)
            self.assertIn("project_media.role =", cover_compiled)
            self.assertIn("project_media.role =", list_compiled)
            self.assertIn("ORDER BY project_media.role", list_compiled)

            await repository.delete_association(
                project_id,
                uuid4(),
                ProjectMediaRole.GALLERY,
            )
            delete_statement = session.execute.await_args.args[0]
            delete_compiled = str(
                delete_statement.compile(dialect=postgresql.dialect())
            )
            self.assertIn("DELETE FROM project_media", delete_compiled)

        asyncio.run(run())

    def test_project_media_repository_checks_published_usage(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            session.scalar.return_value = True
            repository = ProjectMediaRepository(session)

            has_published_usage = await repository.has_published_usage(uuid4())

            query = session.scalar.await_args.args[0]
            compiled = str(query.compile(dialect=postgresql.dialect()))
            self.assertTrue(has_published_usage)
            self.assertIn("EXISTS", compiled.upper())
            self.assertIn("project_media.media_id =", compiled)
            self.assertIn("project_media.project_id = projects.id", compiled)
            self.assertIn("projects.status =", compiled)

        asyncio.run(run())

    def test_project_repository_lists_filtered_projects_with_total(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            project = MagicMock(spec=Project)
            result = MagicMock()
            result.all.return_value = [project]
            session.scalars.return_value = result
            session.scalar.return_value = 4
            repository = ProjectRepository(session)
            category_id = uuid4()

            projects, total = await repository.list_projects(
                offset=2,
                limit=5,
                status=ProjectStatus.PUBLISHED,
                development_status=DevelopmentStatus.COMPLETED,
                is_featured=True,
                category_id=category_id,
                tag_id=uuid4(),
                active_catalog_only=True,
            )

            query = session.scalars.await_args.args[0]
            compiled = str(query.compile(dialect=postgresql.dialect()))
            self.assertEqual(projects, [project])
            self.assertEqual(total, 4)
            self.assertIn("projects.status = ", compiled)
            self.assertIn("projects.development_status = ", compiled)
            self.assertIn("projects.is_featured = true", compiled)
            self.assertIn("project_categories", compiled)
            self.assertIn("categories.is_active IS true", compiled)
            self.assertIn("project_tags", compiled)
            self.assertIn("tags.is_active IS true", compiled)
            self.assertIn("ORDER BY projects.display_order", compiled)
            self.assertIn("LIMIT", compiled)
            self.assertIn("OFFSET", compiled)
            session.scalar.assert_awaited_once()

        asyncio.run(run())

    def test_project_repository_loads_detail_associations_without_lazy_queries(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            project = MagicMock(spec=Project)
            session.scalar.return_value = project
            repository = ProjectRepository(session)

            by_id = await repository.get_with_associations_by_id(uuid4())
            id_query = session.scalar.await_args.args[0]
            id_compiled = str(id_query.compile(dialect=postgresql.dialect()))
            self.assertEqual(by_id, project)
            self.assertIn("projects.id =", id_compiled)
            self.assertEqual(len(id_query._with_options), 4)

            by_slug = await repository.get_published_by_slug("published")
            slug_query = session.scalar.await_args.args[0]
            slug_compiled = str(slug_query.compile(dialect=postgresql.dialect()))
            self.assertEqual(by_slug, project)
            self.assertIn("projects.slug =", slug_compiled)
            self.assertIn("projects.status =", slug_compiled)
            self.assertEqual(len(slug_query._with_options), 4)

        asyncio.run(run())

    def test_category_repository_lists_ordered_categories_with_total(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            category = MagicMock(spec=Category)
            result = MagicMock()
            result.all.return_value = [category]
            session.scalars.return_value = result
            session.scalar.return_value = 3
            repository = CategoryRepository(session)

            categories, total = await repository.list_categories(
                offset=1,
                limit=10,
                is_active=False,
            )

            query = session.scalars.await_args.args[0]
            compiled = str(query.compile(dialect=postgresql.dialect()))
            self.assertEqual(categories, [category])
            self.assertEqual(total, 3)
            self.assertIn("categories.is_active = false", compiled)
            self.assertIn("ORDER BY categories.parent_id", compiled)
            self.assertIn("LIMIT", compiled)
            self.assertIn("OFFSET", compiled)
            count_query = session.scalar.await_args.args[0]
            count_compiled = str(count_query.compile(dialect=postgresql.dialect()))
            self.assertIn("count(*)", count_compiled)

        asyncio.run(run())

    def test_login_attempt_repository_upserts_failure_window(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            repository = LoginAttemptRepository(session)
            now = datetime.now(timezone.utc)

            await repository.record_failure(
                "hashed-client-key",
                now=now,
                window=timedelta(minutes=15),
                maximum_failures=10,
            )

            statement = session.execute.await_args_list[0].args[0]
            compiled = str(statement.compile(dialect=postgresql.dialect()))
            self.assertIn("INSERT INTO login_attempts", compiled)
            self.assertIn("ON CONFLICT (client_key) DO UPDATE", compiled)
            self.assertIn("failure_count", compiled)
            self.assertIn("blocked_until", compiled)
            self.assertEqual(session.execute.await_count, 2)

        asyncio.run(run())

    def test_audit_log_repository_lists_filtered_logs_with_pagination_and_total(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            audit_log = MagicMock()
            result = MagicMock()
            result.all.return_value = [audit_log]
            session.scalars.return_value = result
            session.scalar.return_value = 5
            repository = AuditLogRepository(session)
            user_id = uuid4()
            request_id = uuid4()

            logs, total = await repository.list_audit_logs(
                offset=2,
                limit=1,
                user_id=user_id,
                status="failure",
                request_id=request_id,
            )

            query = session.scalars.await_args.args[0]
            compiled = str(query.compile(dialect=postgresql.dialect()))
            self.assertEqual(logs, [audit_log])
            self.assertEqual(total, 5)
            self.assertIn("audit_logs.user_id = ", compiled)
            self.assertIn("audit_logs.status = ", compiled)
            self.assertIn("audit_logs.request_id = ", compiled)
            self.assertIn("ORDER BY audit_logs.created_at DESC", compiled)
            self.assertIn("LIMIT", compiled)
            self.assertIn("OFFSET", compiled)
            session.scalar.assert_awaited_once()

        asyncio.run(run())

    def test_audit_log_repository_gets_logs_by_request_id(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            audit_log = MagicMock()
            result = MagicMock()
            result.all.return_value = [audit_log]
            session.scalars.return_value = result
            repository = AuditLogRepository(session)

            logs = await repository.get_by_request_id(uuid4())

            query = session.scalars.await_args.args[0]
            compiled = str(query.compile(dialect=postgresql.dialect()))
            self.assertEqual(logs, [audit_log])
            self.assertIn("audit_logs.request_id = ", compiled)
            self.assertIn("ORDER BY audit_logs.created_at DESC", compiled)
            session.scalars.assert_awaited_once()

        asyncio.run(run())

    def test_user_repository_lists_users_with_pagination_and_total(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            admin = MagicMock(spec=User)
            editor = MagicMock(spec=User)
            result = MagicMock()
            result.all.return_value = [admin, editor]
            session.scalars.return_value = result
            session.scalar.return_value = 7
            repository = UserRepository(session)

            users, total = await repository.list_users(offset=3, limit=2)

            query = session.scalars.await_args.args[0]
            compiled = str(query.compile(dialect=postgresql.dialect()))
            self.assertEqual(users, [admin, editor])
            self.assertEqual(total, 7)
            self.assertIn("ORDER BY users.created_at DESC", compiled)
            self.assertIn("LIMIT", compiled)
            self.assertIn("OFFSET", compiled)
            self.assertIn("users.role IN", compiled)
            session.scalar.assert_awaited_once()

        asyncio.run(run())

    def test_user_repository_deletes_related_rows_and_preserves_audit_history(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            user = MagicMock(spec=User)
            user.id = uuid4()
            repository = UserRepository(session)

            await repository.delete_account(user)

            self.assertEqual(session.execute.await_count, 4)
            statements = [call.args[0] for call in session.execute.await_args_list]
            self.assertIn("DELETE FROM sessions", str(statements[0]))
            self.assertIn("DELETE FROM trusted_devices", str(statements[1]))
            self.assertIn("UPDATE audit_logs", str(statements[2]))
            self.assertIn("DELETE FROM users", str(statements[3]))
            session.commit.assert_not_awaited()

        asyncio.run(run())

    def test_session_repository_revokes_only_active_sessions_for_user(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            repository = SessionRepository(session)
            user_id = uuid4()

            await repository.revoke_active_for_user(
                user_id,
                revoked_at=datetime.now(timezone.utc),
                reason="password_changed",
            )

            statement = session.execute.await_args.args[0]
            compiled = statement.compile(dialect=postgresql.dialect())
            self.assertIn("UPDATE sessions", str(compiled))
            self.assertIn("sessions.user_id = ", str(compiled))
            self.assertIn("sessions.revoked_at IS NULL", str(compiled))
            self.assertIn("password_changed", compiled.params.values())

        asyncio.run(run())

    def test_trusted_device_lock_targets_only_trusted_devices(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            session.scalar.return_value = None
            repository = TrustedDeviceRepository(session)

            await repository.get_by_device_token_hash("hashed-token")

            statement = session.scalar.await_args.args[0]
            compiled = str(statement.compile(dialect=postgresql.dialect()))
            self.assertIn("LEFT OUTER JOIN users", compiled)
            self.assertIn("FOR UPDATE OF trusted_devices", compiled)

        asyncio.run(run())

    def test_session_repository_fetches_by_refresh_token_hash(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            login_session = MagicMock(spec=Session)
            session.scalar.return_value = login_session
            repository = SessionRepository(session)

            result = await repository.get_by_refresh_token_hash("hashed-token")

            self.assertIs(result, login_session)
            session.scalar.assert_awaited_once()
            statement = session.scalar.await_args.args[0]
            compiled = str(statement.compile(dialect=postgresql.dialect()))
            self.assertIn("LEFT OUTER JOIN trusted_devices", compiled)
            self.assertIn("FOR UPDATE OF sessions", compiled)

        asyncio.run(run())

    def test_base_repository_fetches_by_primary_key(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            user = MagicMock(spec=User)
            user_id = uuid4()
            session.get.return_value = user
            repository = BaseRepository[User, type(user_id)](session, User)

            result = await repository.get_by_id(user_id)

            self.assertIs(result, user)
            session.get.assert_awaited_once_with(User, user_id)

        asyncio.run(run())

    def test_base_repository_lists_entities(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            user = MagicMock(spec=User)
            scalar_result = MagicMock()
            scalar_result.all.return_value = [user]
            session.scalars.return_value = scalar_result
            repository = BaseRepository[User, object](session, User)

            result = await repository.get_all()

            self.assertEqual(result, [user])
            session.scalars.assert_awaited_once()

        asyncio.run(run())

    def test_base_repository_creates_without_committing(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            user = MagicMock(spec=User)
            repository = UserRepository(session)

            result = await repository.create(user)

            self.assertIs(result, user)
            session.add.assert_called_once_with(user)
            session.flush.assert_awaited_once()
            session.refresh.assert_awaited_once_with(user)
            session.commit.assert_not_awaited()

        asyncio.run(run())

    def test_base_repository_deletes_without_committing(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            user = MagicMock(spec=User)
            repository = UserRepository(session)

            await repository.delete(user)

            session.delete.assert_awaited_once_with(user)
            session.flush.assert_awaited_once()
            session.commit.assert_not_awaited()

        asyncio.run(run())
