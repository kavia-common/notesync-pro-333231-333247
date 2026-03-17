"""
Notes schemas — request and response models for notes endpoints.

Contract:
- CreateNoteRequest: title, content, tags (optional list of tag name strings)
- UpdateNoteRequest: title, content, tags (all optional)
- NoteResponse: id, title, content, tags (string[]), created_at, updated_at, user_id
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class CreateNoteRequest(BaseModel):
    """Request payload to create a new note."""
    title: str = Field(default="", max_length=500, description="Note title")
    content: str = Field(default="", description="Note content")
    tags: Optional[List[str]] = Field(default=None, description="List of tag names to associate")


class UpdateNoteRequest(BaseModel):
    """Request payload to update an existing note. All fields optional."""
    title: Optional[str] = Field(default=None, max_length=500, description="Updated title")
    content: Optional[str] = Field(default=None, description="Updated content")
    tags: Optional[List[str]] = Field(default=None, description="Updated list of tag names")


class NoteResponse(BaseModel):
    """Note returned to the frontend — matches the TypeScript Note interface."""
    id: str = Field(..., description="Note UUID")
    title: str = Field(..., description="Note title")
    content: str = Field(..., description="Note content")
    tags: List[str] = Field(default_factory=list, description="List of tag name strings")
    created_at: str = Field(..., description="ISO creation timestamp")
    updated_at: str = Field(..., description="ISO last-updated timestamp")
    user_id: Optional[str] = Field(default=None, description="Owner user UUID")

    model_config = {"from_attributes": True}
