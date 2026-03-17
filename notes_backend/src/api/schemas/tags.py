"""
Tags schemas — response models for tag endpoints.

Contract:
- TagResponse: id (string), name (string)
"""

from pydantic import BaseModel, Field


class TagResponse(BaseModel):
    """Tag entity returned to the frontend — matches the TypeScript Tag interface."""
    id: str = Field(..., description="Tag UUID")
    name: str = Field(..., description="Tag name")

    model_config = {"from_attributes": True}
