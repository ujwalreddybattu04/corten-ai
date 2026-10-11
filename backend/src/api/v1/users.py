"""
Users endpoints — Profile and preferences.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_db, get_current_user_id
from src.api.v1.auth import get_me
from src.services.auth_service import auth_service

router = APIRouter()


@router.get("/me")
async def get_current_user(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    """Get current user profile."""
    return await get_me(user_id, db)


class ProfileRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        return value.strip()


@router.put("/me")
async def update_profile(body: ProfileRequest, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    """Update user profile and preferences."""
    user = await auth_service.get_user_by_id(db, user_id)
    user.name = body.name
    await db.flush()
    return await get_me(user_id, db)
