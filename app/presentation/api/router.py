from fastapi import APIRouter

from app.presentation.api.v1.router import router as v1_router

router = APIRouter()
router.include_router(v1_router, prefix="/api/v1")


@router.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello, World!"}
