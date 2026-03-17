"""
Pydantic schemas package — request/response models for the API.

Contract:
- All schemas use Field(..., description=...) for OpenAPI docs.
- Response models mirror the frontend TypeScript types exactly.
- UUIDs are serialized as strings.
"""
