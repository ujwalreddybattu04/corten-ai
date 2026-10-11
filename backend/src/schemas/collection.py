"""Pydantic schemas for collections."""
from pydantic import BaseModel
from typing import List
from datetime import datetime


class CollectionCreate(BaseModel):
    name: str


class CollectionUpdate(BaseModel):
    thread_ids: List[str]


class CollectionResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
