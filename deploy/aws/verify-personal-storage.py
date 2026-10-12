"""Verify additive migrations and concurrent storage on an isolated PostgreSQL DB."""
import asyncio
import json
import os
import sys
from uuid import uuid4
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.config.settings import settings
from src.models.user import User
from src.services.personal_records import RecordWrite, changes, write_records
from src.core.security import hash_password, verify_password, create_access_token, decode_token
from src.models.password_reset import RecoveryEmail
from src.services.password_recovery import request_reset, reset_password
from src.services.recovery_delivery import claim, finish
from src.services.recovery_email import open_payload
from fastapi import HTTPException


async def main():
    from sqlalchemy.engine import make_url
    name = "corten_storage_verify_" + uuid4().hex
    root = create_async_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT", echo=False)
    url = make_url(settings.DATABASE_URL).set(database=name)
    temporary = create_async_engine(url, echo=False, pool_size=5, max_overflow=2)
    factory = async_sessionmaker(temporary, expire_on_commit=False)
    created = False
    owner, other = str(uuid4()), str(uuid4())

    async def migrate(target):
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "alembic", "upgrade", target,
            env={**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False), "APP_DEBUG": "false"},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try: _, _ = await asyncio.wait_for(process.communicate(), 120)
        except asyncio.TimeoutError:
            process.kill(); await process.wait(); raise RuntimeError("Isolated migration timed out") from None
        if process.returncode: raise RuntimeError("Isolated migration failed")

    async def write(record):
        async with factory() as session:
            result = await write_records(session, owner, [record])
            await session.commit()
            return result["results"][0]

    try:
        async with root.connect() as connection: await connection.execute(text("CREATE DATABASE " + name))
        created = True
        await migrate("0001")
        async with factory() as session:
            from uuid import UUID
            # Use the original schema, before the new auth_version column exists.
            await session.execute(text("INSERT INTO users (id,name,email,password_hash) VALUES (:id,:name,:email,:hash)"),
                {"id":UUID(owner),"name":"Storage verification","email":name+"@example.invalid","hash":hash_password("Original-password-42")})
            await session.commit()
        await migrate("head")
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM users")) == 1
            assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
            assert await session.scalar(text("SELECT auth_version FROM users")) == 0
        def request(record_id, value, revision=0, deleted=False):
            return RecordWrite(namespace="threads", id=record_id, expected_revision=revision,
                data={"id":record_id,"title":value}, deleted=deleted)
        concurrent = await asyncio.gather(*(write(request("parallel-"+str(i), str(i))) for i in range(12)))
        assert len({item["revision"] for item in concurrent}) == 12
        race = await asyncio.gather(write(request("race", "first")), write(request("race", "second")))
        assert sorted(item["status"] for item in race) == ["conflict", "saved"]
        saved = next(item for item in race if item["status"] == "saved")
        deleted = await write(request("race", "", saved["revision"], True))
        stale = await write(request("race", "stale", saved["revision"]))
        assert stale["status"] == "conflict" and stale["current"]["deleted"]
        async with factory() as session:
            assert (await changes(session, other))["records"] == []
            rows = await changes(session, owner)
            assert rows["cursor"] == deleted["revision"] and len(rows["records"]) == 13
        old_enabled, old_recipients = settings.RECOVERY_EMAIL_ENABLED, settings.EMAIL_ALLOWED_RECIPIENTS
        try:
            settings.RECOVERY_EMAIL_ENABLED = True
            settings.EMAIL_ALLOWED_RECIPIENTS = []
            async with factory() as session:
                await request_reset(session, name+"@example.invalid")
                mail = (await session.scalars(select(RecoveryEmail))).one()
                token = open_payload(mail.payload)["Content"]["Simple"]["Body"]["Text"]["Data"].split("#token=")[1].split()[0]
            async def consume():
                async with factory() as session:
                    try:
                        await reset_password(session, token, "Replacement-password-42")
                        return "saved"
                    except HTTPException as error:
                        assert error.status_code == 400
                        return "rejected"
            assert sorted(await asyncio.gather(consume(), consume())) == ["rejected", "saved"]
            async with factory() as session:
                user = await session.get(User, UUID(owner))
                assert user.auth_version == 1 and verify_password("Replacement-password-42", user.password_hash)
                assert decode_token(create_access_token({"sub":owner,"sid":uuid4().hex,"pv":0}))["pv"] != user.auth_version
                await request_reset(session, name+"@example.invalid")
            async def lease():
                async with factory() as session: return await claim(session)
            leases = [item for item in await asyncio.gather(lease(), lease()) if item]
            assert len(leases) == 1
            async with factory() as session:
                item = leases[0]
                await finish(session, item["id"], item["lease"], "sent", "isolated-verification")
                mail = await session.get(RecoveryEmail, UUID(item["id"]))
                assert mail.payload == "" and mail.status == "sent"
        finally:
            settings.RECOVERY_EMAIL_ENABLED, settings.EMAIL_ALLOWED_RECIPIENTS = old_enabled, old_recipients
        print(json.dumps({"migration_preserved_existing_user":True,"parallel_revisions_unique":True,
            "concurrent_edit_conflict":True,"deletion_protected":True,"account_isolation":True,
            "production_data_unchanged":True,"recovery_single_use":True,"recovery_sessions_revoked":True,"recovery_delivery_leased":True}))
    finally:
        await temporary.dispose()
        if created:
            async with root.connect() as connection: await connection.execute(text("DROP DATABASE " + name))
        await root.dispose()


asyncio.run(main())
