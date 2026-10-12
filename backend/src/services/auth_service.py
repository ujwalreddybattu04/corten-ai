"""
Auth service — registration, login, token refresh, OAuth.
"""

import uuid
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.models.user import User
from src.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from src.services.auth_sessions import create_session, rotate_session, revoke_session
from src.config.settings import settings

logger = logging.getLogger(__name__)
_DUMMY_HASH = hash_password("non-user-comparison-password")


class AuthService:

    async def register(self, db, name, email, password):
        email = email.strip().lower()
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise ValueError("Email already registered")
        user = User(
            id=uuid.uuid4(),
            name=name.strip(),
            email=email.lower().strip(),
            password_hash=await asyncio.to_thread(hash_password, password),
        )
        db.add(user)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise ValueError("Email already registered") from None
        access_token, refresh_token, sid, jti = self._issue_tokens(str(user.id), version=user.auth_version or 0)
        await create_session(sid, str(user.id), jti, settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400)
        # Do not issue a successful browser session before its user is durable.
        try:
            await db.commit()
        except Exception:
            await revoke_session(sid, str(user.id))
            raise
        return user, access_token, refresh_token

    async def login(self, db, email, password):
        result = await db.execute(select(User).where(User.email == email.strip().lower()).with_for_update())
        user = result.scalar_one_or_none()
        valid = await asyncio.to_thread(verify_password, password, user.password_hash if user and user.password_hash else _DUMMY_HASH)
        if not user or not user.password_hash or not valid or not user.is_active:
            raise ValueError("Invalid email or password")
        access_token, refresh_token, sid, jti = self._issue_tokens(str(user.id), version=user.auth_version or 0)
        await create_session(sid, str(user.id), jti, settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400)
        return user, access_token, refresh_token

    async def refresh(self, db, refresh_token):
        payload = decode_token(refresh_token, "refresh")
        if not payload:
            raise ValueError("Invalid or expired refresh token")
        jti = payload.get("jti")
        user_id = payload.get("sub")
        if not jti or not user_id:
            raise ValueError("Malformed token")
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise ValueError("User not found or deactivated")
        if payload.get("pv", 0) != (user.auth_version or 0):
            raise ValueError("Password changed. Sign in again.")
        remaining = timedelta(seconds=payload["exp"] - datetime.now(timezone.utc).timestamp())
        new_access, new_refresh, sid, new_jti = self._issue_tokens(str(user.id), payload["sid"], remaining, user.auth_version or 0)
        if not await rotate_session(sid, str(user.id), jti, new_jti):
            raise ValueError("Refresh token revoked, expired or already used")
        return user, new_access, new_refresh

    async def logout(self, refresh_token):
        payload = decode_token(refresh_token, "refresh")
        if payload:
            await revoke_session(payload["sid"], payload["sub"])

    async def get_user_by_id(self, db, user_id):
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        return result.scalar_one_or_none()

    def _issue_tokens(self, user_id, sid=None, remaining=None, version=0):
        sid = sid or uuid.uuid4().hex
        jti = uuid.uuid4().hex
        access_token = create_access_token({"sub": user_id, "sid": sid, "pv": version})
        refresh_token = create_refresh_token({"sub": user_id, "sid": sid, "jti": jti, "pv": version}, remaining)
        return access_token, refresh_token, sid, jti


auth_service = AuthService()
