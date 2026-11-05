"""Authenticated dashboard summaries and audit views."""

from fastapi import APIRouter
from sqlalchemy import text

from app.db.repositories import get_engine
from app.security.access_control import AdminUser, AuthenticatedUser

router = APIRouter()


@router.get("/dashboard/summary")
def dashboard_summary(user: AuthenticatedUser) -> dict[str, int]:
    with get_engine().connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM source_registry WHERE enabled) AS sources,
                    (SELECT count(*) FROM import_batches) AS batches_total,
                    (SELECT count(*) FROM import_batches
                        WHERE status = 'completed') AS batches_completed,
                    (SELECT coalesce(sum(records_loaded), 0)
                        FROM import_batches) AS records_loaded,
                    (SELECT count(*) FROM correlation_results) AS results_total,
                    (SELECT count(*) FROM correlation_results
                        WHERE review_status = 'unreviewed') AS results_unreviewed
                """
            )
        ).mappings().one()
        return {key: int(value) for key, value in row.items()}


@router.get("/audit")
def list_audit(user: AdminUser, limit: int = 50) -> list[dict]:
    limit = min(max(limit, 1), 200)
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT a.action, a.source_code, a.outcome, a.request_id::text,
                       a.parameters_summary, a.created_at, u.username AS actor
                FROM analysis_audit AS a
                LEFT JOIN app_users AS u ON u.id = a.user_id
                ORDER BY a.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings()
        return [dict(row) for row in rows]
