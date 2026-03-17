"""
NoteSync Pro Backend — FastAPI application entry point.

Flow: ApplicationBootstrap
Entrypoint: app (FastAPI instance)

Contract:
- Mounts all route modules at their respective prefixes.
- Configures CORS from environment variables.
- Provides health check at GET /.
- Includes OpenAPI metadata for documentation.

Observability:
- Structured logging configured at startup.
- Health check endpoint for monitoring.

How to debug (for future developers):
1. Check /docs for interactive API documentation.
2. Check logs for request-level logging from route handlers.
3. Health check at GET / confirms the server is running.
"""

import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# OpenAPI metadata
openapi_tags = [
    {
        "name": "Health",
        "description": "Health check endpoint",
    },
    {
        "name": "Authentication",
        "description": "User registration, login, and profile endpoints",
    },
    {
        "name": "Notes",
        "description": "CRUD operations for notes, including search and autosave",
    },
    {
        "name": "Tags",
        "description": "Tag management endpoints",
    },
]

app = FastAPI(
    title="NoteSync Pro API",
    description=(
        "Backend API for NoteSync Pro — a fullstack notes application with "
        "JWT authentication, notes CRUD, full-text search, tags management, "
        "and autosave support."
    ),
    version="1.0.0",
    openapi_tags=openapi_tags,
)

# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------
# Reads allowed origins from ALLOWED_ORIGINS env var (comma-separated).
# Also dynamically includes FRONTEND_URL and SITE_URL if set.
# This ensures the frontend preview can always reach the backend.
# ---------------------------------------------------------------------------
allowed_origins_str = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:4000",
)
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()]

# Also include FRONTEND_URL and SITE_URL if they are set (common deployment patterns)
for env_key in ("FRONTEND_URL", "SITE_URL"):
    extra_origin = os.getenv(env_key, "").strip()
    if extra_origin and extra_origin not in allowed_origins:
        allowed_origins.append(extra_origin)

allowed_methods_str = os.getenv("ALLOWED_METHODS", "GET,POST,PUT,DELETE,PATCH,OPTIONS")
allowed_methods = [m.strip() for m in allowed_methods_str.split(",") if m.strip()]

allowed_headers_str = os.getenv("ALLOWED_HEADERS", "Content-Type,Authorization,X-Requested-With")
allowed_headers = [h.strip() for h in allowed_headers_str.split(",") if h.strip()]

logger.info("CORS allowed origins: %s", allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=allowed_methods,
    allow_headers=allowed_headers,
)

# Import and mount route modules
from src.api.routes.auth import router as auth_router  # noqa: E402
from src.api.routes.notes import router as notes_router  # noqa: E402
from src.api.routes.tags import router as tags_router  # noqa: E402

app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(tags_router)


# PUBLIC_INTERFACE
@app.get("/", tags=["Health"], summary="Health check", description="Returns a simple health status message.")
def health_check():
    """
    Health check endpoint.

    Returns:
        JSON object with a status message confirming the service is running.
    """
    return {"message": "Healthy", "service": "NoteSync Pro API", "version": "1.0.0"}


logger.info("NoteSync Pro API initialized with %d routes", len(app.routes))
