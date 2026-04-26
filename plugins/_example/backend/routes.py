"""Example plugin routes — single demo endpoint."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/_example", tags=["_example"])


@router.get("/ping")
async def ping():
    return {"plugin": "_example", "status": "ok"}
