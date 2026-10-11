"""
Collections endpoints — CRUD for user collections.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_collections():
    return []


@router.post("")
async def create_collection(name: str = ""):
    return {"id": "placeholder", "name": name}


@router.put("/{collection_id}")
async def update_collection(collection_id: str):
    return {"id": collection_id}


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str):
    return {"deleted": True}
