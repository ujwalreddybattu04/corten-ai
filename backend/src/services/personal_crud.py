"""Owner-scoped adapters for personal Spaces and collections."""
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from src.models.personal_record import PersonalRecord
from src.services.personal_records import RecordWrite, serialize, write_records


async def list_records(db, owner, namespace):
    rows = (await db.scalars(select(PersonalRecord).where(PersonalRecord.user_id == UUID(owner),
        PersonalRecord.namespace == namespace, PersonalRecord.deleted.is_(False))
        .order_by(PersonalRecord.revision.desc()))).all()
    return {"items": [serialize(row) for row in rows]}


async def get_record(db, owner, namespace, record_id):
    row = await db.get(PersonalRecord, (UUID(owner), namespace, record_id))
    if not row or row.deleted:
        raise HTTPException(404, "Record not found")
    return serialize(row)


async def mutate_record(db, owner, namespace, record_id, revision, data=None, deleted=False):
    result = (await write_records(db, owner, [RecordWrite(namespace=namespace, id=record_id,
        expected_revision=revision, deleted=deleted, data=data)]))["results"][0]
    if result["status"] == "conflict":
        raise HTTPException(409, "This record has changed. Reload it before saving.")
    if result["status"] == "quota":
        raise HTTPException(413, "Account storage limit reached. Export or remove older records.")
    await db.commit()
    return result
