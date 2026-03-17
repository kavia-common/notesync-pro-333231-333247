"""
Auth routes — registration, login (OAuth2 token), and user profile.

Flow: AuthRoutes
Entrypoint: router (APIRouter mounted at /auth)

Endpoints:
- POST /auth/register → Create a new user account
- POST /auth/login → Authenticate and receive a JWT token
- GET /auth/me → Get current user profile

Contract:
- Register accepts JSON { username, email, password }
- Login accepts form-encoded { username, password } (OAuth2 standard)
- Login uses email field for lookup when username contains '@', otherwise username
- All responses match frontend TypeScript types

Failure modes:
1. Duplicate email/username → 400 Bad Request
2. Invalid credentials → 401 Unauthorized
3. DB errors → 500 Internal Server Error
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from src.api.db.session import get_db
from src.api.db.models import User
from src.api.auth.security import hash_password, verify_password, create_access_token
from src.api.auth.dependencies import get_current_user
from src.api.schemas.auth import RegisterRequest, UserResponse, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# PUBLIC_INTERFACE
@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Creates a new user account with username, email, and password.",
    responses={
        400: {"description": "Username or email already exists"},
    },
)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new user.

    Args:
        data: RegisterRequest with username, email, password.
        db: Async database session.

    Returns:
        UserResponse with the created user's info.
    """
    logger.info("Registration attempt: username=%s email=%s", data.username, data.email)

    # Check for existing user with same email or username
    result = await db.execute(
        select(User).where(
            or_(User.email == data.email, User.username == data.username)
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        detail = "Email already registered" if existing.email == data.email else "Username already taken"
        logger.warning("Registration failed: %s", detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    # Create the user
    user = User(
        email=data.email,
        username=data.username,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("User registered: id=%s username=%s", user.id, user.username)
    return UserResponse(id=str(user.id), username=user.username or "", email=user.email)


# PUBLIC_INTERFACE
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and get access token",
    description="Authenticates a user with username/email and password. Returns a JWT access token.",
    responses={
        401: {"description": "Invalid credentials"},
    },
)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate a user and return a JWT token.

    The 'username' field in the form may contain either a username or email address.
    This follows the OAuth2 password flow convention.

    Args:
        form_data: OAuth2 form with username and password fields.
        db: Async database session.

    Returns:
        TokenResponse with access_token and token_type.
    """
    login_identifier = form_data.username
    logger.info("Login attempt: identifier=%s", login_identifier)

    # Look up user by email or username
    result = await db.execute(
        select(User).where(
            or_(User.email == login_identifier, User.username == login_identifier)
        )
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.password_hash):
        logger.warning("Login failed for identifier=%s", login_identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    logger.info("Login successful: user_id=%s", user.id)
    return TokenResponse(access_token=access_token, token_type="bearer")


# PUBLIC_INTERFACE
@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Returns the profile of the currently authenticated user.",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get the authenticated user's profile.

    Args:
        current_user: User object from JWT dependency.

    Returns:
        UserResponse with user info.
    """
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username or "",
        email=current_user.email,
    )
