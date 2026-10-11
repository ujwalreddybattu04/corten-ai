"""
Auth service — registration, login, token refresh, OAuth.
"""

import uuid
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.user import User
from src.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from src.db.redis import store_refresh_token, validate_refresh_token, revoke_refresh_token
from src.config.settings import settings

logger = logging.getLogger(__name__)


class AuthService:

    async def register(self, db, name, email, password):
        result = await db.execute(select(User).where(User.email == email.lower()))
        if result.scalar_one_or_none():
            raise ValueError("Email already registered")
        user = User(
            id=uuid.uuid4(),
            name=name.strip(),
            email=email.lower().strip(),
            password_hash=hash_password(password),
        )
        db.add(user)
        await db.flush()
        access_token, refresh_token, jti = self._issue_tokens(str(user.id))
        await store_refresh_token(jti, str(user.id), ttl=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400)
        return user, access_token, refresh_token

    async def login(self, db, email, password):
        result = await db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        if not user or not user.password_hash:
            raise ValueError("Invalid email or password")
        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")
        if not user.is_active:
            raise ValueError("Account is deactivated")
        access_token, refresh_token, jti = self._issue_tokens(str(user.id))
        await store_refresh_token(jti, str(user.id), ttl=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400)
        return user, access_token, refresh_token

    async def refresh(self, db, refresh_token):
        payload = decode_token(refresh_token)
        if not payload:
            raise ValueError("Invalid or expired refresh token")
        jti = payload.get("jti")
        user_id = payload.get("sub")
        if not jti or not user_id:
            raise ValueError("Malformed token")
        stored = await validate_refresh_token(jti)
        if not stored:
            raise ValueError("Refresh token revoked or expired")
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise ValueError("User not found or deactivated")
        await revoke_refresh_token(jti)
        new_access, new_refresh, new_jti = self._issue_tokens(str(user.id))
        await store_refresh_token(new_jti, str(user.id), ttl=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400)
        return user, new_access, new_refresh

    async def logout(self, refresh_token):
        payload = decode_token(refresh_token)
        if payload and payload.get("jti"):
            await revoke_refresh_token(payload["jti"])

    async def get_user_by_id(self, db, user_id):
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        return result.scalar_one_or_none()

    def _issue_tokens(self, user_id):
        jti = uuid.uuid4().hex
        access_token = create_access_token({"sub": user_id})
        refresh_token = create_refresh_token({"sub": user_id, "jti": jti})
        return access_token, refresh_token, jti


auth_service = AuthService()
