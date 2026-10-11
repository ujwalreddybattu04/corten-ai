"""
Threads endpoints — CRUD for conversation threads and messages.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_db, get_current_user_id, get_optional_user_id
from src.services.thread_service import thread_service

router = APIRouter()


class RenameRequest(BaseModel):
    title: str


class ShareRequest(BaseModel):
    is_public: bool


def _thread_to_dict(t) -> dict:
    return {
        "id": str(t.id),
        "title": t.title,
        "focus_mode": t.focus_mode,
        "model_used": t.model_used,
        "is_public": t.is_public,
        "share_token": t.share_token,
        "message_count": t.message_count,
        "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _message_to_dict(m) -> dict:
    return {
        "id": str(m.id),
        "role": m.role,
        "content": m.content,
        "model_used": m.model_used,
        "tokens_used": m.tokens_used,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("")
async def list_threads(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all threads for the current user, newest first."""
    threads = await thread_service.list_threads(db, user_id, limit=limit, offset=offset)
    return [_thread_to_dict(t) for t in threads]


@router.get("/{thread_id}")
async def get_thread(
    thread_id: str,
    user_id: Optional[str] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a thread with its messages.
    - Authenticated owner can always access.
    - Public threads (is_public=True) accessible without auth.
    """
    thread = await thread_service.get_thread(db, thread_id, user_id)
    if not thread:
        # Try public access
        thread = await thread_service.get_thread(db, thread_id)
        if not thread or not thread.is_public:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    messages = await thread_service.get_messages(db, thread_id)
    result = _thread_to_dict(thread)
    result["messages"] = [_message_to_dict(m) for m in messages]
    return result


@router.patch("/{thread_id}/rename")
async def rename_thread(
    thread_id: str,
    body: RenameRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Rename a thread title."""
    thread = await thread_service.rename_thread(db, thread_id, user_id, body.title)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return _thread_to_dict(thread)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a thread and all its messages."""
    deleted = await thread_service.delete_thread(db, thread_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")


@router.post("/{thread_id}/share")
async def toggle_share(
    thread_id: str,
    body: ShareRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Toggle public sharing for a thread. Returns the share_token when making public."""
    thread = await thread_service.toggle_share(db, thread_id, user_id, body.is_public)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return {
        "is_public": thread.is_public,
        "share_token": thread.share_token,
        "share_url": f"/s/{thread.share_token}" if thread.share_token else None,
    }
