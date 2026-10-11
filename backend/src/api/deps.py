"""
API dependency injection helpers.
"""

from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from src.db.session import async_session_factory
from src.core.security import decode_token
from src.services.auth_sessions import session_active
from src.services.auth_service import auth_service

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session with auto commit/rollback."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            raise HTTPException(503, "Account data is temporarily unavailable. Please try again shortly.", headers={"Retry-After": "10"}) from None
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Extract and validate the JWT bearer token.
    Returns the user_id (sub claim) string.
    Raises 401 if token is missing or invalid.
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if not await session_active(payload["sid"], payload["sub"]):
        raise HTTPException(401, "Session expired or signed out", headers={"WWW-Authenticate": "Bearer"})
    user = await auth_service.get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(401, "Account unavailable", headers={"WWW-Authenticate": "Bearer"})
    return payload["sub"]


async def get_optional_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[str]:
    """Same as get_current_user_id but returns None instead of raising for unauthenticated requests."""
    if not credentials:
        return None
    return await get_current_user_id(credentials, db)
