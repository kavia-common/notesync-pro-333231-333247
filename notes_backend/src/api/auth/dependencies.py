"""
Auth dependencies — FastAPI dependencies for extracting the current user.

Flow: AuthDependency
Entrypoint: get_current_user()

Contract:
- Input: Bearer token from Authorization header (via OAuth2PasswordBearer)
- Output: User ORM object for the authenticated user
- Errors: HTTPException 401 if token invalid/expired or user not found
- Side effects: DB query to fetch user by ID

Failure modes:
1. Missing token → 401 "Not authenticated"
2. Invalid/expired JWT → 401 "Invalid or expired token"
3. User ID not in DB → 401 "User not found"
"""

import logging
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError

from src.api.auth.security import decode_access_token
from src.api.db.session import get_db
from src.api.db.models import User

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# PUBLIC_INTERFACE
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that extracts and validates the current user from the JWT token.

    Args:
        token: Bearer token extracted from the Authorization header.
        db: Async database session.

    Returns:
        The authenticated User ORM object.

    Raises:
        HTTPException: 401 if token is invalid or user is not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            logger.warning("JWT payload missing 'sub' claim")
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        logger.warning("Invalid user ID in JWT: %s", user_id_str)
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning("User not found for JWT sub=%s", user_id_str)
        raise credentials_exception

    return user
