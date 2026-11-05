"""Build minimized verified aggregate context for local AI explanations."""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def load_verified_summary(connection: Connection) -> dict[str, int]:
    row = connection.execute(
        text(
            """
            SELECT
                (SELECT count(*) FROM source_registry WHERE enabled) AS active_sources,
                (SELECT count(*) FROM import_batches) AS import_batches,
                (SELECT coalesce(sum(records_loaded), 0) FROM import_batches) AS records_loaded,
                (SELECT count(*) FROM correlation_results) AS correlations,
                (SELECT count(*) FROM correlation_results
                    WHERE review_status = 'unreviewed') AS unreviewed_correlations
            """
        )
    ).mappings().one()
    return {key: int(value) for key, value in row.items()}
