"""Local document ingestion, exact identifier search, and grounded answers."""

import logging
import os
import re
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.ai.ollama_client import answer_from_documents
from app.db.repositories import get_engine
from app.ingestion.document_reader import (
    SUPPORTED_EXTENSIONS,
    extract_document,
    split_pages_into_chunks,
)
from app.ingestion.importer import safe_filename
from app.security.access_control import AnalystUser
from app.security.audit import record_audit

LOGGER = logging.getLogger(__name__)
router = APIRouter()
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024
MAX_DOCUMENT_CHUNKS = 10_000
MAX_SEARCH_RESULTS = 8
NIK_PATTERN = re.compile(r"(?<!\d)\d{16}(?!\d)")


class DocumentSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=256)
    ask_ai: bool = True

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Search query must not be blank.")
        if any(ord(character) < 32 for character in value):
            raise ValueError("Search query contains unsupported control characters.")
        return value


@router.post("/documents", status_code=201)
async def upload_document(
    file: Annotated[UploadFile, File()],
    user: AnalystUser,
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required.")
    extension = Path(file.filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Format tidak didukung. Gunakan PDF, TXT, DOC/DOCX, ODT, RTF, HTML, atau MD.",
        )
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File melebihi batas {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    try:
        extracted = extract_document(file.filename, content)
        chunks = split_pages_into_chunks(extracted.pages)
    except ValueError as exc:
        with get_engine().begin() as connection:
            record_audit(
                connection,
                action="document_import",
                outcome="failed",
                user_id=user["id"],
                summary={"file_type": extension.lstrip("."), "reason": str(exc)[:120]},
            )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if len(chunks) > MAX_DOCUMENT_CHUNKS:
        raise HTTPException(
            status_code=413,
            detail=f"Dokumen melebihi batas {MAX_DOCUMENT_CHUNKS} bagian.",
        )

    digest = hashlib.sha256(content).hexdigest()
    page_count = extracted.page_count or max(
        (page.page_number or 0 for page in extracted.pages), default=0
    ) or None
    try:
        with get_engine().begin() as connection:
            document_id = connection.execute(
                text(
                    """
                    INSERT INTO local_documents
                        (file_name, file_sha256, file_type, page_count,
                         chunk_count, character_count, imported_by)
                    VALUES
                        (:file_name, :file_sha256, :file_type, :page_count,
                         :chunk_count, :character_count, :imported_by)
                    ON CONFLICT (file_sha256) DO NOTHING
                    RETURNING id::text
                    """
                ),
                {
                    "file_name": safe_filename(file.filename),
                    "file_sha256": digest,
                    "file_type": extension.lstrip("."),
                    "page_count": page_count,
                    "chunk_count": len(chunks),
                    "character_count": sum(len(page.text) for page in extracted.pages),
                    "imported_by": user["id"],
                },
            ).scalar_one_or_none()
            duplicate = document_id is None
            if duplicate:
                document_id = connection.execute(
                    text(
                        "SELECT id::text FROM local_documents WHERE file_sha256 = :digest"
                    ),
                    {"digest": digest},
                ).scalar_one()
            else:
                for index, chunk in enumerate(chunks):
                    connection.execute(
                        text(
                            """
                            INSERT INTO local_document_chunks
                                (document_id, chunk_index, page_number, content)
                            VALUES (:document_id, :chunk_index, :page_number, :content)
                            """
                        ),
                        {
                            "document_id": document_id,
                            "chunk_index": index,
                            "page_number": chunk.page_number,
                            "content": chunk.text,
                        },
                    )
            record_audit(
                connection,
                action="document_import",
                outcome="duplicate" if duplicate else "completed",
                user_id=user["id"],
                summary={
                    "file_type": extension.lstrip("."),
                    "characters": sum(len(page.text) for page in extracted.pages),
                    "chunks": 0 if duplicate else len(chunks),
                    "ocr_pages": extracted.ocr_pages,
                },
            )
    except SQLAlchemyError as exc:
        LOGGER.error("Document indexing failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=500, detail="Dokumen gagal diindeks ke PostgreSQL."
        ) from exc

    return {
        "document_id": document_id,
        "file_name": safe_filename(file.filename),
        "file_type": extension.lstrip("."),
        "status": "already_indexed" if duplicate else "indexed",
        "chunks": 0 if duplicate else len(chunks),
        "characters": sum(len(page.text) for page in extracted.pages),
        "page_count": page_count,
        "ocr_pages": extracted.ocr_pages,
    }


@router.get("/documents")
def list_documents(user: AnalystUser) -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        documents = connection.execute(
            text(
                """
                SELECT id::text AS document_id, file_name, file_type, page_count,
                       chunk_count, character_count, created_at
                FROM local_documents
                ORDER BY created_at DESC
                LIMIT 200
                """
            )
        ).mappings()
        return [dict(document) for document in documents]


@router.post("/documents/search")
def search_documents(
    payload: DocumentSearchRequest, user: AnalystUser
) -> dict[str, Any]:
    query = payload.query
    nik_match = NIK_PATTERN.search(query)
    nik = nik_match.group(0) if nik_match else None
    nik_regex = f"(^|[^0-9]){nik}([^0-9]|$)" if nik else None
    escaped_query = (
        query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    )
    name_pattern = f"%{escaped_query}%"

    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT d.id::text AS document_id, d.file_name, d.file_type,
                       d.page_count, c.chunk_index, c.page_number,
                       left(c.content, 1600) AS excerpt,
                       ts_rank(c.search_vector,
                           websearch_to_tsquery('simple', CAST(:query AS TEXT))) AS rank
                FROM local_document_chunks AS c
                JOIN local_documents AS d ON d.id = c.document_id
                WHERE
                    (CAST(:nik_regex AS TEXT) IS NOT NULL AND c.content ~ :nik_regex)
                    OR (
                        CAST(:nik_regex AS TEXT) IS NULL
                        AND (
                            c.search_vector @@ websearch_to_tsquery(
                                'simple', CAST(:query AS TEXT)
                            )
                            OR c.content ILIKE :name_pattern ESCAPE '!'
                        )
                    )
                ORDER BY
                    CASE
                        WHEN CAST(:nik_regex AS TEXT) IS NOT NULL
                             AND c.content ~ :nik_regex THEN 1
                        ELSE 0
                    END DESC,
                    rank DESC,
                    d.created_at DESC
                LIMIT :limit
                """
            ),
            {
                "nik_regex": nik_regex,
                "query": query,
                "name_pattern": name_pattern,
                "limit": MAX_SEARCH_RESULTS,
            },
        ).mappings()
        matches = [dict(row) for row in rows]

    for match in matches:
        match["rank"] = float(match["rank"])
    with get_engine().begin() as connection:
        record_audit(
            connection,
            action="document_search",
            outcome="retrieved",
            user_id=user["id"],
            summary={
                "query_type": "nik" if nik else "text",
                "query_length": len(query),
                "result_count": len(matches),
                "ai_requested": payload.ask_ai and bool(matches),
            },
        )

    answer = None
    if payload.ask_ai and matches:
        model = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
        try:
            answer = answer_from_documents(base_url, model, query, matches)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503,
                detail="AI lokal tidak tersedia. Hasil pencarian dokumen tetap dapat dibuka.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=502, detail="AI lokal mengembalikan jawaban yang tidak valid."
            ) from exc

    return {
        "query_type": "nik" if nik else "text",
        "result_count": len(matches),
        "matches": matches,
        "answer": answer,
        "model": os.environ.get("OLLAMA_MODEL", "llama3.2:3b") if answer else None,
        "notice": (
            "Jawaban AI dirangkum dari cuplikan dokumen yang ditemukan. "
            "Periksa kutipan sumber; AI dapat keliru."
        ),
    }
