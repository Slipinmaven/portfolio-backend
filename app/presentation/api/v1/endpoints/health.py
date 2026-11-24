import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_db_session

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Report that the API process is responsive without checking dependencies."""
    return {"status": "ok"}


@router.get("/ready", tags=["health"])
async def readiness_check(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Check that the API can reach its configured database."""
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Database readiness check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc
    return {"status": "ready"}
