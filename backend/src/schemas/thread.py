"""Pydantic schemas for threads."""
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime


class ThreadCreate(BaseModel):
    query: str
    focus_mode: str = "all"
    space_id: Optional[str] = None


class ThreadResponse(BaseModel):
    id: str
    title: str
    focus_mode: str
    model_used: str
    messages: List[MessageResponse] = []
    created_at: datetime
    updated_at: datetime
