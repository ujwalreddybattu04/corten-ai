"""Transactional private storage with compare-and-set writes and bounded quotas."""
import hashlib
import json
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Literal
from sqlalchemy import select, func, text
from src.models.personal_record import PersonalRecord, PersonalRevision

Namespace = Literal["threads", "spaces", "collections", "preferences"]
MAX_RECORD_BYTES = 256 * 1024
MAX_ACCOUNT_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 500


class RecordWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    namespace: Namespace
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    expected_revision: int = Field(ge=0, le=2**53-1)
    deleted: bool = False
    data: dict | list | str | bool | int | None = None

    @model_validator(mode="after")
    def valid_payload(self):
        if self.deleted:
            self.data = None
        elif self.data is None:
            raise ValueError("A saved record must contain data")
        if isinstance(self.data, dict) and self.namespace in ("threads", "spaces", "collections"):
            if self.data.get("id") != self.id:
                raise ValueError("Record identity must match its data")
        elif not self.deleted and self.namespace != "preferences":
            raise ValueError("This record must contain an object")
        if not self.deleted and self.namespace == "spaces":
            name = self.data.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise ValueError("Space name must contain 1–100 characters")
            for field in ("threadIds", "links"):
                value = self.data.get(field, [])
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    raise ValueError("Space links and thread IDs must be lists of text")
            for field in ("description", "instructions", "icon", "color"):
                if field in self.data and not isinstance(self.data[field], str):
                    raise ValueError("Space metadata must contain text")
        try:
            encoded = json.dumps(self.data, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            raise ValueError("Record must contain finite JSON data") from None
        if len(encoded.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ValueError("A record cannot exceed 256 KB")
        def depth(value, level=0):
            if level > 12:
                raise ValueError("Record nesting is too deep")
            if isinstance(value, dict):
                for item in value.values(): depth(item, level+1)
            elif isinstance(value, list):
                if len(value) > 500: raise ValueError("A record array cannot exceed 500 items")
                for item in value: depth(item, level+1)
        depth(self.data)
        return self


def serialize(row):
    return {"namespace": row.namespace, "id": row.record_id, "data": row.data,
        "deleted": row.deleted, "revision": row.revision}


async def changes(db, owner, after=0, limit=50):
    owner = UUID(owner)
    highwater = await db.scalar(select(PersonalRevision.revision).where(PersonalRevision.user_id == owner)) or 0
    if after > highwater:
        raise HTTPException(409, "Cloud cursor is ahead of the account. Reset synchronization.")
    rows = list((await db.scalars(select(PersonalRecord).where(PersonalRecord.user_id == owner,
        PersonalRecord.revision > after, PersonalRecord.revision <= highwater)
        .order_by(PersonalRecord.revision).limit(limit+1))).all())
    more = len(rows) > limit
    rows = rows[:limit]
    return {"records": [serialize(r) for r in rows], "cursor": rows[-1].revision if more else highwater, "has_more": more}


async def write_records(db, owner, writes):
    owner = UUID(owner)
    # Serialize each account's quota and revision allocation across workers.
    if db.get_bind().dialect.name == "postgresql":
        lock = int.from_bytes(hashlib.blake2b(owner.bytes, digest_size=8).digest(), "big", signed=True)
        await db.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": lock})
    counter = await db.get(PersonalRevision, owner, populate_existing=True)
    if counter is None:
        counter = PersonalRevision(user_id=owner, revision=0)
        db.add(counter)
        await db.flush()
    active, size, total = (await db.execute(select(
        func.count().filter(PersonalRecord.deleted.is_(False)),
        func.coalesce(func.sum(PersonalRecord.size_bytes), 0), func.count())
        .where(PersonalRecord.user_id == owner))).one()
    results = []
    for request in writes:
        row = await db.get(PersonalRecord, (owner, request.namespace, request.id), populate_existing=True)
        current_revision = row.revision if row else 0
        # Lost HTTP replies can safely retry the identical mutation.
        if row and row.deleted == request.deleted and row.data == request.data:
            results.append({"status": "saved", **serialize(row)})
            continue
        if current_revision != request.expected_revision:
            results.append({"status": "conflict", "namespace": request.namespace, "id": request.id,
                "current": serialize(row) if row else None})
            continue
        new_size = 0 if request.deleted else len(json.dumps(request.data, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        delta_active = (not request.deleted) - (bool(row) and not row.deleted)
        proposed_size = size - (row.size_bytes if row else 0) + new_size
        if active + delta_active > MAX_RECORDS or proposed_size > MAX_ACCOUNT_BYTES or (row is None and total >= 5000):
            results.append({"status": "quota", "namespace": request.namespace, "id": request.id,
                "reason": "retained_history" if row is None and total >= 5000 else "storage"})
            continue
        if row is None:
            row = PersonalRecord(user_id=owner, namespace=request.namespace, record_id=request.id)
            db.add(row)
            total += 1
        if counter.revision >= 2**53-1:
            raise HTTPException(409, "Account revision limit reached. Contact support.")
        counter.revision += 1
        row.data, row.deleted, row.revision, row.size_bytes = request.data, request.deleted, counter.revision, new_size
        active += delta_active
        size = proposed_size
        await db.flush()
        results.append({"status": "saved", **serialize(row)})
    return {"results": results}
