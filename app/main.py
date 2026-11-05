"""FastAPI health endpoints for the Dockerized MVP."""

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.db.connection import create_database_engine

app = FastAPI(
    title="Local AI Data Intelligence Platform",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)


@lru_cache
def get_engine() -> Engine:
    return create_database_engine()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def database_health() -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL is unavailable or not configured.",
        ) from exc
    return {"status": "ok", "database": "postgresql"}
