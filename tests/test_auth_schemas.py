import ipaddress
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.presentation.schemas.auth import SessionSummary


class AuthSchemaTests(unittest.TestCase):
    def test_session_summary_serializes_database_ip_address(self) -> None:
        now = datetime.now(timezone.utc)
        session = SimpleNamespace(
            id=uuid4(),
            trusted_device_id=None,
            ip_address=ipaddress.ip_address("127.0.0.1"),
            user_agent="test-agent",
            created_at=now,
            last_activity_at=now,
            expires_at=now,
            revoked_at=None,
            revocation_reason=None,
        )

        summary = SessionSummary.model_validate(session)

        self.assertEqual(summary.ip_address, "127.0.0.1")
        self.assertEqual(summary.model_dump()["ip_address"], "127.0.0.1")
