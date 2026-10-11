"""
Users endpoints — Profile and preferences.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/me")
async def get_current_user():
    """Get current user profile."""
    # TODO: Implement with auth dependency
    return {"id": "placeholder"}


@router.put("/me")
async def update_profile():
    """Update user profile and preferences."""
    # TODO: Implement
    return {"updated": True}
