from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.login_attempt import LoginAttemptRepository
from app.infrastructure.database.repositories.session import SessionRepository
from app.infrastructure.database.repositories.trusted_device import TrustedDeviceRepository
from app.infrastructure.database.repositories.user import UserRepository
from app.infrastructure.database.unit_of_work.base import BaseUnitOfWork


class AuthenticationUnitOfWork(BaseUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)
        self._users: UserRepository | None = None
        self._sessions: SessionRepository | None = None
        self._trusted_devices: TrustedDeviceRepository | None = None
        self._audit_logs: AuditLogRepository | None = None
        self._login_attempts: LoginAttemptRepository | None = None

    @property
    def users(self) -> UserRepository:
        if self._users is None:
            self._users = UserRepository(session=self.session)
        return self._users

    @property
    def sessions(self) -> SessionRepository:
        if self._sessions is None:
            self._sessions = SessionRepository(session=self.session)
        return self._sessions

    @property
    def trusted_devices(self) -> TrustedDeviceRepository:
        if self._trusted_devices is None:
            self._trusted_devices = TrustedDeviceRepository(session=self.session)
        return self._trusted_devices

    @property
    def audit_logs(self) -> AuditLogRepository:
        if self._audit_logs is None:
            self._audit_logs = AuditLogRepository(session=self.session)
        return self._audit_logs

    @property
    def login_attempts(self) -> LoginAttemptRepository:
        if self._login_attempts is None:
            self._login_attempts = LoginAttemptRepository(session=self.session)
        return self._login_attempts
