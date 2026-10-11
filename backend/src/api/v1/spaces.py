"""
Spaces endpoints — CRUD for collaborative workspaces.
"""

from fastapi import APIRouter, UploadFile, File

router = APIRouter()


@router.get("")
async def list_spaces():
    """List all spaces for the current user."""
    return []


@router.post("")
async def create_space(name: str = "", description: str = ""):
    """Create a new space."""
    return {"id": "placeholder", "name": name}


@router.get("/{space_id}")
async def get_space(space_id: str):
    """Get space details with threads."""
    return {"id": space_id, "threads": []}


@router.put("/{space_id}")
async def update_space(space_id: str):
    """Update space details."""
    return {"id": space_id}


@router.delete("/{space_id}")
async def delete_space(space_id: str):
    """Delete a space."""
    return {"deleted": True}


@router.post("/{space_id}/files")
async def upload_file(space_id: str, file: UploadFile = File(...)):
    """Upload a file to a space."""
    return {"space_id": space_id, "filename": file.filename}
