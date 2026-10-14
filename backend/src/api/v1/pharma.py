"""Dated public pharma updates for the analyst workspace."""

from typing import Literal
import base64
import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from src.api.deps import get_current_user_id
from src.services.pharma_analysis import same_snapshot, stream_analysis
from src.services.pharma_updates import Topic, pharma_updates_service
from src.config.settings import settings
from src.services import pharma_repository
from sqlalchemy.exc import SQLAlchemyError
from src.services.pharma_research import research_stream

router = APIRouter()


@router.get("/updates")
async def updates(
    response: Response,
    topic: Topic = Query("all"),
    days: int = Query(7),
):
    if days not in (7, 30, 90):
        raise HTTPException(status_code=422, detail="Choose a 7, 30 or 90 day window.")
    try:
        feed = await pharma_updates_service.get_feed(topic=topic, days=days)
    except SQLAlchemyError:
        raise HTTPException(503, "Pharma sources are temporarily unavailable.", headers={"Retry-After":"60"}) from None
    if feed.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail="Pharma sources are temporarily unavailable. Please retry shortly.", headers={"Retry-After": "60", "Cache-Control": "no-store"})
    # These are exclusively public records; no account-dependent fields. The
    # authenticated frontend proxy remains no-store for cookie-bearing requests.
    response.headers["Cache-Control"] = "private, no-store"
    return feed


@router.get("/records/{identifier}",dependencies=[Depends(get_current_user_id)])
async def record(identifier: str, response: Response):
    if not settings.PHARMA_INTELLIGENCE_ENABLED:raise HTTPException(404,"Archived records are not enabled.")
    try:result=await pharma_repository.get_record(identifier)
    except SQLAlchemyError:raise HTTPException(503,"The source archive is temporarily unavailable.") from None
    if not result:raise HTTPException(404,"This source record was not found.")
    response.headers["Cache-Control"]="private, no-store"
    return result


@router.get("/drugs",dependencies=[Depends(get_current_user_id)])
async def drugs(response: Response,q: str=Query(min_length=2,max_length=120)):
    if not settings.PHARMA_INTELLIGENCE_ENABLED:raise HTTPException(404,"Drug timelines are not enabled.")
    response.headers["Cache-Control"]="private, no-store"
    try:return {"items":await pharma_repository.search_drugs(q)}
    except SQLAlchemyError:raise HTTPException(503,"Drug identities are temporarily unavailable.") from None


@router.get("/drugs/{identifier}/timeline",dependencies=[Depends(get_current_user_id)])
async def timeline(identifier: str,response: Response,cursor: str|None=Query(None,max_length=300)):
    if not settings.PHARMA_INTELLIGENCE_ENABLED:raise HTTPException(404,"Drug timelines are not enabled.")
    before=None
    if cursor:
        try:
            values=json.loads(base64.urlsafe_b64decode(cursor+"="*((-len(cursor))%4)))
            if not isinstance(values,list) or len(values)!=2 or not isinstance(values[1],str) or len(values[1])!=64:raise ValueError()
            before=(date.fromisoformat(values[0]),values[1])
        except (ValueError,TypeError,UnicodeError):raise HTTPException(422,"Invalid timeline cursor.") from None
    try:result=await pharma_repository.drug_timeline(identifier,before=before)
    except SQLAlchemyError:raise HTTPException(503,"The drug timeline is temporarily unavailable.") from None
    if not result:raise HTTPException(404,"This verified drug identity was not found.")
    result["next_cursor"]=base64.urlsafe_b64encode(json.dumps(result.pop("next")).encode()).decode().rstrip("=") if result["next"] else None
    result.pop("next",None)
    response.headers["Cache-Control"]="private, no-store"
    return result


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6000)


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1,max_length=8000)
    messages: list[HistoryMessage] = Field(default_factory=list,max_length=12)
    record_id: str | None = Field(default=None,min_length=1,max_length=240)
    record_fingerprint: str | None = Field(default=None,min_length=1,max_length=20000)

    @model_validator(mode='after')
    def bounded(self):
        if not self.query.strip():raise ValueError('Please enter a Pharma question.')
        if bool(self.record_id)!=bool(self.record_fingerprint):raise ValueError('Reopen the source record before continuing.')
        if sum(len(m.content.encode()) for m in self.messages)>18000:raise ValueError('Conversation context is too large.')
        return self


@router.post('/research/stream',dependencies=[Depends(get_current_user_id)])
async def research(request: ResearchRequest):
    if not settings.PHARMA_INTELLIGENCE_ENABLED:raise HTTPException(404,'Pharma research is not enabled.')
    if request.record_id:
        try:resolved=await pharma_repository.get_record(request.record_id)
        except SQLAlchemyError:raise HTTPException(503,'The source archive is temporarily unavailable.') from None
        if not resolved:raise HTTPException(404,'This source record was not found.')
        if not same_snapshot(resolved['item'],request.record_fingerprint):
            raise HTTPException(409,'The source record changed. Reopen it to review the current version.')
    return StreamingResponse(research_stream(request.query,[m.model_dump() for m in request.messages],request.record_id),
        media_type='text/event-stream',headers={'Cache-Control':'private, no-store','X-Accel-Buffering':'no'})


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
    refresh: bool = False

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value):
        if not value.strip():
            raise ValueError("Please enter a question.")
        return value


@router.post("/analysis/stream", dependencies=[Depends(get_current_user_id)])
async def analysis(request: AnalysisRequest):
    if settings.PHARMA_INTELLIGENCE_ENABLED:
        try:resolved=await pharma_repository.get_record(request.record_id)
        except SQLAlchemyError:raise HTTPException(503,"The source archive is temporarily unavailable.") from None
        if not resolved:raise HTTPException(404,"This archived source record was not found.")
        item,source=resolved["item"],resolved["source"]
        if not same_snapshot(item,request.record_fingerprint):raise HTTPException(409,"The source record changed. Reopen it to review the current version.")
        return StreamingResponse(stream_analysis(item,source,request.query,
            [m.model_dump() for m in request.messages],request.kind,request.mode,request.refresh),media_type="text/event-stream",
            headers={"Cache-Control":"private, no-store","X-Accel-Buffering":"no"})
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
