"""System endpoints under /api/v1."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUserId, DbSession
from app.core.errors import NotFound
from app.core.repositories import UserRepository

router = APIRouter(tags=["system"])


class MeOut(BaseModel):
    id: uuid.UUID
    display_name: str
    is_local_default: bool


@router.get("/me")
async def me(session: DbSession, user_id: CurrentUserId) -> MeOut:
    user = await UserRepository(session).get(user_id)
    if user is None:
        raise NotFound("User not found.")
    return MeOut(id=user.id, display_name=user.display_name, is_local_default=user.is_local_default)
