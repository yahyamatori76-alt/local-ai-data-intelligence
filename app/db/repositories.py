"""Shared cached SQLAlchemy engine for application services."""

from functools import lru_cache

from sqlalchemy.engine import Engine

from app.db.connection import create_database_engine


@lru_cache
def get_engine() -> Engine:
    return create_database_engine()
