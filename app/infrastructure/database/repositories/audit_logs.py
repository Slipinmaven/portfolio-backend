from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=AuditLog)

    async def get_by_request_id(self, request_id: UUID) -> list[AuditLog]:
        query = (
            select(AuditLog)
            .where(AuditLog.request_id == request_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def list_audit_logs(
        self,
        *,
        offset: int,
        limit: int,
        user_id: UUID | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        status: str | None = None,
        request_id: UUID | None = None,
    ) -> tuple[list[AuditLog], int]:
        filters = []
        if user_id is not None:
            filters.append(AuditLog.user_id == user_id)
        if action is not None:
            filters.append(AuditLog.action == action)
        if entity_type is not None:
            filters.append(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            filters.append(AuditLog.entity_id == entity_id)
        if status is not None:
            filters.append(AuditLog.status == status)
        if request_id is not None:
            filters.append(AuditLog.request_id == request_id)

        query = (
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id)
            .offset(offset)
            .limit(limit)
        )
        logs = list((await self.session.scalars(query)).all())
        total_query = select(func.count()).select_from(AuditLog).where(*filters)
        total = await self.session.scalar(total_query)
        return logs, total or 0