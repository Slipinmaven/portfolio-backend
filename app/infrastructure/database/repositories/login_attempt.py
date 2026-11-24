from datetime import datetime, timedelta

from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.login_attempt import LoginAttempt


class LoginAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_blocked(self, client_key: str, *, now: datetime) -> bool:
        attempt = await self.session.get(LoginAttempt, client_key)
        return (
            attempt is not None
            and attempt.blocked_until is not None
            and attempt.blocked_until > now
        )

    async def record_failure(
        self,
        client_key: str,
        *,
        now: datetime,
        window: timedelta,
        maximum_failures: int,
    ) -> None:
        window_expired = LoginAttempt.window_started_at < now - window
        failure_count = case(
            (window_expired, 1),
            else_=LoginAttempt.failure_count + 1,
        )
        statement = (
            insert(LoginAttempt)
            .values(
                client_key=client_key,
                failure_count=1,
                window_started_at=now,
                blocked_until=None,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[LoginAttempt.client_key],
                set_={
                    "failure_count": failure_count,
                    "window_started_at": case(
                        (window_expired, now),
                        else_=LoginAttempt.window_started_at,
                    ),
                    "blocked_until": case(
                        (window_expired, None),
                        (
                            LoginAttempt.failure_count + 1 >= maximum_failures,
                            now + window,
                        ),
                        else_=LoginAttempt.blocked_until,
                    ),
                    "updated_at": now,
                },
            )
        )
        await self.session.execute(statement)
        await self.session.execute(
            delete(LoginAttempt).where(
                LoginAttempt.updated_at < now - timedelta(days=1),
                LoginAttempt.client_key != client_key,
            )
        )

    async def clear(self, client_key: str) -> None:
        await self.session.execute(
            delete(LoginAttempt).where(LoginAttempt.client_key == client_key)
        )
