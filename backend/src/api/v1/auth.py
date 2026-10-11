"""
Auth endpoints — JWT authentication (register, login, refresh, logout).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_db, get_current_user_id
from src.services.auth_service import auth_service

router = APIRouter()


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    subscription_tier: str
    avatar_url: str | None


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user with email + password."""
    try:
        user, access_token, refresh_token = await auth_service.register(
            db, body.name, str(body.email), body.password
        )
        return {
            "user": {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "subscription_tier": user.subscription_tier,
                "avatar_url": user.avatar_url,
            },
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/login", response_model=dict)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email + password. Returns access + refresh tokens."""
    try:
        user, access_token, refresh_token = await auth_service.login(
            db, str(body.email), body.password
        )
        return {
            "user": {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "subscription_tier": user.subscription_tier,
                "avatar_url": user.avatar_url,
            },
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/refresh", response_model=dict)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new token pair (rotation)."""
    try:
        user, access_token, new_refresh = await auth_service.refresh(db, body.refresh_token)
        return {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest):
    """Revoke the refresh token immediately."""
    await auth_service.logout(body.refresh_token)


@router.get("/me", response_model=dict)
async def get_me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the currently authenticated user's profile."""
    user = await auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "subscription_tier": user.subscription_tier,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
