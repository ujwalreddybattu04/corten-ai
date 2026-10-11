"""
Collections endpoints — CRUD for user collections.
"""

from fastapi import APIRouter, Depends, HTTPException
from src.api.deps import get_current_user_id

router = APIRouter(dependencies=[Depends(get_current_user_id)])


@router.get("")
async def list_collections():
    raise HTTPException(501, "Server collection storage is not configured")


@router.post("")
async def create_collection(name: str = ""):
    raise HTTPException(501, "Server collection storage is not configured")


@router.put("/{collection_id}")
async def update_collection(collection_id: str):
    raise HTTPException(501, "Server collection storage is not configured")


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str):
    raise HTTPException(501, "Server collection storage is not configured")
