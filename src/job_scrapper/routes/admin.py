"""Admin-only endpoints: user management."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from job_scrapper.auth import CurrentUser, hash_password, require_admin
from job_scrapper.storage.postgres.models import UserModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=6)
    role: str = Field(default="normal", pattern="^(admin|normal)$")


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(body: CreateUserRequest, request: Request):
    manager: DatabaseSessionManager = request.app.state.manager
    async with manager.session() as session:
        existing = await session.scalar(
            select(UserModel).where(UserModel.email == body.email)
        )
        if existing:
            raise HTTPException(409, "A user with this email already exists")
        user = UserModel(
            email=body.email,
            password_hash=hash_password(body.password),
            role=body.role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return UserResponse(id=str(user.id), email=user.email, role=user.role, is_active=user.is_active)


@router.get("/users", response_model=list[UserResponse])
async def list_users(request: Request, _: CurrentUser = Depends(require_admin)):
    manager: DatabaseSessionManager = request.app.state.manager
    async with manager.session() as session:
        rows = list(await session.scalars(select(UserModel).order_by(UserModel.created_at)))
        return [UserResponse(id=str(u.id), email=u.email, role=u.role, is_active=u.is_active) for u in rows]
