"""Authentication endpoints: login and current user."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from job_scrapper.auth import (
    CurrentUser,
    create_access_token,
    get_current_user,
    verify_password,
)
from job_scrapper.storage.postgres.models import UserModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    email: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    manager: DatabaseSessionManager = request.app.state.manager
    async with manager.session() as session:
        user = await session.scalar(
            select(UserModel).where(UserModel.email == body.email, UserModel.is_active.is_(True))
        )
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token(str(user.id), user.role)
    return LoginResponse(access_token=token, user=UserResponse(email=user.email, role=user.role))


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser = Depends(get_current_user)):
    return UserResponse(email=user.email, role=user.role)
