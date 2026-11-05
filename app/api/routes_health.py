"""Public, deliberately limited service health endpoints."""

import os

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.repositories import get_engine

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def database_health() -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=503, detail="PostgreSQL is unavailable."
        ) from exc
    return {"status": "ok", "database": "postgresql"}


@router.get("/health/ollama")
def ollama_health() -> dict[str, str]:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Local Ollama service is unavailable."
        ) from exc
    return {"status": "ok", "service": "ollama"}
