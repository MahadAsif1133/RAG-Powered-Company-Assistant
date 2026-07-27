from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check() -> JSONResponse:
    """Railway and uptime monitor health check endpoint."""
    return JSONResponse(content={"status": "ok"})
