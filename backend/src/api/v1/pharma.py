"""Dated public pharma updates for the analyst workspace."""

from fastapi import APIRouter, HTTPException, Query, Response
from src.services.pharma_updates import Topic, pharma_updates_service

router = APIRouter()


@router.get("/updates")
async def updates(
    response: Response,
    topic: Topic = Query("all"),
    days: int = Query(7),
):
    if days not in (7, 30, 90):
        raise HTTPException(status_code=422, detail="Choose a 7, 30 or 90 day window.")
    response.headers["Cache-Control"] = "no-store"
    return await pharma_updates_service.get_feed(topic=topic, days=days)
