"""Dated public pharma updates for the analyst workspace."""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from src.api.deps import get_current_user_id
from src.services.pharma_analysis import same_snapshot, stream_analysis
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
    feed = await pharma_updates_service.get_feed(topic=topic, days=days)
    if feed.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail="Pharma sources are temporarily unavailable. Please retry shortly.", headers={"Retry-After": "60", "Cache-Control": "no-store"})
    # These are exclusively public records; no account-dependent fields. The
    # authenticated frontend proxy remains no-store for cookie-bearing requests.
    response.headers["Cache-Control"] = "private, no-store"
    return feed


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6000)


class AnalysisRequest(BaseModel):
    record_id: str = Field(min_length=1, max_length=240)
    record_fingerprint: str = Field(min_length=1, max_length=20000)
    topic: Topic = "all"
    days: Literal[7, 30, 90] = 7
    kind: Literal["brief", "question"] = "question"
    query: str = Field(min_length=1, max_length=16000)
    messages: list[HistoryMessage] = Field(default_factory=list, max_length=120)
    mode: Literal["auto", "fast", "pro", "think"] = "auto"
    incognito: bool = False

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value):
        if not value.strip():
            raise ValueError("Please enter a question.")
        return value


@router.post("/analysis/stream", dependencies=[Depends(get_current_user_id)])
async def analysis(request: AnalysisRequest):
    # Resolve evidence on the server, never accept caller-supplied clinical facts.
    feed = await pharma_updates_service.get_feed(topic=request.topic, days=request.days)
    if feed.get("status") == "unavailable":
        raise HTTPException(503, "Pharma sources are temporarily unavailable. Please retry shortly.")
    item = next((item for item in feed["items"] if item["id"] == request.record_id), None)
    if not item:
        raise HTTPException(404, "This record is no longer in the current feed. Return to Pharma intelligence and select a current record.")
    if not same_snapshot(item, request.record_fingerprint):
        raise HTTPException(409, "This source record has changed. Return to Pharma intelligence, check updates and reopen the record.")
    source = next(source for source in feed["sources"] if source["id"] == item["source"])
    return StreamingResponse(stream_analysis(item, source, request.query,
        [message.model_dump() for message in request.messages], request.kind, request.mode),
        media_type="text/event-stream", headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"})
