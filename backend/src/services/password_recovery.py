"""One-use password reset with durable email enqueue and account-wide revocation."""
import asyncio
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, update
from src.config.settings import settings
from src.core.security import hash_password
from src.models.user import User
from src.models.password_reset import PasswordReset, RecoveryEmail
from src.services.recovery_email import reset_message, protect_payload

GENERIC = "If an eligible account exists for that address, we'll send a password reset link."
INVALID = "This reset link is invalid or has expired. Request a new link."

def now(): return datetime.now(timezone.utc)
def token_digest(token): return hashlib.sha256(token.encode()).hexdigest()
def aware(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

async def request_reset(db, email):
    email = email.strip().lower()
    if not settings.RECOVERY_EMAIL_ENABLED:
        raise HTTPException(503, "Password-reset email is not available yet. Please try again later.")
    permitted = {address.lower() for address in settings.EMAIL_ALLOWED_RECIPIENTS}
    if permitted and email not in permitted:
        raise HTTPException(503, "Password-reset email is currently limited to approved test recipients. Public delivery is awaiting provider setup.")
    user = (await db.execute(select(User).where(User.email == email).with_for_update())).scalar_one_or_none()
    if user and user.is_active and user.password_hash:
        stamp = now()
        await db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(used_at=stamp))
        token = secrets.token_urlsafe(32)
        row = PasswordReset(id=uuid.uuid4(), user_id=user.id, digest=token_digest(token), expires_at=stamp+timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES))
        db.add(row)
        await db.flush()
        db.add(RecoveryEmail(id=uuid.uuid4(), reset_id=row.id, payload=protect_payload(reset_message(user.name,email,token)),
            status="pending", attempts=0, available_at=stamp, expires_at=row.expires_at))
        await db.commit()
    # Both known and unknown accounts use the same reply and a small timing floor.
    await asyncio.sleep(0.15)
    return {"message": GENERIC}

async def reset_password(db, token, password):
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token): raise HTTPException(400, INVALID)
    # All recovery operations lock the user first, so requests and concurrent resets
    # cannot deadlock on reversed reset/user lock order.
    candidate = (await db.execute(select(PasswordReset).where(PasswordReset.digest == token_digest(token)))).scalar_one_or_none()
    if not candidate or candidate.used_at or aware(candidate.expires_at) <= now(): raise HTTPException(400, INVALID)
    hashed = await asyncio.to_thread(hash_password, password)
    user = (await db.execute(select(User).where(User.id == candidate.user_id).with_for_update())).scalar_one_or_none()
    reset = (await db.execute(select(PasswordReset).where(PasswordReset.id == candidate.id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not user or not user.is_active or not reset or reset.used_at or aware(reset.expires_at) <= now():
        raise HTTPException(400, INVALID)
    if (user.auth_version or 0) >= 2**31-1: raise HTTPException(503, "Please contact support to recover this account.")
    user.password_hash = hashed
    user.auth_version = (user.auth_version or 0)+1
    await db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(used_at=now()))
    await db.commit()
    return {"message": "Password updated. Sign in with your new password."}
