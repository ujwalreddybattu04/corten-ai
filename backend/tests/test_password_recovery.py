"""Recovery behavior against isolated SQL storage; never send mail or change real users."""
import re
from datetime import timedelta
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from src.models.user import User
from src.models.password_reset import PasswordReset, RecoveryEmail
from src.services.password_recovery import request_reset, reset_password, now
from src.services.recovery_email import open_payload, reset_message, protect_payload
from src.services.recovery_delivery import claim, finish
from src.core.security import hash_password, verify_password, create_access_token, decode_token
from src.config.settings import settings

@compiles(JSONB, "sqlite")
def json_for_sqlite(type_, compiler, **kwargs): return "JSON"

@pytest_asyncio.fixture
async def recovery(monkeypatch):
    engine=create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (User.__table__, PasswordReset.__table__, RecoveryEmail.__table__): await connection.run_sync(table.create)
    monkeypatch.setattr(settings,"RECOVERY_EMAIL_ENABLED",True)
    monkeypatch.setattr(settings,"EMAIL_ALLOWED_RECIPIENTS",[])
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as db:
        user=User(id=uuid4(),name='Analyst 张三',email='recovery@example.com',password_hash=hash_password('Previous-password-42'),is_active=True,auth_version=0)
        db.add(user);await db.commit();yield db,user
    await engine.dispose()

async def pending(db):
    rows=(await db.scalars(select(RecoveryEmail).order_by(RecoveryEmail.created_at))).all()
    message=open_payload(rows[-1].payload)
    token=re.search(r'#token=([A-Za-z0-9_-]{43})',message['Content']['Simple']['Body']['Text']['Data']).group(1)
    return rows[-1],token

@pytest.mark.asyncio
async def test_known_and_unknown_emails_return_same_message_and_only_known_account_enqueues(recovery):
    db,user=recovery
    known=await request_reset(db,user.email);unknown=await request_reset(db,'unknown@example.com')
    assert known==unknown
    mails=(await db.scalars(select(RecoveryEmail))).all();assert len(mails)==1
    mail,token=await pending(db)
    assert token not in mail.payload and user.email not in mail.payload
    reset=(await db.scalars(select(PasswordReset))).one()
    assert reset.digest!=token and len(reset.digest)==64

@pytest.mark.asyncio
async def test_reset_changes_hash_and_invalidates_all_old_session_versions_once(recovery):
    db,user=recovery
    await request_reset(db,user.email);mail,token=await pending(db)
    old=decode_token(create_access_token({'sub':str(user.id),'sid':uuid4().hex,'pv':0}))
    await reset_password(db,token,'New-password-42')
    assert verify_password('New-password-42',user.password_hash)
    assert not verify_password('Previous-password-42',user.password_hash)
    assert user.auth_version==1 and old['pv']!=user.auth_version
    with pytest.raises(HTTPException) as failure:await reset_password(db,token,'Another-password-42')
    assert failure.value.status_code==400 and user.auth_version==1

@pytest.mark.asyncio
async def test_new_request_cancels_old_link_and_old_queued_delivery(recovery):
    db,user=recovery
    await request_reset(db,user.email);_,older=await pending(db)
    await request_reset(db,user.email);_,newer=await pending(db)
    assert older!=newer
    with pytest.raises(HTTPException):await reset_password(db,older,'New-password-42')
    delivery=await claim(db)
    assert newer in delivery['message']['Content']['Simple']['Body']['Text']['Data']

@pytest.mark.asyncio
async def test_expired_invalid_and_deactivated_accounts_cannot_reset(recovery):
    db,user=recovery
    await request_reset(db,user.email);_,token=await pending(db)
    reset=(await db.scalars(select(PasswordReset))).one();reset.expires_at=now()-timedelta(seconds=1);await db.commit()
    for value in (token,'invalid','a'*43):
        with pytest.raises(HTTPException) as failure:await reset_password(db,value,'New-password-42')
        assert failure.value.status_code==400
    user.is_active=False;await db.commit();await request_reset(db,user.email)
    assert len((await db.scalars(select(RecoveryEmail))).all())==1

@pytest.mark.asyncio
async def test_sender_not_ready_and_sandbox_restrictions_never_pretend_mail_was_sent(recovery,monkeypatch):
    db,user=recovery
    monkeypatch.setattr(settings,'RECOVERY_EMAIL_ENABLED',False)
    with pytest.raises(HTTPException) as failure:await request_reset(db,user.email)
    assert failure.value.status_code==503
    monkeypatch.setattr(settings,'RECOVERY_EMAIL_ENABLED',True);monkeypatch.setattr(settings,'EMAIL_ALLOWED_RECIPIENTS',['verified@example.com'])
    with pytest.raises(HTTPException) as failure:await request_reset(db,user.email)
    assert failure.value.status_code==503
    assert (await db.scalars(select(RecoveryEmail))).all()==[]

@pytest.mark.asyncio
async def test_delivery_lease_retry_and_ack_scrub_plaintext_and_prevent_old_ack(recovery):
    db,user=recovery
    await request_reset(db,user.email);delivery=await claim(db)
    assert await claim(db) is None
    await finish(db,delivery['id'],'f'*32,'sent','untrusted-receipt')
    row=await db.get(RecoveryEmail,__import__('uuid').UUID(delivery['id']));assert row.status=='sending'
    await finish(db,delivery['id'],delivery['lease'],'retry')
    assert row.status=='pending' and row.payload
    row.available_at=now()-timedelta(seconds=1);await db.commit()
    retry=await claim(db);assert retry['lease']!=delivery['lease']
    await finish(db,retry['id'],retry['lease'],'sent','provider-receipt')
    assert row.status=='sent' and row.payload=='' and row.receipt=='provider-receipt'

def test_email_template_has_safe_html_plain_text_and_trusted_fragment_link(monkeypatch):
    monkeypatch.setattr(settings,'EMAIL_PUBLIC_BASE_URL','https://d3a7ful0miola1.cloudfront.net')
    message=reset_message('<script>alert(1)</script>','recovery@example.com','a'*43)
    body=message['Content']['Simple']['Body'];html=body['Html']['Data']
    assert '&lt;script&gt;' in html and '<script>alert' not in html
    assert 'Reset password' in html and 'Chryselys Private Limited' in html and '30 minutes' in html
    assert '/auth/reset-password#token=' in body['Text']['Data']
    assert open_payload(protect_payload(message))==message
    monkeypatch.setattr(settings,'EMAIL_PUBLIC_BASE_URL','https://evil.example/path')
    with pytest.raises(ValueError):reset_message('Analyst','recovery@example.com','a'*43)
