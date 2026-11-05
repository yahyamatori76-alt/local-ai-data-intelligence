"""Local Ollama chat based only on verified aggregate summaries."""

import os
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app.ai.analysis_planner import load_verified_summary
from app.ai.ollama_client import explain_verified_summary
from app.api.routes_documents import DocumentSearchRequest, search_documents
from app.db.repositories import get_engine
from app.security.access_control import AuthenticatedUser
from app.security.audit import record_audit

router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be blank.")
        return value


@router.post("/chat")
def chat(payload: ChatRequest, user: AuthenticatedUser) -> dict[str, Any]:
    contains_nik = re.search(
        r"(?<!\d)(?:\d[\s-]?){15}\d(?!\d)", payload.question
    )
    if re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", payload.question) or re.search(
        r"\b(?:\+?62|0)8\d{8,12}\b", payload.question
    ):
        raise HTTPException(
            status_code=422,
            detail="Jangan masukkan email atau nomor telepon ke chat.",
        )
    if contains_nik and user["role"] not in ("admin", "analyst"):
        raise HTTPException(
            status_code=403,
            detail="Pencarian NIK hanya diizinkan untuk admin dan analyst.",
        )

    model = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
    if user["role"] in ("admin", "analyst"):
        document_result = search_documents(
            DocumentSearchRequest(query=payload.question[:256], ask_ai=True),
            user,
        )
        if document_result["matches"]:
            with get_engine().begin() as connection:
                record_audit(
                    connection,
                    action="chat",
                    outcome="success",
                    user_id=user["id"],
                    summary={
                        "model": model,
                        "question_length": len(payload.question),
                        "context": "local_document_rag",
                        "result_count": document_result["result_count"],
                    },
                )
            return {
                "answer": document_result["answer"],
                "model": model,
                "context": "local_document_rag",
                "sources": document_result["matches"],
                "limitations": (
                    "Jawaban dirangkum dari dokumen lokal yang ditemukan. "
                    "Periksa kutipan sumber; AI dapat keliru."
                ),
            }

    with get_engine().connect() as connection:
        summary = load_verified_summary(connection)
    try:
        answer = explain_verified_summary(
            base_url, model, payload.question, summary
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Local AI service is unavailable."
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="Local AI returned an invalid response."
        ) from exc

    with get_engine().begin() as connection:
        record_audit(
            connection,
            action="chat",
            outcome="success",
            user_id=user["id"],
            summary={
                "model": model,
                "question_length": len(payload.question),
                "context": "verified_aggregate_summary",
            },
        )
    return {
        "answer": answer,
        "model": model,
        "context": "verified_aggregate_summary",
        "sources": [],
        "limitations": "Jawaban bersifat penjelasan dan harus divalidasi analis.",
    }
