"""Persist validated source files and row-level rejection metadata."""

import hashlib
import json
from pathlib import PurePath
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.analytics.quality_checks import summarize_rejections
from app.ingestion.validation import ValidationResult
from app.security.audit import record_audit


TABLE_BY_SOURCE = {
    "population": "dukcapil_records",
    "marketplace": "marketplace_transactions",
    "system_log": "system_events",
}


def safe_filename(filename: str) -> str:
    name = PurePath(filename.replace("\\", "/")).name
    clean = "".join(char for char in name if char.isprintable())[:255]
    return clean or "upload"


def save_import(
    engine: Engine,
    *,
    source: dict[str, Any],
    filename: str,
    file_content: bytes,
    result: ValidationResult,
    user_id: str,
) -> dict[str, Any]:
    batch_id: UUID | None = None
    digest = hashlib.sha256(file_content).hexdigest()
    with engine.begin() as connection:
        batch_id = connection.execute(
            text(
                """
                INSERT INTO import_batches
                    (source_id, file_name, file_sha256, status, records_read,
                     imported_by, started_at)
                VALUES
                    (:source_id, :file_name, :file_sha256, 'processing',
                     :records_read, :imported_by, NOW())
                RETURNING id
                """
            ),
            {
                "source_id": source["id"],
                "file_name": safe_filename(filename),
                "file_sha256": digest,
                "records_read": result.records_read,
                "imported_by": user_id,
            },
        ).scalar_one()

        table = TABLE_BY_SOURCE[source["source_type"]]
        for record in result.records:
            data = record.data
            if source["source_type"] == "population":
                connection.execute(
                    text(
                        """
                        INSERT INTO dukcapil_records
                            (batch_id, record_ref, masked_identity_ref, region_code,
                             attributes, record_hash)
                        VALUES
                            (:batch_id, :record_ref, :masked_identity_ref, :region_code,
                             CAST(:attributes AS jsonb), :record_hash)
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        **data,
                        "attributes": json.dumps(data["attributes"]),
                        "record_hash": hashlib.sha256(
                            json.dumps(data, sort_keys=True, default=str).encode()
                        ).hexdigest(),
                    },
                )
            elif source["source_type"] == "marketplace":
                connection.execute(
                    text(
                        """
                        INSERT INTO marketplace_transactions
                            (batch_id, transaction_ref, event_time, status, amount,
                             currency, authorized_join_ref, attributes)
                        VALUES
                            (:batch_id, :transaction_ref, :event_time, :status, :amount,
                             :currency, :authorized_join_ref, CAST(:attributes AS jsonb))
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        **data,
                        "attributes": json.dumps(data["attributes"]),
                    },
                )
            else:
                connection.execute(
                    text(
                        """
                        INSERT INTO system_events
                            (batch_id, event_time, severity, event_type, event_ref,
                             authorized_join_ref, message, attributes)
                        VALUES
                            (:batch_id, :event_time, :severity, :event_type, :event_ref,
                             :authorized_join_ref, :message, CAST(:attributes AS jsonb))
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        **data,
                        "attributes": json.dumps(data["attributes"]),
                    },
                )

        for row_number, reason_code in result.rejections:
            connection.execute(
                text(
                    """
                    INSERT INTO import_rejections (batch_id, row_number, reason_code)
                    VALUES (:batch_id, :row_number, :reason_code)
                    """
                ),
                {
                    "batch_id": batch_id,
                    "row_number": row_number,
                    "reason_code": reason_code,
                },
            )

        rejection_summary = summarize_rejections(
            reason_code for _, reason_code in result.rejections
        )
        loaded_count = len(result.records)
        rejected_count = len(result.rejections)
        connection.execute(
            text(
                """
                UPDATE import_batches
                SET status = 'completed', records_loaded = :loaded,
                    records_rejected = :rejected, completed_at = NOW()
                WHERE id = :batch_id
                """
            ),
            {
                "loaded": loaded_count,
                "rejected": rejected_count,
                "batch_id": batch_id,
            },
        )
        record_audit(
            connection,
            action="import",
            outcome="completed",
            user_id=user_id,
            source_code=source["source_code"],
            summary={
                "records_loaded": loaded_count,
                "records_rejected": rejected_count,
            },
        )

    return {
        "batch_id": str(batch_id),
        "status": "completed",
        "records_read": result.records_read,
        "records_loaded": len(result.records),
        "records_rejected": len(result.rejections),
        "rejection_summary": summarize_rejections(
            reason_code for _, reason_code in result.rejections
        ),
    }


def create_failed_batch(
    engine: Engine,
    *,
    source: dict[str, Any],
    filename: str,
    file_content: bytes,
    user_id: str,
    error_code: str,
) -> dict[str, Any]:
    with engine.begin() as connection:
        batch_id = connection.execute(
            text(
                """
                INSERT INTO import_batches
                    (source_id, file_name, file_sha256, status, error_summary,
                     imported_by, started_at, completed_at)
                VALUES
                    (:source_id, :file_name, :file_sha256, 'failed', :error_summary,
                     :imported_by, NOW(), NOW())
                RETURNING id
                """
            ),
            {
                "source_id": source["id"],
                "file_name": safe_filename(filename),
                "file_sha256": hashlib.sha256(file_content).hexdigest(),
                "error_summary": error_code,
                "imported_by": user_id,
            },
        ).scalar_one()
        record_audit(
            connection,
            action="import",
            outcome="failed",
            user_id=user_id,
            source_code=source["source_code"],
            summary={"error_code": error_code},
        )
    return {
        "batch_id": str(batch_id),
        "status": "failed",
        "records_read": 0,
        "records_loaded": 0,
        "records_rejected": 0,
        "error": error_code,
    }
