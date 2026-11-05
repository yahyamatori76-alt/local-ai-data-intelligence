CREATE TABLE IF NOT EXISTS import_rejections (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES import_batches(id),
    row_number INTEGER NOT NULL,
    reason_code VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (batch_id, row_number)
);

CREATE INDEX IF NOT EXISTS idx_import_rejections_batch
    ON import_rejections(batch_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_correlation_result_provenance
    ON correlation_results (
        rule_id, batch_id, left_source, left_record_ref,
        right_source, right_record_ref
    );
