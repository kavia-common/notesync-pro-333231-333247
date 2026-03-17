"""
Database package — provides async session factory and engine for PostgreSQL.

Flow: DatabaseConnection
Entrypoint: get_db() async generator

Contract:
- Reads DATABASE_URL from environment (with fallback).
- Provides async SQLAlchemy sessions via get_db dependency.
- Sessions are scoped per-request and auto-closed after use.

Invariants:
- One engine and sessionmaker per process lifetime.
- All DB access goes through get_db() dependency injection.
"""
