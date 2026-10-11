import logging
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

from src.services.search_orchestrator import search_orchestrator

router = APIRouter()

class SearchRequest(BaseModel):
    query: str
    focus_mode: str = "all"
    messages: Optional[List[Dict[str, str]]] = None

@router.post("/stream")
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
    query: str

@router.post("/title")
async def generate_title(request: TitleRequest):
    """
    Generate a short thread title from the initial query.
    """
    try:
        from src.services.llm_service import groq_llm_service
        title = await groq_llm_service.generate_thread_title(request.query)
        return {"title": title}
    except Exception as e:
        logger.error(f"Error in title generation: {e}", exc_info=True)
        # Fallback to a generic title rather than failing
        return {"title": "Corten Search"}

@router.post("/suggestions")
async def search_suggestions(query: str = ""):
    """Get auto-complete search suggestions."""
    # TODO: Implement suggestion engine
    return []
