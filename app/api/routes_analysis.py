"""Deterministic correlation and analyst review API routes."""

import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.analytics.correlation import correlate_records
from app.db.repositories import get_engine
from app.security.access_control import AnalystUser, AuthenticatedUser
from app.security.audit import record_audit

router = APIRouter()


class CorrelateRequest(BaseModel):
    rule_code: str = Field(min_length=1, max_length=100)
    time_window_seconds: int = Field(default=300, ge=0, le=86400)


class ReviewRequest(BaseModel):
    review_status: str = Field(pattern=r"^(confirmed|rejected)$")


@router.get("/analysis/rules")
def list_rules(user: AuthenticatedUser) -> list[dict]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT rule_code, rule_name, rule_version, rule_definition,
                       enabled, created_at
                FROM correlation_rules
                ORDER BY rule_code
                """
            )
        ).mappings()
        return [dict(row) for row in rows]


@router.post("/analysis/correlate")
def correlate(payload: CorrelateRequest, user: AnalystUser) -> dict[str, int | str]:
    with get_engine().begin() as connection:
        rule = connection.execute(
            text(
                """
                SELECT id::text AS id, rule_code, rule_version, rule_definition
                FROM correlation_rules
                WHERE rule_code = :rule_code AND enabled = TRUE
                """
            ),
            {"rule_code": payload.rule_code},
        ).mappings().one_or_none()
        if rule is None:
            raise HTTPException(status_code=404, detail="Enabled rule not found.")

        definition = rule["rule_definition"]
        if isinstance(definition, str):
            definition = json.loads(definition)
        if (
            definition.get("left_table") != "marketplace_transactions"
            or definition.get("right_table") != "system_events"
            or definition.get("join_field") != "authorized_join_ref"
        ):
            raise HTTPException(
                status_code=422,
                detail="This rule definition is not supported by the deterministic engine.",
            )
        max_window = min(
            payload.time_window_seconds,
            int(definition.get("time_window_seconds", 300)),
        )

        transactions = connection.execute(
            text(
                """
                SELECT id, batch_id, transaction_ref, event_time, authorized_join_ref
                FROM marketplace_transactions
                WHERE authorized_join_ref IS NOT NULL AND event_time IS NOT NULL
                ORDER BY event_time
                """
            )
        ).mappings()
        events = connection.execute(
            text(
                """
                SELECT id, event_ref, event_time, authorized_join_ref
                FROM system_events
                WHERE authorized_join_ref IS NOT NULL AND event_time IS NOT NULL
                ORDER BY event_time
                """
            )
        ).mappings()

        matches = correlate_records(
            [dict(row) for row in transactions],
            [dict(row) for row in events],
            time_window_seconds=max_window,
        )
        inserted = 0
        for transaction, event, delta in matches:
            result_id = connection.execute(
                text(
                    """
                    INSERT INTO correlation_results
                        (rule_id, batch_id, left_source, left_record_ref,
                         right_source, right_record_ref, match_method, evidence)
                    VALUES
                        (:rule_id, :batch_id, 'marketplace',
                         :left_record_ref, 'system_log', :right_record_ref,
                         'authorized_ref_time_window',
                         CAST(:evidence AS jsonb))
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "rule_id": rule["id"],
                    "batch_id": transaction["batch_id"],
                    "left_record_ref": transaction["transaction_ref"],
                    "right_record_ref": event["event_ref"],
                    "evidence": json.dumps(
                        {
                            "rule_version": rule["rule_version"],
                            "time_difference_seconds": delta,
                            "time_window_seconds": max_window,
                            "matching_method": "exact_authorized_join_ref",
                        }
                    ),
                },
            ).scalar_one_or_none()
            if result_id is not None:
                inserted += 1

        record_audit(
            connection,
            action="correlate",
            outcome="success",
            user_id=user["id"],
            summary={
                "rule_code": rule["rule_code"],
                "rule_version": rule["rule_version"],
                "time_window_seconds": max_window,
                "new_results": inserted,
            },
        )
    return {
        "rule_code": payload.rule_code,
        "rule_version": rule["rule_version"],
        "matches_evaluated": len(matches),
        "results_created": inserted,
    }


@router.get("/analysis/results")
def list_results(
    user: AuthenticatedUser,
    review_status: Annotated[
        str | None, Query(pattern=r"^(unreviewed|confirmed|rejected)$")
    ] = None,
    limit: int = 50,
) -> list[dict]:
    limit = min(max(limit, 1), 200)
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT r.id::text AS result_id, cr.rule_code, cr.rule_version,
                       r.batch_id::text AS batch_id, r.left_source,
                       r.left_record_ref, r.right_source, r.right_record_ref,
                       r.match_method, r.confidence, r.evidence,
                       r.review_status, r.reviewed_by::text AS reviewed_by,
                       r.created_at
                FROM correlation_results AS r
                JOIN correlation_rules AS cr ON cr.id = r.rule_id
                WHERE (CAST(:review_status AS VARCHAR) IS NULL
                       OR r.review_status = :review_status)
                ORDER BY r.created_at DESC
                LIMIT :limit
                """
            ),
            {"review_status": review_status, "limit": limit},
        ).mappings()
        return [dict(row) for row in rows]


@router.post("/analysis/results/{result_id}/review")
def review_result(
    result_id: str, payload: ReviewRequest, user: AnalystUser
) -> dict[str, str]:
    with get_engine().begin() as connection:
        row = connection.execute(
            text(
                """
                UPDATE correlation_results
                SET review_status = :review_status, reviewed_by = :user_id
                WHERE id = :result_id
                RETURNING id::text, review_status
                """
            ),
            {
                "review_status": payload.review_status,
                "user_id": user["id"],
                "result_id": result_id,
            },
        ).mappings().one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Correlation result not found.")
        record_audit(
            connection,
            action="result_review",
            outcome="success",
            user_id=user["id"],
            summary={"review_status": payload.review_status},
        )
    return {"result_id": row["id"], "review_status": row["review_status"]}
