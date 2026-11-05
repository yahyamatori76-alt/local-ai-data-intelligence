"""Authorized source registry, user, and file-import API routes."""

import logging
import os
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import bcrypt
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db.repositories import get_engine
from app.ingestion.importer import create_failed_batch, save_import
from app.ingestion.validation import parse_file, validate_rows
from app.security.access_control import AdminUser, AnalystUser, AuthenticatedUser
from app.security.audit import record_audit

LOGGER = logging.getLogger(__name__)
router = APIRouter()
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024


class SourceCreate(BaseModel):
    source_code: str = Field(min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    source_name: str = Field(min_length=2, max_length=150)
    source_type: str = Field(pattern=r"^(population|marketplace|system_log|other)$")
    authorized_purpose: str = Field(min_length=5, max_length=1000)
    description: str | None = Field(default=None, max_length=2000)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: str = Field(pattern=r"^(admin|analyst|viewer)$")

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes.")
        return value


@router.get("/auth/me")
def current_user(user: AuthenticatedUser) -> dict[str, str]:
    return {"username": user["username"], "role": user["role"]}


@router.post("/auth/users", status_code=201)
def create_user(payload: UserCreate, user: AdminUser) -> dict[str, str]:
    password_hash = bcrypt.hashpw(
        payload.password.encode("utf-8"), bcrypt.gensalt()
    ).decode("ascii")
    try:
        with get_engine().begin() as connection:
            user_id = connection.execute(
                text(
                    """
                    INSERT INTO app_users (username, password_hash, role)
                    VALUES (:username, :password_hash, :role)
                    RETURNING id::text
                    """
                ),
                {
                    "username": payload.username,
                    "password_hash": password_hash,
                    "role": payload.role,
                },
            ).scalar_one()
            record_audit(
                connection,
                action="user_create",
                outcome="success",
                user_id=user["id"],
                summary={"role": payload.role},
            )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username already exists.") from exc
    return {"id": user_id, "username": payload.username, "role": payload.role}


@router.get("/sources")
def list_sources(user: AuthenticatedUser) -> list[dict]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT id::text, source_code, source_name, source_type,
                       description, authorized_purpose, enabled, created_at
                FROM source_registry
                ORDER BY source_name
                """
            )
        ).mappings()
        return [dict(row) for row in rows]


@router.post("/sources", status_code=201)
def create_source(payload: SourceCreate, user: AdminUser) -> dict[str, str]:
    try:
        with get_engine().begin() as connection:
            source_id = connection.execute(
                text(
                    """
                    INSERT INTO source_registry
                        (source_code, source_name, source_type, description,
                         authorized_purpose)
                    VALUES
                        (:source_code, :source_name, :source_type, :description,
                         :authorized_purpose)
                    RETURNING id::text
                    """
                ),
                payload.model_dump(),
            ).scalar_one()
            record_audit(
                connection,
                action="source_create",
                outcome="success",
                user_id=user["id"],
                source_code=payload.source_code,
            )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Source code already exists.") from exc
    return {"id": source_id, "source_code": payload.source_code}


@router.patch("/sources/{source_code}/enabled")
def set_source_enabled(
    source_code: str, enabled: bool, user: AdminUser
) -> dict[str, str | bool]:
    with get_engine().begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE source_registry SET enabled = :enabled
                WHERE source_code = :source_code
                RETURNING source_code
                """
            ),
            {"source_code": source_code, "enabled": enabled},
        ).scalar_one_or_none()
        if result is None:
            raise HTTPException(status_code=404, detail="Source not found.")
        record_audit(
            connection,
            action="source_update",
            outcome="success",
            user_id=user["id"],
            source_code=source_code,
            summary={"enabled": enabled},
        )
    return {"source_code": result, "enabled": enabled}


@router.post("/imports", status_code=201)
async def import_file(
    source_code: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    user: AnalystUser,
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
        )

    with get_engine().connect() as connection:
        source = connection.execute(
            text(
                """
                SELECT id::text AS id, source_code, source_type
                FROM source_registry
                WHERE source_code = :source_code AND enabled = TRUE
                """
            ),
            {"source_code": source_code},
        ).mappings().one_or_none()
    if source is None:
        raise HTTPException(
            status_code=404, detail="Enabled data source was not found."
        )

    try:
        rows = parse_file(file.filename, content)
        result = validate_rows(source["source_type"], rows)
    except ValueError as exc:
        error_code = str(exc)[:300]
        failed_batch = create_failed_batch(
            get_engine(),
            source=dict(source),
            filename=file.filename,
            file_content=content,
            user_id=user["id"],
            error_code=error_code,
        )
        raise HTTPException(status_code=422, detail=failed_batch) from exc

    try:
        return save_import(
            get_engine(),
            source=dict(source),
            filename=file.filename,
            file_content=content,
            result=result,
            user_id=user["id"],
        )
    except SQLAlchemyError as exc:
        LOGGER.error("Database import failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=500, detail="Import failed while writing to PostgreSQL."
        ) from exc


@router.get("/imports")
def list_imports(
    user: AuthenticatedUser, limit: int = 50
) -> list[dict]:
    limit = min(max(limit, 1), 200)
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT b.id::text AS batch_id, s.source_code, s.source_name,
                       b.file_name, b.file_sha256, b.status, b.records_read,
                       b.records_loaded, b.records_rejected, b.error_summary,
                       b.started_at, b.completed_at, b.created_at
                FROM import_batches AS b
                JOIN source_registry AS s ON s.id = b.source_id
                ORDER BY b.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings()
        return [dict(row) for row in rows]


@router.get("/imports/{batch_id}")
def get_import(batch_id: str, user: AuthenticatedUser) -> dict:
    with get_engine().connect() as connection:
        batch = connection.execute(
            text(
                """
                SELECT b.id::text AS batch_id, s.source_code, s.source_name,
                       b.file_name, b.file_sha256, b.status, b.records_read,
                       b.records_loaded, b.records_rejected, b.error_summary,
                       b.started_at, b.completed_at, b.created_at
                FROM import_batches AS b
                JOIN source_registry AS s ON s.id = b.source_id
                WHERE b.id = :batch_id
                """
            ),
            {"batch_id": batch_id},
        ).mappings().one_or_none()
        if batch is None:
            raise HTTPException(status_code=404, detail="Import batch not found.")
        rejections = connection.execute(
            text(
                """
                SELECT row_number, reason_code, count(*) OVER () AS total_rejections
                FROM import_rejections
                WHERE batch_id = :batch_id
                ORDER BY row_number
                LIMIT 100
                """
            ),
            {"batch_id": batch_id},
        ).mappings()
        return {
            "batch": dict(batch),
            "rejections": [
                {"row_number": row["row_number"], "reason_code": row["reason_code"]}
                for row in rejections
            ],
        }
