"""Personal preferences, response style and memory management."""
from typing import Literal, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from src.api.deps import get_current_user_id, get_db
from src.services import personalization

router = APIRouter()


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: Optional[Literal["normal", "concise", "explanatory", "formal", "custom"]] = None
    custom_style: Optional[str] = Field(default=None, max_length=1000)
    personal_instructions: Optional[str] = Field(default=None, max_length=2000)
    memory_enabled: Optional[bool] = None

    @model_validator(mode="after")
    def has_changes(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("Provide at least one change")
        return self


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=500)


@router.get("/personalization")
async def get_preferences(user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return await personalization.get_preferences(db, user)


@router.put("/personalization")
async def update_preferences(body: PreferencesUpdate, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    changes = {key: value.strip() if isinstance(value, str) else value for key, value in body.model_dump(exclude_none=True).items()}
    result = await personalization.update_preferences(db, user, changes)
    await db.commit()
    return result


@router.get("/memories")
async def list_memories(user: str = Depends(get_current_user_id), db=Depends(get_db)):
    return {"items": await personalization.list_memories(db, user)}


@router.post("/memories", status_code=201)
async def add_memory(body: MemoryInput, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    result = await personalization.add_memory(db, user, body.content)
    await db.commit()
    return result or {"duplicate": True}


@router.patch("/memories/{memory_id}")
async def edit_memory(memory_id: str, body: MemoryInput, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    result = await personalization.edit_memory(db, user, memory_id, body.content)
    await db.commit()
    return result


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, user: str = Depends(get_current_user_id), db=Depends(get_db)):
    await personalization.delete_memory(db, user, memory_id)
    await db.commit()


@router.delete("/memories")
async def clear_memories(user: str = Depends(get_current_user_id), db=Depends(get_db)):
    removed = await personalization.clear_memories(db, user)
    await db.commit()
    return {"removed": removed}
