"""Storage regressions against a real isolated SQL database."""
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from pydantic import ValidationError
from fastapi import HTTPException
from src.models.personal_record import PersonalRecord, PersonalRevision
from src.services.personal_records import RecordWrite, changes, write_records
from src.services.personal_crud import get_record
from src.api.v1.personal import BatchWrite


@pytest_asyncio.fixture
async def storage():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        await connection.run_sync(lambda sync: PersonalRevision.__table__.create(sync))
        await connection.run_sync(lambda sync: PersonalRecord.__table__.create(sync))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


def record(revision=0, value="original", deleted=False, record_id="thread-a"):
    return RecordWrite(namespace="threads", id=record_id, expected_revision=revision,
        deleted=deleted, data={"id": record_id, "title": value})


@pytest.mark.asyncio
async def test_private_records_are_scoped_even_when_ids_match(storage):
    first, second = str(uuid4()), str(uuid4())
    await write_records(storage, first, [record(value="first")])
    assert (await changes(storage, second))["records"] == []
    with pytest.raises(HTTPException) as failure: await get_record(storage, second, "threads", "thread-a")
    assert failure.value.status_code == 404
    await write_records(storage, second, [record(value="second")])
    assert (await changes(storage, first))["records"][0]["data"]["title"] == "first"
    assert (await changes(storage, second))["records"][0]["data"]["title"] == "second"


@pytest.mark.asyncio
async def test_stale_edit_conflicts_and_lost_reply_retry_is_idempotent(storage):
    owner = str(uuid4())
    original = (await write_records(storage, owner, [record()]))["results"][0]
    retry = (await write_records(storage, owner, [record()]))["results"][0]
    assert original == retry
    updated = (await write_records(storage, owner, [record(original["revision"], "new")]))["results"][0]
    stale = (await write_records(storage, owner, [record(original["revision"], "old")]))["results"][0]
    assert stale["status"] == "conflict" and stale["current"]["data"]["title"] == "new"
    assert updated["revision"] == 2


@pytest.mark.asyncio
async def test_deletion_is_a_tombstone_and_stale_devices_cannot_resurrect_it(storage):
    owner = str(uuid4())
    await write_records(storage, owner, [record()])
    removed = (await write_records(storage, owner, [record(1, deleted=True)]))["results"][0]
    assert removed["deleted"] is True and removed["data"] is None
    stale = (await write_records(storage, owner, [record(1, "stale")]))["results"][0]
    assert stale["status"] == "conflict" and stale["current"]["deleted"] is True
    assert (await changes(storage, owner, after=1))["records"][0]["deleted"] is True


@pytest.mark.asyncio
async def test_changes_paginate_without_skipping_revisions(storage):
    owner = str(uuid4())
    await write_records(storage, owner, [record(record_id=f"r-{i}") for i in range(4)])
    page = await changes(storage, owner, limit=2)
    assert page["cursor"] == 2 and page["has_more"]
    following = await changes(storage, owner, page["cursor"], 2)
    assert following["cursor"] == 4 and not following["has_more"]
    assert {r["id"] for r in page["records"] + following["records"]} == {f"r-{i}" for i in range(4)}
    with pytest.raises(HTTPException): await changes(storage, owner, 999)


@pytest.mark.asyncio
async def test_quota_failure_keeps_previous_data(storage, monkeypatch):
    from src.services import personal_records
    monkeypatch.setattr(personal_records, "MAX_RECORDS", 1)
    owner = str(uuid4())
    result = await write_records(storage, owner, [record(), record(record_id="second")])
    assert [r["status"] for r in result["results"]] == ["saved", "quota"]
    assert len((await changes(storage, owner))["records"]) == 1


def test_rejects_spoofing_duplicate_identity_and_unbounded_json():
    for data in ({"id": "other"}, {"id": "thread-a", "x": float("inf")}, {"id": "thread-a", "x": "x"*300000}):
        with pytest.raises(ValidationError): RecordWrite(namespace="threads", id="thread-a", expected_revision=0, data=data)
    with pytest.raises(ValidationError): BatchWrite(records=[record(), record()])
    with pytest.raises(ValidationError): RecordWrite(namespace="threads", id="thread-a", expected_revision=0, user_id=str(uuid4()), data={"id":"thread-a"})
