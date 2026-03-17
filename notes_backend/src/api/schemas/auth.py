"""
Authentication schemas — request and response models for auth endpoints.

Contract:
- RegisterRequest: username, email, password (all required)
- UserResponse: id (string), username, email
- TokenResponse: access_token, token_type
"""

from pydantic import BaseModel, Field, EmailStr


class RegisterRequest(BaseModel):
    """Request payload for user registration."""
    username: str = Field(..., min_length=2, max_length=100, description="Unique username")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=6, max_length=128, description="Account password")


class UserResponse(BaseModel):
    """User information returned to the frontend."""
    id: str = Field(..., description="User UUID")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """OAuth2-compatible token response."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
