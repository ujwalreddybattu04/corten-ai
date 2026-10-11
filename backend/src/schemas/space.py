"""Pydantic schemas for spaces."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SpaceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    custom_instructions: Optional[str] = None


class SpaceResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    custom_instructions: Optional[str] = None
    created_at: datetime
    updated_at: datetime
