"""Authentication: password hashing, JWT tokens, FastAPI dependencies, admin seeding."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from job_scrapper.config import get_settings
from job_scrapper.storage.postgres.models import UserModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager

logger = logging.getLogger(__name__)

_bearer = HTTPBearer()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


@dataclass
class CurrentUser:
    id: UUID
    email: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    manager: DatabaseSessionManager = request.app.state.manager
    async with manager.session() as session:
        user = await session.scalar(
            select(UserModel).where(UserModel.id == payload["sub"], UserModel.is_active.is_(True))
        )
    if user is None:
        raise HTTPException(401, "User not found or inactive")
    return CurrentUser(id=user.id, email=user.email, role=user.role)


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user


async def seed_admin(manager: DatabaseSessionManager) -> None:
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        return
    async with manager.session() as session:
        existing = await session.scalar(
            select(UserModel).where(UserModel.email == settings.admin_email)
        )
        if existing:
            return
        session.add(UserModel(
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            role="admin",
        ))
        await session.commit()
        logger.info("Seeded admin user: %s", settings.admin_email)
