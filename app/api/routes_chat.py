"""Local Ollama chat based only on verified aggregate summaries."""

import os
import re

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.ai.analysis_planner import load_verified_summary
from app.ai.ollama_client import explain_verified_summary
from app.db.repositories import get_engine
from app.security.access_control import AuthenticatedUser
from app.security.audit import record_audit

router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/chat")
def chat(payload: ChatRequest, user: AuthenticatedUser) -> dict[str, str]:
    if (
        re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", payload.question)
        or re.search(r"\b\d{16}\b", payload.question)
        or re.search(r"\b(?:\+?62|0)8\d{8,12}\b", payload.question)
    ):
        raise HTTPException(
            status_code=422,
            detail="Jangan masukkan email, nomor identitas, atau nomor telepon ke chat.",
        )
    model = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
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
        "limitations": "Jawaban bersifat penjelasan dan harus divalidasi analis.",
    }
