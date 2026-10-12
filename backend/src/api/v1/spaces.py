"""Owner-scoped personal spaces storage with compare-and-set writes."""
import time
from uuid import uuid4
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.api.deps import get_current_user_id, get_db
from src.services.personal_crud import list_records, get_record, mutate_record

router = APIRouter()


class SpaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    threadIds: list[str] = Field(default_factory=list, max_length=500)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=20000)
    links: list[str] = Field(default_factory=list, max_length=100)
    icon: str = Field(default="bookmark", max_length=30)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("links")
    @classmethod
    def safe_links(cls, links):
        from urllib.parse import urlsplit
        for link in links:
            parsed = urlsplit(link)
            if len(link) > 2048 or parsed.scheme not in ("https", "http") or not parsed.hostname:
                raise ValueError("Reference links must use HTTP or HTTPS")
        return links

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip(): raise ValueError("Name cannot be blank")
        return value.strip()


class SpaceUpdate(SpaceInput):
    expected_revision: int = Field(ge=1, le=2**53-1)


@router.get("")
async def list_spaces(owner: str = Depends(get_current_user_id), db=Depends(get_db)):
    return await list_records(db, owner, "spaces")


@router.post("", status_code=201)
async def create_space(body: SpaceInput, owner: str = Depends(get_current_user_id), db=Depends(get_db)):
    record_id, now = str(uuid4()), int(time.time()*1000)
    data = {**body.model_dump(), "id": record_id, "isPrivate": True, "createdAt": now, "updatedAt": now}
    return await mutate_record(db, owner, "spaces", record_id, 0, data)


@router.get("/{record_id}")
async def get_space(record_id: str, owner: str = Depends(get_current_user_id), db=Depends(get_db)):
    return await get_record(db, owner, "spaces", record_id)


@router.put("/{record_id}")
async def update_space(record_id: str, body: SpaceUpdate, owner: str = Depends(get_current_user_id), db=Depends(get_db)):
    previous = await get_record(db, owner, "spaces", record_id)
    data = {**body.model_dump(exclude={"expected_revision"}), "id": record_id, "isPrivate": True,
        "createdAt": previous["data"].get("createdAt", int(time.time()*1000)), "updatedAt": int(time.time()*1000)}
    return await mutate_record(db, owner, "spaces", record_id, body.expected_revision, data)


@router.delete("/{record_id}")
async def delete_space(record_id: str, expected_revision: int = Query(..., ge=1, le=2**53-1),
        owner: str = Depends(get_current_user_id), db=Depends(get_db)):
    await get_record(db, owner, "spaces", record_id)
    return await mutate_record(db, owner, "spaces", record_id, expected_revision, deleted=True)
