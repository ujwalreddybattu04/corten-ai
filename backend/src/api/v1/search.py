import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Response, Depends
from src.api.deps import get_current_user_id, get_db
from src.services.space_service import search_context
from src.services import attachments, personalization
from src.services.chat_context import TurnContext
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from typing import List, Dict, Optional, Literal

logger = logging.getLogger(__name__)

from src.services.search_orchestrator import search_orchestrator

router = APIRouter()

@router.get("/status")
async def search_status(response: Response):
    """Confirm the application is serving before sending a billable generation."""
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ready"}

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=16000)
    focus_mode: str = "all"
    messages: Optional[List[Dict[str, str]]] = Field(default=None, max_length=120)
    space_id: Optional[str] = Field(default=None, max_length=64)
    mode: Literal["auto", "fast", "pro", "think"] = "auto"
    attachments: List[str] = Field(default_factory=list, max_length=10)
    # Files from earlier messages in the conversation; documents are read only when relevant to this question.
    context_attachments: List[str] = Field(default_factory=list, max_length=10)
    # Private chats: no memory is read or written.
    incognito: bool = False

@router.post("/stream")
async def search_stream(request: SearchRequest, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    """Submit a search query and receive a streaming AI-generated answer with citations."""
    # Resolved before streaming: membership errors are ordinary HTTP errors, not mid-stream events.
    space = await search_context(db, request.space_id, user) if request.space_id else None
    documents, images, image_names = await attachments.load_for_turn(db, user, request.attachments)
    earlier = [item for item in request.context_attachments if item not in request.attachments]
    context_documents, earlier_images, earlier_names = await attachments.load_for_turn(
        db, user, earlier[:max(0, attachments.MAX_PER_QUESTION - len(request.attachments))])
    room = max(0, attachments.MAX_IMAGES_PER_QUESTION - len(images))
    images, image_names = images + earlier_images[:room], image_names + earlier_names[:room]
    turn = TurnContext(mode=request.mode, documents=documents, context_documents=context_documents,
                       images=images, image_names=image_names,
                       personal=await personalization.personal_block(db, user, request.incognito),
                       incognito=request.incognito, user_id=user)
    remember = None if request.incognito else BackgroundTask(personalization.remember_from_message, user, request.query)
    try:
        return StreamingResponse(
            search_orchestrator.stream_search(request.query, request.focus_mode, request.messages, space=space, turn=turn),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no" # Essential for Nginx if present
            },
            background=remember,
        )
    except Exception as e:
        logger.error(f"Error in search stream: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class TitleRequest(BaseModel):
    query: str = Field(min_length=1, max_length=16000)
    answer: str = Field(default="", max_length=2000)

@router.post("/title", dependencies=[Depends(get_current_user_id)])
async def generate_title(request: TitleRequest):
    """
    Generate a bounded topic heading without web search or blocking chat streaming.
    """
    try:
        from src.services.conversation_memory import conversation_intent
        from src.services.thread_titles import fallback_title, is_greeting
        from src.services.app_state import selection_question
        fallback = fallback_title(request.query)
        if selection_question(request.query):
            return {"title": "Chat mode selection", "source": "local"}
        if conversation_intent(request.query) or is_greeting(request.query):
            return {"title": fallback, "source": "local"}
        from src.services.llm_service import groq_llm_service
        title = await groq_llm_service.generate_thread_title(request.query, request.answer)
        return {"title": title, "source": "fallback" if title == fallback else "generated"}
    except Exception as e:
        logger.warning("Thread title unavailable (%s)", type(e).__name__)
        from src.services.thread_titles import fallback_title
        return {"title": fallback_title(request.query), "source": "fallback"}

@router.post("/suggestions", dependencies=[Depends(get_current_user_id)])
async def search_suggestions(query: str = ""):
    """Get auto-complete search suggestions."""
    # TODO: Implement suggestion engine
    return []
