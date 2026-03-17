"""
Tags routes — list all tags for the authenticated user.

Flow: TagsRoutes
Entrypoint: router (APIRouter mounted at /tags)

Endpoints:
- GET /tags → List all tags for the authenticated user

Contract:
- All endpoints require Bearer token authentication.
- Tags are scoped to the authenticated user.
- Returns TagResponse with id and name.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.db.session import get_db
from src.api.db.models import User, Tag
from src.api.auth.dependencies import get_current_user
from src.api.schemas.tags import TagResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tags", tags=["Tags"])


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[TagResponse],
    summary="List all tags",
    description="Fetches all tags belonging to the authenticated user.",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def list_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all tags for the current user, ordered alphabetically.

    Args:
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        List of TagResponse objects.
    """
    logger.info("Listing tags: user_id=%s", current_user.id)

    result = await db.execute(
        select(Tag)
        .where(Tag.user_id == current_user.id)
        .order_by(Tag.name)
    )
    tags = result.scalars().all()

    return [TagResponse(id=str(tag.id), name=tag.name) for tag in tags]
