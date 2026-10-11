"""
Spaces endpoints — CRUD for collaborative workspaces.
"""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from src.api.deps import get_current_user_id

router = APIRouter(dependencies=[Depends(get_current_user_id)])


@router.get("")
async def list_spaces():
    """List all spaces for the current user."""
    raise HTTPException(501, "Server workspace storage is not configured. Spaces are currently saved in your browser.")


@router.post("")
async def create_space(name: str = "", description: str = ""):
    """Create a new space."""
    raise HTTPException(501, "Server workspace storage is not configured")


@router.get("/{space_id}")
async def get_space(space_id: str):
    """Get space details with threads."""
    raise HTTPException(501, "Server workspace storage is not configured")


@router.put("/{space_id}")
async def update_space(space_id: str):
    """Update space details."""
    raise HTTPException(501, "Server workspace storage is not configured")


@router.delete("/{space_id}")
async def delete_space(space_id: str):
    """Delete a space."""
    raise HTTPException(501, "Server workspace storage is not configured")


@router.post("/{space_id}/files")
async def upload_file(space_id: str, file: UploadFile = File(...)):
    """Upload a file to a space."""
    raise HTTPException(501, "Server workspace storage is not configured")
