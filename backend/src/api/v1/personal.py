"""Account-owned cloud changes. Guests never upload browser/private history."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, ConfigDict, model_validator
from src.api.deps import get_db, get_current_user_id
from src.services.personal_records import RecordWrite, changes, write_records

router = APIRouter()


class BatchWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[RecordWrite] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def distinct_records(self):
        identities = [(record.namespace, record.id) for record in self.records]
        if len(set(identities)) != len(identities):
            raise ValueError("Each record may appear only once in a batch")
        return self


@router.get("/changes")
async def get_changes(after: int = Query(0, ge=0, le=2**53-1), limit: int = Query(50, ge=1, le=50),
        owner: str = Depends(get_current_user_id), db=Depends(get_db)):
    return await changes(db, owner, after, limit)


@router.post("/records")
async def put_records(body: BatchWrite, owner: str = Depends(get_current_user_id), db=Depends(get_db)):
    result = await write_records(db, owner, body.records)
    await db.commit()
    return result
