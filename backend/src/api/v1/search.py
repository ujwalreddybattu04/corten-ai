import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Response, Depends
from src.api.deps import get_current_user_id
from fastapi.responses import StreamingResponse
from typing import List, Dict, Optional

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

@router.post("/stream", dependencies=[Depends(get_current_user_id)])
async def search_stream(request: SearchRequest):
    """Submit a search query and receive a streaming AI-generated answer with citations."""
    try:
        return StreamingResponse(
            search_orchestrator.stream_search(request.query, request.focus_mode, request.messages),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no" # Essential for Nginx if present
            }
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
        fallback = fallback_title(request.query)
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
