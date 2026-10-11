"""Pydantic schemas for users."""
from pydantic import BaseModel
from typing import Optional


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar_url: Optional[str] = None
    subscription_tier: str = "free"


class UserUpdate(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: Optional[dict] = None
