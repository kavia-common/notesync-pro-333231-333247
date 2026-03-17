"""
Notes routes — CRUD, search, and autosave support.

Flow: NotesRoutes
Entrypoint: router (APIRouter mounted at /notes)

Endpoints:
- GET /notes → List all notes for user (with optional search and tag filters)
- GET /notes/{note_id} → Get a single note by ID
- POST /notes → Create a new note
- PUT /notes/{note_id} → Update a note (also serves as autosave endpoint)
- DELETE /notes/{note_id} → Delete a note

Contract:
- All endpoints require Bearer token authentication.
- Notes are scoped to the authenticated user.
- Tags are passed as string arrays; backend resolves to Tag entities.
- Search uses PostgreSQL full-text search on title and content.
- Autosave is handled by the PUT endpoint (frontend debounces calls).

Failure modes:
1. Note not found → 404
2. Note belongs to different user → 404 (no information leak)
3. DB constraint violation → 500
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, delete as sa_delete
from sqlalchemy.orm import selectinload

from src.api.db.session import get_db
from src.api.db.models import User, Note, Tag, note_tags
from src.api.auth.dependencies import get_current_user
from src.api.schemas.notes import CreateNoteRequest, UpdateNoteRequest, NoteResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notes", tags=["Notes"])


def _note_to_response(note: Note) -> NoteResponse:
    """
    Convert a Note ORM object to a NoteResponse schema.

    Invariant: note.tags must be loaded (via selectinload or lazy="selectin").
    """
    return NoteResponse(
        id=str(note.id),
        title=note.title or "",
        content=note.content or "",
        tags=[tag.name for tag in note.tags] if note.tags else [],
        created_at=note.created_at.isoformat() if note.created_at else "",
        updated_at=note.updated_at.isoformat() if note.updated_at else "",
        user_id=str(note.user_id) if note.user_id else None,
    )


async def _resolve_tags(
    db: AsyncSession, tag_names: List[str], user_id: UUID
) -> List[Tag]:
    """
    Resolve tag name strings to Tag ORM objects, creating new tags as needed.

    Contract:
    - Input: list of tag name strings and the owning user_id
    - Output: list of Tag ORM objects (existing or newly created)
    - Side effects: may INSERT new tags into the database

    Invariant: tag names are unique per user (enforced by DB constraint).
    """
    if not tag_names:
        return []

    # Normalize tag names
    normalized = [name.strip() for name in tag_names if name.strip()]
    if not normalized:
        return []

    # Fetch existing tags for this user that match the names
    result = await db.execute(
        select(Tag).where(Tag.user_id == user_id, Tag.name.in_(normalized))
    )
    existing_tags = list(result.scalars().all())
    existing_names = {tag.name for tag in existing_tags}

    # Create tags that don't exist yet
    new_tags = []
    for name in normalized:
        if name not in existing_names:
            tag = Tag(name=name, user_id=user_id)
            db.add(tag)
            new_tags.append(tag)
            existing_names.add(name)

    if new_tags:
        await db.flush()  # Assign IDs to new tags

    return existing_tags + new_tags


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[NoteResponse],
    summary="List all notes",
    description="Fetches all notes for the authenticated user. Supports optional search and tag filtering.",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def list_notes(
    search: Optional[str] = Query(default=None, description="Full-text search query"),
    tag: Optional[str] = Query(default=None, description="Filter by tag name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all notes for the current user with optional search and tag filters.

    Search uses PostgreSQL full-text search (tsvector) on title and content.
    Tag filter matches notes that have the specified tag associated.

    Args:
        search: Optional search string for full-text search.
        tag: Optional tag name to filter by.
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        List of NoteResponse objects ordered by updated_at descending.
    """
    logger.info(
        "Listing notes: user_id=%s search=%s tag=%s",
        current_user.id, search, tag,
    )

    query = (
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.user_id == current_user.id)
    )

    # Apply full-text search filter
    if search and search.strip():
        search_term = search.strip()
        # Use PostgreSQL full-text search with the existing GIN indexes
        ts_query = func.plainto_tsquery("english", search_term)
        query = query.where(
            or_(
                func.to_tsvector("english", Note.title).op("@@")(ts_query),
                func.to_tsvector("english", Note.content).op("@@")(ts_query),
            )
        )

    # Apply tag filter
    if tag and tag.strip():
        query = query.join(Note.tags).where(Tag.name == tag.strip())

    # Order by most recently updated
    query = query.order_by(Note.updated_at.desc())

    result = await db.execute(query)
    notes = result.scalars().unique().all()

    return [_note_to_response(note) for note in notes]


# PUBLIC_INTERFACE
@router.get(
    "/{note_id}",
    response_model=NoteResponse,
    summary="Get a single note",
    description="Fetches a single note by ID for the authenticated user.",
    responses={
        404: {"description": "Note not found"},
        401: {"description": "Not authenticated"},
    },
)
async def get_note(
    note_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a single note by ID.

    Args:
        note_id: UUID string of the note.
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        NoteResponse for the requested note.

    Raises:
        HTTPException 404 if note not found or belongs to another user.
    """
    try:
        uuid_id = UUID(note_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    result = await db.execute(
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.id == uuid_id, Note.user_id == current_user.id)
    )
    note = result.scalar_one_or_none()

    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    return _note_to_response(note)


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new note",
    description="Creates a new note for the authenticated user. Optionally associates tags.",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def create_note(
    data: CreateNoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new note.

    Args:
        data: CreateNoteRequest with title, content, and optional tags.
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        NoteResponse for the newly created note.
    """
    logger.info("Creating note: user_id=%s title=%s", current_user.id, data.title[:50] if data.title else "")

    note = Note(
        user_id=current_user.id,
        title=data.title or "",
        content=data.content or "",
    )
    db.add(note)
    await db.flush()  # Get the note ID

    # Resolve and associate tags via the junction table directly
    # This avoids the MissingGreenlet error that occurs when assigning
    # to note.tags on a freshly-flushed object in an async context.
    if data.tags:
        tags = await _resolve_tags(db, data.tags, current_user.id)
        if tags:
            # Insert into the junction table directly to avoid lazy-load triggers
            for tag in tags:
                await db.execute(
                    note_tags.insert().values(note_id=note.id, tag_id=tag.id)
                )

    await db.commit()

    # Reload note with tags eagerly loaded
    result = await db.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note.id)
    )
    note = result.scalar_one()

    logger.info("Note created: id=%s user_id=%s", note.id, current_user.id)
    return _note_to_response(note)


# PUBLIC_INTERFACE
@router.put(
    "/{note_id}",
    response_model=NoteResponse,
    summary="Update a note",
    description="Updates an existing note. Also serves as the autosave endpoint — the frontend debounces PUT calls.",
    responses={
        404: {"description": "Note not found"},
        401: {"description": "Not authenticated"},
    },
)
async def update_note(
    note_id: str,
    data: UpdateNoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update an existing note (also used for autosave).

    Only provided fields are updated. The updated_at timestamp is refreshed.

    Args:
        note_id: UUID string of the note to update.
        data: UpdateNoteRequest with optional title, content, tags.
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        NoteResponse for the updated note.
    """
    try:
        uuid_id = UUID(note_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    result = await db.execute(
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.id == uuid_id, Note.user_id == current_user.id)
    )
    note = result.scalar_one_or_none()

    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    logger.info("Updating note: id=%s user_id=%s", note_id, current_user.id)

    # Update only provided fields
    if data.title is not None:
        note.title = data.title
    if data.content is not None:
        note.content = data.content

    # Update timestamp
    note.updated_at = datetime.now(timezone.utc)

    # Update tags if provided — use junction table directly to avoid lazy-load issues
    if data.tags is not None:
        tags = await _resolve_tags(db, data.tags, current_user.id)

        # Remove existing tag associations for this note
        await db.execute(
            sa_delete(note_tags).where(note_tags.c.note_id == note.id)
        )

        # Insert new tag associations
        for tag in tags:
            await db.execute(
                note_tags.insert().values(note_id=note.id, tag_id=tag.id)
            )

    await db.commit()

    # Reload with tags
    result = await db.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note.id)
    )
    note = result.scalar_one()

    return _note_to_response(note)


# PUBLIC_INTERFACE
@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a note",
    description="Permanently deletes a note and its tag associations.",
    responses={
        404: {"description": "Note not found"},
        401: {"description": "Not authenticated"},
    },
)
async def delete_note(
    note_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a note by ID.

    Args:
        note_id: UUID string of the note to delete.
        db: Async database session.
        current_user: Authenticated user.

    Raises:
        HTTPException 404 if note not found or belongs to another user.
    """
    try:
        uuid_id = UUID(note_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    result = await db.execute(
        select(Note).where(Note.id == uuid_id, Note.user_id == current_user.id)
    )
    note = result.scalar_one_or_none()

    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    logger.info("Deleting note: id=%s user_id=%s", note_id, current_user.id)
    await db.delete(note)
    await db.commit()
