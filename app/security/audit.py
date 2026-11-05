"""Write minimized audit events without sensitive request payloads."""

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection


def record_audit(
    connection: Connection,
    *,
    action: str,
    outcome: str,
    user_id: str | UUID | None = None,
    source_code: str | None = None,
    summary: dict[str, Any] | None = None,
    request_id: UUID | None = None,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO analysis_audit
                (user_id, action, source_code, request_id, parameters_summary, outcome)
            VALUES
                (:user_id, :action, :source_code, :request_id,
                 CAST(:parameters_summary AS jsonb), :outcome)
            """
        ),
        {
            "user_id": str(user_id) if user_id else None,
            "action": action,
            "source_code": source_code,
            "request_id": request_id or uuid4(),
            "parameters_summary": json.dumps(summary or {}),
            "outcome": outcome,
        },
    )
