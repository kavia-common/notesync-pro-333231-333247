"""
Security utilities — password hashing and JWT token operations.

Flow: SecurityUtils
Entrypoint: create_access_token(), verify_password(), hash_password()

Contract:
- hash_password(plain) → bcrypt hash string
- verify_password(plain, hashed) → bool
- create_access_token(data, expires_delta?) → JWT string
- decode_access_token(token) → payload dict or raises

Invariants:
- JWT_SECRET is read from environment once at module load.
- All tokens contain 'sub' claim with user ID and 'exp' claim.

Observability:
- Logs token creation (user_id, expiry) at DEBUG level.
- Logs token decode failures at WARNING level.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

# Configuration — read from environment, never hardcoded in logic
# JWT_SECRET must be set in production; fallback is for development only
JWT_SECRET = os.getenv("JWT_SECRET", "notesync-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))


# PUBLIC_INTERFACE
def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Args:
        plain_password: The plaintext password to hash.

    Returns:
        Bcrypt hash string.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


# PUBLIC_INTERFACE
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.

    Args:
        plain_password: Plaintext password from user input.
        hashed_password: Stored bcrypt hash.

    Returns:
        True if password matches, False otherwise.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# PUBLIC_INTERFACE
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Claims to encode (must include 'sub' with user ID).
        expires_delta: Optional custom expiry duration.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=JWT_EXPIRATION_HOURS))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.debug("Created access token for sub=%s, expires=%s", data.get("sub"), expire.isoformat())
    return token


# PUBLIC_INTERFACE
def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Args:
        token: The JWT string.

    Returns:
        Decoded payload dictionary.

    Raises:
        JWTError: If the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise
