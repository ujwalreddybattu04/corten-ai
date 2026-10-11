"""
Security utilities — JWT token creation and verification, password hashing.
"""

from datetime import datetime, timedelta, timezone
import uuid
import jwt
from jwt.exceptions import PyJWTError as JWTError
from passlib.context import CryptContext
from src.config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        # Legacy bcrypt must never silently truncate different long passwords.
        if hashed_password.startswith("$2") and len(plain_password.encode("utf-8")) > 72:
            return False
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta is not None else timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now, "iss": "corten-api", "aud": "corten", "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta is not None else timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "iat": now, "iss": "corten-api", "aud": "corten", "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], audience="corten", issuer="corten-api",
                             options={"require": ["exp", "iat", "sub", "aud", "iss", "sid", "type"] + (["jti"] if expected_type == "refresh" else [])})
        if payload.get("type") != expected_type:
            return None
        for claim in ("sub", "sid") + (("jti",) if expected_type == "refresh" else ()):
            uuid.UUID(payload[claim])
        return payload
    except (JWTError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None
