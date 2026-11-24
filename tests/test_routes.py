import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.application.auth.dto import AuthTokens
from app.application.errors import AppError, AuthorizationError
from app.application.users.dto import CreateEditorData, UpdateUserData
from app.infrastructure.database.session import get_db_session
from app.infrastructure.database.models.enums import UserRole
from app.infrastructure.database.models.user import User
from app.main import app
from app.presentation.dependencies.auth import (
    get_current_user,
    require_admin,
    require_editor_or_admin,
)
from app.presentation.dependencies.services import get_auth_service, get_user_service
from app.presentation.middleware.exception_handling import ExceptionHandlingMiddleware
from app.presentation.middleware.request_logging import RequestLoggingMiddleware


class RouteTests(unittest.TestCase):
    def test_root_route_keeps_existing_response(self) -> None:
        with TestClient(app) as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Hello, World!"})

    def test_versioned_health_route(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_me_returns_safe_current_user_profile(self) -> None:
        user = User(
            id=uuid4(),
            email="user@example.com",
            password_hash="do-not-return-this",
            first_name="Test",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        app.dependency_overrides[get_current_user] = lambda: user
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["email"], "user@example.com")
        self.assertEqual(body["role"], "editor")
        self.assertNotIn("password_hash", body)

    def test_role_dependencies_accept_admin_and_editor_as_configured(self) -> None:
        async def run() -> None:
            editor = User(
                email="editor@example.com",
                password_hash="hashed",
                first_name="Edit",
                last_name="Or",
                role=UserRole.EDITOR,
                is_active=True,
            )
            admin = User(
                email="admin@example.com",
                password_hash="hashed",
                first_name="Ad",
                last_name="Min",
                role=UserRole.ADMIN,
                is_active=True,
            )

            self.assertIs(await require_editor_or_admin(editor), editor)
            self.assertIs(await require_admin(admin), admin)
            with self.assertRaises(AuthorizationError):
                await require_admin(editor)
                

        asyncio.run(run())

    def test_admin_can_create_editor_through_user_service(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed-editor-password",
            first_name="New",
            last_name="Editor",
            role=UserRole.EDITOR,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        captured: dict[str, CreateEditorData] = {}

        class FakeUserService:
            async def create_editor(self, data: CreateEditorData) -> User:
                captured["data"] = data
                return editor

        app.dependency_overrides[require_admin] = lambda: admin
        app.dependency_overrides[get_user_service] = lambda: FakeUserService()
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/users",
                json={
                    "email": "editor@example.com",
                    "password": "long-enough-password",
                    "first_name": "New",
                    "last_name": "Editor",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"], "editor")
        self.assertNotIn("password_hash", response.json())
        self.assertEqual(captured["data"].created_by_admin_id, str(admin.id))
        self.assertNotIn("long-enough-password", repr(captured["data"]))

    def test_editor_cannot_create_another_user(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        app.dependency_overrides[get_current_user] = lambda: editor
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/users",
                json={
                    "email": "new-editor@example.com",
                    "password": "long-enough-password",
                    "first_name": "New",
                    "last_name": "Editor",
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_create_user_request_cannot_choose_admin_role(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        app.dependency_overrides[require_admin] = lambda: admin
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/users",
                json={
                    "email": "new-editor@example.com",
                    "password": "long-enough-password",
                    "first_name": "New",
                    "last_name": "Editor",
                    "role": "admin",
                },
            )

        self.assertEqual(response.status_code, 422)

    def test_admin_can_update_own_profile(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="unchanged-hash",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        captured: dict[str, UpdateUserData] = {}

        class FakeUserService:
            async def update_profile(
                self,
                user_id,
                data: UpdateUserData,
                *,
                actor_id,
                editor_only=False,
            ) -> User:
                self.assert_ids(user_id, actor_id, admin.id)
                if editor_only:
                    raise AssertionError("Self-profile updates should not be editor-only.")
                captured["data"] = data
                admin.first_name = data.first_name or admin.first_name
                return admin

            @staticmethod
            def assert_ids(user_id, actor_id, expected_id) -> None:
                if user_id != expected_id or actor_id != expected_id:
                    raise AssertionError("Self-profile update used incorrect identity.")

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_user_service] = lambda: FakeUserService()
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/users/me",
                json={"first_name": "Updated", "password": "new-secure-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["first_name"], "Updated")
        self.assertNotIn("password_hash", response.json())
        self.assertEqual(captured["data"].password, "new-secure-password")

    def test_admin_can_update_editor_but_editor_cannot_update_other_user(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        captured: dict[str, object] = {}

        class FakeUserService:
            async def update_profile(
                self,
                user_id,
                data: UpdateUserData,
                *,
                actor_id,
                editor_only=False,
            ) -> User:
                captured["user_id"] = user_id
                captured["editor_only"] = editor_only
                captured["actor_id"] = actor_id
                editor.last_name = data.last_name or editor.last_name
                return editor

        app.dependency_overrides[require_admin] = lambda: admin
        app.dependency_overrides[get_user_service] = lambda: FakeUserService()
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/users/{editor.id}",
                json={"last_name": "Updated"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["last_name"], "Updated")
        self.assertTrue(captured["editor_only"])
        self.assertEqual(captured["actor_id"], admin.id)

        app.dependency_overrides.clear()
        app.dependency_overrides[get_current_user] = lambda: editor
        self.addCleanup(app.dependency_overrides.clear)
        with TestClient(app) as client:
            forbidden = client.patch(
                f"/api/v1/users/{admin.id}",
                json={"last_name": "Updated"},
            )
        self.assertEqual(forbidden.status_code, 403)

    def test_profile_update_rejects_empty_null_and_unrecognized_fields(self) -> None:
        user = User(
            id=uuid4(),
            email="user@example.com",
            password_hash="hashed",
            first_name="Test",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        app.dependency_overrides[get_current_user] = lambda: user
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            empty = client.patch("/api/v1/users/me", json={})
            null_value = client.patch("/api/v1/users/me", json={"first_name": None})
            role_field = client.patch(
                "/api/v1/users/me",
                json={"role": "admin"},
            )

        self.assertEqual(empty.status_code, 422)
        self.assertEqual(null_value.status_code, 422)
        self.assertEqual(role_field.status_code, 422)

    def test_admin_can_list_admins_and_editors_with_pagination(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="secret-hash",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="another-secret-hash",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        captured: dict[str, int] = {}

        class FakeUserService:
            async def list_users(self, *, offset: int, limit: int):
                captured["offset"] = offset
                captured["limit"] = limit
                return [admin, editor], 12

        app.dependency_overrides[require_admin] = lambda: admin
        app.dependency_overrides[get_user_service] = lambda: FakeUserService()
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.get("/api/v1/users?offset=2&limit=5")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 12)
        self.assertEqual(body["offset"], 2)
        self.assertEqual(body["limit"], 5)
        self.assertEqual([user["role"] for user in body["users"]], ["admin", "editor"])
        self.assertTrue(all("password_hash" not in user for user in body["users"]))
        self.assertEqual(captured, {"offset": 2, "limit": 5})

    def test_editor_cannot_list_users(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: editor
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.get("/api/v1/users")

        self.assertEqual(response.status_code, 403)

    def test_admin_can_delete_editor_account(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
        )
        target_id = uuid4()
        captured: dict[str, object] = {}

        class FakeUserService:
            async def delete_editor(self, user_id, *, actor_id) -> None:
                captured["user_id"] = user_id
                captured["actor_id"] = actor_id

        app.dependency_overrides[require_admin] = lambda: admin
        app.dependency_overrides[get_user_service] = lambda: FakeUserService()
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.delete(f"/api/v1/users/{target_id}")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(captured["user_id"], target_id)
        self.assertEqual(captured["actor_id"], admin.id)

    def test_editor_cannot_delete_user_account(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: editor
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.delete(f"/api/v1/users/{uuid4()}")

        self.assertEqual(response.status_code, 403)

    def test_request_id_is_preserved_when_valid(self) -> None:
        request_id = "client-request:123"
        with TestClient(app) as client:
            response = client.get("/", headers={"X-Request-ID": request_id})

        self.assertEqual(response.headers["x-request-id"], request_id)

    def test_invalid_request_id_is_replaced(self) -> None:
        with TestClient(app) as client:
            response = client.get("/", headers={"X-Request-ID": "bad\r\nvalue"})

        request_id = response.headers["x-request-id"]
        self.assertNotEqual(request_id, "bad\r\nvalue")
        self.assertRegex(request_id, r"^[0-9a-f-]{36}$")

    def test_unhandled_exception_returns_safe_error_with_request_id(self) -> None:
        test_app = FastAPI()

        @test_app.get("/failure")
        async def fail() -> None:
            raise RuntimeError("sensitive internal details")

        test_app.add_middleware(ExceptionHandlingMiddleware)
        test_app.add_middleware(RequestLoggingMiddleware)

        with self.assertLogs("app.error", level="ERROR") as captured:
            with TestClient(test_app) as client:
                response = client.get("/failure")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Internal server error"})
        self.assertRegex(response.headers["x-request-id"], r"^[0-9a-f-]{36}$")
        self.assertIn("sensitive internal details", captured.output[0])

    def test_application_error_returns_defined_status_and_payload(self) -> None:
        test_app = FastAPI()
        error = AppError(
            code="AUTHENTICATION_FAILED",
            message="Authentication failed.",
            status_code=401,
        )
        self.assertEqual(str(error), "Authentication failed.")

        @test_app.get("/failure")
        async def fail() -> None:
            raise error

        test_app.add_middleware(ExceptionHandlingMiddleware)
        test_app.add_middleware(RequestLoggingMiddleware)

        with TestClient(test_app) as client:
            response = client.get("/failure")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "code": "AUTHENTICATION_FAILED",
                "message": "Authentication failed.",
            },
        )
        self.assertRegex(response.headers["x-request-id"], r"^[0-9a-f-]{36}$")

    def test_readiness_route_checks_database(self) -> None:
        session = AsyncMock()
        app.dependency_overrides[get_db_session] = lambda: session
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.get("/api/v1/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})
        session.execute.assert_awaited_once()

    def test_login_passes_client_ip_and_login_data_to_service(self) -> None:
        captured = {}

        class FakeAuthService:
            async def login(self, data) -> AuthTokens:
                captured["data"] = data
                return AuthTokens(
                    user_id="user-id",
                    access_token="access-jwt",
                    refresh_token="refresh-secret",
                    access_expires_in=900,
                    refresh_max_age=604800,
                )

        app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "secret-password",
                    "trusted_device": True,
                },
                headers={
                    "user-agent": "TestClient/1.0",
                    "origin": "http://testserver",
                },
            )

        self.assertEqual(response.status_code, 200)
        login_data = captured["data"]
        self.assertEqual(login_data.email, "user@example.com")
        self.assertEqual(login_data.password, "secret-password")
        self.assertTrue(login_data.trusted_device)
        self.assertEqual(login_data.client_ip, "testclient")
        self.assertEqual(login_data.user_agent, "TestClient/1.0")
        self.assertNotIn("secret-password", repr(login_data))
        self.assertEqual(response.json()["access_token"], "access-jwt")
        self.assertIn("refresh_token=refresh-secret", response.headers["set-cookie"])
        self.assertIn("httponly", response.headers["set-cookie"].lower())

    def test_login_sets_trusted_device_cookie_when_requested(self) -> None:
        class FakeAuthService:
            async def login(self, data) -> AuthTokens:
                if not data.trusted_device:
                    raise AssertionError("Expected trusted_device=True")
                return AuthTokens(
                    user_id="user-id",
                    access_token="access-jwt",
                    refresh_token="refresh-secret",
                    access_expires_in=900,
                    refresh_max_age=604800,
                    trusted_device_token="device-secret",
                    trusted_device_max_age=2592000,
                )

        app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "secret-password",
                    "trusted_device": True,
                },
                headers={"origin": "http://testserver"},
            )

        self.assertEqual(response.status_code, 200)
        cookies = response.headers.get_list("set-cookie")
        self.assertTrue(any("trusted_device=device-secret" in item for item in cookies))
        self.assertTrue(all("httponly" in item.lower() for item in cookies))

    def test_refresh_rotates_refresh_cookie_without_clearing_trusted_device(self) -> None:
        class FakeAuthService:
            async def refresh(self, token: str) -> AuthTokens:
                if token != "old-refresh-secret":
                    raise AssertionError("Unexpected refresh token")
                return AuthTokens(
                    user_id="user-id",
                    access_token="new-access-jwt",
                    refresh_token="new-refresh-secret",
                    access_expires_in=900,
                    refresh_max_age=604000,
                )

        app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            client.cookies.set("refresh_token", "old-refresh-secret")
            response = client.post(
                "/api/v1/auth/refresh",
                headers={"origin": "http://testserver"},
            )

        self.assertEqual(response.status_code, 200)
        cookies = response.headers.get_list("set-cookie")
        self.assertEqual(len(cookies), 1)
        self.assertIn("refresh_token=new-refresh-secret", cookies[0])
        self.assertEqual(response.json()["access_token"], "new-access-jwt")

    def test_login_rejects_untrusted_origin(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "secret-password",
                },
                headers={"origin": "https://attacker.example"},
            )

        self.assertEqual(response.status_code, 403)

    def test_login_requires_origin_header(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "secret-password",
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_logout_revokes_refresh_session_and_clears_refresh_cookie(self) -> None:
        captured: dict[str, str | None] = {}

        class FakeAuthService:
            async def logout(self, refresh_token: str | None) -> None:
                captured["refresh_token"] = refresh_token

        app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            client.cookies.set("refresh_token", "refresh-secret")
            response = client.post(
                "/api/v1/auth/logout",
                headers={"origin": "http://testserver"},
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(captured["refresh_token"], "refresh-secret")
        self.assertIn("refresh_token=", response.headers["set-cookie"])

    def test_login_rejects_client_supplied_device_metadata(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "secret-password",
                    "browser": "Spoofed Browser",
                },
            )

        self.assertEqual(response.status_code, 422)

    def test_readiness_route_returns_unavailable_on_database_error(self) -> None:
        session = AsyncMock()
        session.execute.side_effect = SQLAlchemyError("database unavailable")
        app.dependency_overrides[get_db_session] = lambda: session
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.get("/api/v1/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Database is unavailable"})

    def test_liveness_route_does_not_depend_on_database(self) -> None:
        async def fail_if_called():
            raise HTTPException(status_code=503, detail="database unavailable")

        app.dependency_overrides[get_db_session] = fail_if_called
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            response = client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
